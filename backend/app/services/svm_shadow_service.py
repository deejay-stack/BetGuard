"""Optional background comparison; never provides a production decision."""
from collections import Counter, deque
from concurrent.futures import ThreadPoolExecutor
import logging
from threading import RLock
from time import perf_counter

from app.core.config import SVM_SHADOW_VERSION, svm_shadow_settings

logger = logging.getLogger(__name__)
MAX_RECORDS = 128
LOAD_TIMEOUT = 30.0
INFERENCE_TIMEOUT = 1.5
BASELINE_CLASSES = {
    "ml_low_risk": "non_gambling",
    "ml_warning": "gambling",
    "ml_high_risk": "gambling",
}


def load_shadow_model(settings):
    # Disabled mode never imports the ML package or deserializes this model.
    from betguard_runtime.optimized_svm_shadow import FrozenSVMShadow
    return FrozenSVMShadow.load(settings.artifact_directory,
                                expected_manifest_sha256=settings.manifest_sha256)


class SVMShadowService:
    def __init__(self, *, status="disabled"):
        self._status = status
        self._lock = RLock()
        self._counts = Counter()
        self._recent = deque(maxlen=MAX_RECORDS)
        self._model = None
        self._executor = None
        self._future = None
        self._started = None
        self._deadline = None
        self._baseline = None

    @classmethod
    def from_environment(cls):
        try:
            settings = svm_shadow_settings()
        except Exception as error:
            logger.warning("SVM shadow configuration unavailable (%s); production unchanged.", type(error).__name__)
            return cls(status="unavailable")
        if settings is None:
            return cls()
        service = cls(status="loading")
        try:
            service._executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="betguard-svm-shadow")
            with service._lock:
                service._started = perf_counter()
                service._deadline = service._started + LOAD_TIMEOUT
                service._future = service._executor.submit(load_shadow_model, settings)
                service._future.add_done_callback(service._loaded)
        except Exception as error:
            service._status = "unavailable"
            if service._executor:
                service._executor.shutdown(wait=False, cancel_futures=True)
            logger.warning("SVM shadow initialization unavailable (%s); production unchanged.", type(error).__name__)
        return service

    def _expire_locked(self):
        # A deadline opens the circuit; the single running thread retains its
        # capacity until it ends. No timeout/retry can create a second worker.
        if self._deadline is not None and perf_counter() > self._deadline and self._status in {"loading", "ready"}:
            loading = self._status == "loading"
            self._status = "unavailable"
            self._counts["load_failed" if loading else "failed"] += 1
            if not loading:
                self._record_locked(success=False, error_type="TimeoutError")
            logger.warning("SVM shadow deadline exceeded; production unchanged. Restart to retry.")

    def _loaded(self, future):
        with self._lock:
            try:
                self._expire_locked()
                if self._status != "loading":
                    if self._status == "unavailable":
                        self._counts["late_load_results_discarded"] += 1
                    return
                self._model = future.result()
                self._status = "ready"
                self._counts["loaded"] += 1
                logger.info("SVM shadow ready: version=%s; production remains authoritative.", SVM_SHADOW_VERSION)
            except Exception as error:
                self._status = "unavailable"
                self._counts["load_failed"] += 1
                logger.warning("SVM shadow artifact unavailable (%s); production unchanged.", type(error).__name__)
            finally:
                self._started = self._deadline = None
                self._future = None

    def observe(self, decision):
        """Compare ML fallback at the existing warning classification point.

        Explicit rule/list outcomes are enforcement evidence, not baseline ML
        predictions. WARN is a positive classification that still allows DNS.
        """
        if self._status in {"disabled", "closed"}:
            return False
        baseline = BASELINE_CLASSES.get(decision.decision_source)
        if baseline is None:
            with self._lock:
                self._counts["skipped_rules"] += 1
            return False
        return self.submit(decision.domain, baseline)

    def submit(self, domain, baseline_classification):
        """Nonblocking offer. Drop rather than queue when the worker is busy."""
        with self._lock:
            self._expire_locked()
            if self._status != "ready":
                self._counts["skipped_" + self._status] += 1
                return False
            if self._future is not None:
                self._counts["skipped_busy"] += 1
                return False
            if baseline_classification not in {"gambling", "non_gambling"}:
                self._counts["invalid_comparison"] += 1
                return False
            self._baseline = baseline_classification
            self._started = perf_counter()
            self._deadline = self._started + INFERENCE_TIMEOUT
            try:
                self._future = self._executor.submit(self._model.classify, [domain])
                self._counts["submitted"] += 1
                self._future.add_done_callback(self._completed)
                return True
            except Exception as error:
                self._status = "unavailable"
                self._counts["failed"] += 1
                self._record_locked(success=False, error_type=type(error).__name__)
                self._started = self._deadline = self._baseline = None
                self._future = None
                return False

    def _record_locked(self, *, success, prediction=None, error_type=None):
        # No hostname, URL, request ID, client IP, timestamp or user data is
        # retained, logged or exposed by an HTTP route.
        margin = prediction["decision_score"] if success else None
        classification = {0: "non_gambling", 1: "gambling"}[prediction["predicted_label"]] if success else None
        self._recent.append({"baseline_classification": self._baseline,
                             "svm_classification": classification, "svm_decision_margin": margin,
                             "agree": classification == self._baseline if success else None,
                             "success": success, "error_type": error_type,
                             "duration_ms": (perf_counter() - self._started) * 1000})

    def _completed(self, future):
        with self._lock:
            self._expire_locked()
            try:
                if self._status == "closed":
                    return
                if self._status == "unavailable":
                    self._counts["late_results_discarded"] += 1
                    return
                prediction = future.result()[0]
                self._record_locked(success=True, prediction=prediction)
                self._counts["completed"] += 1
                self._counts["agreed" if self._recent[-1]["agree"] else "disagreed"] += 1
            except Exception as error:
                self._counts["failed"] += 1
                self._record_locked(success=False, error_type=type(error).__name__)
                self._status = "unavailable"
                logger.warning("SVM shadow inference unavailable (%s); production unchanged. Restart to retry.", type(error).__name__)
            finally:
                self._started = self._deadline = self._baseline = None
                self._future = None

    def snapshot(self):
        """Private, in-process diagnostics for tests/debuggers, never HTTP."""
        with self._lock:
            self._expire_locked()
            return {"status": self._status, "version": SVM_SHADOW_VERSION,
                    "counts": dict(self._counts), "recent": [dict(record) for record in self._recent],
                    "inflight": self._future is not None, "capacity": 1, "record_limit": MAX_RECORDS}

    def close(self):
        with self._lock:
            self._status = "closed"
            self._model = None
            self._recent.clear()
            executor = self._executor
        if executor:
            executor.shutdown(wait=False, cancel_futures=True)
