"""Synthetic data here tests software only. It is never deployable training data."""
from concurrent.futures import Future, ProcessPoolExecutor, TimeoutError
from multiprocessing import get_context
from dataclasses import asdict
import json
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

pytest.importorskip("sklearn", reason="Optional ML development dependencies are not installed")
pytest.importorskip("skops")
pytest.importorskip("tldextract")
import numpy as np
from fastapi.testclient import TestClient
from scipy.sparse import issparse

from app.schemas.catalog import normalize_hostname
from app.core.config import ConfigurationError
from app.main import app
from app.ml import POLICY_VERSION
from app.ml.artifacts import load_artifact
from ml_tools.data import Observation, audit, digest, group_records, json_write, registrable_domain, usable_data
from app.ml.features import scores
from ml_tools.features import pipelines
from ml_tools.protocol import TrainingConfig, assert_no_leakage, decisions, split_records, tune_thresholds
from ml_tools.workflow import create_split, evaluate, export, load_split, train
from app.services.model_service import InferenceUnavailable, ModelService, _predict, _ready


def fixture_worker_initialize(directory, trusted_hash):
    """Test-only initializer: never used by application startup/deployment."""
    from pathlib import Path
    from threadpoolctl import threadpool_limits
    import app.services.model_service as worker
    worker._thread_limit = threadpool_limits(limits=1)
    worker._pipeline, worker._manifest = load_artifact(Path(directory), expected_manifest_sha256=trusted_hash, deployment=False)


def observation(index=0, **changes):
    return {"record_id": f"fixture-{index}", "hostname": f"casino-fixture-{index}.com",
            "classification": "gambling", "label_provenance": "software fixture only",
            "review_status": "reviewed", "reviewed_at": "2026-01-01T00:00:00Z",
            "source_uri": "test://fixture", "collected_at": "2025-12-01T00:00:00Z",
            "license": "test-only", "license_uri": "test://terms", "usage_allowed": True,
            "reviewed_by": "test-suite", "evidence": "Synthetic fixture, not a real site label.",
            "policy_version": POLICY_VERSION, "synthetic": True, **changes}


@pytest.fixture
def dataset(tmp_path):
    rows = [observation(i, hostname=f"casino-fixture-{i}.com" if i % 2 else f"library-fixture-{i}.org",
                        classification="gambling" if i % 2 else "non_gambling") for i in range(100)]
    path = tmp_path / "software-fixtures.jsonl"
    path.write_text("\n".join(json.dumps(row) for row in rows), encoding="utf-8")
    return path


@pytest.mark.parametrize("value,expected", [
    ("HTTPS://a.EXAMPLE.co.uk./path", "example.co.uk"),
    ("x.y.example.com.au", "example.com.au"),
    ("a.tenant.blogspot.com", "tenant.blogspot.com"),
    ("b.tenant.github.io", "tenant.github.io"),
    ("https://bücher.de", "xn--bcher-kva.de"),
])
def test_normalization_and_psl(value, expected):
    assert registrable_domain(value) == expected
    assert normalize_hostname(normalize_hostname(value)) == normalize_hostname(value)


@pytest.mark.parametrize("value", ["localhost", "127.0.0.1", "co.uk", "host.invalid", "user:secret@example.com"])
def test_ineligible_public_suffix_or_input(value):
    with pytest.raises(ValueError):
        registrable_domain(value)


def test_aliases_and_subdomains_are_transitively_grouped():
    rows = [Observation.model_validate(observation(0, hostname="one.example.co.uk", related_group_id="operator-a", related_group_evidence="reviewed ownership evidence")),
            Observation.model_validate(observation(1, hostname="two.example.co.uk")),
            Observation.model_validate(observation(2, hostname="other-brand.net", related_group_id="operator-a", related_group_evidence="reviewed alias evidence")),
            Observation.model_validate(observation(3, hostname="unrelated.org"))]
    groups = group_records(rows)
    assert groups[rows[0].record_id] == groups[rows[1].record_id] == groups[rows[2].record_id]
    assert groups[rows[0].record_id] != groups[rows[3].record_id]


@pytest.mark.parametrize("changes", [
    {"reviewed_by": None}, {"usage_allowed": "not-a-boolean"}, {"license": " "},
    {"collected_at": "2999-01-01T00:00:00Z"}, {"collected_at": "2025-01-01T00:00:00"},
    {"policy_version": "different"}, {"related_group_id": "operator-with-no-evidence"},
    {"classification": "safe"}, {"confidence": .95},
])
def test_review_metadata_validation(changes):
    with pytest.raises(ValueError):
        Observation.model_validate(observation(**changes))


def test_audit_actual_counts_duplicates_conflicts_and_exclusion(tmp_path):
    rows = [observation(), observation(1, hostname="HTTPS://CASINO-FIXTURE-0.COM/path"),
            observation(2, hostname="casino-fixture-0.com", classification="non_gambling"),
            observation(3, classification="unknown"),
            observation(4, review_status="pending", reviewed_at=None), observation(5, usage_allowed=False)]
    path = tmp_path / "audit.jsonl"
    path.write_text("\n".join(json.dumps(row) for row in rows) + '\n{"hostname":"missing-fields.com"}', encoding="utf-8")
    report, eligible, _ = audit(path)
    assert report["rows"] == 7 and report["invalid_rows"] == 1
    assert report["duplicate_rows"] == 2 and len(report["conflicting_hostnames"]) == 1
    assert report["supervised_unique_rows"] == 0 and not eligible
    assert report["missing_fields"]["classification"] == 1
    with pytest.raises(ValueError):
        usable_data(path, software_test=True)


def test_synthetic_data_never_enters_normal_training(dataset):
    with pytest.raises(ValueError, match="Synthetic"):
        usable_data(dataset)


def test_split_deterministic_group_disjoint_and_immutable(dataset, tmp_path):
    config = TrainingConfig(min_class_per_split=2, trees=4, max_features=200)
    _, rows, groups = usable_data(dataset, software_test=True)
    first = split_records(rows, groups, config)
    assert first == split_records(rows, groups, config)
    assert_no_leakage(first)
    first["test"].append(first["train"][0])
    with pytest.raises(ValueError, match="leakage"):
        assert_no_leakage(first)
    path = tmp_path / "split.json"
    create_split(dataset, path, config, software_test=True)
    with pytest.raises(ValueError, match="already exists"):
        create_split(dataset, path, config, software_test=True)
    modified = json.loads(path.read_text())
    modified["train"][0]["group"] = "altered"
    json_write(path, modified)
    with pytest.raises(ValueError, match="altered"):
        load_split(dataset, path, software_test=True)


def test_features_fit_only_on_train_and_remain_sparse():
    hosts = ["casino-a.com", "library-a.org", "casino-b.com", "library-b.org"]
    model = pipelines(max_features=200, trees=2)["logistic_regression"]
    model.fit(hosts, [1, 0, 1, 0])
    vocabulary = model.named_steps["features"].transformer_list[0][1].vocabulary_.copy()
    matrix = model.named_steps["features"].transform(["zzzzuniquevalidationzzzz.net"])
    assert issparse(matrix)
    assert vocabulary == model.named_steps["features"].transformer_list[0][1].vocabulary_
    assert "zzz" not in vocabulary


def test_abstention_is_not_a_probability_or_forced_binary_result():
    config = TrainingConfig(min_class_per_split=1, min_decisions=1)
    thresholds = tune_thresholds([0, 0, 1, 1], [-3, -2, 2, 3], config)
    assert list(decisions([-3, 0, 3], thresholds)) == [0, -1, 1]
    impossible = tune_thresholds([0, 1], [0, 0], config)
    assert list(decisions([0], impossible)) == [-1]


def test_three_pipeline_workflow_and_trusted_roundtrip(dataset, tmp_path):
    split = tmp_path / "split.json"
    config = TrainingConfig(min_class_per_split=2, min_decisions=1, max_features=200, trees=4)
    create_split(dataset, split, config, software_test=True)
    run = tmp_path / "software-test-run"
    summary = train(dataset, split, run, software_test=True)
    assert summary["test_evaluated"] is False
    assert set(summary["results"]) == {"logistic_regression", "svm", "random_forest"}
    for name in summary["results"]:
        directory = run / name
        trusted = digest(directory / "manifest.json")
        first, metadata = load_artifact(directory, expected_manifest_sha256=trusted, deployment=False)
        second, _ = load_artifact(directory, expected_manifest_sha256=trusted, deployment=False)
        np.testing.assert_array_equal(scores(first, ["fixture.example.com"]), scores(second, ["fixture.example.com"]))
        assert metadata["purpose"] == "software_test"
        assert "test" not in metadata["evaluation"]
        with pytest.raises(ValueError, match="approved real-data"):
            load_artifact(directory, expected_manifest_sha256=trusted)
        with pytest.raises(ValueError, match="trusted digest"):
            load_artifact(directory, expected_manifest_sha256="0" * 64, deployment=False)
    report = evaluate(dataset, run, software_test=True)
    assert report["selected_before_test"] == summary["selected"]
    assert all("binary_confusion_matrix" in entry["test"] for entry in report["results"].values())
    with pytest.raises(ValueError, match="already started"):
        evaluate(dataset, run, software_test=True)
    with pytest.raises(ValueError):
        export(run, tmp_path / "must-not-export", reviewer="test", note="synthetic")
    manifest = run / "svm" / "manifest.json"
    value = json.loads(manifest.read_text())
    value["environment"]["scikit-learn"] = "incompatible"
    json_write(manifest, value)
    with pytest.raises(ValueError, match="incompatible"):
        load_artifact(manifest.parent, expected_manifest_sha256=digest(manifest), deployment=False)
    # Exercise the real spawned-worker inference path without marking fixtures
    # deployable or adding a test-mode switch to application startup.
    directory = run / "logistic_regression"
    with ProcessPoolExecutor(max_workers=1, mp_context=get_context("spawn"), initializer=fixture_worker_initialize,
                             initargs=(str(directory), digest(directory / "manifest.json"))) as executor:
        version = executor.submit(_ready).result(timeout=30)
        service = ModelService("available", executor, version)
        assert service.predict("fixture.example.com")["classification"] in {"gambling", "non_gambling", "unknown"}
        assert service.predict("host.invalid")["reason"] == "model_ineligible"
    payload = directory / "model.skops"
    payload.write_bytes(payload.read_bytes() + b"tampered-test-only")
    with pytest.raises(ValueError, match="integrity"):
        load_artifact(directory, expected_manifest_sha256=digest(directory / "manifest.json"), deployment=False)


