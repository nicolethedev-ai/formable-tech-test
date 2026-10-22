import requests, json, time, sys
sys.path.insert(0, '.')

PORTALS = {
    'data.gov.au': 'https://data.gov.au/data/api/3/action/',
    'data.nsw.gov.au': 'https://data.nsw.gov.au/data/api/3/action/',
    'data.qld.gov.au': 'https://www.data.qld.gov.au/api/3/action/',
    'data.vic.gov.au': 'https://discover.data.vic.gov.au/api/3/action/',
}
QUERIES = ['ABN', 'ACN', 'business register', 'licence register', 'licensed contractors',
           'company', 'building approvals', 'procurement contracts', 'suppliers',
           'workplace safety notices', 'registered businesses', 'trade licence',
           'court list', 'liquor licence', 'food business', 'contractor register']

def search(base, q, rows=100):
    r = requests.get(base + 'package_search', params={'q': q, 'rows': rows}, timeout=30)
    r.raise_for_status()
    return r.json()['result']['results']

if __name__ == '__main__':
    pool, stats = {}, {}
    for name, base in PORTALS.items():
        stats[name] = 0
        for q in QUERIES:
            try:
                for p in search(base, q):
                    if p['id'] not in pool:
                        pool[p['id']] = {**p, '_portal': name}
                        stats[name] += 1
            except Exception as e:
                print('FAIL', name, q, e)
            time.sleep(0.5)
    json.dump(list(pool.values()), open('data/raw/catalogue.json', 'w'))
    json.dump(stats, open('outputs/discover_stats.json', 'w'), indent=2)
    print(len(pool), 'records', stats)