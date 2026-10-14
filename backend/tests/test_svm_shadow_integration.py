"""Backend shadow integration against the existing release, without training."""
from concurrent.futures import ThreadPoolExecutor
import json
from pathlib import Path
from threading import Event
from time import perf_counter
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from fastapi.testclient import TestClient
import pytest

from app.core.config import ConfigurationError, SVMShadowSettings, svm_shadow_settings
from app.main import app
from app.schemas.domain import DomainDecision
from app.services.domain_service import evaluate
from app.services.model_service import ModelService
from app.services.svm_shadow_service import SVMShadowService
from betguard_runtime.optimized_svm_shadow import FrozenSVMShadow
from betguard_runtime.runtime_service import BetGuardRuntime

ARTIFACT = Path(__file__).resolve().parents[2] / "ml/models/optimized_svm_shadow_2026-10-11"


@pytest.fixture(autouse=True)
def isolated_environment(monkeypatch):
    monkeypatch.setenv("BETGUARD_SVM_SHADOW_ENABLED", "false")
    monkeypatch.setenv("BETGUARD_ROUTER_ENABLED", "0")


@pytest.fixture(scope="module")
def frozen():
    return FrozenSVMShadow.load(ARTIFACT, expected_manifest_sha256=SVMShadowSettings(ARTIFACT).manifest_sha256)


@pytest.fixture(scope="module")
def runtime():
    return BetGuardRuntime(verbose=False, use_user_lists=False)


def wait_status(service, expected, timeout=5):
    deadline = perf_counter() + timeout
    while perf_counter() < deadline:
        if service.snapshot()["status"] == expected:
            return
        Event().wait(0.01)
    pytest.fail(f"Shadow status did not become {expected}: {service.snapshot()['status']}")


def wait_idle(service, timeout=5):
    deadline = perf_counter() + timeout
    while perf_counter() < deadline:
        if not service.snapshot()["inflight"]:
            return
        Event().wait(0.01)
    pytest.fail("Shadow worker did not finish")


def create_service(monkeypatch, model):
    monkeypatch.setenv("BETGUARD_SVM_SHADOW_ENABLED", "true")
    with patch("app.services.svm_shadow_service.load_shadow_model", return_value=model):
        service = SVMShadowService.from_environment()
        wait_status(service, "ready")
    return service


def client_context(runtime):
    # No private database, metadata worker, router listener or router settings.
    from contextlib import ExitStack
    stack = ExitStack()
    stack.enter_context(patch("app.main.make_engine", side_effect=ConfigurationError("test")))
    stack.enter_context(patch("app.main.ModelService.from_environment", return_value=ModelService()))
    stack.enter_context(patch("app.main.AppMetadataService.from_environment", return_value=ModelService()))
    stack.enter_context(patch("app.main.load_runtime", return_value=runtime))
    client = stack.enter_context(TestClient(app))
    return stack, client


@pytest.mark.parametrize("value", [None, "false", "0", "FALSE", " false "])
def test_disabled_flag_does_not_load_or_create_worker(monkeypatch, value):
    if value is None:
        monkeypatch.delenv("BETGUARD_SVM_SHADOW_ENABLED", raising=False)
    else:
        monkeypatch.setenv("BETGUARD_SVM_SHADOW_ENABLED", value)
    with patch("app.services.svm_shadow_service.load_shadow_model") as loader, \
         patch("app.services.svm_shadow_service.ThreadPoolExecutor") as worker:
        service = SVMShadowService.from_environment()
        assert service.snapshot()["status"] == "disabled"
        assert not service.submit("example.com", "non_gambling")
        loader.assert_not_called()
        worker.assert_not_called()
        service.close()


@pytest.mark.parametrize("value", ["true", "1", "TRUE", " true "])
def test_enabled_settings_use_existing_resource_root(monkeypatch, tmp_path, value):
    monkeypatch.setenv("BETGUARD_SVM_SHADOW_ENABLED", value)
    monkeypatch.setenv("BETGUARD_ML_ROOT", str(tmp_path))
    settings = svm_shadow_settings()
    assert settings.artifact_directory == tmp_path / "models/optimized_svm_shadow_2026-10-11"
    assert settings.manifest_sha256 == SVMShadowSettings(ARTIFACT).manifest_sha256


def test_invalid_flag_only_disables_shadow(monkeypatch, caplog):
    monkeypatch.setenv("BETGUARD_SVM_SHADOW_ENABLED", "private-invalid-value")
    with patch("app.services.svm_shadow_service.ThreadPoolExecutor") as worker:
        service = SVMShadowService.from_environment()
        assert service.snapshot()["status"] == "unavailable"
        worker.assert_not_called()
    assert "private-invalid-value" not in caplog.text


def test_disabled_application_startup_and_public_contract(runtime):
    with patch("app.services.svm_shadow_service.load_shadow_model") as loader:
        stack, client = client_context(runtime)
        with stack:
            assert app.state.svm_shadow.snapshot()["status"] == "disabled"
            assert client.get("/health/live").status_code == 200
            assert client.get("/health/detection").json()["model_name"] == "baseline"
            assert client.post("/v1/domain/check", json={"domain": "wikipedia.org"}).status_code == 200
            loader.assert_not_called()
        assert app.state.svm_shadow is None


def test_enabled_application_loads_real_release_once_and_preserves_responses(monkeypatch, runtime):
    baseline_requests = ["wikipedia.org", "microsoft.com", "alphabet.com", "bpi.com.ph", "stake.com"]
    stack, client = client_context(runtime)
    with stack:
        runtime.clear_cache()
        before = [client.post("/v1/domain/check", json={"domain": host}).json() for host in baseline_requests]
        before_health = client.get("/health/detection").json()
        before_schema = client.get("/openapi.json").json()
        runtime.clear_cache()
        before_batch = client.post("/v1/domain/check-batch", json={"domains": baseline_requests}).json()
    monkeypatch.setenv("BETGUARD_SVM_SHADOW_ENABLED", "true")
    from app.services.svm_shadow_service import load_shadow_model
    with patch("app.services.svm_shadow_service.load_shadow_model", wraps=load_shadow_model) as loader:
        stack, client = client_context(runtime)
        with stack:
            service = app.state.svm_shadow
            wait_status(service, "ready")
            runtime.clear_cache()
            after = []
            for host in baseline_requests:
                after.append(client.post("/v1/domain/check", json={"domain": host}).json())
                wait_idle(service)
            assert before == after
            after_health = client.get("/health/detection").json()
            assert set(before_health) == set(after_health)
            assert after_health["model_name"] == "baseline"
            assert before_schema == client.get("/openapi.json").json()
            runtime.clear_cache()
            assert client.post("/v1/domain/check-batch", json={"domains": baseline_requests}).json() == before_batch
            wait_idle(service)
            loader.assert_called_once()
            snapshot = service.snapshot()
            assert snapshot["counts"]["loaded"] == 1
            assert snapshot["counts"]["completed"] >= 4
            assert snapshot["counts"]["agreed"] >= 2
            assert snapshot["counts"]["disagreed"] >= 1
            assert snapshot["counts"]["skipped_rules"] >= 1
            for response in after:
                assert set(response["result"]) == {"domain", "enforcement_action", "intervention", "risk_status", "decision_source", "matched_domain", "ml_score", "cache_hit"}
            assert not any(host in json.dumps(snapshot) for host in baseline_requests)
        assert app.state.svm_shadow is None
        assert service.snapshot()["status"] == "closed"


@pytest.mark.parametrize("host", ["wikipedia.org", "alphabet.com", "bsp.gov.ph", "bpi.com.ph", "up.edu.ph", "xn--bcher-kva.example"])
def test_adapter_matches_frozen_inference_and_keeps_margin_internal(monkeypatch, frozen, host):
    service = create_service(monkeypatch, frozen)
    try:
        expected = frozen.classify([host])[0]
        assert service.submit(host, "non_gambling")
        wait_idle(service)
        record = service.snapshot()["recent"][-1]
        assert record["svm_decision_margin"] == expected["decision_score"]
        assert record["svm_classification"] == {0: "non_gambling", 1: "gambling"}[expected["predicted_label"]]
        assert record["agree"] == (expected["predicted_label"] == 0)
        assert record["duration_ms"] >= 0
        assert "ml_score" not in record and "probability" not in json.dumps(record)
    finally:
        service.close()


@pytest.mark.parametrize("failure", ["missing_manifest", "missing_model", "corrupt_manifest", "corrupt_model", "wrong_hash"])
def test_bad_artifact_does_not_break_startup_or_baseline(monkeypatch, runtime, tmp_path, caplog, failure):
    import shutil
    directory = tmp_path / "artifact"
    shutil.copytree(ARTIFACT, directory)
    if failure.startswith("missing_"):
        (directory / ("manifest.json" if failure.endswith("manifest") else "model.joblib")).unlink()
    elif failure.startswith("corrupt_"):
        (directory / ("manifest.json" if failure.endswith("manifest") else "model.joblib")).write_bytes(b"private-corruption-fixture")
    settings = SVMShadowSettings(directory, "0" * 64) if failure == "wrong_hash" else SVMShadowSettings(directory)
    monkeypatch.setenv("BETGUARD_SVM_SHADOW_ENABLED", "true")
    with patch("app.services.svm_shadow_service.svm_shadow_settings", return_value=settings):
        stack, client = client_context(runtime)
        with stack:
            wait_status(app.state.svm_shadow, "unavailable")
            assert client.get("/health/live").status_code == 200
            assert client.get("/health/detection").status_code == 200
            assert client.post("/v1/domain/check", json={"domain": "stake.com"}).json()["result"]["enforcement_action"] == "BLOCK"
            assert client.post("/v1/domain/check", json={"domain": "wikipedia.org"}).json()["result"]["enforcement_action"] == "ALLOW"
    assert "private-corruption-fixture" not in caplog.text and str(directory) not in caplog.text


def test_loading_does_not_delay_production_requests(monkeypatch, runtime, frozen):
    entered, release = Event(), Event()
    def slow_load(_settings):
        entered.set()
        assert release.wait(5)
        return frozen
    monkeypatch.setenv("BETGUARD_SVM_SHADOW_ENABLED", "true")
    with patch("app.services.svm_shadow_service.load_shadow_model", side_effect=slow_load):
        stack, client = client_context(runtime)
        with stack:
            try:
                assert entered.wait(5)
                assert app.state.svm_shadow.snapshot()["status"] == "loading"
                start = perf_counter()
                assert client.post("/v1/domain/check", json={"domain": "wikipedia.org"}).status_code == 200
                assert perf_counter() - start < 1.0
                assert app.state.svm_shadow.snapshot()["counts"]["skipped_loading"] == 1
            finally:
                release.set()
            wait_status(app.state.svm_shadow, "ready")


def test_inference_and_observer_failure_do_not_change_baseline(monkeypatch, runtime, caplog):
    model = MagicMock()
    model.classify.side_effect = RuntimeError("private-path-or-token")
    service = create_service(monkeypatch, model)
    try:
        runtime.clear_cache()
        baseline = evaluate(runtime, ["wikipedia.org"])[0].model_dump()
        runtime.clear_cache()
        assert evaluate(runtime, ["wikipedia.org"], shadow=service)[0].model_dump() == baseline
        wait_idle(service)
        assert service.snapshot()["status"] == "unavailable"
        assert service.snapshot()["recent"][-1]["error_type"] == "RuntimeError"
        # Circuit is open: no repeated failing jobs are submitted.
        assert not service.submit("example.com", "non_gambling")
        assert model.classify.call_count == 1
        broken_observer = MagicMock()
        broken_observer.observe.side_effect = RuntimeError("private-path-or-token")
        runtime.clear_cache()
        assert evaluate(runtime, ["wikipedia.org"], shadow=broken_observer)[0].model_dump() == baseline
        assert "private-path-or-token" not in caplog.text
    finally:
        service.close()


@pytest.mark.parametrize("value", ["", "127.0.0.1", "https://user:private@example.com", "https://[bad", "example..com", "-bad.com"])
def test_invalid_requests_never_reach_shadow(monkeypatch, runtime, frozen, value):
    service = create_service(monkeypatch, frozen)
    stack, client = client_context(runtime)
    with stack, patch.object(service, "observe") as observe:
        original = app.state.svm_shadow
        app.state.svm_shadow = service
        try:
            response = client.post("/v1/domain/check", json={"domain": value})
            assert response.status_code == 422 and "private" not in response.text
            observe.assert_not_called()
        finally:
            app.state.svm_shadow = original
            service.close()


def test_rules_and_blocklists_are_preserved_and_not_compared(monkeypatch, runtime, frozen):
    from betguard_runtime.decision_engine import decide_domain
    service = create_service(monkeypatch, frozen)
    try:
        lists = [(set(), set(), "verified_gambling_blocklist", "BLOCK"),
                 ({"stake.com"}, {"stake.com"}, "user_allowlist", "ALLOW"),
                 (set(), {"stake.com"}, "user_blocklist", "BLOCK")]
        for allowlist, blocklist, source, action in lists:
            result = decide_domain("casino.stake.com", runtime.model, runtime.model_config,
                                   runtime.gambling_lookup, allowlist, blocklist)
            before = dict(result)
            assert not service.observe(DomainDecision.model_validate(result))
            assert result == before
            assert result["decision_source"] == source and result["enforcement_action"] == action
        assert service.snapshot()["counts"]["skipped_rules"] == 3
        assert service.snapshot()["counts"].get("submitted", 0) == 0
    finally:
        service.close()


def test_busy_worker_is_nonblocking_and_has_no_queue(monkeypatch, frozen):
    entered, release = Event(), Event()
    def slow_inference(domains):
        entered.set()
        assert release.wait(5)
        return frozen.classify(domains)
    model = MagicMock()
    model.classify.side_effect = slow_inference
    service = create_service(monkeypatch, model)
    try:
        assert service.submit("wikipedia.org", "non_gambling")
        assert entered.wait(5)
        start = perf_counter()
        with ThreadPoolExecutor(max_workers=8) as callers:
            results = list(callers.map(lambda _i: service.submit("bpi.com.ph", "non_gambling"), range(32)))
        assert perf_counter() - start < 1.0
        assert not any(results)
        assert service.snapshot()["counts"]["submitted"] == 1
        assert service.snapshot()["counts"]["skipped_busy"] == 32
        assert model.classify.call_count == 1
    finally:
        release.set()
        wait_idle(service)
        service.close()


def test_inference_timeout_retains_capacity_and_discards_late_result(monkeypatch, frozen):
    entered, release = Event(), Event()
    def slow_inference(domains):
        entered.set()
        assert release.wait(5)
        return frozen.classify(domains)
    model = MagicMock()
    model.classify.side_effect = slow_inference
    service = create_service(monkeypatch, model)
    try:
        assert service.submit("wikipedia.org", "non_gambling")
        assert entered.wait(5)
        with service._lock:
            service._deadline = perf_counter() - 1
        assert not service.submit("example.com", "non_gambling")
        snapshot = service.snapshot()
        assert snapshot["status"] == "unavailable" and snapshot["inflight"]
        assert snapshot["counts"]["failed"] == 1
        assert snapshot["recent"][-1]["error_type"] == "TimeoutError"
        release.set()
        wait_idle(service)
        assert service.snapshot()["counts"]["late_results_discarded"] == 1
        assert service.snapshot()["counts"].get("completed", 0) == 0
    finally:
        release.set()
        service.close()


def test_repeated_inference_and_bounded_hostname_free_diagnostics(monkeypatch, frozen):
    service = create_service(monkeypatch, frozen)
    try:
        for _ in range(132):
            assert service.submit("bpi.com.ph", "non_gambling")
            wait_idle(service)
        snapshot = service.snapshot()
        assert snapshot["counts"]["completed"] == 132
        assert snapshot["counts"]["disagreed"] == 132
        assert len(snapshot["recent"]) == 128
        assert max(record["duration_ms"] for record in snapshot["recent"]) < 1500
        assert "bpi.com.ph" not in json.dumps(snapshot)
        assert len({record["svm_decision_margin"] for record in snapshot["recent"]}) == 1
    finally:
        service.close()


def test_svm_positive_never_triggers_block_or_warning(monkeypatch, runtime, frozen):
    service = create_service(monkeypatch, frozen)
    try:
        runtime.clear_cache()
        decision = evaluate(runtime, ["bpi.com.ph"], shadow=service)[0]
        wait_idle(service)
        record = service.snapshot()["recent"][-1]
        assert record["svm_classification"] == "gambling"
        assert record["baseline_classification"] == "non_gambling"
        assert record["agree"] is False
        assert decision.enforcement_action == "ALLOW" and decision.intervention == "NONE"
        assert decision.decision_source == "ml_low_risk"
        assert 0 <= decision.ml_score <= 1
    finally:
        service.close()


def test_load_timeout_and_shutdown_discard_late_models(monkeypatch, frozen):
    entered, release = Event(), Event()
    def slow_load(_settings):
        entered.set()
        assert release.wait(5)
        return frozen
    monkeypatch.setenv("BETGUARD_SVM_SHADOW_ENABLED", "true")
    with patch("app.services.svm_shadow_service.load_shadow_model", side_effect=slow_load):
        service = SVMShadowService.from_environment()
        try:
            assert entered.wait(5)
            with service._lock:
                service._deadline = perf_counter() - 1
            assert service.snapshot()["status"] == "unavailable"
            assert not service.submit("example.com", "non_gambling")
            release.set()
            wait_idle(service)
            assert service.snapshot()["counts"]["load_failed"] == 1
            assert service.snapshot()["counts"]["late_load_results_discarded"] == 1
            assert service._model is None
        finally:
            release.set()
            service.close()


def test_executor_submission_failure_stays_private(monkeypatch, frozen):
    service = create_service(monkeypatch, frozen)
    try:
        with patch.object(service._executor, "submit", side_effect=RuntimeError("private-process-data")):
            assert not service.submit("example.com", "non_gambling")
        snapshot = service.snapshot()
        assert snapshot["status"] == "unavailable"
        assert snapshot["counts"]["failed"] == 1
        assert snapshot["recent"][-1]["error_type"] == "RuntimeError"
        assert "private-process-data" not in json.dumps(snapshot)
    finally:
        service.close()


def test_shutdown_does_not_wait_for_or_keep_an_inflight_prediction(monkeypatch, frozen):
    entered, release = Event(), Event()
    def slow_inference(domains):
        entered.set()
        assert release.wait(5)
        return frozen.classify(domains)
    model = MagicMock()
    model.classify.side_effect = slow_inference
    service = create_service(monkeypatch, model)
    try:
        assert service.submit("wikipedia.org", "non_gambling")
        assert entered.wait(5)
        start = perf_counter()
        service.close()
        assert perf_counter() - start < 1.0
        assert not service.submit("example.com", "non_gambling")
        release.set()
        wait_idle(service)
        assert service.snapshot()["status"] == "closed"
        assert service.snapshot()["recent"] == []
    finally:
        release.set()
        service.close()


@pytest.mark.parametrize("url,host", [("HTTPS://WWW.Wikipedia.ORG.:443/path?private=token", "wikipedia.org"),
                                     ("https://bücher.example/path", "xn--bcher-kva.example")])
def test_existing_normalization_feeds_the_same_frozen_features(monkeypatch, runtime, frozen, url, host):
    monkeypatch.setenv("BETGUARD_SVM_SHADOW_ENABLED", "true")
    stack, client = client_context(runtime)
    with stack:
        wait_status(app.state.svm_shadow, "ready")
        response = client.post("/v1/domain/check", json={"domain": url})
        assert response.status_code == 200
        assert response.json()["result"]["domain"] == host
        assert "private" not in response.text
        wait_idle(app.state.svm_shadow)
        record = app.state.svm_shadow.snapshot()["recent"][-1]
        assert record["svm_decision_margin"] == frozen.classify([host])[0]["decision_score"]
