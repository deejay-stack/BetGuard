"""Frozen optimized SVM export and offline inference. Never selects production.

Only trusted project-owned joblib files may be loaded. The manifest digest is
an external trust anchor, not a signature. Margins are not probabilities and
the frozen classification threshold does not authorize automatic blocking.
"""
import argparse
import hashlib
import importlib.metadata
import json
import platform
from pathlib import Path
import re

import joblib
import numpy as np
from scipy.sparse import hstack
from sklearn.metrics import accuracy_score, precision_score, recall_score, f1_score, roc_auc_score, confusion_matrix
from sklearn.svm import LinearSVC
from threadpoolctl import threadpool_limits
import tldextract

if __package__:
    from . import optimized_svm_features_frozen as features
else:
    import optimized_svm_features_frozen as features

ML_ROOT = Path(__file__).resolve().parents[1]
CONFIG = "reports/optimized_svm_frozen_candidate.json"
THRESHOLD = -0.05278699316952151
FORMAT = "betguard-optimized-svm-shadow-v1"
ENV_PACKAGES = ("scikit-learn", "numpy", "scipy", "pandas", "joblib", "tldextract")
EXTRACT = tldextract.TLDExtract(suffix_list_urls=(), cache_dir=None)


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def environment():
    return {"python": ".".join(platform.python_version_tuple()[:2]), **{name: importlib.metadata.version(name) for name in ENV_PACKAGES}}


def json_write(path, value):
    path.write_text(json.dumps(value, indent=2, sort_keys=True, allow_nan=False) + "\n", encoding="utf-8")


def canonical_host(value):
    # Inference accepts already validated ASCII hostnames, not arbitrary URLs.
    # The API's strict URL/IDNA normalization can supply these in a future adapter.
    if not isinstance(value, str) or not value or len(value) > 253:
        raise ValueError("Supply a canonical ASCII hostname.")
    labels = value.split(".")
    if value != value.lower() or len(labels) < 2 or labels[-1].isdigit() or not all(
        re.fullmatch(r"[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?", label) for label in labels
    ):
        raise ValueError("Supply a canonical ASCII hostname.")
    return features.normalize_domain(value)


def metrics(labels, scores):
    predicted = (np.asarray(scores) >= THRESHOLD).astype(int)
    tn, fp, fn, tp = confusion_matrix(labels, predicted, labels=[0, 1]).ravel()
    return {"accuracy": float(accuracy_score(labels, predicted)), "precision": float(precision_score(labels, predicted, zero_division=0)),
            "recall": float(recall_score(labels, predicted, zero_division=0)), "f1": float(f1_score(labels, predicted, zero_division=0)),
            "roc_auc": float(roc_auc_score(labels, scores)), "true_negatives": int(tn), "false_positives": int(fp),
            "false_negatives": int(fn), "true_positives": int(tp), "total": len(predicted)}


def check_configuration(config):
    expected = {"model": "linear_svm", "ngram_range": [2, 6], "min_df": 1, "C": 0.5,
                "uses_lexical_features": True, "threshold": THRESHOLD}
    if any(config.get(key) != value for key, value in expected.items()):
        raise ValueError("Configuration differs from the frozen experiment.")


def validate_payload(vectorizer, classifier, manifest):
    if not isinstance(classifier, LinearSVC) or list(classifier.classes_) != [0, 1]:
        raise ValueError("Positive-margin class must be gambling label 1.")
    if (classifier.C != 0.5 or classifier.class_weight != "balanced" or classifier.random_state != 42
            or classifier.max_iter != 10000 or vectorizer.analyzer != "char" or vectorizer.ngram_range != (2, 6)
            or vectorizer.min_df != 1 or vectorizer.sublinear_tf is not True or vectorizer.norm != "l2"):
        raise ValueError("Artifact estimator parameters differ from the frozen experiment.")
    lexical_size = features.build_lexical_matrix(["example.com"]).shape[1]
    tfidf_size = vectorizer.transform(["example.com"]).shape[1]
    if (lexical_size != 25 or manifest.get("lexical_features") != lexical_size
            or manifest.get("tfidf_features") != tfidf_size or manifest.get("total_features") != tfidf_size + lexical_size
            or classifier.n_features_in_ != tfidf_size + lexical_size):
        raise ValueError("Saved feature order/dimensions are incompatible.")


class FrozenSVMShadow:
    """Load once for offline comparison; exposes margins/classification only."""
    def __init__(self, vectorizer, classifier, manifest):
        validate_payload(vectorizer, classifier, manifest)
        self.vectorizer, self.classifier, self.manifest = vectorizer, classifier, manifest

    @classmethod
    def load(cls, directory, *, expected_manifest_sha256):
        directory = Path(directory)
        manifest_path = directory / "manifest.json"
        if not re.fullmatch(r"[0-9a-f]{64}", expected_manifest_sha256) or manifest_path.stat().st_size > 2_000_000 or digest(manifest_path) != expected_manifest_sha256:
            raise ValueError("Manifest failed its external integrity check.")
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        check_configuration(manifest["configuration"])
        if (manifest.get("format") != FORMAT or manifest.get("purpose") != "offline_shadow"
                or manifest.get("production_approved") is not False or manifest.get("calibrated_probability") is not False
                or manifest.get("classes") != [0, 1] or manifest.get("environment") != environment()
                or manifest.get("feature_sha256") != digest(features.__file__)
                or manifest.get("adapter_sha256") != digest(__file__) or manifest.get("model_file") != "model.joblib"):
            raise ValueError("Artifact code, environment or purpose is incompatible.")
        model_path = directory / "model.joblib"
        if model_path.stat().st_size > 50_000_000 or digest(model_path) != manifest["model_sha256"]:
            raise ValueError("Model failed its integrity check.")
        # No untrusted or remote pickle input. Check bytes before deserialization.
        payload = joblib.load(model_path)
        return cls(payload["vectorizer"], payload["classifier"], manifest)

    def decision_function(self, domains):
        hosts = [canonical_host(value) for value in domains]
        if not hosts:
            return np.asarray([], dtype=float)
        matrix = hstack([self.vectorizer.transform(hosts), features.build_lexical_matrix(hosts)], format="csr")
        scores = np.asarray(self.classifier.decision_function(matrix), dtype=float)
        if not np.isfinite(scores).all():
            raise ValueError("Inference returned a non-finite margin.")
        return scores

    def classify(self, domains):
        scores = self.decision_function(domains)
        return [{"domain": canonical_host(domain), "decision_score": float(score), "score_type": "svm_margin",
                 "predicted_label": int(score >= THRESHOLD), "classification_threshold": THRESHOLD,
                 "automatic_blocking_approved": False} for domain, score in zip(domains, scores)]


def export_shadow(output, *, ml_root=ML_ROOT):
    """Reproduce the fixed experiment, fitting exclusively original train rows."""
    output, ml_root = Path(output), Path(ml_root)
    if output.exists():
        raise ValueError("Use a new artifact directory; do not overwrite prior evidence.")
    paths = {"configuration": ml_root / CONFIG,
             **{name: ml_root / f"data/processed/splits/baseline_{name}.csv" for name in ("train", "validation", "test")},
             "historical_metrics": ml_root / "reports/optimized_svm_historical_test_metrics.json",
             "historical_predictions": ml_root / "reports/optimized_svm_historical_test_predictions.csv"}
    hashes = {name: digest(path) for name, path in paths.items()}
    config = json.loads(paths["configuration"].read_text(encoding="utf-8"))
    check_configuration(config)
    splits = {name: features.load_split(paths[name]) for name in ("train", "validation", "test")}
    if [len(splits[name]) for name in splits] != [507, 169, 170]:
        raise ValueError("Historical split sizes changed.")
    groups = []
    hosts = []
    for split in splits.values():
        actual = [EXTRACT(domain).top_domain_under_public_suffix or domain for domain in split.domain]
        if actual != list(split.domain_family) or split.domain.duplicated().any():
            raise ValueError("Saved domain families or unique membership are inconsistent.")
        groups.append(set(actual))
        hosts.append(set(split.domain))
    if any(groups[a] & groups[b] or hosts[a] & hosts[b] for a, b in ((0, 1), (0, 2), (1, 2))):
        raise ValueError("Historical train/validation/test leakage detected.")
    x_train, x_validation, vectorizer = features.build_feature_matrices(
        splits["train"].domain, splits["validation"].domain, (2, 6), 1)
    classifier = LinearSVC(C=0.5, class_weight="balanced", random_state=42, max_iter=10000)
    with threadpool_limits(limits=1):
        classifier.fit(x_train, splits["train"].label)
    validation_metrics = metrics(splits["validation"].label, classifier.decision_function(x_validation))
    if not np.isclose(validation_metrics["accuracy"], config["validation_accuracy"], atol=1e-8, rtol=0):
        raise ValueError("Frozen validation accuracy did not reproduce; export aborted.")
    x_test = hstack([vectorizer.transform(splits["test"].domain), features.build_lexical_matrix(splits["test"].domain)], format="csr")
    scores = classifier.decision_function(x_test)
    test_metrics = metrics(splits["test"].label, scores)
    saved = json.loads(paths["historical_metrics"].read_text(encoding="utf-8"))
    for name, values in (("validation_reproduction", validation_metrics), ("test_metrics", test_metrics)):
        if any(not np.isclose(value, saved[name][key], atol=1e-8, rtol=0) for key, value in values.items()):
            raise ValueError("Historical metrics did not reproduce; export aborted.")
    predictions = features.pd.read_csv(paths["historical_predictions"])
    if list(predictions.domain) != list(splits["test"].domain) or list(predictions.label) != list(splits["test"].label):
        raise ValueError("Historical prediction membership changed.")
    if not np.allclose(scores, predictions.svm_decision_score, atol=1e-6, rtol=0):
        raise ValueError("Historical margins did not reproduce; export aborted.")
    if not np.array_equal(scores >= THRESHOLD, predictions.predicted_label.astype(bool)):
        raise ValueError("Historical classification decisions did not reproduce.")
    if hashes != {name: digest(path) for name, path in paths.items()}:
        raise ValueError("Input files changed during export.")
    output.mkdir(parents=True)
    joblib.dump({"vectorizer": vectorizer, "classifier": classifier}, output / "model.joblib")
    manifest = {"format": FORMAT, "purpose": "offline_shadow", "production_approved": False, "calibrated_probability": False,
                "model_file": "model.joblib", "model_sha256": digest(output / "model.joblib"), "configuration": config,
                "classes": [int(v) for v in classifier.classes_], "feature_sha256": digest(features.__file__), "adapter_sha256": digest(__file__),
                "environment": environment(), "lexical_features": 25, "tfidf_features": x_train.shape[1] - 25, "total_features": x_train.shape[1],
                "inputs": {name: {"path": path.relative_to(ml_root).as_posix(), "sha256": hashes[name]} for name, path in paths.items()},
                "fit_split": "train_only_507", "independent_new_holdout": False, "validation_metrics": validation_metrics,
                "historical_test_metrics": test_metrics, "max_saved_margin_difference": float(np.max(np.abs(scores - predictions.svm_decision_score)))}
    json_write(output / "manifest.json", manifest)
    anchor = digest(output / "manifest.json")
    loaded = FrozenSVMShadow.load(output, expected_manifest_sha256=anchor)
    if not np.array_equal(loaded.decision_function(list(splits["test"].domain)), scores):
        raise ValueError("Serialized artifact prediction round trip failed.")
    return manifest, anchor


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    exporting = commands.add_parser("export")
    exporting.add_argument("--output", type=Path, required=True)
    predicting = commands.add_parser("predict")
    predicting.add_argument("--artifact", type=Path, required=True)
    predicting.add_argument("--manifest-sha256", required=True)
    predicting.add_argument("domains", nargs="+")
    args = parser.parse_args()
    if args.command == "export":
        manifest, anchor = export_shadow(args.output)
        print(json.dumps({"purpose": manifest["purpose"], "manifest_sha256": anchor, "feature_dimensions": manifest["total_features"],
                          "validation": manifest["validation_metrics"], "historical_test": manifest["historical_test_metrics"]}, indent=2))
    else:
        model = FrozenSVMShadow.load(args.artifact, expected_manifest_sha256=args.manifest_sha256)
        print(json.dumps(model.classify(args.domains), indent=2))


if __name__ == "__main__":
    main()
