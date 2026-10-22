import os, json, pathlib

class Storage:
    def __init__(self):
        self.bucket = os.getenv('S3_BUCKET') if os.getenv('USE_S3') == '1' else None
        if self.bucket:
            import boto3
            self.s3 = boto3.client('s3')

    def put_json(self, key, obj):
        body = json.dumps(obj, ensure_ascii=False, indent=2)
        if self.bucket:
            self.s3.put_object(Bucket=self.bucket, Key=key, Body=body.encode('utf-8'))
        p = pathlib.Path(key)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(body, encoding='utf-8')  # luôn giữ bản local

    def get_json(self, key):
        if self.bucket:
            return json.loads(self.s3.get_object(Bucket=self.bucket, Key=key)['Body'].read())
        return json.loads(pathlib.Path(key).read_text(encoding='utf-8'))