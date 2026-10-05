"""Features use only the normalized hostname available to explicit checks/DNS."""
from collections import Counter
import math

import numpy as np
from scipy.sparse import csr_matrix
from sklearn.base import BaseEstimator, TransformerMixin
from app.schemas.catalog import normalize_hostname


class NormalizeHostnames(TransformerMixin, BaseEstimator):
    def fit(self, X, y=None):
        return self

    def transform(self, X):
        return [normalize_hostname(value) for value in X]


class HostnameLexicalFeatures(TransformerMixin, BaseEstimator):
    def fit(self, X, y=None):
        return self

    def transform(self, X):
        rows = []
        for host in X:
            size = len(host)
            counts = Counter(host)
            entropy = -sum((n / size) * math.log2(n / size) for n in counts.values())
            rows.append([size / 253, sum(c.isdigit() for c in host) / size,
                         host.count("-") / size, host.count(".") / 10,
                         max(map(len, host.split("."))) / 63,
                         float(any(label.startswith("xn--") for label in host.split("."))), entropy / 6])
        return csr_matrix(np.asarray(rows, dtype=np.float32))


def scores(pipeline, hosts):
    # Internal ranking scores only. Neither SVM margins nor uncalibrated
    # predict_proba output are exposed as confidence/probability to users.
    if hasattr(pipeline, "decision_function"):
        return np.asarray(pipeline.decision_function(hosts), dtype=float)
    return np.asarray(pipeline.predict_proba(hosts)[:, 1], dtype=float)
