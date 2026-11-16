"""Create short-lived presigned R2 URLs so the browser pane can upload a product video straight to a PRIVATE Cloudflare R2 bucket (no long-lived secret ever touches a web page).
Env: KEYS (space separated object keys e.g. media/B0HCVGY3RL/supplier.mp4), R2_ACCOUNT_ID, R2_ACCESS_KEY_ID, R2_SECRET_ACCESS_KEY, R2_BUCKET, DATABASE_URL.
Stores {key, put_url (15 min), expires} in deals.media_upload_urls; log prints counts only."""
import json, os, boto3, psycopg
from botocore.config import Config
s3 = boto3.client("s3", endpoint_url="https://%s.r2.cloudflarestorage.com" % os.environ["R2_ACCOUNT_ID"], aws_access_key_id=os.environ["R2_ACCESS_KEY_ID"],
                  aws_secret_access_key=os.environ["R2_SECRET_ACCESS_KEY"], region_name="auto", config=Config(signature_version="s3v4"))
cx = psycopg.connect(os.environ["DATABASE_URL"], autocommit=True)
cx.execute("create table if not exists deals.media_upload_urls (id bigserial primary key, at timestamptz default now(), key text, put_url text, expires_at timestamptz)")
n = 0
for k in (os.environ.get("KEYS") or "").split():
    u = s3.generate_presigned_url("put_object", Params={"Bucket": os.environ["R2_BUCKET"], "Key": k, "ContentType": "video/mp4"}, ExpiresIn=900)
    cx.execute("insert into deals.media_upload_urls(key, put_url, expires_at) values (%s,%s, now() + interval '15 minutes')", (k, u)); n += 1
print("r2_presign: %d upload urls created" % n)
