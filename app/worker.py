import logging
import os
import signal
import threading

from app import runtime
from app.infrastructure.aws import client


def process(job_id):
    return runtime.training_service().process(job_id)


def main():
    logging.basicConfig(level=logging.INFO)
    queue, service = runtime.queue(), runtime.training_service()
    stop = threading.Event()
    signal.signal(signal.SIGTERM, lambda *_: stop.set())
    signal.signal(signal.SIGINT, lambda *_: stop.set())

    def protect(enabled):
        if os.getenv("WORKER_GROUP") and os.getenv("INSTANCE_ID"):
            client("autoscaling").set_instance_protection(AutoScalingGroupName=os.environ["WORKER_GROUP"],
                InstanceIds=[os.environ["INSTANCE_ID"]], ProtectedFromScaleIn=enabled)

    while not stop.is_set():
        try:
            for message in queue.receive():
                try:
                    protect(True)
                    if service.process(message.job_id, heartbeat=lambda: queue.heartbeat(message)):
                        queue.acknowledge(message)
                finally:
                    protect(False)
        except Exception:
            logging.exception("Worker polling failed; retrying")
            stop.wait(5)


if __name__ == "__main__":
    main()
