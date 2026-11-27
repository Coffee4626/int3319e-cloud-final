"""Real upload -> profile -> preprocess -> SQS training -> deploy -> inference smoke test."""
import argparse
import json
import os
import time
import uuid
from urllib.error import HTTPError
from urllib.request import Request, urlopen

base = os.getenv("API_URL", "http://localhost:8000").rstrip("/")


def request(path, payload=None, key=None, method=None):
    headers = {"Content-Type": "application/json"}
    if key:
        headers["x-api-key"] = key
    elif os.getenv("ID_TOKEN"):
        headers["Authorization"] = os.environ["ID_TOKEN"]
    req = Request(base + path, data=json.dumps(payload).encode() if payload is not None else None,
                  headers=headers, method=method)
    try:
        with urlopen(req, timeout=60) as result:
            return json.load(result)
    except HTTPError as exc:
        raise RuntimeError(f"{exc.code} {path}: {exc.read().decode()}") from exc


def upload_csv(name, csv):
    ticket = request("/uploads", {"name": name})
    boundary = "stratus" + uuid.uuid4().hex
    chunks = []
    for key, value in ticket["upload"]["fields"].items():
        chunks.append(f'--{boundary}\r\nContent-Disposition: form-data; name="{key}"\r\n\r\n{value}\r\n')
    chunks.append(f'--{boundary}\r\nContent-Disposition: form-data; name="file"; filename="{name}"\r\nContent-Type: text/csv\r\n\r\n{csv}\r\n--{boundary}--\r\n')
    req = Request(ticket["upload"]["url"], data="".join(chunks).encode(),
                  headers={"Content-Type": f"multipart/form-data; boundary={boundary}"}, method="POST")
    with urlopen(req, timeout=60) as result:
        assert result.status in (200, 201, 204)
    return request(f'/datasets/{ticket["dataset_id"]}/complete', {})


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--task", choices=["tabular", "classification", "regression", "all"], default="all")
    parser.add_argument("--timeout", type=int, default=1800)
    args = parser.parse_args()
    tasks = ["classification", "regression"] if args.task == "all" else [args.task]
    jobs = []
    for task in tasks:
        labels = [("low" if i < 120 else "high") if task == "classification" else 2*i+i%3 for i in range(240)]
        csv = "x,y\n" + "".join(f"{i},{label}\n" for i, label in enumerate(labels))
        data = upload_csv(f"smoke-{task}.csv", csv)
        assert data["profile"]["rows"] == 240
        clean = request(f'/datasets/{data["dataset_id"]}/preprocess', {"target": "y", "drop_duplicates": True})
        job = request("/jobs", {"dataset_id": clean["dataset_id"], "task": task, "time_limit": 30,
                                "name": f"Smoke {task}"})
        jobs.append((task, job["job_id"]))
        print(task, "queued:", job["job_id"], flush=True)
    deadline = time.monotonic() + args.timeout
    for task, job_id in jobs:
        while time.monotonic() < deadline:
            status = request("/jobs/" + job_id)
            if status["status"] == "FAILED":
                raise SystemExit(status.get("error"))
            if status["status"] == "COMPLETED":
                break
            time.sleep(5)
        else:
            raise SystemExit("Timed out; inspect worker logs and SQS/DLQ")
        assert status["metrics"]["leaderboard"], status
        deployment = request("/deploy", {"job_id": job_id})
        payload = {"rows": [{"x": 12}, {"x": 195}]}
        result = request(deployment["predict_path"], payload, key=deployment["api_key"])
        assert len(result["predictions"]) == 2, result
        if task == "classification":
            assert all(value in ("low", "high") for value in result["predictions"]), result
        else:
            assert all(isinstance(value, (int, float)) for value in result["predictions"]), result
        try:
            request(deployment["predict_path"], payload, key="not-a-valid-key")
        except RuntimeError as exc:
            assert str(exc).startswith("401"), str(exc)
        else:
            raise AssertionError("Unauthenticated inference was accepted")
        print(task, "PASS", "deployment:", deployment["deployment_id"], result, flush=True)
