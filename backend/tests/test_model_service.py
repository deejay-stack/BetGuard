"""Optional model behavior and API contract; no ML dependencies or real database."""
from concurrent.futures import Future, TimeoutError
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import MagicMock, patch
import pytest
from fastapi.testclient import TestClient
from app.core.config import ConfigurationError
from app.main import app
from app.services.model_service import InferenceUnavailable, ModelService


def test_missing_model_does_not_start_workers(monkeypatch):
    monkeypatch.delenv("MODEL_ARTIFACT_DIR", raising=False)
    monkeypatch.delenv("MODEL_MANIFEST_SHA256", raising=False)
    with patch("app.services.model_service.ProcessPoolExecutor") as pool:
        service = ModelService.from_environment()
        assert service.status == "absent" and service.predict("example.com") is None
        pool.assert_not_called()


def test_timeout_retains_capacity_until_work_actually_finishes():
    future = Future()
    executor = MagicMock()
    executor.submit.return_value = future
    service = ModelService("available", executor, "fixture")
    with patch.object(future, "result", side_effect=TimeoutError):
        with pytest.raises(InferenceUnavailable):
            service.predict("example.com")
    with pytest.raises(InferenceUnavailable, match="busy"):
        service.predict("example.org")
    assert executor.submit.call_count == 1
    future.set_result({"classification": "unknown", "reason": "model_abstained"})
    assert service.slot.acquire(blocking=False)
    service.slot.release()


@pytest.fixture
def model_client():
    with patch("app.main.make_engine", side_effect=ConfigurationError("test")), patch("app.main.ModelService.from_environment", return_value=ModelService()), patch("app.main.load_runtime", return_value=None):
        with TestClient(app) as client:
            app.state.engine = MagicMock()
            yield client


@pytest.mark.parametrize("classification", ["gambling", "non_gambling", "unknown"])
def test_reviewed_catalog_including_unknown_takes_precedence(model_client, classification):
    entry = SimpleNamespace(review_status="reviewed", reviewed_at=datetime(2026, 1, 1, tzinfo=timezone.utc), classification=classification, label_provenance="test review")
    with patch("app.services.catalog_service.Session") as session, patch.object(app.state.model, "predict") as predict:
        session.return_value.__enter__.return_value.get.return_value = entry
        response = model_client.post("/v1/check", json={"hostname": "example.com"})
        assert response.json()["source"] == "reviewed_catalog"
        assert response.json()["classification"] == classification
        predict.assert_not_called()
        session.return_value.__enter__.return_value.add.assert_not_called()


@pytest.mark.parametrize("status", ["absent", "unsuitable"])
def test_no_suitable_model_returns_honest_unknown(model_client, status):
    app.state.model.status = status
    with patch("app.services.catalog_service.Session") as session:
        session.return_value.__enter__.return_value.get.return_value = None
        response = model_client.post("/v1/check", json={"hostname": "example.com"})
        assert response.status_code == 200
        assert response.json()["source"] == "unavailable"
        assert response.json()["classification"] == "unknown"
        assert "model_version" not in response.json()


@pytest.mark.parametrize("classification,reason", [("gambling", "model_prediction"), ("unknown", "model_abstained")])
def test_model_source_and_abstention(model_client, classification, reason):
    app.state.model.version = "test-version"
    with patch("app.services.catalog_service.Session") as session, patch.object(app.state.model, "predict", return_value={"classification": classification, "reason": reason}):
        session.return_value.__enter__.return_value.get.return_value = None
        data = model_client.post("/v1/check", json={"hostname": "example.com"}).json()
        assert data["source"] == "model" and data["model_version"] == "test-version"
        assert data["classification"] == classification and "calibrated_probability" not in data


def test_database_failure_is_not_hidden_by_model(model_client):
    app.state.engine = None
    with patch.object(app.state.model, "predict") as predict:
        response = model_client.post("/v1/check", json={"hostname": "example.com"})
        assert response.status_code == 503 and response.json()["source"] == "unavailable"
        predict.assert_not_called()


def test_model_worker_errors_are_unavailable_not_unknown(model_client):
    with patch("app.services.catalog_service.Session") as session, patch.object(app.state.model, "predict", side_effect=InferenceUnavailable("test")):
        session.return_value.__enter__.return_value.get.return_value = None
        response = model_client.post("/v1/check", json={"hostname": "example.com"})
        assert response.status_code == 503
        assert response.json()["error"]["code"] == "model_unavailable"
        assert "classification" not in response.json()


def test_broken_worker_stays_an_error_on_subsequent_checks():
    executor = MagicMock()
    executor.submit.side_effect = RuntimeError("worker failed")
    service = ModelService("available", executor, "fixture")
    for _ in range(2):
        with pytest.raises(InferenceUnavailable):
            service.predict("example.com")
    assert service.status == "failed"
    assert executor.submit.call_count == 1


def test_partial_model_configuration_is_unsuitable_without_loading(monkeypatch):
    monkeypatch.setenv("MODEL_ARTIFACT_DIR", "test-only-placeholder")
    monkeypatch.delenv("MODEL_MANIFEST_SHA256", raising=False)
    with patch("app.services.model_service.ProcessPoolExecutor") as pool:
        assert ModelService.from_environment().status == "unsuitable"
        pool.assert_not_called()


@pytest.mark.parametrize("status", ["absent", "unsuitable"])
def test_database_readiness_does_not_require_model(model_client, status):
    app.state.model.status = status
    connection = app.state.engine.connect.return_value.__enter__.return_value
    connection.execute.return_value.scalars.return_value.all.return_value = ["0001_catalog"]
    response = model_client.get("/health/ready")
    assert response.status_code == 200
    assert response.json() == {"status": "ready", "model": status}


def test_missing_artifact_files_do_not_spawn_worker(monkeypatch, tmp_path):
    monkeypatch.setenv("MODEL_ARTIFACT_DIR", str(tmp_path))
    monkeypatch.setenv("MODEL_MANIFEST_SHA256", "0" * 64)
    with patch("app.services.model_service.ProcessPoolExecutor") as pool:
        assert ModelService.from_environment().status == "unsuitable"
        pool.assert_not_called()
