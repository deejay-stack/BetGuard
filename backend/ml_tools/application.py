"""Explicit app-metadata experiments: grouped 80/20 holdout, three algorithms.

No scraping, startup training, automatic deployment or fabricated study results.
Run: python -m ml_tools.application --help
"""
import argparse
from collections import Counter
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import time

from pydantic import Field, StrictBool, ValidationError, model_validator
from app.schemas.application import AppMetadata, enough_metadata, metadata_text
from app.ml.application_artifacts import FORMAT, environment, feature_hash, sha256


class AppObservation(AppMetadata):
    record_id: str = Field(min_length=1, max_length=120)
    classification: str = Field(pattern=r"^(gambling|non_gambling|unknown)$")
    family_id: str = Field(min_length=1, max_length=200)
    family_evidence: str = Field(min_length=1, max_length=2000)
    source_uri: str = Field(min_length=1, max_length=1000)
    license: str = Field(min_length=1, max_length=200)
    license_uri: str = Field(min_length=1, max_length=1000)
    usage_allowed: StrictBool
    review_status: str = Field(pattern=r"^(reviewed|pending)$")
    reviewed_by: str = Field(default="", max_length=200)
    label_evidence: str = Field(min_length=1, max_length=2000)
    collected_at: datetime
    reviewed_at: datetime | None = None
    synthetic: StrictBool = False

    @model_validator(mode="after")
    def validate_evidence(self):
        now = datetime.now(timezone.utc)
        if self.collected_at.tzinfo is None or self.collected_at > now:
            raise ValueError("Collection date must be timezone aware and not in the future.")
        if self.review_status == "reviewed" and (not self.reviewed_by or self.reviewed_at is None
                or self.reviewed_at.tzinfo is None or not self.collected_at <= self.reviewed_at <= now):
            raise ValueError("Reviewed labels require a reviewer and a valid review date.")
        if not enough_metadata(self):
            raise ValueError("A description or public reviews are required, not just a name.")
        return self


def app_groups(rows):
    """Union evidenced families, package versions and identical feature text."""
    parent = {}

    def find(value):
        parent.setdefault(value, value)
        if parent[value] != value:
            parent[value] = find(parent[value])
        return parent[value]

    def union(a, b):
        a, b = find(a), find(b)
        parent[max(a, b)] = min(a, b)

    for row in rows:
        fingerprint = hashlib.sha256(metadata_text(row).lower().encode()).hexdigest()
        union("row:" + row.record_id, "text:" + fingerprint)
        union("row:" + row.record_id, "family:" + row.family_id)
        if row.package_name:
            union("row:" + row.record_id, "package:" + row.package_name)
    return [find("row:" + row.record_id) for row in rows]


def read_dataset(path: Path):
    if path.stat().st_size > 50_000_000:
        raise ValueError("App dataset exceeds 50 MB.")
    rows = []
    for index, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        if not line.strip():
            continue
        try:
            rows.append(AppObservation.model_validate_json(line))
        except ValidationError:
            raise ValueError(f"Invalid app observation at line {index}; inspect required metadata and provenance privately.") from None
        if len(rows) > 20000:
            raise ValueError("App dataset exceeds 20,000 observations.")
    if not rows or len({r.record_id for r in rows}) != len(rows):
        raise ValueError("Supply nonempty observations with unique record IDs.")
    fingerprints = {}
    for row in rows:
        fingerprint = metadata_text(row).lower()
        if fingerprint in fingerprints and fingerprints[fingerprint] != row.classification:
            raise ValueError("Identical app metadata has conflicting labels; resolve before training.")
        fingerprints[fingerprint] = row.classification
    eligible = []
    unique_text = set()
    for row in sorted(rows, key=lambda r: r.record_id):
        fingerprint = metadata_text(row).lower()
        if row.usage_allowed and row.review_status == "reviewed" and row.classification != "unknown" and fingerprint not in unique_text:
            eligible.append(row)
            unique_text.add(fingerprint)
    return rows, eligible


def eligible_groups(rows, eligible):
    # Excluded observations may still contain an evidenced alias connection.
    groups = dict(zip((r.record_id for r in rows), app_groups(rows)))
    return [groups[r.record_id] for r in eligible]


def audit(path):
    rows, eligible = read_dataset(path)
    return {"input": "application_metadata", "dataset_sha256": sha256(path), "rows": len(rows),
            "eligible_rows": len(eligible), "excluded_rows": len(rows) - len(eligible),
            "class_counts": dict(Counter(r.classification for r in eligible)),
            "independent_groups": len(set(eligible_groups(rows, eligible))),
            "synthetic_rows": sum(r.synthetic for r in rows),
            "eligible_field_presence": {field: sum(bool(getattr(row, field)) for row in eligible)
                                        for field in ("description", "keywords", "permissions", "reviews")},
            "feature_fields": ["app_name", "description", "keywords", "permissions", "reviews"]}


def classification_metrics(truth, predicted):
    from sklearn.metrics import accuracy_score, confusion_matrix, f1_score, precision_score, recall_score
    tn, fp, fn, tp = map(int, confusion_matrix(truth, predicted, labels=[0, 1]).ravel())
    sensitivity = tp / (tp + fn) if tp + fn else None
    specificity = tn / (tn + fp) if tn + fp else None
    return {"rows": len(truth), "confusion_matrix": [[tn, fp], [fn, tp]],
            "accuracy": float(accuracy_score(truth, predicted)),
            "precision": float(precision_score(truth, predicted, zero_division=0)),
            "sensitivity": sensitivity, "specificity": specificity,
            "true_skill_statistic": sensitivity + specificity - 1 if sensitivity is not None and specificity is not None else None,
            "f1": float(f1_score(truth, predicted, zero_division=0))}


def pipelines():
    from sklearn.ensemble import RandomForestClassifier
    from sklearn.feature_extraction.text import TfidfVectorizer
    from sklearn.linear_model import LogisticRegression
    from sklearn.pipeline import Pipeline
    from sklearn.svm import LinearSVC
    estimators = {
        "logistic_regression": LogisticRegression(solver="liblinear", class_weight="balanced", max_iter=500, random_state=42),
        "svm": LinearSVC(class_weight="balanced", max_iter=5000, random_state=42, dual="auto"),
        "random_forest": RandomForestClassifier(n_estimators=64, max_depth=14, min_samples_leaf=2,
                                                class_weight="balanced_subsample", n_jobs=1, random_state=42),
    }
    return {name: Pipeline([("text", TfidfVectorizer(lowercase=True, strip_accents="unicode", ngram_range=(1, 2),
                                                   min_df=1, max_features=8000, sublinear_tf=True)),
                             ("classifier", estimator)]) for name, estimator in estimators.items()}


def write_json(path, value):
    path.write_text(json.dumps(value, indent=2, sort_keys=True, allow_nan=False) + "\n", encoding="utf-8")


def compare(dataset: Path, run: Path, *, software_test=False, minimum=20):
    import numpy as np
    import skops.io as sio
    from sklearn.base import clone
    from sklearn.model_selection import StratifiedGroupKFold, cross_val_predict
    from threadpoolctl import threadpool_limits

    report = audit(dataset)
    rows, eligible = read_dataset(dataset)
    if any(r.synthetic for r in rows) and not software_test:
        raise ValueError("Synthetic observations are software fixtures, never study/deployment data.")
    groups = np.asarray(eligible_groups(rows, eligible))
    truth = np.asarray([int(r.classification == "gambling") for r in eligible])
    texts = [metadata_text(r) for r in eligible]
    if len(set(groups)) < 5 or any(sum(truth == c) < 5 for c in (0, 1)):
        raise ValueError("Collect both classes and at least five independent app families.")
    # One fixed fold reserves about 20% of independent groups; never search seeds.
    development, test = next(StratifiedGroupKFold(n_splits=5, shuffle=True, random_state=42).split(texts, truth, groups))
    for indices in (development, test):
        if min(sum(truth[indices] == c) for c in (0, 1)) < minimum:
            raise ValueError("Fixed 80/20 split has too few examples of a class; collect more data.")
    dev_groups, dev_truth = groups[development], truth[development]
    folds = list(StratifiedGroupKFold(n_splits=3, shuffle=True, random_state=43).split(development, dev_truth, dev_groups))
    if any(len(set(dev_truth[train])) != 2 or len(set(dev_truth[val])) != 2 for train, val in folds):
        raise ValueError("Development folds lack both classes; collect more independent groups.")
    if set(groups[development]) & set(groups[test]):
        raise ValueError("App family leakage detected.")
    run.mkdir(parents=True, exist_ok=False)
    membership = {name: [{"record_id": eligible[i].record_id, "group": str(groups[i]), "label": int(truth[i])}
                         for i in indices] for name, indices in (("development", development), ("test", test))}
    write_json(run / "split.json", {"dataset_sha256": report["dataset_sha256"], "seed": 42,
                                    "protocol": "grouped_80_20_with_3_fold_development_selection", **membership})
    dev_text = [texts[i] for i in development]
    test_text = [texts[i] for i in test]
    results, fitted = {}, {}
    with threadpool_limits(limits=1):
        for name, pipeline in pipelines().items():
            started = time.perf_counter()
            predicted = cross_val_predict(clone(pipeline), dev_text, dev_truth, cv=folds, method="predict", n_jobs=1)
            cv_time = time.perf_counter() - started
            started = time.perf_counter()
            pipeline.fit(dev_text, dev_truth)
            train_time = time.perf_counter() - started
            results[name] = {"development_cv": classification_metrics(dev_truth, predicted),
                             "development_fit": classification_metrics(dev_truth, pipeline.predict(dev_text)),
                             "cv_seconds": cv_time, "training_seconds": train_time}
            fitted[name] = pipeline
        # Selection locked before any held-out prediction, prioritizing low FP.
        preference = {"logistic_regression": 2, "svm": 1, "random_forest": 0}
        selected = max(results, key=lambda name: (results[name]["development_cv"]["true_skill_statistic"],
                                                  results[name]["development_cv"]["specificity"],
                                                  results[name]["development_cv"]["precision"], preference[name]))
        write_json(run / "selection.json", {"selected": selected, "basis": "development_cv_only", "results": results})
        write_json(run / "evaluation_started.json", {"held_out_exposed": True, "selected": selected})
        predictions = []
        for name, pipeline in fitted.items():
            predicted = pipeline.predict(test_text)
            elapsed = []
            for text in test_text[:100]:
                start = time.perf_counter(); pipeline.predict([text]); elapsed.append((time.perf_counter() - start) * 1000)
            results[name]["held_out"] = classification_metrics(truth[test], predicted)
            results[name]["latency_ms"] = {"median": float(np.median(elapsed)), "p95": float(np.quantile(elapsed, .95)),
                                            "samples": len(elapsed), "scope": "model_only_excludes_network_device"}
            if name == selected:
                predictions = [{"record_id": eligible[i].record_id, "truth": int(truth[i]), "prediction": int(p)}
                               for i, p in zip(test, predicted)]
        sio.dump(fitted[selected], run / "model.skops")
    manifest = {"format": FORMAT, "purpose": "software_test" if software_test else "candidate", "synthetic": bool(report["synthetic_rows"]),
                "algorithm": selected, "labels": {"non_gambling": 0, "gambling": 1}, "environment": environment(),
                "feature_sha256": feature_hash(), "model_sha256": sha256(run / "model.skops"),
                "dataset_sha256": report["dataset_sha256"], "model_version": f"app-{selected}-{report['dataset_sha256'][:12]}",
                "held_out_evaluation": results[selected]["held_out"], "approval": None}
    write_json(run / "manifest.json", manifest)
    write_json(run / "predictions.json", predictions)
    result = {"input": "application_metadata", "selected": selected, "selection_basis": "development_cv_only",
              "audit": report, "development_rows": len(development), "test_rows": len(test), "results": results,
              "human_expert_comparison": "not_collected", "student_exposure_reduction": "not_measured",
              "limitations": ["Metrics describe this dataset, not all apps or BISU students.",
                              "Permissions alone are not proof of gambling.", "No calibrated confidence or on-device model.",
                              "Synthetic software fixtures never establish capstone results."]}
    write_json(run / "comparison.json", result)
    return result


def export(run: Path, output: Path, reviewer: str, note: str):
    import shutil
    from app.ml.application_artifacts import load_application_artifact
    if not reviewer.strip() or len(note.strip()) < 20:
        raise ValueError("Supply a reviewer identifier and a substantive evaluation/scope note.")
    pipeline, manifest = load_application_artifact(run, sha256(run / "manifest.json"), deployment=False)
    del pipeline
    if manifest.get("synthetic") is not False or manifest.get("purpose") != "candidate":
        raise ValueError("Only a real-data candidate can be exported.")
    comparison = json.loads((run / "comparison.json").read_text(encoding="utf-8"))
    selected = json.loads((run / "selection.json").read_text(encoding="utf-8"))["selected"]
    if comparison["selected"] != selected or manifest["algorithm"] != selected or not manifest["held_out_evaluation"]:
        raise ValueError("Selection and held-out evaluation are inconsistent.")
    # Explicit minimum release gates; research review must also assess subgroup errors.
    measured = manifest["held_out_evaluation"]
    if (measured["rows"] < 40 or measured["precision"] < .95 or measured["specificity"] < .98
            or measured["sensitivity"] < .80):
        raise ValueError("Held-out app model does not meet release gates; retain advisory/manual protection.")
    output.mkdir(parents=True, exist_ok=False)
    shutil.copy2(run / "model.skops", output / "model.skops")
    for name in ("split.json", "selection.json", "comparison.json"):
        shutil.copy2(run / name, output / name)
    manifest.update(purpose="deployment", approval={"reviewed_by": reviewer.strip(), "note": note.strip(),
                                                  "reviewed_at": datetime.now(timezone.utc).isoformat()})
    write_json(output / "manifest.json", manifest)
    return {"manifest_sha256": sha256(output / "manifest.json"), "model_version": manifest["model_version"]}


def compare_experts(predictions_path: Path, experts_path: Path):
    from scipy.stats import binomtest
    from sklearn.metrics import cohen_kappa_score
    predictions = json.loads(predictions_path.read_text(encoding="utf-8"))
    labels = [json.loads(line) for line in experts_path.read_text(encoding="utf-8").splitlines() if line.strip()]
    expected = {r["record_id"] for r in predictions}
    if not expected or len(expected) != len(predictions) or len(labels) != len(expected):
        raise ValueError("Supply one independent expert decision for every held-out prediction.")
    by_id = {r["record_id"]: r for r in labels}
    if set(by_id) != expected or any(r.get("label") not in (0, 1) or type(r.get("label")) is not int
            or r.get("blinded_to_model") is not True or not str(r.get("reviewed_by", "")).strip() for r in labels):
        raise ValueError("Expert labels require matching unique IDs, binary labels, a reviewer and blinded_to_model=true.")
    if any(type(r.get(key)) is not int or r[key] not in (0, 1) for r in predictions for key in ("truth", "prediction")):
        raise ValueError("Invalid held-out predictions.")
    truth = [r["truth"] for r in predictions]
    if set(truth) != {0, 1}:
        raise ValueError("Expert comparison requires both true classes.")
    model = [r["prediction"] for r in predictions]
    expert = [by_id[r["record_id"]]["label"] for r in predictions]
    model_only = sum(m == t and e != t for m, e, t in zip(model, expert, truth))
    expert_only = sum(m != t and e == t for m, e, t in zip(model, expert, truth))
    return {"rows": len(truth), "model": classification_metrics(truth, model),
            "expert": classification_metrics(truth, expert), "model_expert_agreement": sum(m == e for m, e in zip(model, expert)) / len(truth),
            "cohen_kappa": float(cohen_kappa_score(model, expert)) if len(set(model + expert)) == 2 else None,
            "mcnemar_discordant": {"model_correct_expert_wrong": model_only, "expert_correct_model_wrong": expert_only},
            "mcnemar_exact_p": float(binomtest(model_only, model_only + expert_only, .5).pvalue) if model_only + expert_only else 1.0,
            "scope": "paired held-out cases; no claim of student exposure reduction"}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    schema = sub.add_parser("schema"); schema.add_argument("output", type=Path)
    data_audit = sub.add_parser("audit"); data_audit.add_argument("dataset", type=Path)
    training = sub.add_parser("compare"); training.add_argument("dataset", type=Path); training.add_argument("--run", type=Path, required=True)
    release = sub.add_parser("export"); release.add_argument("--run", type=Path, required=True); release.add_argument("--output", type=Path, required=True)
    release.add_argument("--reviewed-by", required=True); release.add_argument("--review-note", required=True)
    human = sub.add_parser("experts"); human.add_argument("predictions", type=Path); human.add_argument("labels", type=Path); human.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    try:
        if args.command == "schema":
            write_json(args.output, AppObservation.model_json_schema()); result = {"schema": str(args.output)}
        elif args.command == "audit": result = audit(args.dataset)
        elif args.command == "compare":
            report = compare(args.dataset, args.run); result = {"report": str(args.run / "comparison.json"), "selected": report["selected"]}
        elif args.command == "export": result = export(args.run, args.output, args.reviewed_by, args.review_note)
        else:
            result = compare_experts(args.predictions, args.labels); write_json(args.output, result)
        print(json.dumps(result, indent=2, allow_nan=False))
    except (OSError, ValueError, KeyError, TypeError):
        parser.exit(1, "Application research command failed. Check dataset schema, independent groups, provenance, release gates and unused output path. No deployed model was changed.\n")


if __name__ == "__main__":
    main()
