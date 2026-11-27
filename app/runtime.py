"""Composition root: services are wired to AWS implementations only here."""
import os
import tempfile
from functools import lru_cache
from pathlib import Path

from app.infrastructure.aws import DynamoJobRepository, S3ArtifactStore, SQSJobQueue, client, table
from app.services import JobService, ModelCache, PredictionService, TrainingService
from app.tasks.factory import default_factory


def repository():
    return DynamoJobRepository(table())


def artifacts():
    return S3ArtifactStore(client("s3"), os.environ["BUCKET_NAME"])


def queue():
    return SQSJobQueue(client("sqs"), os.environ["QUEUE_URL"])


def job_service(owner="local"):
    return JobService(repository(), artifacts(), queue(), default_factory(), owner)


def dataset_service(owner="local"):
    from app.datasets import DatasetService
    return DatasetService(repository(), artifacts(), owner)


def training_service():
    return TrainingService(repository(), artifacts(), default_factory())


@lru_cache
def prediction_service():
    cache = ModelCache(artifacts(), Path(tempfile.gettempdir()) / "automl-model")
    return PredictionService(repository(), default_factory(), cache)
