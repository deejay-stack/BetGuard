"""Separate, reviewed app-metadata artifacts. Hostname models are incompatible."""
import hashlib
import importlib.metadata
import json
from pathlib import Path
import platform
import zipfile

FORMAT = "betguard-app-metadata-v1"
ALGORITHMS = {"svm", "random_forest", "logistic_regression"}


def sha256(path: Path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def environment():
    return {"python": ".".join(platform.python_version_tuple()[:2]),
            **{name: importlib.metadata.version(name) for name in ("scikit-learn", "numpy", "scipy", "skops")}}


def feature_hash():
    return sha256(Path(__file__).parents[1] / "schemas" / "application.py")


def load_application_artifact(directory: Path, trusted_hash: str, *, deployment=True):
    import skops.io as sio
    from sklearn.pipeline import Pipeline
    from sklearn.feature_extraction.text import TfidfVectorizer
    from sklearn.linear_model import LogisticRegression
    from sklearn.ensemble import RandomForestClassifier
    from sklearn.svm import LinearSVC

    manifest_file = directory / "manifest.json"
    if manifest_file.stat().st_size > 2_000_000 or sha256(manifest_file) != trusted_hash:
        raise ValueError("App model manifest integrity failed.")
    manifest = json.loads(manifest_file.read_text(encoding="utf-8"))
    if (manifest.get("format") != FORMAT or manifest.get("environment") != environment()
            or manifest.get("feature_sha256") != feature_hash()
            or manifest.get("algorithm") not in ALGORITHMS
            or manifest.get("labels") != {"non_gambling": 0, "gambling": 1}):
        raise ValueError("Incompatible app metadata artifact.")
    if deployment and (manifest.get("purpose") != "deployment" or manifest.get("synthetic") is not False
                       or not manifest.get("approval") or not manifest.get("held_out_evaluation")):
        raise ValueError("App model needs reviewed real data and held-out evaluation.")
    if not isinstance(manifest.get("model_version"), str) or not 1 <= len(manifest["model_version"]) <= 200:
        raise ValueError("App model version is required.")
    model_file = directory / "model.skops"
    if model_file.stat().st_size > 50_000_000 or sha256(model_file) != manifest.get("model_sha256"):
        raise ValueError("App model payload integrity failed.")
    with zipfile.ZipFile(model_file) as archive:
        if sum(item.file_size for item in archive.infolist()) > 250_000_000:
            raise ValueError("App model exceeds the memory limit.")
    allowed = {"sklearn.tree._tree.Tree"}
    if set(sio.get_untrusted_types(file=model_file)) - allowed:
        raise ValueError("Unapproved app model types.")
    pipeline = sio.load(model_file, trusted=list(allowed))
    if (not isinstance(pipeline, Pipeline) or list(pipeline.classes_) != [0, 1]
            or list(pipeline.named_steps) != ["text", "classifier"]
            or not isinstance(pipeline.named_steps["text"], TfidfVectorizer)
            or not isinstance(pipeline.named_steps["classifier"],
                              {"svm": LinearSVC, "random_forest": RandomForestClassifier,
                               "logistic_regression": LogisticRegression}[manifest["algorithm"]])):
        raise ValueError("Invalid fitted app metadata pipeline.")
    return pipeline, manifest
