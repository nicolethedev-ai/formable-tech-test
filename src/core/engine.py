import os, json, hashlib, time, sys, yaml, jsonschema
from datetime import datetime, timezone
import pandas as pd
from src.core.transforms import TRANSFORMS
from src.core.validators import validate
from src.core.config_schema import CONFIG_SCHEMA

ENGINE_VERSION = '0.1.0'

def get_values(obj, path):
    # hỗ trợ 'cot', 'a.b', 'a[*].b'. [*] bung danh sách thành nhiều giá trị
    if isinstance(obj, dict) and path in obj:
        return [obj[path]] if obj[path] not in (None, '') else []
    cur = [obj]
    for part in path.split('.'):
        star = part.endswith('[*]')
        key = part[:-3] if star else part
        nxt = []
        for c in cur:
            if isinstance(c, dict) and key in c:
                v = c[key]
                nxt.extend(v if (star and isinstance(v, list)) else [v])
        cur = nxt
    return [v for v in cur if v not in (None, '')]

def read_records(path, rd):
    fmt = rd['format']
    if fmt in ('csv', 'xlsx'):
        if fmt == 'csv':
            df = pd.read_csv(path, dtype=str, skiprows=rd.get('skiprows', 0),
                             encoding=rd.get('encoding', 'utf-8'), sep=rd.get('delimiter', ','))
        else:
            df = pd.read_excel(path, dtype=str, skiprows=rd.get('skiprows', 0),
                               sheet_name=rd.get('sheet', 0))
        return df.astype(object).where(df.notna(), None).to_dict('records')
    if fmt == 'json':
        data = json.load(open(path, encoding='utf-8'))
    else:
        import xmltodict
        data = xmltodict.parse(open(path, 'rb'))
    for key in filter(None, rd.get('record_path', '').split('.')):
        data = data[key]
    return data if isinstance(data, list) else [data]

def row_hash(rec):
    return hashlib.sha1(json.dumps(rec, sort_keys=True, default=str).encode()).hexdigest()[:16]

def make_record_id(spec, rec):
    if spec.get('strategy') == 'field' and spec.get('field'):
        vals = get_values(rec, spec['field'])
        if vals:
            return str(vals[0])
    return 'h-' + row_hash(rec)

def apply(value, steps):
    for s in steps:
        params = {k: v for k, v in s.items() if k != 'name'}
        value = TRANSFORMS[s['name']](value, **params)
        if value is None:
            return None
    return value

def extract(config_path, data_path, out_dir='outputs', limit=1000, cfg=None, records=None):
    t0 = time.time()
    if cfg is None:
        cfg = yaml.safe_load(open(config_path, encoding='utf-8'))
    jsonschema.validate(cfg, CONFIG_SCHEMA)
    cfg_hash = hashlib.sha1(json.dumps(cfg, sort_keys=True).encode()).hexdigest()[:8]
    version = 'cfg' + str(cfg['config_version']) + '+eng' + ENGINE_VERSION + '+' + cfg_hash
    sid = cfg['source']['source_id']
    if records is None:
        records = read_records(data_path, cfg['reader'])
    records = records[:limit]          
    ingested = datetime.now(timezone.utc).isoformat()
    os.makedirs(out_dir + '/observations', exist_ok=True)
    os.makedirs(out_dir + '/rejects', exist_ok=True)
    stats = {}
    obs_f = open(out_dir + '/observations/' + sid + '.json', 'w', encoding='utf-8')
    rej_f = open(out_dir + '/rejects/' + sid + '.json', 'w', encoding='utf-8')
    for rec in records:
        rid = make_record_id(cfg['record_id'], rec)
        oa = cfg['observed_at']
        observed_at = oa['value'] if oa['strategy'] == 'constant' else (get_values(rec, oa['field']) or [None])[0]
        for f in cfg['fields']:
            sf = f['source_field']
            label = str(sf) + ' -> ' + f['canonical_field']
            st = stats.setdefault(label, dict(emitted=0, null=0, rejected=0))
            if isinstance(sf, list):
                parts = [get_values(rec, x) for x in sf]
                joined = f.get('join_sep', ' ').join(str(p[0]) for p in parts if p)
                vals = [joined] if joined else []
            else:
                vals = get_values(rec, sf)
            if not vals:
                st['null'] += 1
                continue
            for raw in vals:
                v = apply(raw, f.get('transforms', []))
                if v is None:
                    st['null'] += 1
                    continue
                ok, why = validate(f['canonical_field'], v)
                if not ok:
                    st['rejected'] += 1
                    print(json.dumps(dict(source_record_id=rid, canonical_field=f['canonical_field'],
                                          raw_value=str(raw), value=str(v), reason=why),
                                     ensure_ascii=False), file=rej_f)
                    continue
                obs = dict(source_id=sid, source_record_id=rid, observed_at=observed_at,
                           ingested_at=ingested, valid_from=None, valid_to=None,
                           licence=cfg['source']['licence'], extractor_version=version,
                           canonical_field=f['canonical_field'], value=v, raw_value=str(raw),
                           source_field=sf, transforms=[s['name'] for s in f.get('transforms', [])],
                           derivation_level='L1' if f.get('transforms') else 'L0',
                           field_confidence=f['field_confidence'],
                           source_reliability=cfg['source']['source_reliability'])
                print(json.dumps(obs, ensure_ascii=False), file=obs_f)
                st['emitted'] += 1
    obs_f.close(); rej_f.close()
    summary = dict(source_id=sid, extractor_version=version, records=len(records),
                   seconds=round(time.time() - t0, 2), fields=stats)
    json.dump(summary, open(out_dir + '/observations/' + sid + '.stats.json', 'w'), indent=2)
    return summary

if __name__ == '__main__':
    if len(sys.argv) < 2:
        sys.exit('Cách dùng: python -m src.core.engine <config.yaml> [du_lieu]')
    data = sys.argv[2] if len(sys.argv) > 2 else None
    if data is None:
        sid = yaml.safe_load(open(sys.argv[1], encoding='utf-8'))['source']['source_id']
        data = json.load(open('data/raw/' + sid + '.meta.json'))['path']
    print(json.dumps(extract(sys.argv[1], data), indent=2))