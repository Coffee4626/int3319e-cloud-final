"""SQS DLQ consumer: make exhausted deliveries visible in the application."""
from app import runtime


def handler(event, context):
    failures = []
    repo = runtime.repository()
    for record in event.get("Records", []):
        try:
            job_id = record["body"]
            job = repo.get_job(job_id)
            if job and job["status"] not in ("COMPLETED", "FAILED", "CANCELLED"):
                if not repo.dead_letter(job_id):
                    failures.append({"itemIdentifier": record["messageId"]})
        except Exception:
            failures.append({"itemIdentifier": record["messageId"]})
    return {"batchItemFailures": failures}
