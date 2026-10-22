import json, csv, re

STRONG = ['abn', 'acn', 'business name', 'licensee', 'registered', 'contractor', 'supplier', 'trading name']
MEDIUM = ['licence', 'license', 'permit', 'approval', 'company', 'operator', 'register', 'tender', 'notice']
NEGATIVE = ['statistics', 'aggregate', 'census', 'rainfall', 'boundary', 'population', 'weather', 'forecast']
TABULAR = {'csv', 'json', 'xlsx', 'xls', 'xml', 'geojson'}
MAX_SCORE = 3 * 4 + 1 * 4 + 2  # trần để chuẩn hóa, chỉnh sau khi xem phân phối

def score(pkg):
    text = ' '.join([pkg.get('title') or '', pkg.get('notes') or '',
                     ' '.join(r.get('name') or '' for r in pkg.get('resources', []))]).lower()
    fmts = {(r.get('format') or '').lower() for r in pkg.get('resources', [])}
    s, reasons = 0, []
    for k in STRONG:
        if re.search(r'\b' + re.escape(k) + r'\b', text):
            s += 3; reasons.append('+3 ' + k)
    for k in MEDIUM:
        if k in text:
            s += 1; reasons.append('+1 ' + k)
    for k in NEGATIVE:
        if k in text:
            s -= 3; reasons.append('-3 ' + k)
    if fmts & TABULAR:
        s += 2; reasons.append('+2 tải được dạng bảng')
    else:
        s -= 3; reasons.append('-3 không có CSV/JSON/XLSX/XML')
    return s, reasons, sorted(f for f in fmts if f)

if __name__ == '__main__':
    pool = json.load(open('data/raw/catalogue.json'))
    rows = []
    for p in pool:
        s, reasons, fmts = score(p)
        org = (p.get('organization') or {}).get('title', '')
        rows.append(dict(dataset_id=p['id'], title=p.get('title'), organization=org,
                         formats='|'.join(fmts), confidence=round(max(0, min(1, s / MAX_SCORE)), 2),
                         raw_score=s, reason='; '.join(reasons), license_id=p.get('license_id', ''),
                         portal=p['_portal']))
    rows.sort(key=lambda r: (-r['raw_score'], r['dataset_id']))
    top = rows[:50]
    with open('outputs/shortlist.csv', 'w', newline='', encoding='utf-8') as f:
        w = csv.DictWriter(f, fieldnames=list(top[0].keys()))
        w.writeheader(); w.writerows(top)
    print('pool', len(rows), '| shortlist', len(top))