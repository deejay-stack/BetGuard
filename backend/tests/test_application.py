"""Software fixtures only, never claimed as real capstone observations."""
from concurrent.futures import Future, TimeoutError
import json
from unittest.mock import MagicMock, patch

from fastapi.testclient import TestClient
import pytest
from pydantic import ValidationError

from app.core.config import ConfigurationError
from app.main import app
from app.schemas.application import AppMetadata, enough_metadata, metadata_text
from app.services.application_service import AppMetadataService
from app.services.model_service import InferenceUnavailable, ModelService


def metadata(**overrides):
    return {"app_name": "Software fixture", "package_name": "test.fixture",
            "description": "Public description of a software test fixture only.", **overrides}


@pytest.fixture
def client():
    with patch("app.main.make_engine", side_effect=ConfigurationError("test")), \
            patch("app.main.ModelService.from_environment", return_value=ModelService()), \
            patch("app.main.AppMetadataService.from_environment", return_value=AppMetadataService()), \
            patch("app.main.load_runtime", return_value=None):
        with TestClient(app) as value:
            yield value


def test_missing_app_model_does_not_classify_with_domain_model(client):
    with patch.object(app.state.model, "predict") as domain:
        response = client.post("/v1/apps/check", json=metadata())
    assert response.status_code == 200
    assert response.json()["classification"] == "unknown"
    assert response.json()["reason"] == "app_model_unavailable"
    assert response.json()["enforcement"] == "dns_network_only"
    assert response.headers["cache-control"] == "no-store"
    domain.assert_not_called()
    assert client.get("/health/apps").json()["ready"] is False


def test_name_and_permissions_alone_are_not_a_gambling_label(client):
    response = client.post("/v1/apps/check", json=metadata(description="", app_name="Casino", permissions=["android.permission.INTERNET"]))
    assert response.json()["reason"] == "insufficient_metadata"
    assert response.json()["classification"] == "unknown"


@pytest.mark.parametrize("overrides", [
    {"app_name": " "}, {"package_name": "https://example.com"}, {"description": "x" * 6001},
    {"reviews": ["x" * 1001]}, {"keywords": ["word"] * 41}, {"student_name": "PRIVATE_SENTINEL"},
    {"permissions": ["permission"] * 151},
])
def test_validation_does_not_echo_sensitive_inputs(client, overrides):
    response = client.post("/v1/apps/check", json=metadata(**overrides))
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "invalid_app_metadata"
    assert "PRIVATE_SENTINEL" not in response.text


def test_served_app_prediction_is_distinct_and_versioned(client):
    with patch.object(app.state.app_metadata_model, "check", return_value={
        "classification": "gambling", "source": "app_metadata_model", "reason": "model_prediction",
        "explanation": "Test prediction", "model_version": "test-only",
    }):
        result = client.post("/v1/apps/check", json=metadata()).json()
    assert result["source"] == "app_metadata_model"
    assert result["model_version"] == "test-only"
    assert "confidence" not in result


def test_worker_timeout_keeps_app_inference_bounded():
    future = Future()
    executor = MagicMock()
    executor.submit.return_value = future
    service = AppMetadataService("available", executor, "test")
    with patch.object(future, "result", side_effect=TimeoutError):
        with pytest.raises(InferenceUnavailable): service.check(AppMetadata(**metadata()))
    with pytest.raises(InferenceUnavailable, match="busy"): service.check(AppMetadata(**metadata()))
    assert executor.submit.call_count == 1
    future.set_result({"classification": "unknown"})


def test_features_include_scope_fields_but_exclude_package_identifier():
    value = AppMetadata(**metadata(keywords=["fixture"], permissions=["permission.INTERNET"], reviews=["Public fixture review"]))
    text = metadata_text(value)
    assert "test.fixture" not in text
    assert "Public fixture review" in text and "permission.INTERNET" in text
    assert enough_metadata(value)


def observation(index):
    gambling = bool(index % 2)
    return {**metadata(app_name=f"Fixture {index}", package_name=f"test.fixture{index}",
                      description=("Synthetic real money wagering casino fixture for software tests only." if gambling else
                                   "Synthetic educational reading library fixture without wagering for software tests only.")),
            "record_id": f"test-{index}", "classification": "gambling" if gambling else "non_gambling",
            "family_id": f"fixture-family-{index // 2}", "family_evidence": "Related synthetic software test pair",
            "source_uri": "test://fixture", "license": "test-only", "license_uri": "test://license",
            "usage_allowed": True, "review_status": "reviewed", "reviewed_by": "test-suite",
            "label_evidence": "Artificial fixture; never a real application.", "collected_at": "2026-01-01T00:00:00Z",
            "reviewed_at": "2026-01-02T00:00:00Z", "synthetic": True}


def test_app_research_preserves_holdout_and_rejects_fixture_deployment(tmp_path):
    pytest.importorskip("skops")
    from app.ml.application_artifacts import load_application_artifact, sha256
    from ml_tools.application import compare, export
    dataset = tmp_path / "fixtures.jsonl"
    dataset.write_text("\n".join(json.dumps(observation(i)) for i in range(60)))
    with pytest.raises(ValueError, match="Synthetic"): compare(dataset, tmp_path / "bad")
    run = tmp_path / "software-run"
    report = compare(dataset, run, software_test=True, minimum=2)
    assert set(report["results"]) == {"svm", "random_forest", "logistic_regression"}
    assert report["development_rows"] == 48 and report["test_rows"] == 12
    split = json.loads((run / "split.json").read_text())
    assert not {r["group"] for r in split["development"]} & {r["group"] for r in split["test"]}
    for result in report["results"].values():
        assert "true_skill_statistic" in result["held_out"]
        assert "specificity" in result["held_out"]
    with pytest.raises(ValueError): load_application_artifact(run, sha256(run / "manifest.json"))
    with pytest.raises(ValueError): export(run, tmp_path / "release", "test", "Software fixture must not deploy.")
    with pytest.raises(FileExistsError): compare(dataset, run, software_test=True, minimum=2)


def test_app_provenance_requires_valid_dates_and_genuine_boolean():
    from ml_tools.application import AppObservation
    with pytest.raises(ValidationError): AppObservation(**{**observation(1), "usage_allowed": "true"})
    with pytest.raises(ValidationError): AppObservation(**{**observation(1), "reviewed_at": "2025-01-01T00:00:00Z"})


def test_experts_need_matching_blinded_cases_and_compute_paired_counts(tmp_path):
    from ml_tools.application import compare_experts
    predicted = tmp_path / "predictions.json"
    experts = tmp_path / "experts.jsonl"
    predicted.write_text(json.dumps([{"record_id": "a", "truth": 0, "prediction": 1}, {"record_id": "b", "truth": 1, "prediction": 1}]))
    rows = [{"record_id": "a", "label": 0, "reviewed_by": "test", "blinded_to_model": True},
            {"record_id": "b", "label": 1, "reviewed_by": "test", "blinded_to_model": True}]
    experts.write_text("\n".join(map(json.dumps, rows)))
    result = compare_experts(predicted, experts)
    assert result["model"]["accuracy"] == .5 and result["expert"]["accuracy"] == 1
    assert result["mcnemar_discordant"]["expert_correct_model_wrong"] == 1
    rows[0]["blinded_to_model"] = False
    experts.write_text("\n".join(map(json.dumps, rows)))
    with pytest.raises(ValueError): compare_experts(predicted, experts)


def test_pilot_requires_consent_matching_phases_and_does_not_invent_denominators(tmp_path):
    from ml_tools.capstone import pilot_summary
    file = tmp_path / "pilot.jsonl"
    rows = [{"participant_code": "P-001", "phase": phase, "consented": True,
             "gambling_attempts": 0, "accessible_gambling_attempts": 0} for phase in ("baseline", "protected")]
    file.write_text("\n".join(map(json.dumps, rows)))
    report = pilot_summary(file)
    assert report["baseline"]["accessible_rate"] is None
    assert report["accessible_rate_change_percentage_points"] is None
    rows[0]["consented"] = False
    file.write_text("\n".join(map(json.dumps, rows)))
    with pytest.raises(ValueError): pilot_summary(file)
