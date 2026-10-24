import copy
import csv
import hashlib
import json
import os
import random
import re
import tempfile
from datetime import datetime, timezone

import jsonschema
import pandas as pd
import yaml

from src.adapters.llm import call_llm
from src.agent.fetch import fetch
from src.core.config_schema import CONFIG_SCHEMA
from src.core.engine import extract, get_values, read_records
from src.core.validators import ONT, valid_abn, valid_acn

NL = chr(10)
MAX_REVISIONS = 3
STATES = set(ONT["address"]["state"]["values"])

TRANSFORM_DOC = {
    "trim": {},
    "upper": {},
    "lower": {},
    "digits_only": {},
    "regex_extract": {"pattern": "str", "group": "int, default 1"},
    "date_parse": {"formats": "list of strptime formats"},
    "split": {"sep": "str", "index": "int"},
    "map": {
        "table": "dict, UPPERCASE source value -> canonical value",
        "default": "optional",
    },
    "null_if": {"values": "list of junk strings such as N/A"},
    "constant": {"value": "str"},
}

# Model chỉ điền 4 phần này. Phần còn lại (licence, reader, observed_at...) do code điền.
MODEL_SCHEMA = {
    "type": "object",
    "required": ["dataset_kind", "record_id", "fields", "unmapped"],
    "properties": dict(
        {
            k: CONFIG_SCHEMA["properties"][k]
            for k in ("record_id", "fields", "unmapped")
        },
        dataset_kind={
            "type": "string",
            "description": "one line: what this dataset is",
        },
    ),
}
TOOL = {
    "name": "submit_config",
    "description": "Submit the mapping config for this source",
    "inputSchema": {"json": MODEL_SCHEMA},
}

SYSTEM = """You map ONE raw data source onto a fixed ontology by calling the tool submit_config.
Rules:
1. Use only source fields that appear in column_profile. Never invent a column.
2. canonical_field must be one of canonical_fields, written as group.name (for example entity.abn). Never invent one.
3. transforms must come from allowed_transforms, in execution order, with their parameters. Never write code.
4. If a column does not clearly map, put it in unmapped with a reason. Not mapping is better than a wrong mapping.
5. entity_type and status: map only if a column clearly states them, with the map transform (UPPERCASE keys, no default).
6. ABN and ACN columns: use digits_only. abn_like and acn_like in the profile show the share of values passing the checksum.
7. field_confidence is your honest probability that the mapping is right. Use 0.5 or less when unsure.
8. record_id: strategy field only if a column looks like a unique key, otherwise strategy hash. Always fill how.
9. rationale: one short sentence citing profile evidence."""
PROMPT_HASH = hashlib.sha1(
    (SYSTEM + json.dumps(MODEL_SCHEMA, sort_keys=True)).encode()
).hexdigest()[:8]


def fetch_step(state):
    a = state["args"]
    state["meta"] = fetch(a["dataset_id"], a["resource"], state["source_id"])


def find_records(data, prefix="", depth=0):
    # tìm danh sách dict dài nhất, trả về (đường dẫn, độ dài)
    if isinstance(data, list):
        return (prefix, len(data)) if data and isinstance(data[0], dict) else None
    best = None
    if isinstance(data, dict) and depth < 4:
        for k, v in data.items():
            hit = find_records(v, (prefix + "." + k) if prefix else k, depth + 1)
            if hit and (best is None or hit[1] > best[1]):
                best = hit
    return best


def inspect_step(state):
    path, fmt = state["meta"]["path"], state["meta"]["format"].lower()
    info = {}
    if fmt in ("csv", "txt", "tsv"):
        raw = open(path, "rb").read()
        enc = "utf-8-sig"
        try:
            text = raw.decode(enc)
        except UnicodeDecodeError:
            enc = "cp1252"
            text = raw.decode(enc, errors="replace")
        try:
            delim = (
                csv.Sniffer().sniff(text[:5000], delimiters=",;|" + chr(9)).delimiter
            )
        except csv.Error:
            delim = ","
        reader = dict(format="csv", encoding=enc, delimiter=delim)
    elif fmt in ("xlsx", "xls"):
        xl = pd.ExcelFile(path)
        best = None
        for sh in xl.sheet_names:
            df = xl.parse(sh, header=None, dtype=str, nrows=2000)
            if best is None or len(df) > best[1]:
                best = (sh, len(df), df)
        counts = best[2].head(15).notna().sum(axis=1)
        header_row = int(
            (counts >= 0.8 * counts.max()).idxmax()
        )  # bỏ qua dòng tiêu đề rác phía trên
        reader = dict(format="xlsx", sheet=best[0], skiprows=header_row)
        info = dict(sheets=xl.sheet_names, header_row=header_row)
    elif fmt in ("json", "geojson", "xml"):
        if fmt == "xml":
            import xmltodict

            data = xmltodict.parse(open(path, "rb"))
        else:
            data = json.load(open(path, encoding="utf-8"))
        hit = find_records(data)
        reader = dict(
            format="xml" if fmt == "xml" else "json", record_path=hit[0] if hit else ""
        )
    else:
        raise ValueError("format chưa hỗ trợ: " + fmt + " (chọn resource khác)")
    state["reader"] = reader
    state["n_records"] = len(read_records(path, reader))
    state["inspect"] = info


def flatten_paths(rec, prefix="", out=None, depth=0):
    out = set() if out is None else out
    if depth > 6:
        return out
    if isinstance(rec, dict):
        for k, v in rec.items():
            flatten_paths(v, prefix + "." + k if prefix else k, out, depth + 1)
    elif isinstance(rec, list):
        for v in rec[:5]:
            flatten_paths(v, prefix + "[*]", out, depth + 1)
    elif prefix:
        out.add(prefix)
    return out


def profile(records, paths):
    prof = {}
    for p in sorted(paths):
        vals, nulls = [], 0
        for r in records:
            v = get_values(r, p)
            if v:
                vals.extend(str(x) for x in v)
            else:
                nulls += 1
        if not vals:
            continue
        digits = [re.sub("[^0-9]", "", x) for x in vals]
        uniq = sorted(set(vals))
        prof[p] = dict(
            non_null_rate=round(1 - nulls / len(records), 3),
            distinct=len(uniq),
            examples=[x[:60] for x in random.Random(0).sample(uniq, min(5, len(uniq)))],
            abn_like=round(sum(valid_abn(d) for d in digits) / len(vals), 3),
            acn_like=round(sum(valid_acn(d) for d in digits) / len(vals), 3),
            state_like=round(
                sum(x.strip().upper() in STATES for x in vals) / len(vals), 3
            ),
            avg_len=round(sum(len(x) for x in vals) / len(vals), 1),
        )
    return prof


def sample_step(state):
    records = load_records(state)
    n = len(records)
    if n < 20:
        raise ValueError("chỉ có %d record, quá ít để tách holdout" % n)
    idx = list(range(n))
    random.Random(42).shuffle(idx)
    k = min(150, n // 2)
    state["propose_idx"] = sorted(idx[:k])
    state["holdout_idx"] = sorted(
        idx[k : k + 500]
    )  # model KHÔNG được thấy các dòng này
    state["n_propose"] = k
    paths = set()
    for i in state["propose_idx"]:
        flatten_paths(records[i], out=paths)
    prof = profile([records[i] for i in state["propose_idx"]], paths)
    keep = sorted(prof, key=lambda c: -max(prof[c]["abn_like"], prof[c]["acn_like"]))[
        :80
    ]
    state["profile"] = {c: prof[c] for c in keep}


def ontology_summary():
    out = {}
    for group in ("entity", "address"):
        for name, spec in ONT[group].items():
            d = {
                k: spec[k] for k in ("type", "values", "pattern", "notes") if k in spec
            }
            out[group + "." + name] = d
    return out


def build_user(state, extra=""):
    m = state["meta"]
    payload = dict(
        dataset=dict(
            title=m["title"],
            publisher=m["organization"],
            description=m["notes"],
            licence=m["licence"],
        ),
        rows_total=state["n_records"],
        rows_profiled=state["n_propose"],
        column_profile=state["profile"],
        canonical_fields=ontology_summary(),
        allowed_transforms=TRANSFORM_DOC,
    )
    return json.dumps(payload, ensure_ascii=False) + extra


def parse_tool(out):
    if isinstance(out, str):
        raise ValueError("model không gọi tool: " + out[:200])
    for k in ("fields", "unmapped"):
        if isinstance(out.get(k), str):
            out[k] = json.loads(out[k])
    return out


def finalize(model_out, state, rev):
    m = state["meta"]
    lic = m.get("licence") or "unknown"
    rid = model_out.get('record_id') or {}
    if rid.get('strategy') != 'field' or rid.get('field') not in state['profile']:
        rid = dict(strategy='hash', how='sha1 of row content (model gave no usable key column)')
    return dict(
        config_version=str(rev),
        dataset_kind=model_out.get("dataset_kind", ""),
        source=dict(
            source_id=state["source_id"], licence=lic, source_reliability=0.5
        ),  # 0.5 là chỗ giữ chỗ, người duyệt đặt giá trị thật
        reader=state["reader"],
        record_id=rid,
        observed_at=dict(
            strategy="constant",
            value=m.get("metadata_modified") or datetime.now(timezone.utc).isoformat(),
        ),
        fields=model_out.get("fields", []),
        unmapped=model_out.get("unmapped", []),
    )


_CACHE = {}

def load_records(state):
    key = (state['meta']['path'], json.dumps(state['reader'], sort_keys=True))
    if key not in _CACHE:
        _CACHE[key] = read_records(state['meta']['path'], state['reader'])
    return _CACHE[key]

def propose_step(state):
    out = parse_tool(
        call_llm(
            SYSTEM,
            build_user(state),
            tool=TOOL,
            max_tokens=4000,
            step="propose",
            source_id=state["source_id"],
        )
    )
    state["configs"] = [finalize(out, state, 1)]
    state["validations"] = []
    state["prompt_hash"] = PROMPT_HASH


def validate_config(state, cfg):
    sid, prof = state["source_id"], state["profile"]
    issues = []

    def add(code, severity, field, message):
        issues.append(dict(code=code, severity=severity, field=field, message=message))

    try:
        jsonschema.validate(cfg, CONFIG_SCHEMA)
    except jsonschema.ValidationError as e:
        return dict(
            ok=False,
            metrics={},
            issues=[
                dict(code="schema", severity="error", field="", message=e.message[:300])
            ],
        )
    records = load_records(state)
    holdout = [records[i] for i in state["holdout_idx"]]
    with tempfile.TemporaryDirectory() as d:
        try:
            summary = extract(
                None, None, out_dir=d, limit=len(holdout), cfg=cfg, records=holdout
            )
        except Exception as e:
            return dict(
                ok=False,
                metrics={},
                issues=[
                    dict(
                        code="engine_error",
                        severity="error",
                        field="",
                        message=repr(e)[:300],
                    )
                ],
            )
        rejects = [
            json.loads(l)
            for l in open(d + "/rejects/" + sid + ".json", encoding="utf-8")
        ]
    mapped_cols, per_field = set(), {}
    for f in cfg["fields"]:
        sf, cf = f["source_field"], f["canonical_field"]
        for c in sf if isinstance(sf, list) else [sf]:
            mapped_cols.add(c)
            if c not in prof:
                add(
                    "unknown_source_field",
                    "error",
                    cf,
                    "source field " + c + " is not in column_profile",
                )
        st = summary["fields"].get(
            str(sf) + " -> " + cf, dict(emitted=0, null=0, rejected=0)
        )
        per_field[cf + " <- " + str(sf)] = st
        reasons = [r["reason"] for r in rejects if r["canonical_field"] == cf]
        tot = st["emitted"] + st["rejected"]
        if "canonical_field not in ontology" in reasons:
            add("unknown_canonical_field", "error", cf, cf + " is not in the ontology")
            continue
        if tot == 0:
            add(
                "dead_mapping",
                "error",
                cf,
                "column " + str(sf) + " produced no value on unseen rows",
            )
            continue
        rate = st["rejected"] / tot
        if rate > 0.2:
            code = (
                "checksum_fail" if cf in ("entity.abn", "entity.acn") else "high_reject"
            )
            top = max(set(reasons), key=reasons.count)
            add(
                code,
                "error",
                cf,
                "%d%% of values from %s rejected (%s)" % (round(rate * 100), sf, top),
            )
        if f["field_confidence"] < 0.6:
            add(
                "low_confidence",
                "warning",
                cf,
                "mapping confidence %.2f" % f["field_confidence"],
            )
        if tot / len(holdout) < 0.5:
            add(
                "sparse_field",
                "warning",
                cf,
                "only %d%% of rows have a value" % round(100 * tot / len(holdout)),
            )
    for col, p in prof.items():  # kiểm chéo bằng code, không tin model
        if col in mapped_cols:
            continue
        if p["abn_like"] >= 0.5:
            add(
                "missed_abn",
                "error",
                col,
                "unmapped column "
                + col
                + " looks like ABN (abn_like="
                + str(p["abn_like"])
                + ")",
            )
        elif p["acn_like"] >= 0.5:
            add(
                "missed_acn",
                "error",
                col,
                "unmapped column "
                + col
                + " looks like ACN (acn_like="
                + str(p["acn_like"])
                + ")",
            )
    rid = cfg["record_id"]
    if rid["strategy"] == "field":
        p = prof.get(rid.get("field"))
        if p is None:
            add(
                "record_id_unknown_field",
                "error",
                str(rid.get("field")),
                "record_id.field is not in column_profile",
            )
        else:
            uniq = p["distinct"] / max(1, p["non_null_rate"] * state["n_propose"])
            if uniq < 0.99 or p["non_null_rate"] < 0.99:
                add(
                    "record_id_not_unique",
                    "error",
                    rid["field"],
                    "unique=%.2f non_null=%.2f, use strategy hash"
                    % (uniq, p["non_null_rate"]),
                )
    produced = {k.split(" <- ")[0] for k, st in per_field.items() if st["emitted"] > 0}
    if not produced & {
        "entity.abn",
        "entity.acn",
        "entity.legal_name",
        "entity.trading_name",
    }:
        add(
            "no_identity",
            "error",
            "",
            "no identity field (abn, acn, legal_name, trading_name) produced values",
        )
    if cfg["source"]["licence"] == "unknown":
        add(
            "licence_unknown",
            "warning",
            "",
            "no clear licence in CKAN, flag for the human reviewer",
        )
    ab = [st for k, st in per_field.items() if k.startswith("entity.abn <-")]
    abn_rate = (
        (
            sum(s["emitted"] for s in ab)
            / max(1, sum(s["emitted"] + s["rejected"] for s in ab))
        )
        if ab
        else None
    )
    errs = sum(i["severity"] == "error" for i in issues)
    metrics = dict(
        holdout_n=len(holdout),
        n_mapped=len(cfg["fields"]),
        n_unmapped=len(cfg["unmapped"]),
        n_errors=errs,
        n_warnings=len(issues) - errs,
        abn_pass_rate=abn_rate,
        per_field=per_field,
    )
    return dict(ok=errs == 0, issues=issues, metrics=metrics)


def revise_call(state, cfg, issues):
    errs = [i for i in issues if i["severity"] == "error"]
    prev = dict(
        record_id=cfg["record_id"], fields=cfg["fields"], unmapped=cfg["unmapped"]
    )
    extra = (
        NL
        + NL
        + "PREVIOUS CONFIG:"
        + NL
        + json.dumps(prev, ensure_ascii=False)
        + NL
        + NL
        + "VALIDATION ERRORS found on rows you have not seen. Fix only these and keep what works:"
        + NL
        + json.dumps(errs, ensure_ascii=False)
    )
    out = parse_tool(
        call_llm(
            SYSTEM,
            build_user(state, extra),
            tool=TOOL,
            max_tokens=4000,
            step="revise",
            source_id=state["source_id"],
        )
    )
    return finalize(out, state, len(state["configs"]) + 1)


def refine_step(state):
    cfg = state["configs"][-1]
    while True:
        result = validate_config(state, cfg)
        state["validations"].append(result)
        revisions_used = len(state["configs"]) - 1
        if result["ok"] or revisions_used >= MAX_REVISIONS:
            break
        cfg = revise_call(state, cfg, result["issues"])
        state["configs"].append(cfg)
    state["final_config"], state["final_validation"] = cfg, result


def build_review(state):
    cfg, val, meta = state["final_config"], state["final_validation"], state["meta"]
    pf = val["metrics"].get("per_field", {})
    lic = cfg["source"]["licence"]
    L = [
        "# Review: " + state["source_id"],
        "",
        "Dataset: " + str(meta["title"]),
        "Publisher: " + str(meta["organization"]),
        "Licence: " + lic + ("   <-- UNKNOWN, FLAG" if lic == "unknown" else ""),
        "Format: %s | rows: %d | agent says this is: %s"
        % (meta["format"], state["n_records"], cfg.get("dataset_kind", "")),
        "URL: " + str(meta["resource_url"]),
        "",
        "## Validation on %d unseen rows: %s after %d revision(s)"
        % (
            val["metrics"].get("holdout_n", 0),
            "PASS" if val["ok"] else "FAIL",
            len(state["configs"]) - 1,
        ),
        "",
        "## Mapping",
        "",
        "| source field | canonical field | transforms | confidence | emitted | rejected | rationale |",
        "| --- | --- | --- | --- | --- | --- | --- |",
    ]
    for f in cfg["fields"]:
        st = pf.get(f["canonical_field"] + " <- " + str(f["source_field"]), {})
        L.append(
            "| %s | %s | %s | %.2f | %s | %s | %s |"
            % (
                f["source_field"],
                f["canonical_field"],
                ", ".join(t["name"] for t in f.get("transforms", [])) or "-",
                f["field_confidence"],
                st.get("emitted", "?"),
                st.get("rejected", "?"),
                f["rationale"],
            )
        )
    L += ["", "## Not mapped (left empty on purpose)", ""]
    L += ["- %s: %s" % (u["source_field"], u["reason"]) for u in cfg["unmapped"]] or [
        "- (none)"
    ]
    L += ["", "## Issues", ""]
    L += [
        "- [%s] %s %s: %s" % (i["severity"], i["code"], i["field"], i["message"])
        for i in val["issues"]
    ] or ["- (none)"]
    records = load_records(state)
    five = [records[i] for i in state["holdout_idx"][:5]]
    sid = state["source_id"]
    with tempfile.TemporaryDirectory() as d:
        extract(None, None, out_dir=d, limit=5, cfg=cfg, records=five)
        obs = [
            json.loads(l)
            for l in open(d + "/observations/" + sid + ".json", encoding="utf-8")
        ]
    L += ["", "## 5 sample records: raw -> canonical", ""]
    L += [
        "- %s | %s: %r -> %r"
        % (o["source_record_id"], o["canonical_field"], o["raw_value"], o["value"])
        for o in obs[:30]
    ]
    return NL.join(L)


def approve_step(state):
    sid = state["source_id"]
    review = build_review(state)
    os.makedirs("state/" + sid, exist_ok=True)
    open("state/" + sid + "/review.md", "w", encoding="utf-8").write(review)
    print(review)
    mode = state["args"].get("decision", "ask")
    if not state["final_validation"]["ok"]:
        decision, by = "blocked", "system"  # còn lỗi thì không cho approve
    elif mode == "ask":
        decision = (
            "approved"
            if input("Approve this mapping? [y/N] ").strip().lower() == "y"
            else "rejected"
        )
        by = "human"
    else:
        decision, by = ("approved" if mode == "approve" else "rejected"), "flag:" + mode
    approval = dict(decision=decision, by=by, at=datetime.now(timezone.utc).isoformat())
    if decision == 'blocked':
        print(NL + 'BLOCKED: validation còn lỗi, không hỏi approve. Các lỗi:')
        for i in state['final_validation']['issues']:
            if i['severity'] == 'error':
                print(' -', i['code'], i['field'], i['message'])

    if decision == "approved":
        raw = input("source_reliability 0-1 [0.7]: ").strip() if mode == "ask" else ""
        cfg = copy.deepcopy(state["final_config"])
        cfg["source"]["source_reliability"] = float(raw or 0.7)
        os.makedirs("configs", exist_ok=True)
        yaml.safe_dump(
            cfg,
            open("configs/" + sid + ".yaml", "w", encoding="utf-8"),
            sort_keys=False,
            allow_unicode=True,
        )
        approval["source_reliability"] = cfg["source"]["source_reliability"]
    state["approval"] = approval
