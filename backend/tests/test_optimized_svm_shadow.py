"""Frozen artifact gates and offline adapter regressions; no live wagering/DNS."""
import copy
import json
from pathlib import Path
import shutil
from unittest.mock import patch

import numpy as np
import pytest

from betguard_runtime import optimized_svm_shadow as shadow


@pytest.fixture(scope="module")
def artifact(tmp_path_factory):
    directory = tmp_path_factory.mktemp("svm-shadow") / "artifact"
    manifest, anchor = shadow.export_shadow(directory)
    return directory, manifest, anchor


def test_reproduces_frozen_historical_metrics_without_changing_inputs(artifact):
    directory, manifest, anchor = artifact
    assert manifest["fit_split"] == "train_only_507"
    assert manifest["validation_metrics"]["accuracy"] == pytest.approx(158 / 169)
    assert manifest["historical_test_metrics"]["accuracy"] == pytest.approx(157 / 170)
    assert manifest["historical_test_metrics"]["false_positives"] == 11
    assert manifest["historical_test_metrics"]["false_negatives"] == 2
    assert manifest["lexical_features"] == 25
    assert manifest["total_features"] == 14076
    assert manifest["max_saved_margin_difference"] <= 1e-6
    for item in manifest["inputs"].values():
        assert shadow.digest(shadow.ML_ROOT / item["path"]) == item["sha256"]
    with pytest.raises(ValueError, match="new artifact directory"):
        shadow.export_shadow(directory)
    assert shadow.digest(directory / "manifest.json") == anchor


def test_load_once_and_deterministic_threshold_orientation(artifact):
    directory, _, anchor = artifact
    with patch.object(shadow.joblib, "load", wraps=shadow.joblib.load) as loading:
        model = shadow.FrozenSVMShadow.load(directory, expected_manifest_sha256=anchor)
        domains = ["wikipedia.org", "stake.com", "alphabet.com", "up.edu.ph"]
        first, second = model.classify(domains), model.classify(domains)
        assert first == second
        assert loading.call_count == 1
        for row in first:
            assert row["predicted_label"] == int(row["decision_score"] >= shadow.THRESHOLD)
            assert row["score_type"] == "svm_margin"
            assert row["automatic_blocking_approved"] is False
            assert "gambling_probability" not in row and "ml_score" not in row
        assert model.classify([]) == []
        assert model.classify(["www.wikipedia.org"])[0]["decision_score"] == first[0]["decision_score"]


@pytest.mark.parametrize("value", [None, "", "https://example.com/path", "https://[invalid", "user:secret@example.com", "localhost", "127.0.0.1", "example.com:443", "example..com", "-bad.com", "example.com.", "UP.EDU.PH", "bücher.example", "example.com\n", "a" * 64 + ".com"])
def test_rejects_noncanonical_or_malformed_shadow_input(artifact, value):
    directory, _, anchor = artifact
    model = shadow.FrozenSVMShadow.load(directory, expected_manifest_sha256=anchor)
    with pytest.raises(ValueError, match="canonical ASCII"):
        model.classify([value])


@pytest.mark.parametrize("kind", ["missing_model", "corrupt_model", "wrong_anchor", "environment", "feature_code", "adapter_code", "dimension", "threshold", "purpose", "classes"])
def test_artifact_failure_is_explicit_and_does_not_return_a_decision(artifact, tmp_path, kind):
    source, _, anchor = artifact
    directory = tmp_path / "copy"
    shutil.copytree(source, directory)
    path = directory / "manifest.json"
    manifest = json.loads(path.read_text())
    if kind == "missing_model":
        (directory / "model.joblib").unlink()
    elif kind == "corrupt_model":
        (directory / "model.joblib").write_bytes(b"corrupt pickle fixture")
    elif kind == "wrong_anchor":
        anchor = "0" * 64
    else:
        if kind == "environment":
            manifest["environment"]["scikit-learn"] = "incompatible"
        elif kind in {"feature_code", "adapter_code"}:
            manifest[kind.replace("_code", "_sha256")] = "0" * 64
        elif kind == "dimension":
            manifest["total_features"] += 1
        elif kind == "threshold":
            manifest["configuration"]["threshold"] = 0.512117
        elif kind == "purpose":
            manifest["production_approved"] = True
        elif kind == "classes":
            manifest["classes"] = [1, 0]
        shadow.json_write(path, manifest)
        anchor = shadow.digest(path)
    with pytest.raises((ValueError, FileNotFoundError)):
        shadow.FrozenSVMShadow.load(directory, expected_manifest_sha256=anchor)


def test_invalid_hash_checked_before_deserializing(artifact):
    directory, _, _ = artifact
    with patch.object(shadow.joblib, "load") as loading:
        with pytest.raises(ValueError, match="integrity"):
            shadow.FrozenSVMShadow.load(directory, expected_manifest_sha256="0" * 64)
        loading.assert_not_called()


def test_nonfinite_margin_and_reversed_class_are_rejected(artifact):
    directory, manifest, anchor = artifact
    model = shadow.FrozenSVMShadow.load(directory, expected_manifest_sha256=anchor)
    with patch.object(model.classifier, "decision_function", return_value=np.array([np.nan])):
        with pytest.raises(ValueError, match="non-finite"):
            model.classify(["example.com"])
    classifier = copy.deepcopy(model.classifier)
    classifier.classes_ = np.array([1, 0])
    with pytest.raises(ValueError, match="class"):
        shadow.FrozenSVMShadow(model.vectorizer, classifier, manifest)


def test_production_selection_and_response_contract_remain_baseline():
    from betguard_runtime import decision_engine
    from app.schemas.domain import DomainDecision
    config = json.loads(decision_engine.DEPLOYMENT_CONFIG_FILE.read_text())
    assert config["model_name"] == "baseline"
    assert decision_engine.WARNING_THRESHOLD == 0.512117
    assert decision_engine.AUTO_BLOCK_THRESHOLD == 0.70
    # A raw negative SVM score still cannot accidentally enter the public API.
    with pytest.raises(ValueError):
        DomainDecision(domain="example.com", enforcement_action="ALLOW", intervention="NONE",
                       risk_status="low", decision_source="ml_low_risk", ml_score=-0.1)
