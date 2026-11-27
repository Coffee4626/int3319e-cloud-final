"""Application use cases. AWS SDK and AutoGluon stay behind injected contracts."""
import logging
import shutil
import tempfile
import time
import uuid
import os
import hashlib
import hmac
import secrets
import threading
from pathlib import Path

from app.domain import ArtifactStore, ConflictError, JobQueue, JobRepository, NotFoundError, TrainingRequest, UnauthorizedError
from app.datasets import DatasetService, MAX_BYTES
from app.tasks.factory import TaskFactory

logger = logging.getLogger(__name__)


class JobService:
    def __init__(self, repository: JobRepository, artifacts: ArtifactStore,
                 queue: JobQueue, tasks: TaskFactory, owner="local"):
        self.repository, self.artifacts, self.queue, self.tasks = repository, artifacts, queue, tasks
        self.owner = owner

    def submit(self, payload: dict) -> dict:
        dataset = None
        if payload.get("dataset_id"):
            dataset = DatasetService(self.repository, self.artifacts, self.owner).get(payload["dataset_id"])
            if dataset["status"] != "READY" or not dataset.get("prepared"):
                raise ConflictError("Preprocess the dataset before training")
            payload = {**payload, "csv": self.artifacts.read_csv(dataset["dataset_key"], MAX_BYTES),
                       "target": dataset["target"]}
        elif isinstance(payload.get("csv"), str) and len(payload["csv"].encode()) > 1_000_000:
            raise ValueError("Inline CSV limit: 1 MB; use /uploads for larger datasets")
        request = TrainingRequest.parse(payload)
        self.tasks.create(request.task).validate_training(request)
        job_id = uuid.uuid4().hex
        name = payload.get("name") or (dataset["name"] if dataset else "Untitled experiment")
        if not isinstance(name, str) or len(name) > 120:
            raise ValueError("Experiment name must be at most 120 characters")
        key = dataset["dataset_key"] if dataset else f"datasets/{job_id}.csv"
        if not dataset:
            self.artifacts.save_csv(key, request.csv)
        self.repository.create_job({
            "id": job_id, "status": "QUEUED", "dataset_key": key, "task": request.task,
            "name": name, "owner": self.owner, "dataset_id": dataset["dataset_id"] if dataset else None,
            "image_uri": os.getenv("MODEL_IMAGE_URI", "automl:local"),
            "target": request.target, "time_limit": request.time_limit, "created_at": int(time.time())})
        try:
            self.queue.enqueue(job_id)
        except Exception:
            self.repository.submission_failed(job_id)
            raise
        return {"job_id": job_id, "status": "QUEUED", "task": request.task}

    def get(self, job_id: str) -> dict:
        job = self.repository.get_job(job_id)
        if not job or job.get("owner", "local") != self.owner:
            raise NotFoundError("Job not found")
        return {key: value for key, value in job.items() if key not in ("lease_owner", "lease_until")}

    def list(self, kind, cursor=None):
        page = self.repository.list_records(kind, self.owner, cursor)
        page["items"] = [public_record(item) for item in page["items"]]
        return page

    def cancel(self, job_id):
        self.get(job_id)
        if not self.repository.cancel(job_id):
            raise ConflictError("Only queued jobs can be cancelled")
        return {"id": job_id, "status": "CANCELLED"}

    def retry(self, job_id):
        job = self.get(job_id)
        if job["status"] not in ("FAILED", "CANCELLED"):
            raise ConflictError("Only failed or cancelled jobs can be retried")
        payload = {key: job[key] for key in ("target", "task", "time_limit", "name")}
        payload["time_limit"] = int(job["time_limit"])
        if job.get("dataset_id"):
            payload["dataset_id"] = job["dataset_id"]
        else:
            payload["csv"] = self.artifacts.read_csv(job["dataset_key"], MAX_BYTES)
        return self.submit(payload)

    def deploy(self, job_id: str) -> dict:
        if not isinstance(job_id, str) or not job_id:
            raise ValueError("job_id must be a non-empty string")
        job = self.get(job_id)
        if job["status"] != "COMPLETED":
            raise ConflictError("Job must be COMPLETED before deploying")
        current_image = os.getenv("MODEL_IMAGE_URI", "automl:local")
        if job.get("image_uri", current_image) != current_image:
            raise ConflictError("This model was trained with another image. Retrain with the current runtime before deploying.")
        task = job.get("task", "tabular")  # Existing jobs remain deployable.
        self.tasks.create(task)
        deployment_id = uuid.uuid4().hex
        api_key = secrets.token_urlsafe(32)
        self.repository.create_deployment({"id": f"deploy#{deployment_id}", "job_id": job_id,
            "deployment_id": deployment_id, "owner": self.owner, "status": "ACTIVE",
            "name": job.get("name", "Model endpoint"), "target": job.get("target"),
            "dataset_id": job.get("dataset_id"), "image_uri": current_image,
            "key_hash": hashlib.sha256(api_key.encode()).hexdigest(),
            "key_prefix": api_key[:6], "model_key": job["model_key"], "task": task})
        return {"deployment_id": deployment_id, "predict_path": f"/predict/{deployment_id}",
                "task": task, "api_key": api_key, "image_uri": current_image}

    def deployment(self, deployment_id):
        item = self.repository.get_deployment(deployment_id)
        if not item or item.get("owner", "local") != self.owner:
            raise NotFoundError("Deployment not found")
        return public_record(item)

    def revoke(self, deployment_id):
        self.deployment(deployment_id)
        self.repository.update_deployment(deployment_id, self.owner, {"status": "REVOKED"})
        return {"status": "REVOKED"}

    def rotate_key(self, deployment_id):
        deployment = self.deployment(deployment_id)
        if deployment["status"] != "ACTIVE":
            raise ConflictError("Deployment is revoked")
        key = secrets.token_urlsafe(32)
        self.repository.update_deployment(deployment_id, self.owner,
            {"key_hash": hashlib.sha256(key.encode()).hexdigest(), "key_prefix": key[:6]})
        return {"api_key": key, "deployment_id": deployment_id}


def public_record(item):
    return {k: v for k, v in item.items() if k not in ("key_hash", "lease_owner", "lease_until", "scope", "created_id")}


class TrainingService:
    def __init__(self, repository: JobRepository, artifacts: ArtifactStore, tasks: TaskFactory):
        self.repository, self.artifacts, self.tasks = repository, artifacts, tasks

    def process(self, job_id: str, heartbeat=None) -> bool:
        """Return True only when this delivery can safely be acknowledged."""
        job = self.repository.get_job(job_id)
        if not job or job["status"] in ("COMPLETED", "FAILED", "CANCELLED"):
            return True
        owner = uuid.uuid4().hex
        if not self.repository.claim(job_id, owner, int(time.time())):
            return False
        stop = threading.Event()

        def renew():
            while not stop.wait(30):
                try:
                    if not self.repository.heartbeat(job_id, owner):
                        return
                    if heartbeat:
                        heartbeat()
                except Exception:
                    logger.exception("Lease renewal failed for %s", job_id)

        thread = threading.Thread(target=renew, daemon=True)
        thread.start()
        try:
            if job.get("image_uri", os.getenv("MODEL_IMAGE_URI", "automl:local")) != os.getenv("MODEL_IMAGE_URI", "automl:local"):
                raise ValueError("Worker image differs from the submitted runtime. Retry after the worker rollout.")
            task = self.tasks.create(job.get("task", "tabular"))
            with tempfile.TemporaryDirectory() as folder:
                root = Path(folder)
                self.artifacts.download(job["dataset_key"], root / "data.csv")
                metrics = task.train(root / "data.csv", root / "model", job) or {}
                total_bytes = sum(p.stat().st_size for p in (root / "model").rglob("*") if p.is_file())
                if total_bytes > 1_000_000_000:
                    raise ValueError("Model exceeds the 1 GB Lambda inference limit")
                metrics["artifact_bytes"] = total_bytes
                # Isolate attempts: an expired worker cannot overwrite the winning artifact.
                key = f"models/{job_id}/{owner}.zip"
                self.artifacts.upload_model(key, root / "model")
        except Exception as exc:
            logger.exception("Training failed: %s", job_id)
            return self.repository.finish(job_id, owner, error=str(exc))
        finally:
            stop.set()
            thread.join(timeout=2)
        return self.repository.finish(job_id, owner, model_key=key, metrics=metrics)


class ModelCache:
    """One model per warm process; both task and artifact identify the cache entry."""

    def __init__(self, artifacts: ArtifactStore, directory: Path):
        self.artifacts, self.directory = artifacts, directory
        self._key, self._model = None, None

    def get(self, task_name, key, task):
        identity = (task_name, key)
        if identity != self._key:
            self._key, self._model = None, None
            shutil.rmtree(self.directory, ignore_errors=True)
            self.directory.mkdir(parents=True)
            self.artifacts.extract_model(key, self.directory)
            model = task.load(self.directory)
            self._model, self._key = model, identity
        return self._model


class PredictionService:
    def __init__(self, repository: JobRepository, tasks: TaskFactory, cache: ModelCache):
        self.repository, self.tasks, self.cache = repository, tasks, cache

    def predict(self, deployment_id: str, payload: dict, api_key=None, enforce_auth=False) -> dict:
        deployment = self.repository.get_deployment(deployment_id)
        if not deployment:
            raise NotFoundError("Deployment not found")
        if enforce_auth:
            actual = hashlib.sha256((api_key or "").encode()).hexdigest()
            if not hmac.compare_digest(actual, deployment.get("key_hash", "")):
                raise UnauthorizedError("Invalid deployment API key")
        if deployment.get("status", "ACTIVE") != "ACTIVE":
            raise ConflictError("Deployment has been revoked")
        current_image = os.getenv("MODEL_IMAGE_URI", "automl:local")
        if deployment.get("image_uri", current_image) != current_image:
            raise ConflictError("Model image differs from the inference runtime; retrain and redeploy")
        task_name = deployment.get("task", "tabular")
        task = self.tasks.create(task_name)
        rows = task.validate_prediction(payload)
        model = self.cache.get(task_name, deployment["model_key"], task)
        return task.predict(model, rows)
