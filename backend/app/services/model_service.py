"""Optional, one-process model inference. No ML dependencies needed when off."""
from concurrent.futures import ProcessPoolExecutor
from multiprocessing import get_context
import os
from pathlib import Path
from threading import BoundedSemaphore

_pipeline = None
_manifest = None
_thread_limit = None


class InferenceUnavailable(RuntimeError):
    pass


def _initialize(directory: str, manifest_hash: str):
    global _pipeline, _manifest, _thread_limit
    from threadpoolctl import threadpool_limits
    from app.ml.artifacts import load_artifact
    _thread_limit = threadpool_limits(limits=1)
    _pipeline, _manifest = load_artifact(Path(directory), expected_manifest_sha256=manifest_hash)


def _ready():
    return _manifest["model_version"]


def _predict(hostname: str):
    from app.ml.runtime import registrable_domain
    from app.ml.features import scores
    from app.ml.runtime import decisions
    try:
        registrable_domain(hostname)
    except ValueError:
        return {"classification": "unknown", "reason": "model_ineligible"}
    value = int(decisions(scores(_pipeline, [hostname]), _manifest["thresholds"])[0])
    return {"classification": {0: "non_gambling", 1: "gambling", -1: "unknown"}[value],
            "reason": "model_abstained" if value == -1 else "model_prediction"}


class ModelService:
    def __init__(self, status="absent", executor=None, version=None):
        self.status = status
        self.executor = executor
        self.version = version
        self.slot = BoundedSemaphore(1)

    @classmethod
    def from_environment(cls):
        directory, trusted_hash = os.getenv("MODEL_ARTIFACT_DIR"), os.getenv("MODEL_MANIFEST_SHA256")
        if not directory and not trusted_hash:
            return cls()
        if not directory or not trusted_hash:
            return cls("unsuitable")
        executor = None
        try:
            # Reject incomplete/missing artifacts before creating any worker.
            import re
            path = Path(directory)
            if not re.fullmatch(r"[a-fA-F0-9]{64}", trusted_hash) or not all(
                (path / name).is_file() for name in ("manifest.json", "model.skops")
            ):
                return cls("unsuitable")
            # Lazy imports/loading happen once inside the single model process.
            # A distinct worker keeps CPU inference away from HTTP/database work.
            executor = ProcessPoolExecutor(max_workers=1, mp_context=get_context("spawn"),
                                           initializer=_initialize, initargs=(directory, trusted_hash))
            version = executor.submit(_ready).result(timeout=30)
            return cls("available", executor, version)
        except Exception:
            if executor:
                executor.shutdown(wait=False, cancel_futures=True)
            return cls("unsuitable")

    def predict(self, hostname):
        return self._infer(_predict, hostname)

    def _infer(self, operation, value):
        if self.status == "failed":
            raise InferenceUnavailable("Model worker failed; restart the backend.")
        if self.status != "available":
            return None
        if not self.slot.acquire(blocking=False):
            raise InferenceUnavailable("Model inference is busy.")
        try:
            future = self.executor.submit(operation, value)
        except Exception:
            self.slot.release()
            self.status = "failed"
            raise InferenceUnavailable("Model worker is unavailable.") from None
        # A timeout does not release the slot until the work actually ends;
        # repeated requests cannot build an unbounded process queue.
        future.add_done_callback(lambda _future: self.slot.release())
        try:
            return future.result(timeout=1.5)
        except Exception:
            raise InferenceUnavailable("Model inference is unavailable.") from None

    def close(self):
        if self.executor:
            self.executor.shutdown(wait=False, cancel_futures=True)
