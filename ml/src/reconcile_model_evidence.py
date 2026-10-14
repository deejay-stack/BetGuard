"""Recalculate saved metrics and offline shadow comparisons without editing evidence."""
import argparse
import csv
import json
from pathlib import Path
import sys

import joblib
import numpy as np
import pandas as pd
from sklearn.metrics import accuracy_score, precision_score, recall_score, f1_score, roc_auc_score, confusion_matrix

if __package__:
    from . import optimized_svm_shadow as shadow
    from .runtime_service import BetGuardRuntime
else:
    import optimized_svm_shadow as shadow
    from runtime_service import BetGuardRuntime

ROOT = Path(__file__).resolve().parents[1]


def evaluate(labels, scores, threshold):
    predicted = (np.asarray(scores) >= threshold).astype(int)
    tn, fp, fn, tp = confusion_matrix(labels, predicted, labels=[0, 1]).ravel()
    return {"accuracy": float(accuracy_score(labels, predicted)), "precision": float(precision_score(labels, predicted, zero_division=0)),
            "recall": float(recall_score(labels, predicted, zero_division=0)), "f1": float(f1_score(labels, predicted, zero_division=0)),
            "roc_auc": float(roc_auc_score(labels, scores)), "false_positives": int(fp), "false_negatives": int(fn),
            "true_negatives": int(tn), "true_positives": int(tp)}


def csv_write(path, rows):
    with path.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def reconcile(artifact, anchor, output):
    output = Path(output)
    if output.exists():
        raise ValueError("Use a new report directory; preserve previous evidence.")
    svm = shadow.FrozenSVMShadow.load(artifact, expected_manifest_sha256=anchor)
    runtime = BetGuardRuntime(verbose=False, use_user_lists=False)
    splits = {name: pd.read_csv(ROOT / f"data/processed/splits/baseline_{name}.csv") for name in ("train", "validation", "test")}
    benchmark = pd.read_csv(ROOT / "data/processed/balanced_domain_dataset.csv")
    membership = pd.concat(splits.values(), ignore_index=True)
    label_map = dict(zip(benchmark.domain, benchmark.label))
    split_map = dict(zip(membership.domain, membership.label))
    if membership.domain.duplicated().any() or label_map != split_map:
        raise ValueError("Balanced dataset and splits disagree.")
    overlaps = {f"{a}_{b}": sorted(set(splits[a].domain_family) & set(splits[b].domain_family)) for a, b in (("train", "validation"), ("train", "test"), ("validation", "test"))}
    if any(overlaps.values()):
        raise ValueError("Family leakage detected.")
    # Historical hybrid pickle names its source module. Resolve this local
    # trusted module explicitly without changing the saved experiment binary.
    sys.path.insert(0, str(ROOT / "src"))
    hybrid = joblib.load(ROOT / "models/hybrid_evaluation_model.joblib")
    ordinary = joblib.load(ROOT / "models/svm_domain_classifier.joblib")
    forest = joblib.load(ROOT / "models/random_forest_domain_classifier.joblib")
    specs = [
        ("baseline_f1", "baseline", "gambling_probability", "selected_threshold", "test_metrics", runtime.model, "TF-IDF char (3,5); min_df=2"),
        ("hybrid_f1", "hybrid", "gambling_probability", None, "f1_threshold_test_metrics", hybrid, "TF-IDF char (3,5) + scaled lexical"),
        ("ordinary_svm", "svm", "svm_decision_score", "selected_threshold", "test_metrics", ordinary, "TF-IDF char (3,5); min_df=2; no lexical"),
        ("random_forest", "random_forest", "gambling_probability", "selected_threshold", "test_metrics", forest, "TF-IDF char (3,5); min_df=2"),
        ("optimized_svm", "optimized_svm_historical", "svm_decision_score", None, "test_metrics", svm, "TF-IDF char (2,6); min_df=1 + 25 lexical"),
    ]
    comparisons, checks, scores_by_model = [], {}, {}
    for name, prefix, score_column, threshold_key, metrics_key, model, feature_description in specs:
        metrics_file = ROOT / "reports" / ("optimized_svm_historical_test_metrics.json" if name == "optimized_svm" else f"{prefix}_metrics.json")
        predictions_file = ROOT / "reports" / ("optimized_svm_historical_test_predictions.csv" if name == "optimized_svm" else f"{prefix}_test_predictions.csv")
        report = json.loads(metrics_file.read_text())
        predictions = pd.read_csv(predictions_file)
        if list(predictions.domain) != list(splits["test"].domain) or list(predictions.label) != list(splits["test"].label):
            raise ValueError(f"Prediction membership mismatch: {name}")
        threshold = shadow.THRESHOLD if name == "optimized_svm" else report[threshold_key] if threshold_key else report[metrics_key]["threshold"]
        saved_metrics = evaluate(predictions.label, predictions[score_column], threshold)
        expected = report[metrics_key]
        discrepancies = {key: {"saved": expected.get(key), "recalculated": value} for key, value in saved_metrics.items() if key in expected and not np.isclose(value, expected[key], atol=1e-10, rtol=0)}
        if "confusion_matrix" in expected:
            actual_matrix = [[saved_metrics["true_negatives"], saved_metrics["false_positives"]], [saved_metrics["false_negatives"], saved_metrics["true_positives"]]]
            if expected["confusion_matrix"] != actual_matrix:
                discrepancies["confusion_matrix"] = {"saved": expected["confusion_matrix"], "recalculated": actual_matrix}
        test_input = splits["test"][["domain"]] if name == "hybrid_f1" else list(splits["test"].domain)
        actual_scores = model.decision_function(test_input) if name in {"ordinary_svm", "optimized_svm"} else model.predict_proba(test_input)[:, 1]
        val_input = splits["validation"][["domain"]] if name == "hybrid_f1" else list(splits["validation"].domain)
        val_scores = model.decision_function(val_input) if name in {"ordinary_svm", "optimized_svm"} else model.predict_proba(val_input)[:, 1]
        scores_by_model[name] = np.asarray(actual_scores)
        val_metrics = evaluate(splits["validation"].label, val_scores, threshold)
        predictions_match = np.array_equal((predictions[score_column].to_numpy() >= threshold).astype(int), predictions.predicted_label)
        score_match = bool(np.allclose(actual_scores, predictions[score_column], atol=1e-6, rtol=0))
        checks[name] = {"metrics_file": metrics_file.relative_to(ROOT).as_posix(), "predictions_file": predictions_file.relative_to(ROOT).as_posix(),
                        "report_discrepancies": discrepancies, "saved_labels_match_threshold": bool(predictions_match), "artifact_scores_match_saved": score_match,
                        "max_score_difference": float(np.max(np.abs(actual_scores - predictions[score_column]))), "validation_recalculated": val_metrics,
                        "test_recalculated": saved_metrics, "threshold": float(threshold)}
        comparisons.append({"algorithm": name, "features": feature_description, "dataset_size": 846, "train_size": 507, "validation_size": 169,
                            "historical_test_size": 170, "threshold": float(threshold), "validation_accuracy": val_metrics["accuracy"], **saved_metrics})
    selected_threshold = runtime.model_config["threshold"]
    for name, threshold in (("baseline_selected_warning", selected_threshold), ("baseline_hard_block_ml_only", 0.70)):
        validation = evaluate(splits["validation"].label, runtime.model.predict_proba(list(splits["validation"].domain))[:, 1], threshold)
        comparisons.append({"algorithm": name, "features": "TF-IDF char (3,5); min_df=2", "dataset_size": 846, "train_size": 507, "validation_size": 169,
                            "historical_test_size": 170, "threshold": threshold, "validation_accuracy": validation["accuracy"],
                            **evaluate(splits["test"].label, scores_by_model["baseline_f1"], threshold)})
    rows = []
    for _, row in splits["test"].iterrows():
        baseline = runtime.evaluate(row.domain)
        optimized = svm.classify([row.domain])[0]
        rows.append({"domain": row.domain, "label": int(row.label), "baseline_probability": baseline["ml_score"],
                     "baseline_enforcement": baseline["enforcement_action"], "baseline_source": baseline["decision_source"],
                     "svm_margin": optimized["decision_score"], "svm_predicted_label": optimized["predicted_label"],
                     "baseline_block_vs_svm_positive_disagrees": (baseline["enforcement_action"] == "BLOCK") != bool(optimized["predicted_label"])})
    fixture_hosts = ["stake.com", "draftkings.com", "wikipedia.org", "microsoft.com", "alphabet.com", "bsp.gov.ph", "bdo.com.ph", "bpi.com.ph", "up.edu.ph", "deped.gov.ph", "doh.gov.ph", "gcash.com", "grab.com", "bethel.edu", "alphabet.edu", "xn--bcher-kva.example"]
    probes = []
    for domain in fixture_hosts:
        baseline = runtime.evaluate(domain)
        probe = svm.classify([domain])[0]
        probes.append({"domain": domain, "baseline_score": baseline["ml_score"], "baseline_source": baseline["decision_source"],
                       "baseline_enforcement": baseline["enforcement_action"], "svm_margin": probe["decision_score"], "svm_predicted_label": probe["predicted_label"]})
    holdout = pd.read_csv(ROOT / "data/processed/external_holdout.csv")
    holdout_metrics = evaluate(holdout.label, svm.decision_function(list(holdout.domain)), shadow.THRESHOLD)
    benign_probes = pd.read_csv(ROOT / "data/expanded/pagcor_ph/benign_expansion_v1/ph_benign_expanded_candidates.csv")
    benign_scores = svm.decision_function(list(benign_probes.domain))
    exploratory = {"external_holdout": {"rows": len(holdout), "metrics": holdout_metrics, "independent_new_holdout": False,
                    "note": "Previously used for baseline/runtime investigation; this is exploratory reuse, not fresh independent validation."},
                   "ph_benign_candidate_probes": {"rows": len(benign_probes), "svm_positive_predictions": int((benign_scores >= shadow.THRESHOLD).sum()),
                    "verified_labels": False, "note": "Candidates only: predictions cannot be called false positives or used as measured accuracy."}}
    output.mkdir(parents=True)
    csv_write(output / "algorithm_comparison.csv", comparisons)
    csv_write(output / "historical_shadow_comparison.csv", rows)
    csv_write(output / "domain_probes.csv", probes)
    false_positives = splits["test"][(splits["test"].label == 0) & (scores_by_model["optimized_svm"] >= shadow.THRESHOLD)]
    false_positives.to_csv(output / "optimized_svm_false_positive_fixtures.csv", index=False)
    sha_inputs = [ROOT / "data/raw/dataset_with_ssl_dns.csv", ROOT / "data/processed/balanced_domain_dataset.csv", ROOT / "data/runtime/gambling_blocklist.csv",
                  ROOT / "data/processed/external_holdout.csv", *[ROOT / f"data/processed/splits/baseline_{name}.csv" for name in splits]]
    evidence = {"model_checks": checks, "family_overlaps": overlaps, "balanced_membership_matches_splits": True,
                "checksums": {path.relative_to(ROOT).as_posix(): shadow.digest(path) for path in sha_inputs},
                "exploratory": exploratory, "historical_false_positive_domains": list(false_positives.domain),
                "live_runtime_model": runtime.model_config["model_name"], "live_runtime_blocklist_domains": len(runtime.gambling_lookup),
                "shadow_artifact_manifest_sha256": anchor, "production_svm_activated": False,
                "saved_evidence_reconciled": all(not item["report_discrepancies"] and item["artifact_scores_match_saved"] and item["saved_labels_match_threshold"] for item in checks.values())}
    shadow.json_write(output / "reconciliation.json", evidence)
    print(json.dumps({"saved_evidence_reconciled": evidence["saved_evidence_reconciled"], "algorithm_comparison": comparisons,
                      "exploratory": exploratory, "family_overlaps": overlaps}, indent=2))
    return evidence


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--artifact", type=Path, required=True)
    parser.add_argument("--manifest-sha256", required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    reconcile(args.artifact, args.manifest_sha256, args.output)


if __name__ == "__main__":
    main()
