import pandas as pd, json, subprocess, mlflow

pool = json.load(open('data/raw/catalogue.json'))
sl = pd.read_csv('outputs/shortlist.csv')
hc = pd.read_csv('outputs/handcheck_part1.csv')

assert len(pool) >= 200, 'pool < 200'
assert len(sl) == 50 and sl.dataset_id.is_unique, 'shortlist phải đúng 50 dòng, không trùng'
assert sl.confidence.between(0, 1).all()
assert {'dataset_id','title','organization','formats','confidence','reason'} <= set(sl.columns)
assert hc.has_business_entities.isin(['yes', 'no']).all(), 'chưa điền hết hand-check'

fp = (hc.has_business_entities == 'no').sum()
rate = fp / len(hc)
try:
    commit = subprocess.check_output(
        ['git', 'rev-parse', '--short', 'HEAD'],
        stderr=subprocess.DEVNULL).decode().strip()
except subprocess.CalledProcessError:
    commit = 'no-commit'
print(f'pool={len(pool)} | false positive {fp}/{len(hc)} = {rate:.0%}')

mlflow.set_experiment('firmable-part1')
with mlflow.start_run(run_name='triage-rules-v1'):
    mlflow.log_params({'git_commit': commit, 'n_queries': 16, 'rules': 'keyword-score-v1'})
    mlflow.log_metrics({'pool_size': len(pool), 'false_positive_rate': rate})
    mlflow.log_artifact('outputs/shortlist.csv')