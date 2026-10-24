import json, requests

def _pkg(dataset_id):
    return {p['id']: p for p in json.load(open('data/raw/catalogue.json'))}[dataset_id]

def default_source_id(dataset_id):
    return _pkg(dataset_id)['name']

def fetch(dataset_id, resource_index, source_id, max_mb=60):
    pkg = _pkg(dataset_id)
    res = [r for r in pkg['resources'] if r.get('url')][resource_index]
    ext = (res.get('format') or 'dat').lower()
    path = 'data/raw/' + source_id + '.' + ext
    with requests.get(res['url'], timeout=120, stream=True) as r:
        r.raise_for_status()
        size = 0
        with open(path, 'wb') as f:
            for chunk in r.iter_content(1 << 20):
                size += len(chunk)
                if size > max_mb * (1 << 20):
                    raise RuntimeError('file lớn hơn %d MB, chọn resource khác' % max_mb)
                f.write(chunk)
    lic = pkg.get('license_id') or 'unknown'
    meta = dict(source_id=source_id, dataset_id=dataset_id, title=pkg.get('title'),
                organization=(pkg.get('organization') or {}).get('title'),
                notes=(pkg.get('notes') or '')[:800],
                licence='unknown' if lic == 'notspecified' else lic,
                resource_name=res.get('name'), resource_url=res['url'], format=ext,
                metadata_modified=pkg.get('metadata_modified'), path=path)
    json.dump(meta, open('data/raw/' + source_id + '.meta.json', 'w'), indent=2)
    return meta