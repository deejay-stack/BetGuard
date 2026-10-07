"""Summarize existing domain evidence and consented pilot measurements."""
import argparse
import json
from pathlib import Path

from ml_tools.application import classification_metrics, write_json


def metrics_from_counts(counts):
    tn, fp = counts[0]
    fn, tp = counts[1]
    return classification_metrics([0] * (tn + fp) + [1] * (fn + tp),
                                  [0] * tn + [1] * fp + [0] * fn + [1] * tp)


def existing_domain_evidence(ml_root: Path):
    from app.ml.application_artifacts import sha256
    candidate = json.loads((ml_root / "models/deployment_candidate.json").read_text(encoding="utf-8"))
    baseline = json.loads((ml_root / "reports/baseline_metrics.json").read_text(encoding="utf-8"))
    external_path = ml_root / "reports/external_holdout_metrics_v2.json"
    external = json.loads(external_path.read_text(encoding="utf-8"))
    model_file = ml_root / candidate["model_file"].replace("\\", "/")
    return {"input": "hostname", "trained_model_exists": model_file.is_file(),
            "model_file": candidate["model_file"].replace("\\", "/"), "model_sha256": sha256(model_file),
            "algorithm": baseline["model"], "runtime_integration": "FastAPI startup, /v1/domain/check, Android Smart DNS",
            "training_partition": {"train": baseline["train_size"], "validation": baseline["validation_size"], "test": baseline["test_size"]},
            "baseline_original_threshold": {"threshold": baseline["selected_threshold"],
                                            **metrics_from_counts(baseline["test_metrics"]["confusion_matrix"])},
            "selected_candidate_policy": {"threshold": candidate["threshold"], "source": "models/deployment_candidate.json",
                                          "metrics": candidate["test_metrics"]},
            "external_v2_hard_block_policy": {"warning_threshold": external["warning_threshold"],
                                              "block_threshold": external["automatic_block_threshold"],
                                              **metrics_from_counts(external["hard_block_metrics"]["confusion_matrix"])},
            "external_v2_review_or_block_policy": metrics_from_counts(external["intervention_metrics"]["confusion_matrix"]),
            "scope": "Derived from existing saved evaluations; no retraining or new test exposure.",
            "unmet_research_requirements": ["No trained SVM/Random Forest app-metadata artifacts found.",
                                           "Hostname metrics do not evaluate app descriptions or reviews.",
                                           "BISU human-expert comparison and student exposure study not collected.",
                                           "Existing 60/20/20 domain experiment differs from the manuscript's 80/20 protocol."],
            "caution": "WARN remains allowed. Hard-block recall and review-or-block recall measure different outcomes; neither measures student exposure reduction."}


def pilot_summary(path: Path):
    """External anonymized research observations, never automatic phone telemetry."""
    if path.stat().st_size > 5_000_000:
        raise ValueError("Pilot file exceeds 5 MB.")
    rows = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
    fields = {"participant_code", "phase", "consented", "gambling_attempts", "accessible_gambling_attempts"}
    if not rows:
        raise ValueError("No consented pilot observations supplied.")
    participants = {}
    for row in rows:
        if set(row) != fields or row["consented"] is not True or row["phase"] not in ("baseline", "protected"):
            raise ValueError("Use the anonymized consented pilot schema.")
        code = row["participant_code"]
        if not isinstance(code, str) or not code.startswith("P-") or not code[2:].isdigit() or len(code) > 16:
            raise ValueError("Use a pseudonymous P-number code; do not enter student names or contacts.")
        attempts, accessible = row["gambling_attempts"], row["accessible_gambling_attempts"]
        if type(attempts) is not int or type(accessible) is not int or not 0 <= accessible <= attempts <= 100000:
            raise ValueError("Use nonnegative observed counts with accessible <= attempts.")
        bucket = participants.setdefault(code, {})
        if row["phase"] in bucket:
            raise ValueError("Supply one observation per phase per participant.")
        bucket[row["phase"]] = (attempts, accessible)
    if any(set(phases) != {"baseline", "protected"} for phases in participants.values()):
        raise ValueError("Both matched phases are required for every participant.")
    result = {"participants": len(participants), "source": "consented_external_pilot_observations"}
    for phase in ("baseline", "protected"):
        attempts = sum(phases[phase][0] for phases in participants.values())
        accessible = sum(phases[phase][1] for phases in participants.values())
        result[phase] = {"gambling_attempts": attempts, "accessible_attempts": accessible,
                         "accessible_rate": accessible / attempts if attempts else None}
    before, after = result["baseline"]["accessible_rate"], result["protected"]["accessible_rate"]
    result["accessible_rate_change_percentage_points"] = (after - before) * 100 if before is not None and after is not None else None
    result["interpretation"] = "Descriptive matched observations only; not proof of causal improvement, population benefit, addiction reduction or actual student browsing exposure. Use approved simulated tasks rather than asking students to gamble."
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    existing = sub.add_parser("existing-model"); existing.add_argument("--ml-root", type=Path, default=Path(__file__).resolve().parents[2] / "ml")
    existing.add_argument("--output", type=Path, required=True)
    pilot = sub.add_parser("pilot"); pilot.add_argument("file", type=Path); pilot.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    try:
        report = existing_domain_evidence(args.ml_root) if args.command == "existing-model" else pilot_summary(args.file)
        write_json(args.output, report)
        print(json.dumps({"report": str(args.output), "status": "written"}))
    except (OSError, ValueError, KeyError, TypeError):
        parser.exit(1, "Could not create the capstone report. Check input schema and output directory; no model or phone data was changed.\n")


if __name__ == "__main__":
    main()
