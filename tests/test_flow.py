import json
import os
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

from moto import mock_aws

from app import controller, predict, runtime, worker
from app.infrastructure.aws import client, table
from app.services import ModelCache, PredictionService, TrainingService
from app.tasks.base import MLTask
from app.tasks.factory import TaskFactory


class FileTask(MLTask):
    """Lightweight test strategy exercising real artifact storage and dispatch."""

    def __init__(self, name):
        self.name = name
        self.loads = 0

    def validate_training(self, request):
        pass

    def train(self, dataset, model_dir, job):
        assert job["task"] == self.name
        assert dataset.read_text().startswith("x,y")
        model_dir.mkdir()
        (model_dir / "task.txt").write_text(self.name)

    def load(self, model_dir):
        self.loads += 1
        return (model_dir / "task.txt").read_text()

    def predict(self, model, rows):
        assert model == self.name
        return {"predictions": [self.name] * len(rows)}


@mock_aws
class FlowTests(unittest.TestCase):
    def setUp(self):
        self.env = patch.dict(os.environ, {
            "AWS_DEFAULT_REGION": "us-east-1", "BUCKET_NAME": "automl-test",
            "TABLE_NAME": "automl-test", "AWS_ACCESS_KEY_ID": "test", "AWS_SECRET_ACCESS_KEY": "test",
        })
        self.env.start()
        self.addCleanup(self.env.stop)
        client.cache_clear()
        table.cache_clear()
        runtime.prediction_service.cache_clear()
        client("s3").create_bucket(Bucket="automl-test")
        client("dynamodb").create_table(
            TableName="automl-test", BillingMode="PAY_PER_REQUEST",
            KeySchema=[{"AttributeName": "id", "KeyType": "HASH"}],
            AttributeDefinitions=[{"AttributeName": k, "AttributeType": "S"} for k in ("id", "scope", "created_id")],
            GlobalSecondaryIndexes=[{"IndexName": "by-owner", "KeySchema": [
                {"AttributeName": "scope", "KeyType": "HASH"}, {"AttributeName": "created_id", "KeyType": "RANGE"}],
                "Projection": {"ProjectionType": "ALL"}}])
        os.environ["QUEUE_URL"] = client("sqs").create_queue(QueueName="jobs")["QueueUrl"]

    def call(self, path, payload=None, method="POST", handler=controller.handler, headers=None, owner=None, cursor=None):
        event = {"httpMethod": method, "path": path, "body": json.dumps(payload or {}), "headers": headers or {},
                 "queryStringParameters": {"cursor": cursor} if cursor else {}}
        if owner:
            event["requestContext"] = {"authorizer": {"claims": {"sub": owner}}}
        result = handler(event, None)
        return result["statusCode"], json.loads(result["body"])

    def submit(self):
        status, job = self.call("/jobs", {"csv": "x,y\n1,2\n2,4\n", "target": "y"})
        self.assertEqual(status, 202)
        return job["job_id"]

    def test_submit_persists_dataset_state_and_queue_message(self):
        job_id = self.submit()
        self.assertEqual(self.call(f"/jobs/{job_id}", method="GET")[1]["status"], "QUEUED")
        stored = client("s3").get_object(Bucket="automl-test", Key=f"datasets/{job_id}.csv")
        self.assertEqual(stored["Body"].read(), b"x,y\n1,2\n2,4\n")
        messages = client("sqs").receive_message(QueueUrl=os.environ["QUEUE_URL"])["Messages"]
        self.assertEqual(messages[0]["Body"], job_id)

    def test_invalid_csv_does_not_enqueue(self):
        self.assertEqual(self.call("/jobs", {"csv": "x\n1", "target": "y"})[0], 400)
        self.assertNotIn("Messages", client("sqs").receive_message(QueueUrl=os.environ["QUEUE_URL"]))

    def test_deploy_requires_completed_job_and_resolves_model(self):
        job_id = self.submit()
        self.assertEqual(self.call("/deploy", {"job_id": job_id})[0], 409)
        table().update_item(Key={"id": job_id}, UpdateExpression="SET #s = :s, model_key = :key",
                            ExpressionAttributeNames={"#s": "status"},
                            ExpressionAttributeValues={":s": "COMPLETED", ":key": "models/test.zip"})
        status, deployment = self.call("/deploy", {"job_id": job_id})
        self.assertEqual(status, 201)
        saved = table().get_item(Key={"id": "deploy#" + deployment["deployment_id"]})["Item"]
        self.assertEqual(saved["model_key"], "models/test.zip")
        self.assertEqual(self.call(deployment["predict_path"], {"rows": []}, handler=predict.handler,
                                   headers={"x-api-key": deployment["api_key"]})[0], 400)

    def test_duplicate_delivery_does_not_steal_active_training(self):
        table().put_item(Item={"id": "active", "status": "TRAINING", "lease_until": int(time.time()) + 60})
        self.assertFalse(worker.process("active"))
        table().put_item(Item={"id": "finished", "status": "COMPLETED"})
        self.assertTrue(worker.process("finished"))

    def test_training_failure_is_saved_and_message_can_be_acknowledged(self):
        job_id = self.submit()
        fake = MagicMock()
        fake.TabularPredictor.return_value.fit.side_effect = ValueError("Invalid target data")
        with patch.dict("sys.modules", {"autogluon": MagicMock(), "autogluon.tabular": fake}):
            with self.assertLogs(level="ERROR"):
                self.assertTrue(worker.process(job_id))
        job = table().get_item(Key={"id": job_id})["Item"]
        self.assertEqual(job["status"], "FAILED")
        self.assertEqual(job["error"], "Invalid target data")

    def test_unknown_task_is_rejected_before_any_aws_write(self):
        status, _ = self.call("/jobs", {"csv": "x,y\n1,2\n2,3", "target": "y", "task": "unknown"})
        self.assertEqual(status, 400)
        self.assertEqual(table().scan()["Count"], 0)
        self.assertEqual(client("s3").list_objects_v2(Bucket="automl-test")["KeyCount"], 0)

    def test_mixed_tasks_train_deploy_and_predict_through_matching_strategy(self):
        factory = TaskFactory()
        strategies = {name: FileTask(name) for name in ("classification", "regression")}
        for name, strategy in strategies.items():
            factory.register(name, lambda strategy=strategy: strategy)
        trainer = TrainingService(runtime.repository(), runtime.artifacts(), factory)
        deployments = {}
        for name in strategies:
            status, submitted = self.call("/jobs", {"csv": "x,y\n1,2\n2,4", "target": "y", "task": name})
            self.assertEqual(status, 202)
            self.assertTrue(trainer.process(submitted["job_id"]))
            job = table().get_item(Key={"id": submitted["job_id"]})["Item"]
            self.assertEqual(job["status"], "COMPLETED")
            self.assertNotIn("lease_owner", job)
            status, deployment = self.call("/deploy", {"job_id": submitted["job_id"]})
            self.assertEqual(status, 201)
            self.assertEqual(deployment["task"], name)
            deployments[name] = deployment["deployment_id"]
        with tempfile.TemporaryDirectory() as folder:
            cache = ModelCache(runtime.artifacts(), Path(folder) / "cache")
            service = PredictionService(runtime.repository(), factory, cache)
            for name in ("classification", "classification", "regression", "classification"):
                self.assertEqual(service.predict(deployments[name], {"rows": [{"x": 1}]}),
                                 {"predictions": [name]})
            self.assertEqual(strategies["classification"].loads, 2)
            self.assertEqual(strategies["regression"].loads, 1)

    def test_expired_worker_cannot_overwrite_new_attempt(self):
        job_id = self.submit()
        repository = runtime.repository()
        self.assertTrue(repository.claim(job_id, "old-worker", 1))
        self.assertTrue(repository.claim(job_id, "new-worker", int(time.time())))
        self.assertFalse(repository.finish(job_id, "old-worker", model_key="stale.zip"))
        self.assertFalse(repository.finish(job_id, "old-worker", error="stale error"))
        self.assertTrue(repository.finish(job_id, "new-worker", model_key="winner.zip"))
        self.assertEqual(repository.get_job(job_id)["model_key"], "winner.zip")

    def test_legacy_job_and_deployment_default_to_tabular(self):
        table().put_item(Item={"id": "legacy", "status": "COMPLETED", "model_key": "old.zip"})
        status, deployment = self.call("/deploy", {"job_id": "legacy"})
        self.assertEqual(status, 201)
        self.assertEqual(deployment["task"], "tabular")
        table().put_item(Item={"id": "deploy#old", "model_key": "old.zip"})
        factory, cache = MagicMock(), MagicMock()
        PredictionService(runtime.repository(), factory, cache).predict("old", {"rows": [{"x": 1}]})
        factory.create.assert_called_once_with("tabular")

    def upload(self, csv="x,y\n1,a\n2,b\n", owner=None):
        status, ticket = self.call("/uploads", {"name": "sample.csv"}, owner=owner)
        self.assertEqual(status, 201)
        item = runtime.repository().get_record("dataset#" + ticket["dataset_id"])
        client("s3").put_object(Bucket="automl-test", Key=item["upload_key"], Body=csv.encode())
        status, dataset = self.call(f'/datasets/{ticket["dataset_id"]}/complete', {}, owner=owner)
        self.assertEqual(status, 200, dataset)
        return dataset

    def test_upload_snapshot_and_preprocessing_are_immutable(self):
        raw = "id,x,y\n1, 2 ,a\n1, 2 ,a\n3,,b\n4,5,\n"
        dataset = self.upload(raw)
        self.assertEqual(dataset["profile"]["rows"], 4)
        self.assertEqual(dataset["profile"]["duplicates"], 1)
        self.assertEqual(dataset["profile"]["missing_cells"], 2)
        status, prepared = self.call(f'/datasets/{dataset["dataset_id"]}/preprocess',
            {"target": "y", "drop_columns": ["id"], "trim_strings": True, "drop_duplicates": True})
        self.assertEqual(status, 201, prepared)
        self.assertEqual(prepared["profile"]["rows"], 2)
        self.assertTrue(prepared["prepared"])
        self.assertNotEqual(prepared["dataset_id"], dataset["dataset_id"])
        self.assertEqual(prepared["profile"]["preview"][0], {"x": "2", "y": "a"})
        client("s3").put_object(Bucket="automl-test", Key=dataset["upload_key"], Body=b"changed")
        self.assertEqual(runtime.artifacts().read_csv(dataset["dataset_key"], 1000), raw)
        self.assertEqual(self.call(f'/datasets/{dataset["dataset_id"]}/complete', {})[0], 200)
        self.assertEqual(self.call('/jobs', {"dataset_id": dataset["dataset_id"], "task": "classification"})[0], 409)
        status, job = self.call('/jobs', {"dataset_id": prepared["dataset_id"], "task": "classification"})
        self.assertEqual(status, 202, job)

    def test_owner_isolation_covers_dataset_job_deployment_and_lists(self):
        dataset = self.upload(owner="alice")
        path = f'/datasets/{dataset["dataset_id"]}'
        self.assertEqual(self.call(path, method="GET", owner="bob")[0], 404)
        self.assertEqual(self.call(path + "/preprocess", {"target": "y"}, owner="bob")[0], 404)
        status, job = self.call('/jobs', {"csv": "x,y\n1,a\n2,b", "target": "y"}, owner="alice")
        self.assertEqual(status, 202)
        job_id = job["job_id"]
        self.assertEqual(self.call('/jobs/' + job_id, method="GET", owner="bob")[0], 404)
        self.assertEqual(self.call('/jobs/' + job_id + '/cancel', {}, owner="bob")[0], 404)
        self.assertEqual(self.call('/deploy', {"job_id": job_id}, owner="bob")[0], 404)
        self.assertEqual(self.call('/jobs', method="GET", owner="bob")[1]["items"], [])
        self.assertEqual(len(self.call('/jobs', method="GET", owner="alice")[1]["items"]), 1)

    def test_deployment_key_rotation_revocation_and_redaction(self):
        job_id = self.submit()
        repo = runtime.repository()
        repo.claim(job_id, "worker", int(time.time()))
        repo.finish(job_id, "worker", model_key="models/test.zip")
        _, deploy = self.call('/deploy', {"job_id": job_id})
        endpoint = deploy["predict_path"]
        dep_id = deploy["deployment_id"]
        self.assertEqual(self.call(endpoint, {"rows": []}, handler=predict.handler)[0], 401)
        self.assertEqual(self.call(endpoint, {"rows": []}, handler=predict.handler,
            headers={"X-Api-Key": deploy["api_key"]})[0], 400)
        listed = self.call('/deployments', method="GET")[1]["items"][0]
        self.assertNotIn('key_hash', listed)
        self.assertNotIn(deploy["api_key"], json.dumps(listed))
        self.assertEqual(self.call(f'/deployments/{dep_id}', method='GET', owner='bob')[0], 404)
        _, rotated = self.call(f'/deployments/{dep_id}/key', {})
        self.assertNotEqual(rotated["api_key"], deploy["api_key"])
        self.assertEqual(self.call(endpoint, {"rows": []}, handler=predict.handler,
            headers={"x-api-key": deploy["api_key"]})[0], 401)
        self.assertEqual(self.call(f'/deployments/{dep_id}', method='DELETE')[0], 200)
        self.assertEqual(self.call(endpoint, {"rows": []}, handler=predict.handler,
            headers={"x-api-key": rotated["api_key"]})[0], 409)

    def test_pagination_does_not_leak_another_owner(self):
        repo = runtime.repository()
        for i in range(35):
            repo.create_job({"id": str(i), "status": "QUEUED", "owner": "alice"})
        first = self.call('/jobs', method="GET", owner="alice")[1]
        self.assertEqual(len(first["items"]), 30)
        self.assertTrue(first["cursor"])
        second = self.call('/jobs', method="GET", owner="alice", cursor=first["cursor"])[1]
        self.assertEqual(len(second["items"]), 5)
        self.assertEqual(len({i['id'] for i in first['items'] + second['items']}), 35)
        self.assertEqual(self.call('/jobs', method="GET", owner="bob", cursor=first["cursor"])[0], 400)
        self.assertEqual(self.call('/jobs', method="GET", cursor="bad")[0], 400)

    def test_cancel_retry_and_dlq_preserve_active_lease(self):
        from app.dlq import handler as dlq_handler
        job_id = self.submit()
        self.assertEqual(self.call(f'/jobs/{job_id}/cancel', {})[0], 200)
        self.assertTrue(worker.process(job_id))
        status, retry = self.call(f'/jobs/{job_id}/retry', {})
        self.assertEqual(status, 202)
        self.assertNotEqual(retry["job_id"], job_id)
        active = retry["job_id"]
        repo = runtime.repository()
        repo.claim(active, 'worker', int(time.time()))
        self.assertTrue(repo.heartbeat(active, 'worker'))
        self.assertFalse(repo.heartbeat(active, 'other'))
        event = {"Records": [{"body": active, "messageId": "msg"}]}
        self.assertEqual(dlq_handler(event, None)['batchItemFailures'], [{"itemIdentifier": "msg"}])
        table().update_item(Key={"id": active}, UpdateExpression="SET lease_until = :old",
                            ExpressionAttributeValues={":old": 1})
        self.assertEqual(dlq_handler(event, None)['batchItemFailures'], [])
        self.assertEqual(repo.get_job(active)['status'], 'FAILED')

    def test_auth_is_required_in_cloud_and_options_stays_public(self):
        with patch.dict(os.environ, {"AUTH_REQUIRED": "true"}):
            self.assertEqual(self.call('/jobs', method="GET")[0], 401)
            self.assertEqual(self.call('/jobs', method="GET", owner="alice")[0], 200)
            self.assertEqual(self.call('/jobs', method="OPTIONS")[0], 200)

    def test_image_mismatch_cannot_deploy_or_predict(self):
        table().put_item(Item={"id": "old-job", "status": "COMPLETED", "model_key": "m.zip", "image_uri": "old-image"})
        self.assertEqual(self.call('/deploy', {"job_id": "old-job"})[0], 409)

    def test_preprocessing_rejects_target_drop_and_invalid_schema(self):
        dataset = self.upload()
        path = f'/datasets/{dataset["dataset_id"]}/preprocess'
        for payload in ({"target": "y", "drop_columns": ["y"]}, {"target": "absent"},
                        {"target": "y", "drop_columns": "x"}, {"target": "y", "trim_strings": "false"}):
            self.assertEqual(self.call(path, payload)[0], 400, payload)


if __name__ == "__main__":
    unittest.main()
