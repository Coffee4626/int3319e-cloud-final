from app import runtime
from app.http import api, body, response, owner
from app.services import public_record


@api
def handler(event, context):
    method, path = event["httpMethod"], event["path"].rstrip("/")
    user = owner(event)
    service = runtime.job_service(user)
    datasets = runtime.dataset_service(user)
    parts = path.strip("/").split("/")
    query = event.get("queryStringParameters") or {}
    if method == "GET" and path == "/health":
        return response(200, {"status": "ok", "service": "stratus"})
    if method == "GET" and path in ("/jobs", "/datasets", "/deployments"):
        kind = {"/jobs": "job", "/datasets": "dataset", "/deployments": "deployment"}[path]
        return response(200, service.list(kind, query.get("cursor")))
    if len(parts) == 2 and parts[0] == "jobs" and method == "GET":
        return response(200, service.get(parts[1]))
    if len(parts) == 3 and parts[0] == "jobs" and method == "POST":
        if parts[2] == "cancel":
            return response(200, service.cancel(parts[1]))
        if parts[2] == "retry":
            return response(202, service.retry(parts[1]))
    if method == "POST" and path == "/jobs":
        return response(202, service.submit(body(event)))
    if method == "POST" and path == "/deploy":
        return response(201, service.deploy(body(event).get("job_id")))
    if method == "POST" and path == "/uploads":
        return response(201, datasets.create_upload(body(event)))
    if len(parts) == 2 and parts[0] == "datasets" and method == "GET":
        return response(200, public_record(datasets.get(parts[1])))
    if len(parts) == 3 and parts[0] == "datasets" and method == "POST":
        if parts[2] == "complete":
            return response(200, public_record(datasets.complete(parts[1])))
        if parts[2] == "preprocess":
            return response(201, public_record(datasets.preprocess(parts[1], body(event))))
    if len(parts) == 2 and parts[0] == "deployments":
        if method == "GET":
            return response(200, service.deployment(parts[1]))
        if method == "DELETE":
            return response(200, service.revoke(parts[1]))
    if len(parts) == 3 and parts[0] == "deployments" and parts[2] == "key" and method == "POST":
        return response(200, service.rotate_key(parts[1]))
    return response(404, {"error": "Route not found"})
