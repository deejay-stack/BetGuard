"""Offline artifact creation using the runtime loader's compatibility contract."""
from pathlib import Path
import skops.io as sio
from app.ml import FEATURE_VERSION, LABELS, POLICY_VERSION
from app.ml.runtime import digest, json_write, psl_metadata
from app.ml.artifacts import code_metadata, environment_metadata


def save_artifact(directory: Path, pipeline, metadata):
    directory.mkdir(parents=True, exist_ok=False)
    model = directory / "model.skops"
    sio.dump(pipeline, model)
    if model.stat().st_size > 50_000_000:
        raise ValueError("Model exceeds the 50 MB serving limit; reduce features/trees.")
    manifest = {**metadata, "format": "betguard-skops-v1", "model_file": "model.skops",
                "model_sha256": digest(model), "labels": LABELS,
                "feature_version": FEATURE_VERSION, "policy_version": POLICY_VERSION,
                "environment": environment_metadata(), "code": code_metadata(), "psl": psl_metadata(),
                "calibrated_probability": False}
    json_write(directory / "manifest.json", manifest)
    return manifest


