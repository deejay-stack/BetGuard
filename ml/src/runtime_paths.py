"""Resolve finalized resources independently of the server's working directory."""
import os
from pathlib import Path

ML_ROOT = Path(os.environ.get("BETGUARD_ML_ROOT", Path(__file__).resolve().parents[1])).resolve()


def resource_path(value: str) -> Path:
    # The existing deployment manifest uses Windows separators. Support Linux
    # deployments too without changing the manifest or model artifact.
    path = Path(value.replace("\\", "/"))
    return path if path.is_absolute() else ML_ROOT / path
