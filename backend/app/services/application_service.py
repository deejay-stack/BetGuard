"""Bounded app inference; absence never falls back to a hostname classifier."""
from concurrent.futures import ProcessPoolExecutor
from multiprocessing import get_context
import os
from pathlib import Path
import re

from app.schemas.application import AppMetadata, enough_metadata, metadata_text
from app.services.model_service import ModelService

_pipeline = None
_manifest = None
_threads = None


def _initialize(directory, trusted_hash):
    global _pipeline, _manifest, _threads
    from threadpoolctl import threadpool_limits
    from app.ml.application_artifacts import load_application_artifact
    _threads = threadpool_limits(limits=1)
    _pipeline, _manifest = load_application_artifact(Path(directory), trusted_hash)


def _ready():
    return _manifest["model_version"]


def _predict_app(data):
    metadata = AppMetadata.model_validate(data)
    value = int(_pipeline.predict([metadata_text(metadata)])[0])
    return {"classification": "gambling" if value else "non_gambling",
            "source": "app_metadata_model", "reason": "model_prediction",
            "model_version": _manifest["model_version"],
            "explanation": "The reviewed app metadata model classified the supplied information. This is not proof of safety or app-wide blocking."}


class AppMetadataService(ModelService):
    @classmethod
    def from_environment(cls):
        directory = os.getenv("APP_MODEL_ARTIFACT_DIR")
        trusted_hash = os.getenv("APP_MODEL_MANIFEST_SHA256")
        if not directory and not trusted_hash:
            return cls()
        if not directory or not re.fullmatch(r"[a-fA-F0-9]{64}", trusted_hash or ""):
            return cls("unsuitable")
        executor = None
        try:
            if not all((Path(directory) / name).is_file() for name in ("manifest.json", "model.skops")):
                return cls("unsuitable")
            executor = ProcessPoolExecutor(max_workers=1, mp_context=get_context("spawn"),
                                           initializer=_initialize, initargs=(directory, trusted_hash.lower()))
            return cls("available", executor, executor.submit(_ready).result(timeout=30))
        except Exception:
            if executor:
                executor.shutdown(wait=False, cancel_futures=True)
            return cls("unsuitable")

    def check(self, metadata: AppMetadata):
        if not enough_metadata(metadata):
            return {"classification": "unknown", "source": "unavailable", "reason": "insufficient_metadata",
                    "explanation": "Add an app-store description or public reviews. A name or requested permission alone is not enough to classify an app."}
        result = self._infer(_predict_app, metadata.model_dump())
        if result is not None:
            return result
        return {"classification": "unknown", "source": "unavailable", "reason": "app_model_unavailable",
                "explanation": "No reviewed app metadata model is available. Website detection remains separate; this app has not been evaluated."}
