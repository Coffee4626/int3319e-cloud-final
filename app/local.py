"""Local HTTP adapter and LocalStack bootstrap; never used on AWS."""
import os
import sys
from http.server import BaseHTTPRequestHandler, HTTPServer
from urllib.parse import urlsplit, parse_qs

from app import controller, predict
from app.infrastructure.aws import client


def init():
    client("s3").create_bucket(Bucket=os.environ["BUCKET_NAME"])
    client("s3").put_bucket_cors(Bucket=os.environ["BUCKET_NAME"], CORSConfiguration={"CORSRules": [
        {"AllowedOrigins": ["http://localhost:5173", "http://localhost:3000"],
         "AllowedMethods": ["POST"], "AllowedHeaders": ["*"], "ExposeHeaders": ["ETag"]}]})
    client("sqs").create_queue(QueueName="automl-jobs", Attributes={"VisibilityTimeout": "3600"})
    try:
        client("dynamodb").create_table(
            TableName=os.environ["TABLE_NAME"], BillingMode="PAY_PER_REQUEST",
            KeySchema=[{"AttributeName": "id", "KeyType": "HASH"}],
            AttributeDefinitions=[{"AttributeName": k, "AttributeType": "S"} for k in ("id", "scope", "created_id")],
            GlobalSecondaryIndexes=[{"IndexName": "by-owner", "KeySchema": [
                {"AttributeName": "scope", "KeyType": "HASH"}, {"AttributeName": "created_id", "KeyType": "RANGE"}],
                "Projection": {"ProjectionType": "ALL"}}])
    except client("dynamodb").exceptions.ResourceInUseException:
        pass
    client("dynamodb").get_waiter("table_exists").wait(TableName=os.environ["TABLE_NAME"])


class Handler(BaseHTTPRequestHandler):
    def handle_request(self):
        length = int(self.headers.get("Content-Length", 0))
        if length > 2_000_000:
            self.send_error(413)
            return
        url = urlsplit(self.path)
        event = {"httpMethod": self.command, "path": url.path,
                 "queryStringParameters": {k: v[0] for k, v in parse_qs(url.query).items()},
                 "headers": dict(self.headers),
                 "body": self.rfile.read(length).decode()}
        fn = predict.handler if self.path.startswith("/predict/") and self.command == "POST" else controller.handler
        result = fn(event, None)
        self.send_response(result["statusCode"])
        for key, value in result["headers"].items():
            self.send_header(key, value)
        self.end_headers()
        self.wfile.write(result["body"].encode())

    do_GET = handle_request
    do_POST = handle_request
    do_OPTIONS = handle_request
    do_DELETE = handle_request


if __name__ == "__main__":
    if sys.argv[-1] == "init":
        init()
    else:
        HTTPServer(("0.0.0.0", 8000), Handler).serve_forever()
