"""Lambda proxy request/response translation."""
import base64
import json
import logging
import os
from decimal import Decimal
from functools import wraps

from app.domain import ConflictError, NotFoundError, UnauthorizedError


def body(event):
    raw = event.get("body") or "{}"
    if event.get("isBase64Encoded"):
        raw = base64.b64decode(raw).decode()
    value = json.loads(raw)
    if not isinstance(value, dict):
        raise ValueError("Body must be a JSON object")
    return value


def response(status, value):
    return {"statusCode": status, "headers": {"Content-Type": "application/json",
            "Access-Control-Allow-Origin": os.getenv("ALLOWED_ORIGIN", "http://localhost:5173"),
            "Access-Control-Allow-Headers": "Content-Type,Authorization,X-Api-Key",
            "Access-Control-Allow-Methods": "GET,POST,DELETE,OPTIONS", "Vary": "Origin",
            "Cache-Control": "no-store"},
            "body": json.dumps(value, default=lambda v: float(v) if isinstance(v, Decimal) else str(v))}


def owner(event):
    claims = event.get("requestContext", {}).get("authorizer", {}).get("claims", {})
    if claims.get("sub"):
        return claims["sub"]
    if os.getenv("AUTH_REQUIRED", "false").lower() == "true":
        raise UnauthorizedError("Sign in to continue")
    return "local"


def api(fn):
    @wraps(fn)
    def wrapped(event, context):
        try:
            if event.get("httpMethod") == "OPTIONS":
                return response(200, {})
            return fn(event, context)
        except UnauthorizedError as exc:
            return response(401, {"error": str(exc)})
        except NotFoundError as exc:
            return response(404, {"error": str(exc)})
        except ConflictError as exc:
            return response(409, {"error": str(exc)})
        except ValueError as exc:
            return response(400, {"error": str(exc)})
        except Exception:
            logging.exception("Request failed")
            return response(500, {"error": "Internal error; check CloudWatch logs"})
    return wrapped
