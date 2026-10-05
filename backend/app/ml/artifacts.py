"""Project-owned skops artifacts with an external manifest trust anchor."""
import hashlib
import importlib.metadata
import json
import math
import platform
from pathlib import Path
import zipfile

import skops.io as sio
from sklearn.pipeline import Pipeline

from app.ml import FEATURE_VERSION, LABELS, POLICY_VERSION
from app.ml.runtime import digest, psl_metadata

ALLOWED_CUSTOM_TYPES = {
    "app.ml.features.HostnameLexicalFeatures", "app.ml.features.NormalizeHostnames",
    # The exact scikit-learn tree state used by the bounded RandomForest.
    "sklearn.tree._tree.Tree",
}
DEPENDENCIES = ("scikit-learn", "numpy", "scipy", "skops", "tldextract")


def environment_metadata():
    return {"python": ".".join(platform.python_version_tuple()[:2]),
            **{name: importlib.metadata.version(name) for name in DEPENDENCIES}}


def code_metadata():
    directory = Path(__file__).parent
    return {**{name: digest(directory / name) for name in ("features.py", "runtime.py")},
            "normalization": digest(directory.parent / "schemas" / "catalog.py")}


def load_artifact(directory: Path, *, expected_manifest_sha256: str, deployment=True):
    manifest_path = directory / "manifest.json"
    if manifest_path.stat().st_size > 2_000_000 or digest(manifest_path) != expected_manifest_sha256:
        raise ValueError("Model manifest does not match the externally trusted digest.")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if (manifest.get("format") != "betguard-skops-v1" or manifest.get("labels") != LABELS
            or manifest.get("feature_version") != FEATURE_VERSION or manifest.get("policy_version") != POLICY_VERSION
            or manifest.get("environment") != environment_metadata() or manifest.get("code") != code_metadata()
            or manifest.get("psl") != psl_metadata() or manifest.get("calibrated_probability") is not False):
        raise ValueError("Model dependency, feature, label, policy or PSL metadata is incompatible.")
    if deployment and (manifest.get("purpose") != "deployment" or manifest.get("synthetic") is not False
                       or not manifest.get("approval") or not manifest.get("evaluation", {}).get("test")):
        raise ValueError("Only explicitly approved real-data, evaluated artifacts may be served.")
    thresholds = manifest["thresholds"]
    low, high = thresholds["non_gambling_max"], thresholds["gambling_min"]
    if any(value is not None and (not isinstance(value, (float, int)) or not math.isfinite(value)) for value in (low, high)):
        raise ValueError("Invalid decision thresholds.")
    if low is not None and high is not None and low >= high:
        raise ValueError("Overlapping abstention thresholds.")
    if not isinstance(manifest.get("model_version"), str) or not 1 <= len(manifest["model_version"].strip()) <= 200:
        raise ValueError("A model version is required.")
    if manifest.get("model_file") != "model.skops":
        raise ValueError("Unexpected model filename.")
    model = directory / "model.skops"
    if model.stat().st_size > 50_000_000 or digest(model) != manifest["model_sha256"]:
        raise ValueError("Model payload failed its integrity check.")
    with zipfile.ZipFile(model) as archive:
        if sum(item.file_size for item in archive.infolist()) > 250_000_000:
            raise ValueError("Expanded artifact exceeds the serving memory limit.")
    untrusted = set(sio.get_untrusted_types(file=model))
    if untrusted - ALLOWED_CUSTOM_TYPES:
        raise ValueError("Artifact contains types outside the project allowlist.")
    pipeline = sio.load(model, trusted=list(ALLOWED_CUSTOM_TYPES))
    if not isinstance(pipeline, Pipeline) or list(pipeline.classes_) != [0, 1]:
        raise ValueError("Artifact is not a compatible fitted binary pipeline.")
    return pipeline, manifest
