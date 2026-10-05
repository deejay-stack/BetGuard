"""Explicit commands only. Never train/evaluate as a side effect of API startup."""
from dataclasses import asdict
from datetime import datetime, timezone
import json
from pathlib import Path
import time
import warnings

import numpy as np
from sklearn.exceptions import ConvergenceWarning
from threadpoolctl import threadpool_limits

from app.ml.artifacts import load_artifact
from ml_tools.exporting import save_artifact
from ml_tools.data import digest, json_write, usable_data
from app.ml.features import scores
from ml_tools.features import pipelines
from ml_tools.protocol import (TrainingConfig, assert_no_leakage, metrics, split_digest,
                             split_records, tune_thresholds)


def create_split(dataset: Path, output: Path, config: TrainingConfig, *, software_test=False):
    report, records, groups = usable_data(dataset, software_test=software_test)
    split = split_records(records, groups, config)
    split.update({"dataset_sha256": report["dataset_sha256"], "psl": report["psl"],
                  "synthetic": bool(report["synthetic_rows"]), "audit": report})
    if output.exists():
        raise ValueError("Split already exists; immutable split membership must not be overwritten.")
    json_write(output, split)
    return split


def load_split(dataset, split_path, *, software_test=False):
    report, records, groups = usable_data(dataset, software_test=software_test)
    split = json.loads(split_path.read_text(encoding="utf-8"))
    assert_no_leakage(split)
    if split["dataset_sha256"] != report["dataset_sha256"] or split["psl"] != report["psl"]:
        raise ValueError("Dataset or PSL changed since splitting.")
    membership = {row["record_id"]: row for name in ("train", "validation", "test") for row in split[name]}
    if set(membership) != {row.record_id for row in records}:
        raise ValueError("Split membership no longer matches the reviewed dataset.")
    for row in records:
        item = membership[row.record_id]
        if item["hostname"] != row.hostname or item["group"] != groups[row.record_id] or item["label"] != (row.classification == "gambling"):
            raise ValueError("Split records were altered; create a new versioned dataset and split.")
    expected = split_records(records, groups, TrainingConfig(**split["config"]))
    if any(split[name] != expected[name] for name in ("train", "validation", "test")):
        raise ValueError("Split membership was altered from the fixed seeded protocol.")
    return split


def latency(pipeline, hosts):
    # Single-host, warm timings; excludes network and DB. At most 100 probes.
    scores(pipeline, hosts[:1])
    elapsed = []
    for host in hosts[:100]:
        started = time.perf_counter()
        scores(pipeline, [host])
        elapsed.append((time.perf_counter() - started) * 1000)
    return {"median_ms": float(np.median(elapsed)), "p95_ms": float(np.quantile(elapsed, .95)), "samples": len(elapsed)}


def train(dataset: Path, split_path: Path, run: Path, *, software_test=False):
    split = load_split(dataset, split_path, software_test=software_test)
    config = TrainingConfig(**split["config"])
    config.validate()
    run.mkdir(parents=True, exist_ok=False)
    json_write(run / "split.json", split)
    train_hosts = [r["hostname"] for r in split["train"]]
    train_y = [r["label"] for r in split["train"]]
    val_hosts = [r["hostname"] for r in split["validation"]]
    val_y = [r["label"] for r in split["validation"]]
    results, manifests = {}, {}
    with threadpool_limits(limits=1), warnings.catch_warnings():
        warnings.simplefilter("error", ConvergenceWarning)
        for name, pipeline in pipelines(config.seed, config.max_features, config.trees).items():
            started = time.perf_counter()
            pipeline.fit(train_hosts, train_y)
            training_seconds = time.perf_counter() - started
            val_score = scores(pipeline, val_hosts)
            thresholds = tune_thresholds(val_y, val_score, config)
            validation = metrics(val_y, val_score, thresholds, .5 if name == "random_forest" else 0)
            timing = latency(pipeline, val_hosts)
            metadata = {"purpose": "software_test" if software_test else "candidate", "synthetic": split["synthetic"],
                        "model_version": f"{run.name}-{name}-{split_digest(split)[:12]}", "algorithm": name,
                        "created_at": datetime.now(timezone.utc).isoformat(), "config": asdict(config),
                        "dataset_sha256": split["dataset_sha256"], "split_sha256": split_digest(split),
                        "thresholds": thresholds, "evaluation": {"validation": validation},
                        "training_seconds": training_seconds, "inference_latency": timing}
            save_artifact(run / name, pipeline, metadata)
            manifests[name] = digest(run / name / "manifest.json")
            results[name] = metadata
    suitable = [name for name, result in results.items() if result["thresholds"]["gambling_min"] is not None
                and result["inference_latency"]["p95_ms"] <= config.max_latency_ms]
    # Validation ranking: recall under FP/precision constraints, then coverage,
    # then smaller/faster operational cost; no test predictions were computed.
    preference = {"logistic_regression": 2, "svm": 1, "random_forest": 0}
    selected = max(suitable, key=lambda name: (
        results[name]["evaluation"]["validation"]["gambling_recall_including_abstention"],
        results[name]["evaluation"]["validation"]["coverage"],
        preference[name],
    )) if suitable else None
    summary = {"selected": selected, "selection_basis": "validation recall under precision/FPR and latency constraints, coverage, fixed simpler-model preference",
               "candidate_manifests": manifests, "split_sha256": split_digest(split),
               "test_evaluated": False, "results": results}
    json_write(run / "training.json", summary)
    return summary


def evaluate(dataset: Path, run: Path, *, software_test=False):
    if (run / "evaluation.json").exists() or (run / "evaluation.started").exists():
        raise ValueError("This run's held-out evaluation was already started. Do not repeatedly tune against test results.")
    split = load_split(dataset, run / "split.json", software_test=software_test)
    training = json.loads((run / "training.json").read_text(encoding="utf-8"))
    if split_digest(split) != training["split_sha256"]:
        raise ValueError("Training split changed.")
    hosts = [r["hostname"] for r in split["test"]]
    y = [r["label"] for r in split["test"]]
    # Created exclusively before the first prediction. An interrupted run is
    # explicitly incomplete rather than silently allowing another test look.
    with (run / "evaluation.started").open("x", encoding="utf-8") as marker:
        marker.write(datetime.now(timezone.utc).isoformat())
    results = {}
    with threadpool_limits(limits=1):
        for name, expected_hash in training["candidate_manifests"].items():
            pipeline, metadata = load_artifact(run / name, expected_manifest_sha256=expected_hash, deployment=False)
            results[name] = {"test": metrics(y, scores(pipeline, hosts), metadata["thresholds"], .5 if name == "random_forest" else 0),
                             "inference_latency": latency(pipeline, hosts)}
    evaluation = {"selected_before_test": training["selected"], "split_sha256": split_digest(split),
                  "training_sha256": digest(run / "training.json"), "results": results,
                  "scope": "This dataset and fixed grouped split only; no claim of general website performance."}
    json_write(run / "evaluation.json", evaluation)
    return evaluation


def export(run: Path, output: Path, *, reviewer: str, note: str):
    if not reviewer.strip() or not note.strip():
        raise ValueError("Export requires a named human review and a limitations/approval note.")
    training = json.loads((run / "training.json").read_text(encoding="utf-8"))
    evaluation = json.loads((run / "evaluation.json").read_text(encoding="utf-8"))
    if evaluation["training_sha256"] != digest(run / "training.json") or evaluation["selected_before_test"] != training["selected"]:
        raise ValueError("Selection/evaluation changed after test; do not select a different winner on test data.")
    name = training["selected"]
    if not name:
        raise ValueError("No model passed validation selection; collect/review data before export.")
    pipeline, metadata = load_artifact(run / name, expected_manifest_sha256=training["candidate_manifests"][name], deployment=False)
    if metadata["purpose"] != "candidate" or metadata["synthetic"]:
        raise ValueError("Software-test artifacts are never deployable.")
    config = TrainingConfig(**metadata["config"])
    test = evaluation["results"][name]["test"]
    test_positive_count = sum(row[1] for row in test["selective_confusion_matrix"])
    test_negative_count = sum(row[0] for row in test["selective_confusion_matrix"])
    if (test["false_positive_rate_including_abstention"] > config.max_false_positive_rate
            or test["false_negative_rate_including_abstention"] > config.max_false_negative_rate
            or (test["gambling_precision"] or 0) < config.min_predictive_value
            or test["gambling_recall_including_abstention"] <= 0
            or test_positive_count < config.min_decisions
            or (metadata["thresholds"]["non_gambling_max"] is not None and (
                test_negative_count < config.min_decisions or
                (test["non_gambling_predictive_value"] or 0) < config.min_predictive_value))
            or evaluation["results"][name]["inference_latency"]["p95_ms"] > config.max_latency_ms):
        raise ValueError("Selected model failed the preregistered test/latency gates. Do not switch winners using this test set.")
    split = json.loads((run / "split.json").read_text(encoding="utf-8"))
    if split_digest(split) != metadata["split_sha256"]:
        raise ValueError("Split reference changed.")
    metadata.update({"purpose": "deployment", "evaluation": {**metadata["evaluation"], "test": test,
                      "comparison": evaluation["results"]},
                     "approval": {"reviewer": reviewer, "note": note, "at": datetime.now(timezone.utc).isoformat()}})
    save_artifact(output, pipeline, metadata)
    json_write(output / "split.json", split)
    json_write(output / "audit.json", split["audit"])
    return {"model_version": metadata["model_version"], "manifest_sha256": digest(output / "manifest.json")}
