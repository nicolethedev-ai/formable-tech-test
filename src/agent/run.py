import argparse
import json
import os
import time
from datetime import datetime, timezone

import mlflow
from langsmith import traceable

from src.adapters.storage import Storage
from src.agent import steps
from src.agent.fetch import default_source_id

STEPS = [
    ("fetch", steps.fetch_step),
    ("inspect", steps.inspect_step),
    ("sample", steps.sample_step),
    ("propose", steps.propose_step),
    ("refine", steps.refine_step),
    ("approve", steps.approve_step),
]


def state_key(sid):
    return "state/" + sid + "/state.json"


def load_state(storage, sid):
    try:
        return storage.get_json(state_key(sid))
    except Exception:
        return dict(
            source_id=sid,
            args={},
            steps={},
            configs=[],
            validations=[],
            usage_total=dict(calls=0, in_tok=0, out_tok=0, cost_usd=0.0, seconds=0.0),
        )


def run_step(state, name, fn, storage):
    if state["steps"].get(name, {}).get("status") == "done":
        print("[skip]", name)
        return
    t0 = time.time()
    try:
        traceable(name="step_" + name)(fn)(state)  # mỗi bước là một span trên LangSmith
    except Exception as e:
        state["steps"][name] = dict(status="failed", error=repr(e)[:500])
        storage.put_json(state_key(state["source_id"]), state)
        raise
    state["steps"][name] = dict(
        status="done",
        seconds=round(time.time() - t0, 2),
        finished_at=datetime.now(timezone.utc).isoformat(),
    )
    storage.put_json(state_key(state["source_id"]), state)
    print("[done]", name, state["steps"][name]["seconds"], "s")


@traceable(name="onboard_source")
def onboard(state, storage):
    for name, fn in STEPS:
        run_step(state, name, fn, storage)


def usage_since(sid, t_start):
    tot = dict(calls=0, in_tok=0, out_tok=0, cost_usd=0.0, seconds=0.0)
    if os.path.exists("runs/llm_calls.json"):
        with open("runs/llm_calls.json", "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    r = json.loads(line)
                    if r.get("source_id") == sid and r.get("ts", 0) >= t_start:
                        tot["calls"] += 1
                        tot["in_tok"] += r.get("in_tok", 0)
                        tot["out_tok"] += r.get("out_tok", 0)
                        tot["cost_usd"] += r.get("cost_usd", 0.0)
                        tot["seconds"] += r.get("seconds", 0.0)
                except json.JSONDecodeError:
                    # Skip malformed lines instead of raising an unhandled exception
                    continue
    return tot


def log_mlflow(state, usage, failed, wall):
    mlflow.set_experiment("firmable-onboarding")
    fv = state.get("final_validation") or {}
    m = fv.get("metrics", {})
    with mlflow.start_run(run_name=state["source_id"]):
        mlflow.log_params(
            dict(
                source_id=state["source_id"],
                model=os.getenv("BEDROCK_MODEL_ID"),
                prompt_hash=state.get("prompt_hash"),
                revisions=max(0, len(state["configs"]) - 1),
                failed=failed,
                decision=(state.get("approval") or {}).get("decision"),
            )
        )
        metrics = dict(
            llm_calls=usage["calls"],
            in_tokens=usage["in_tok"],
            out_tokens=usage["out_tok"],
            cost_usd=usage["cost_usd"],
            llm_seconds=usage["seconds"],
            wall_seconds=wall,
            validation_ok=int(bool(fv.get("ok"))),
            n_errors=m.get("n_errors"),
            n_warnings=m.get("n_warnings"),
            n_mapped=m.get("n_mapped"),
            n_unmapped=m.get("n_unmapped"),
            abn_pass_rate=m.get("abn_pass_rate"),
        )
        mlflow.log_metrics({k: float(v) for k, v in metrics.items() if v is not None})
        sid = state["source_id"]
        for p in (
            "state/" + sid + "/state.json",
            "state/" + sid + "/review.md",
            "configs/" + sid + ".yaml",
        ):
            if os.path.exists(p):
                mlflow.log_artifact(p)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dataset-id", required=True)
    ap.add_argument("--resource", type=int, default=0)
    ap.add_argument("--source-id")
    ap.add_argument("--decision", choices=["ask", "approve", "reject"], default="ask")
    ap.add_argument("--redo", choices=[n for n, _ in STEPS])
    a = ap.parse_args()
    sid = a.source_id or default_source_id(a.dataset_id)
    storage = Storage()
    state = load_state(storage, sid)
    state["args"] = dict(
        dataset_id=a.dataset_id, resource=a.resource, decision=a.decision
    )
    if a.redo:
        names = [n for n, _ in STEPS]
        for n in names[names.index(a.redo) :]:
            state["steps"].pop(n, None)
    t0, failed = time.time(), False
    try:
        onboard(state, storage)
    except Exception:
        failed = True
        raise
    finally:
        usage = usage_since(sid, t0)
        for k, v in usage.items():
            state["usage_total"][k] = state["usage_total"].get(k, 0) + v
        storage.put_json(state_key(sid), state)
        log_mlflow(state, usage, failed, time.time() - t0)


if __name__ == "__main__":
    main()
