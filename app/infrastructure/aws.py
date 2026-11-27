import os
import shutil
import tempfile
import zipfile
import base64
import json
import time
from decimal import Decimal
from functools import lru_cache
from pathlib import Path

import boto3
from botocore.exceptions import ClientError
from botocore.config import Config
from boto3.dynamodb.conditions import Key

from app.domain import QueueMessage

# Leave time for a replacement worker to claim an expired lease after redelivery.
VISIBILITY_SECONDS = 3600
LEASE_SECONDS = 3500


@lru_cache
def client(service):
    options = {"endpoint_url": os.getenv("AWS_ENDPOINT_URL")}
    if service == "s3":
        options["config"] = Config(signature_version="s3v4")
    return boto3.client(service, **options)


@lru_cache
def table():
    return boto3.resource("dynamodb", endpoint_url=os.getenv("AWS_ENDPOINT_URL")).Table(
        os.environ["TABLE_NAME"])


class DynamoJobRepository:
    def __init__(self, state_table):
        self.table = state_table

    def get_job(self, job_id):
        item = self.table.get_item(Key={"id": job_id}, ConsistentRead=True).get("Item")
        return item if item and "status" in item and item.get("kind", "job") == "job" else None

    def create_job(self, job):
        self.put_record({**job, "kind": "job"}, create=True)

    def put_record(self, item, create=False):
        item.setdefault("created_at", int(time.time()))
        item.setdefault("owner", "local")
        item["scope"] = f'{item["owner"]}#{item["kind"]}'
        item["created_id"] = f'{int(item["created_at"]):012d}#{item["id"]}'
        args = {"Item": json.loads(json.dumps(item, default=float), parse_float=Decimal)}
        if create:
            args["ConditionExpression"] = "attribute_not_exists(id)"
        self.table.put_item(**args)

    def get_record(self, record_id):
        return self.table.get_item(Key={"id": record_id}, ConsistentRead=True).get("Item")

    def list_records(self, kind, owner="local", cursor=None):
        scope = f"{owner}#{kind}"
        args = {"IndexName": "by-owner", "KeyConditionExpression": Key("scope").eq(scope),
                "ScanIndexForward": False, "Limit": 30}
        if cursor:
            try:
                key = json.loads(base64.urlsafe_b64decode(cursor.encode()))
                if key.get("scope") != scope:
                    raise ValueError()
                args["ExclusiveStartKey"] = key
            except Exception as exc:
                raise ValueError("Invalid pagination cursor") from exc
        page = self.table.query(**args)
        next_key = page.get("LastEvaluatedKey")
        return {"items": page.get("Items", []), "cursor":
                base64.urlsafe_b64encode(json.dumps(next_key).encode()).decode() if next_key else None}

    def submission_failed(self, job_id):
        self._conditional_update(
            Key={"id": job_id}, UpdateExpression="SET #s = :failed",
            ConditionExpression="#s = :queued",
            ExpressionAttributeNames={"#s": "status"},
            ExpressionAttributeValues={":failed": "FAILED", ":queued": "QUEUED"})

    def claim(self, job_id, owner, now):
        return self._conditional_update(
            Key={"id": job_id},
            UpdateExpression="SET #s = :running, lease_until = :lease, lease_owner = :owner, started_at = :now",
            ConditionExpression="#s = :queued OR (#s = :running AND lease_until < :now)",
            ExpressionAttributeNames={"#s": "status"},
            ExpressionAttributeValues={":running": "TRAINING", ":queued": "QUEUED",
                                       ":lease": now + LEASE_SECONDS, ":now": now, ":owner": owner})

    def finish(self, job_id, owner, *, model_key=None, error=None, metrics=None):
        field, value = ("error", error[:1000]) if error is not None else ("model_key", model_key)
        return self._conditional_update(
            Key={"id": job_id},
            UpdateExpression="SET #s = :status, #result = :value, finished_at = :now, #metrics = :metrics REMOVE lease_owner, lease_until",
            ConditionExpression="#s = :running AND lease_owner = :owner",
            ExpressionAttributeNames={"#s": "status", "#result": field, "#metrics": "metrics"},
            ExpressionAttributeValues={":status": "FAILED" if error is not None else "COMPLETED",
                                       ":running": "TRAINING", ":owner": owner, ":value": value,
                                       ":now": int(time.time()), ":metrics": json.loads(json.dumps(metrics or {}), parse_float=Decimal)})

    def heartbeat(self, job_id, owner):
        return self._conditional_update(Key={"id": job_id},
            UpdateExpression="SET lease_until = :lease", ConditionExpression="lease_owner = :owner",
            ExpressionAttributeValues={":lease": int(time.time()) + LEASE_SECONDS, ":owner": owner})

    def cancel(self, job_id):
        return self._conditional_update(Key={"id": job_id}, UpdateExpression="SET #s = :cancelled",
            ConditionExpression="#s = :queued", ExpressionAttributeNames={"#s": "status"},
            ExpressionAttributeValues={":cancelled": "CANCELLED", ":queued": "QUEUED"})

    def dead_letter(self, job_id):
        return self._conditional_update(Key={"id": job_id},
            UpdateExpression="SET #s = :failed, #e = :error, finished_at = :now REMOVE lease_owner, lease_until",
            ConditionExpression="attribute_exists(id) AND (#s = :queued OR (#s = :running AND lease_until < :now))",
            ExpressionAttributeNames={"#s": "status", "#e": "error"},
            ExpressionAttributeValues={":failed": "FAILED", ":queued": "QUEUED", ":running": "TRAINING",
                ":error": "Worker delivery failed repeatedly; inspect the dead-letter queue and CloudWatch.", ":now": int(time.time())})

    def _conditional_update(self, **kwargs):
        try:
            self.table.update_item(**kwargs)
            return True
        except ClientError as exc:
            if exc.response["Error"]["Code"] == "ConditionalCheckFailedException":
                return False
            raise

    def get_deployment(self, deployment_id):
        return self.table.get_item(Key={"id": f"deploy#{deployment_id}"}, ConsistentRead=True).get("Item")

    def create_deployment(self, deployment):
        self.put_record({**deployment, "kind": "deployment"}, create=True)

    def update_deployment(self, deployment_id, owner, fields):
        names = {f"#f{i}": key for i, key in enumerate(fields)}
        values = {f":v{i}": value for i, value in enumerate(fields.values())}
        values[":owner"] = owner
        return self._conditional_update(Key={"id": f"deploy#{deployment_id}"},
            UpdateExpression="SET " + ", ".join(f"#f{i} = :v{i}" for i in range(len(fields))),
            ConditionExpression="#owner = :owner", ExpressionAttributeNames={**names, "#owner": "owner"},
            ExpressionAttributeValues=values)


class S3ArtifactStore:
    def __init__(self, s3, bucket):
        self.s3, self.bucket = s3, bucket

    def save_csv(self, key, csv):
        self.s3.put_object(Bucket=self.bucket, Key=key, Body=csv.encode(), ContentType="text/csv")

    def read_csv(self, key, limit):
        try:
            obj = self.s3.get_object(Bucket=self.bucket, Key=key)
        except ClientError as exc:
            if exc.response["Error"]["Code"] in ("NoSuchKey", "404"):
                raise ValueError("Upload not found; upload the CSV first") from exc
            raise
        try:
            if obj["ContentLength"] > limit:
                raise ValueError("CSV limit: 10 MB")
            return obj["Body"].read(limit + 1).decode("utf-8-sig")
        except UnicodeDecodeError as exc:
            raise ValueError("CSV must use UTF-8 encoding") from exc
        finally:
            obj["Body"].close()

    def presign_upload(self, key, limit):
        s3 = self.s3
        if os.getenv("S3_PUBLIC_ENDPOINT"):
            s3 = boto3.client("s3", endpoint_url=os.environ["S3_PUBLIC_ENDPOINT"],
                              config=Config(signature_version="s3v4", s3={"addressing_style": "path"}))
        return s3.generate_presigned_post(self.bucket, key, Fields={"Content-Type": "text/csv"},
            Conditions=[["content-length-range", 1, limit], {"Content-Type": "text/csv"}], ExpiresIn=900)

    def download(self, key, path):
        self.s3.download_file(self.bucket, key, str(path))

    def upload_model(self, key, directory):
        with tempfile.TemporaryDirectory() as folder:
            archive = shutil.make_archive(str(Path(folder) / "model"), "zip", directory)
            self.s3.upload_file(archive, self.bucket, key)

    def extract_model(self, key, directory):
        with tempfile.TemporaryDirectory() as folder:
            archive = Path(folder) / "model.zip"
            self.download(key, archive)
            with zipfile.ZipFile(archive) as model:
                if sum(i.file_size for i in model.infolist()) > 1_000_000_000:
                    raise ValueError("Model exceeds the 1 GB inference artifact limit")
                for info in model.infolist():
                    target = (directory / info.filename).resolve()
                    if directory.resolve() not in target.parents or (info.external_attr >> 16) & 0o170000 == 0o120000:
                        raise ValueError("Unsafe model archive")
                model.extractall(directory)


class SQSJobQueue:
    def __init__(self, sqs, url):
        self.sqs, self.url = sqs, url

    def enqueue(self, job_id):
        self.sqs.send_message(QueueUrl=self.url, MessageBody=job_id)

    def receive(self):
        result = self.sqs.receive_message(QueueUrl=self.url, WaitTimeSeconds=20,
                                         MaxNumberOfMessages=1, VisibilityTimeout=VISIBILITY_SECONDS)
        return [QueueMessage(item["Body"], item["ReceiptHandle"]) for item in result.get("Messages", [])]

    def acknowledge(self, message):
        self.sqs.delete_message(QueueUrl=self.url, ReceiptHandle=message.receipt)

    def heartbeat(self, message):
        self.sqs.change_message_visibility(QueueUrl=self.url, ReceiptHandle=message.receipt,
                                          VisibilityTimeout=VISIBILITY_SECONDS)
