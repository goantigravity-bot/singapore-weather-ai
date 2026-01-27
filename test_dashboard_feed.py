
import boto3
import json
import os
import datetime

S3_BUCKET = "weather-ai-models-de08370c"
S3_ENDPOINT_URL = "http://127.0.0.1:5000"

status = {
    "status": "active",
    "current_batch": 1,
    "total_batches": 2,
    "current_step": "Downloading Satellite Data (Simulated Update)",
    "batch_start": "2025-12-01",
    "batch_end": "2025-12-02",
    "last_updated": datetime.datetime.utcnow().isoformat()
}

print("Uploading simulated status...")
s3 = boto3.client('s3', endpoint_url=S3_ENDPOINT_URL)
s3.put_object(
    Bucket=S3_BUCKET, 
    Key="state/training_state.json", 
    Body=json.dumps(status)
)
print("Done.")
