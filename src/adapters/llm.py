import os, time, json, boto3
from dotenv import load_dotenv
from langsmith import traceable

load_dotenv()

MODEL_ID = os.environ['BEDROCK_MODEL_ID']
PRICE_IN = float(os.getenv('PRICE_IN_PER_MTOK', '0'))
PRICE_OUT = float(os.getenv('PRICE_OUT_PER_MTOK', '0'))
PROJECT_NAME = os.getenv('LANGCHAIN_PROJECT', 'ai-researcher-project')

client = boto3.client('bedrock-runtime', region_name=os.getenv('AWS_REGION', 'us-east-1'))

@traceable(run_type='llm', name='bedrock_converse', project_name=PROJECT_NAME)
def call_llm(system, user, tool=None, max_tokens=2000, step='unknown', source_id='na'):
    kwargs = dict(
        modelId=MODEL_ID,
        system=[{'text': system}],
        messages=[{'role': 'user', 'content': [{'text': user}]}],
        inferenceConfig={'maxTokens': max_tokens, 'temperature': 0},
    )
    if tool:  # tool = {'name':..., 'description':..., 'inputSchema': {'json': {...}}}
        kwargs['toolConfig'] = {'tools': [{'toolSpec': tool}],
                                'toolChoice': {'tool': {'name': tool['name']}}}
    t0 = time.time()
    resp = client.converse(**kwargs)
    dt = time.time() - t0
    u = resp['usage']
    cost = u['inputTokens'] * PRICE_IN / 1e6 + u['outputTokens'] * PRICE_OUT / 1e6
    rec = dict(ts=time.time(), step=step, source_id=source_id, model=MODEL_ID,
               in_tok=u['inputTokens'], out_tok=u['outputTokens'],
               seconds=round(dt, 2), cost_usd=round(cost, 6))
    with open('runs/llm_calls.json', 'a') as f:
        f.write(json.dumps(rec) + '\n')
    blocks = resp['output']['message']['content']
    for b in blocks:
        if 'toolUse' in b:
            return b['toolUse']['input']
    return ''.join(b.get('text', '') for b in blocks)