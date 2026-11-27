from app import runtime
from app.http import api, body, response


@api
def handler(event, context):
    if event.get("httpMethod") != "POST":
        return response(405, {"error": "Use POST"})
    deployment_id = event["path"].rstrip("/").split("/")[-1]
    headers = {k.lower(): v for k, v in (event.get("headers") or {}).items()}
    return response(200, runtime.prediction_service().predict(deployment_id, body(event),
                    headers.get("x-api-key"), enforce_auth=True))
