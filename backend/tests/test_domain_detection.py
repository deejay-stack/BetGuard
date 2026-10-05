"""HTTP integration, real frozen artifacts, lifecycle, and unavailable behavior."""
from concurrent.futures import ThreadPoolExecutor
from threading import Event
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from app.core.config import ConfigurationError
from app.main import app
from app.services.domain_service import load_runtime
from app.services.model_service import ModelService


@pytest.fixture(scope="module")
def runtime():
    # This integration suite intentionally requires the installed local runtime
    # and finalized artifacts. Never train, download blocklists, or edit lists.
    from betguard_runtime.runtime_service import BetGuardRuntime
    return BetGuardRuntime(verbose=False, use_user_lists=False)


@pytest.fixture
def client(runtime):
    runtime.clear_cache()
    with patch("app.main.make_engine", side_effect=ConfigurationError("test")), \
         patch("app.main.ModelService.from_environment", return_value=ModelService()), \
         patch("app.main.load_runtime", return_value=runtime) as loader:
        with TestClient(app) as client:
            yield client
        loader.assert_called_once_with()
        assert app.state.betguard_runtime is None


@pytest.mark.parametrize("hostname,action,intervention,source", [
    ("stake.com", "BLOCK", "BLOCK", "verified_gambling_blocklist"),
    ("wikipedia.org", "ALLOW", "NONE", "ml_low_risk"),
    ("microsoft.com", "ALLOW", "WARN", "ml_warning"),
])
def test_real_artifact_decisions(client, hostname, action, intervention, source):
    response = client.post("/v1/domain/check", json={"domain": hostname})
    assert response.status_code == 200
    result = response.json()["result"]
    assert (result["enforcement_action"], result["intervention"], result["decision_source"]) == (action, intervention, source)
    assert response.headers["Cache-Control"] == "no-store"
    assert "input" not in result


def test_normalization_cache_and_batch(client, runtime):
    values = ["stake.com", "www.stake.com", "https://stake.com", "https://www.stake.com/casino?token=private"]
    response = client.post("/v1/domain/check-batch", json={"domains": values})
    assert response.status_code == 200
    data = response.json()
    assert data["count"] == 4
    assert [r["cache_hit"] for r in data["results"]] == [False, True, True, True]
    assert all(r["domain"] == "stake.com" and r["enforcement_action"] == "BLOCK" for r in data["results"])
    assert "private" not in response.text
    status = client.get("/health/detection").json()
    assert status["ready"] and status["model_name"] == "baseline"
    assert status["gambling_blocklist_domains"] == len(runtime.gambling_lookup)
    assert status["cache_entries"] == 1
    assert "path" not in status and "model_file" not in status
    assert client.get("/health/live").json() == {"status": "ok"}
    assert client.get("/health/ready").status_code == 503
    assert client.post("/v1/check", json={"hostname": "stake.com"}).status_code == 503
    assert "/v1/domain/check-batch" in client.get("/openapi.json").json()["paths"]


@pytest.mark.parametrize("payload", [{"domains": []}, {"domains": ["stake.com"] * 101},
    {"domains": ["stake.com", "https://user:secret@example.com"]}, {"domains": [42]}])
def test_batch_validation_is_atomic(client, runtime, payload):
    with patch.object(runtime, "evaluate_many") as evaluate:
        response = client.post("/v1/domain/check-batch", json=payload)
        assert response.status_code == 422 and "secret" not in response.text
        evaluate.assert_not_called()


@pytest.mark.parametrize("payload", [{"domain": ""}, {"domain": "127.0.0.1"},
    {"domain": "https://user:secret@example.com"}, {"domain": "stake.com", "extra": True},
    {"domain": "a" * 2049}, {"domain": 123}])
def test_strict_requests(client, payload):
    response = client.post("/v1/domain/check", json=payload)
    assert response.status_code == 422 and "secret" not in response.text


def test_startup_failure_keeps_existing_app_running(caplog):
    from betguard_runtime import runtime_service
    with patch.object(runtime_service, "BetGuardRuntime", side_effect=FileNotFoundError("private-path")), \
         patch("app.main.make_engine", side_effect=ConfigurationError("test")), \
         patch("app.main.ModelService.from_environment", return_value=ModelService()):
        with TestClient(app) as client:
            assert client.get("/health/live").status_code == 200
            for path in ("/v1/domain/check", "/v1/domain/check-batch"):
                body = {"domain": "stake.com"} if path.endswith("/check") else {"domains": ["stake.com"]}
                response = client.post(path, json=body)
                assert response.status_code == 503
                assert "private-path" not in response.text
            assert client.get("/health/detection").status_code == 503
    assert "initialization failed" in caplog.text and "private-path" not in caplog.text


@pytest.mark.parametrize("result", [None, {"error": "private-data"},
    {"domain": "stake.com", "enforcement_action": "BLOCK", "intervention": "WARN"}])
def test_inference_errors_never_become_decisions(client, runtime, result):
    with patch.object(runtime, "evaluate", side_effect=RuntimeError("private-data") if result is None else None,
                      return_value=result):
        response = client.post("/v1/domain/check", json={"domain": "stake.com"})
        assert response.status_code == 503
        assert "private-data" not in response.text and "enforcement_action" not in response.text


def test_resource_paths_work_outside_ml(monkeypatch, tmp_path, runtime):
    from betguard_runtime import decision_engine
    from betguard_runtime.runtime_paths import resource_path
    monkeypatch.chdir(tmp_path)
    assert decision_engine.DEPLOYMENT_CONFIG_FILE.is_file()
    assert resource_path(runtime.model_config["model_file"]).is_file()
    assert resource_path("models\\baseline_domain_classifier.joblib") == resource_path("models/baseline_domain_classifier.joblib")
    model, config = decision_engine.load_model()
    assert config["model_name"] == "baseline"
    assert model.predict_proba(["wikipedia.org"])[0][1] < decision_engine.WARNING_THRESHOLD
    assert decision_engine.WARNING_THRESHOLD == 0.512117
    assert decision_engine.AUTO_BLOCK_THRESHOLD == 0.70


def test_shared_runtime_model_and_blocklist_load_once():
    from betguard_runtime import runtime_service
    with patch.object(runtime_service, "load_model", wraps=runtime_service.load_model) as model, \
         patch.object(runtime_service, "load_gambling_blocklist", wraps=runtime_service.load_gambling_blocklist) as blocklist, \
         patch("app.main.make_engine", side_effect=ConfigurationError("test")), \
         patch("app.main.ModelService.from_environment", return_value=ModelService()):
        with TestClient(app) as client:
            for _ in range(3):
                assert client.post("/v1/domain/check", json={"domain": "stake.com"}).status_code == 200
            model.assert_called_once_with()
            blocklist.assert_called_once_with()


def test_concurrent_cache_and_rule_precedence(runtime):
    from betguard_runtime import decision_engine
    runtime.clear_cache()
    with ThreadPoolExecutor(max_workers=8) as executor:
        results = list(executor.map(runtime.evaluate, ["https://www.stake.com/casino"] * 32))
    assert all(r["enforcement_action"] == "BLOCK" for r in results)
    assert len(runtime.cache) == 1
    both = {"stake.com"}
    result = decision_engine.decide_domain("stake.com", runtime.model, runtime.model_config,
                                         runtime.gambling_lookup, both, both)
    assert result["decision_source"] == "user_allowlist" and result["enforcement_action"] == "ALLOW"
    result = decision_engine.decide_domain("stake.com", runtime.model, runtime.model_config,
                                         runtime.gambling_lookup, set(), both)
    assert result["decision_source"] == "user_blocklist"


def test_application_never_reads_shared_text_user_lists():
    from betguard_runtime import runtime_service
    with patch.object(runtime_service, "load_text_list") as text_lists, \
         patch.object(runtime_service, "load_model", return_value=(MagicMock(), {"model_name": "baseline"})), \
         patch.object(runtime_service, "load_gambling_blocklist", return_value={}):
        service = load_runtime()
        service.reload_user_lists()
        assert service.allowlist == service.user_blocklist == set()
        text_lists.assert_not_called()


def test_reload_cannot_cache_a_stale_inflight_decision():
    from betguard_runtime import runtime_service
    with patch.object(runtime_service, "load_model", return_value=(MagicMock(), {"model_name": "baseline"})), \
         patch.object(runtime_service, "load_gambling_blocklist", return_value={"stake.com": "unit fixture"}):
        service = runtime_service.BetGuardRuntime(verbose=False, use_user_lists=False)
    entered, release, snapshot_loaded = Event(), Event(), Event()
    original_decide = runtime_service.decide_domain

    def pending_decision(*args):
        entered.set()
        assert release.wait(5)
        return original_decide(*args)

    def replacement():
        snapshot_loaded.set()
        return {}

    with patch.object(runtime_service, "decide_domain", side_effect=pending_decision), \
         patch.object(runtime_service, "load_gambling_blocklist", side_effect=replacement), \
         ThreadPoolExecutor(max_workers=2) as executor:
        evaluation = executor.submit(service.evaluate, "stake.com")
        assert entered.wait(5)
        reload = executor.submit(service.reload_gambling_blocklist)
        assert snapshot_loaded.wait(5)
        release.set()
        assert evaluation.result(timeout=5)["enforcement_action"] == "BLOCK"
        reload.result(timeout=5)
    assert service.gambling_lookup == {} and len(service.cache) == 0
