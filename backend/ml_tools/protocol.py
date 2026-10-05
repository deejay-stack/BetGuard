"""Fixed grouped holdout protocol and validation-only abstention thresholds."""
from collections import Counter
from dataclasses import asdict, dataclass
import hashlib
import json

import numpy as np
from sklearn.metrics import (accuracy_score, average_precision_score, confusion_matrix,
                             f1_score, precision_score, recall_score, roc_auc_score)
from sklearn.model_selection import StratifiedGroupKFold

from app.ml import LABELS
from app.ml.runtime import decisions


@dataclass(frozen=True)
class TrainingConfig:
    seed: int = 42
    max_rows: int = 20000
    max_features: int = 8000
    trees: int = 64
    min_class_per_split: int = 20
    max_false_positive_rate: float = 0.02
    max_false_negative_rate: float = 0.05
    min_predictive_value: float = 0.95
    min_decisions: int = 5
    max_latency_ms: float = 100.0

    def validate(self):
        if not (100 <= self.max_features <= 20000 and 1 <= self.trees <= 128 and
                1 <= self.max_rows <= 50000 and self.min_class_per_split >= 1 and self.min_decisions >= 1 and
                0 <= self.max_false_positive_rate < 0.5 and 0 <= self.max_false_negative_rate < 0.5 and
                0.5 <= self.min_predictive_value <= 1 and 0 < self.max_latency_ms <= 1000):
            raise ValueError("Configuration exceeds bounded laptop limits or has invalid thresholds.")


def split_records(records, groups, config):
    config.validate()
    y = np.array([LABELS[r.classification] for r in records])
    g = np.array([groups[r.record_id] for r in records])
    if len(records) > config.max_rows:
        raise ValueError("Dataset exceeds max_rows. Create an explicitly sampled, reviewed dataset first.")
    if min(Counter(y).get(i, 0) for i in (0, 1)) < 5 or len(set(g)) < 5:
        raise ValueError("Both classes and at least five independent groups are required.")
    outer = StratifiedGroupKFold(n_splits=5, shuffle=True, random_state=config.seed)
    train_val, test = next(outer.split(y, y, g))
    inner = StratifiedGroupKFold(n_splits=4, shuffle=True, random_state=config.seed + 1)
    train, validation = next(inner.split(y[train_val], y[train_val], g[train_val]))
    indexes = {"train": train_val[train], "validation": train_val[validation], "test": test}
    result = {}
    for name, idx in indexes.items():
        if min(Counter(y[idx]).get(i, 0) for i in (0, 1)) < config.min_class_per_split:
            raise ValueError("A fixed split lacks enough examples of each class. Collect more independent groups; do not search seeds using test results.")
        result[name] = [{"record_id": records[i].record_id, "hostname": records[i].hostname,
                         "group": g[i], "label": int(y[i])} for i in idx]
    assert_no_leakage(result)
    result["config"] = asdict(config)
    return result


def assert_no_leakage(split):
    for key in ("hostname", "record_id", "group"):
        buckets = [{row[key] for row in split[name]} for name in ("train", "validation", "test")]
        if key != "group" and any(len(bucket) != len(split[name]) for bucket, name in zip(buckets, ("train", "validation", "test"))):
            raise ValueError(f"Duplicate {key} inside a split.")
        if any(buckets[i] & buckets[j] for i in range(3) for j in range(i + 1, 3)):
            raise ValueError(f"Split leakage detected for {key}.")


def split_digest(split):
    return hashlib.sha256(json.dumps(split, sort_keys=True).encode()).hexdigest()


def tune_thresholds(y, score, config):
    y, score = np.asarray(y), np.asarray(score)
    # A bounded grid avoids quadratic work on a large validation set.
    candidates = np.unique(np.quantile(score, np.linspace(0, 1, min(201, len(score)))))
    upper, lower = None, None
    for threshold in candidates:
        positive = score >= threshold
        tp, fp = sum(positive & (y == 1)), sum(positive & (y == 0))
        if (sum(positive) >= config.min_decisions and fp / sum(y == 0) <= config.max_false_positive_rate
                and tp / sum(positive) >= config.min_predictive_value):
            upper = float(threshold)
            break
    for threshold in candidates[::-1]:
        negative = score <= threshold
        tn, fn = sum(negative & (y == 0)), sum(negative & (y == 1))
        if (sum(negative) >= config.min_decisions and fn / sum(y == 1) <= config.max_false_negative_rate
                and tn / sum(negative) >= config.min_predictive_value):
            lower = float(threshold)
            break
    if upper is not None and lower is not None and lower >= upper:
        lower = None  # No overlapping decisions; abstain on the negative side.
    return {"non_gambling_max": lower, "gambling_min": upper}


def metrics(y, score, thresholds, default_threshold):
    y, score = np.asarray(y), np.asarray(score)
    binary = (score >= default_threshold).astype(int)
    tn, fp, fn, tp = confusion_matrix(y, binary, labels=[0, 1]).ravel()
    selected = decisions(score, thresholds)
    positive, negative = selected == 1, selected == 0
    covered = selected != -1
    return {
        "rows": len(y), "class_counts": {"non_gambling": int(sum(y == 0)), "gambling": int(sum(y == 1))},
        "binary_confusion_matrix": [[int(tn), int(fp)], [int(fn), int(tp)]],
        "binary_precision": float(precision_score(y, binary, zero_division=0)),
        "binary_recall": float(recall_score(y, binary, zero_division=0)),
        "binary_f1": float(f1_score(y, binary, zero_division=0)),
        "binary_accuracy": float(accuracy_score(y, binary)),
        "binary_false_positive_rate": float(fp / (tn + fp)), "binary_specificity": float(tn / (tn + fp)),
        "roc_auc": float(roc_auc_score(y, score)), "pr_auc_average_precision": float(average_precision_score(y, score)),
        "selective_confusion_matrix": [[int(sum((y == label) & (selected == prediction))) for prediction in (0, 1, -1)] for label in (0, 1)],
        "coverage": float(np.mean(covered)), "abstained": int(sum(~covered)),
        "selective_accuracy": float(np.mean(selected[covered] == y[covered])) if any(covered) else None,
        "gambling_precision": float(sum(positive & (y == 1)) / sum(positive)) if any(positive) else None,
        "gambling_recall_including_abstention": float(sum(positive & (y == 1)) / sum(y == 1)),
        "false_positive_rate_including_abstention": float(sum(positive & (y == 0)) / sum(y == 0)),
        "false_negative_rate_including_abstention": float(sum(negative & (y == 1)) / sum(y == 1)),
        "non_gambling_predictive_value": float(sum(negative & (y == 0)) / sum(negative)) if any(negative) else None,
        "calibration": "not_evaluated_no_probability_exposed",
    }
