"""Verify the actual Lambda image handler via RIE, using existing completed local smoke jobs.

Start: docker compose --profile lambda up -d inference
Then:  python3 scripts/lambda_smoke.py
No credentials are printed or written to disk.
"""
import json
import os
from urllib.request import Request, urlopen

from smoke import request

jobs = request("/jobs")["items"]
job = next(j for j in jobs if j["status"] == "COMPLETED" and j["name"] == "Smoke classification")
deployment = request("/deploy", {"job_id": job["id"]})
event = {"httpMethod": "POST", "path": deployment["predict_path"],
         "headers": {"X-Api-Key": deployment["api_key"]},
         "body": json.dumps({"rows": [{"x": 12}, {"x": 195}]})}
url = os.getenv("LAMBDA_RIE_URL", "http://localhost:9000/2015-03-31/functions/function/invocations")
for run in ("cold", "warm"):
    req = Request(url, data=json.dumps(event).encode(), headers={"Content-Type": "application/json"})
    with urlopen(req, timeout=90) as response:
        result = json.load(response)
    assert result.get("statusCode") == 200, result
    predictions = json.loads(result["body"])["predictions"]
    assert predictions == ["low", "high"], predictions
    print(f"Lambda {run} invocation PASS: {predictions}")
request('/deployments/' + deployment['deployment_id'], method='DELETE')
