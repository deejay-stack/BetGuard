
"""
BETGUARD - PAGCOR PH EVIDENCE REVIEW BATCH 1

Two commands:

PREPARE:
    python src/verify_pagcor_ph_batch1.py

CHECK:
    python src/verify_pagcor_ph_batch1.py --check PATH

Purpose:
    Prepare 100 frozen PAGCOR audit examples and
    17 Philippine hard-negative candidates for
    independent human evidence review.

Safety:
    - No automatic labels.
    - No gambling website requests.
    - No training or deployment.
    - No original datasets overwritten.
    - Human decisions require evidence.
    - Historical evaluation overlap is preserved.
"""

import argparse
import csv
import hashlib
import json
import sys

from collections import Counter
from datetime import datetime, timezone
from pathlib import Path


ML_ROOT = Path(__file__).resolve().parents[1]

ROOT = ML_ROOT / "data/expanded/pagcor_ph"

MASTER = (
    ROOT / "audit_v1/verification_v2"
    / "ph_verification_master_merged.csv"
)

FROZEN_AUDIT = (
    ROOT / "audit_v1"
    / "ph_random_100_family_audit.csv"
)

OUTPUT = (
    ROOT / "audit_v1"
    / "manual_review_batch1"
)

TEMPLATE_NAME = "ph_review_batch1_template.csv"
APPROVED_NAME = "ph_human_approved_batch1.csv"
REPORT_NAME = "ph_review_batch1_report.json"


STATIC_COLUMNS = [
    "domain",
    "domain_family",
    "review_group",
    "suggested_label",
    "category",
    "source",
    "source_pages",
    "official_source_urls",
    "candidate_reference_url",
    "audit_flags",
    "historical_exact_family_overlap",
    "possible_same_name_brand_families",
]

HUMAN_COLUMNS = [
    "review_decision",
    "verified_label",
    "source_pdf_entry_checked",
    "ph_relevance_checked",
    "direct_real_money_wagering_checked",
    "functionality_evidence_reference",
    "evidence_observation",
    "reviewed_by",
    "second_reviewer",
    "reviewed_at_utc",
]

ALL_COLUMNS = STATIC_COLUMNS + HUMAN_COLUMNS

APPROVED_COLUMNS = [
    "domain",
    "domain_family",
    "review_group",
    "suggested_label",
    "verified_label",
    "historical_exact_family_overlap",
    "functionality_evidence_reference",
    "evidence_observation",
    "reviewed_by",
    "second_reviewer",
    "reviewed_at_utc",
    "validation_timestamp_utc",
]


def now():
    return datetime.now(
        timezone.utc
    ).isoformat()


def normalize(value):
    return str(value or "").strip().lower()


def file_hash(path):
    return hashlib.sha256(
        path.read_bytes()
    ).hexdigest()


def read_csv(path):
    if not path.is_file():
        raise FileNotFoundError(path)

    with path.open(
        "r",
        encoding="utf-8-sig",
        newline="",
    ) as handle:
        reader = csv.DictReader(handle)

        columns = list(reader.fieldnames or [])
        rows = list(reader)

    if not columns:
        raise ValueError(
            f"No CSV header: {path}"
        )

    return rows, columns


def csv_safe(value):
    value = str(
        "" if value is None else value
    )

    # Protect spreadsheet applications against
    # formula-like content in imported CSV fields.
    if value.lstrip().startswith(
        ("=", "+", "-", "@")
    ):
        return "'" + value

    return value


def write_csv(path, rows, columns):
    with path.open(
        "x",
        encoding="utf-8-sig",
        newline="",
    ) as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=columns,
            extrasaction="ignore",
        )

        writer.writeheader()

        for row in rows:
            writer.writerow({
                column: csv_safe(
                    row.get(column, "")
                )
                for column in columns
            })


def check_columns(columns, required, name):
    missing = set(required) - set(columns)

    if missing:
        raise RuntimeError(
            f"Missing columns in {name}: "
            f"{sorted(missing)}"
        )


def make_review_row(item, group):
    return {
        "domain": item["domain"],
        "domain_family": item["domain_family"],
        "review_group": group,
        "suggested_label": item["suggested_label"],
        "category": item.get("category", ""),
        "source": item.get("source", ""),
        "source_pages": item.get(
            "source_pages", ""
        ),
        "official_source_urls": item.get(
            "official_source_urls", ""
        ),
        "candidate_reference_url": item.get(
            "benign_candidate_reference_url",
            "",
        ),
        "audit_flags": item.get(
            "audit_flags", ""
        ),
        "historical_exact_family_overlap": (
            item.get(
                "historical_exact_family_overlap",
                "NO",
            )
        ),
        "possible_same_name_brand_families": (
            item.get(
                "possible_same_name_brand_families",
                "",
            )
        ),
        **{
            column: ""
            for column in HUMAN_COLUMNS
        },
    }


def build_batch():

    master, master_columns = read_csv(MASTER)
    audit, audit_columns = read_csv(
        FROZEN_AUDIT
    )

    check_columns(
        master_columns,
        [
            "domain",
            "domain_family",
            "suggested_label",
            "benign_review_priority",
            "historical_exact_family_overlap",
        ],
        "merged master",
    )

    check_columns(
        audit_columns,
        [
            "domain",
            "domain_family",
            "suggested_label",
        ],
        "frozen audit",
    )

    master_by_domain = {}

    for row in master:
        key = normalize(row["domain"])

        if key in master_by_domain:
            raise RuntimeError(
                f"Duplicate master domain: {key}"
            )

        master_by_domain[key] = row

    if len(audit) != 100:
        raise RuntimeError(
            "The frozen audit must contain "
            "exactly 100 rows."
        )

    families = [
        normalize(row["domain_family"])
        for row in audit
    ]

    if len(set(families)) != 100:
        raise RuntimeError(
            "The frozen random audit does not "
            "contain 100 distinct families."
        )

    batch = []
    selected_domains = set()

    # Preserve the original random sample order.

    for source_row in audit:

        key = normalize(
            source_row["domain"]
        )

        original = master_by_domain.get(key)

        if original is None:
            raise RuntimeError(
                f"Frozen audit domain missing "
                f"from master: {key}"
            )

        if (
            normalize(
                original["domain_family"]
            )
            != normalize(
                source_row["domain_family"]
            )
        ):
            raise RuntimeError(
                f"Domain-family mismatch: {key}"
            )

        if original["suggested_label"] != "1":
            raise RuntimeError(
                f"Unexpected PAGCOR candidate "
                f"label: {key}"
            )

        if key in selected_domains:
            raise RuntimeError(
                f"Duplicate selected domain: {key}"
            )

        selected_domains.add(key)

        batch.append(
            make_review_row(
                original,
                "PAGCOR_RANDOM_AUDIT",
            )
        )

    # Select the 17 expanded Philippine
    # hard-negative candidates.

    hard_negatives = [
        item
        for item in master
        if (
            item["suggested_label"] == "0"
            and item.get(
                "benign_review_priority", ""
            ) == "HIGH_HARD_NEGATIVE_REVIEW"
        )
    ]

    if len(hard_negatives) != 17:
        raise RuntimeError(
            "Expected 17 hard-negative "
            "candidates; found "
            f"{len(hard_negatives)}. "
            "Inspect the merged master."
        )

    for item in sorted(
        hard_negatives,
        key=lambda row: row["domain"],
    ):
        key = normalize(item["domain"])

        if key in selected_domains:
            raise RuntimeError(
                f"Duplicate batch domain: {key}"
            )

        selected_domains.add(key)

        batch.append(
            make_review_row(
                item,
                "PH_HARD_NEGATIVE",
            )
        )

    if len(batch) != 117:
        raise RuntimeError(
            "Batch size is not 117."
        )

    return batch


def prepare():

    batch = build_batch()

    if OUTPUT.exists():
        raise RuntimeError(
            f"Output folder already exists:\n"
            f"{OUTPUT}\n"
            "Reviewer data will not be overwritten."
        )

    OUTPUT.mkdir(parents=True)

    template = OUTPUT / TEMPLATE_NAME

    write_csv(
        template,
        batch,
        ALL_COLUMNS,
    )

    report = {
        "generated_at_utc": now(),
        "project": "BetGuard",
        "jurisdiction": "Philippines",
        "status": "UNREVIEWED",
        "random_pagcor_audit": 100,
        "hard_negative_candidates": 17,
        "total_review_rows": 117,
        "historical_overlap_in_batch": sum(
            row[
                "historical_exact_family_overlap"
            ] == "YES"
            for row in batch
        ),
        "human_verified_labels": 0,
        "source_sha256": {
            "merged_master": file_hash(MASTER),
            "frozen_audit": file_hash(
                FROZEN_AUDIT
            ),
        },
        "template_sha256": file_hash(
            template
        ),
        "warning": (
            "No domain is training-eligible "
            "without independent human review."
        ),
    }

    report_path = (
        OUTPUT / "ph_batch1_manifest.json"
    )

    report_path.write_text(
        json.dumps(report, indent=2),
        encoding="utf-8",
    )

    print(
        "\nPH REVIEW BATCH 1 PREPARED"
    )

    print("PAGCOR random audit: 100")
    print("Hard-negative candidates: 17")
    print("Total review rows: 117")
    print("Verified labels: 0")
    print("\nTemplate:", template)


def validate_review(path):

    template_path = OUTPUT / TEMPLATE_NAME

    template, template_columns = read_csv(
        template_path
    )

    reviewed, reviewed_columns = read_csv(
        path
    )

    check_columns(
        reviewed_columns,
        ALL_COLUMNS,
        "completed review",
    )

    if len(reviewed) != len(template):
        raise RuntimeError(
            "Completed review row count differs "
            "from the frozen template."
        )

    approved = []
    errors = []
    decisions = Counter()

    valid_decisions = {
        "",
        "PENDING",
        "UNRESOLVED",
        "EXCLUDE",
        "VERIFY_0",
        "VERIFY_1",
    }

    for number, (original, row) in (
        enumerate(
            zip(template, reviewed),
            start=2,
        )
    ):
        domain = original["domain"]

        # Reviewers must not change candidate
        # identities, source pages, or existing
        # source labels.

        for column in STATIC_COLUMNS:
            if (
                original.get(column, "")
                != row.get(column, "")
            ):
                errors.append(
                    f"Row {number}: protected "
                    f"column changed: {column}"
                )

        decision = (
            row.get("review_decision", "")
            .strip()
            .upper()
        )

        label = (
            row.get("verified_label", "")
            .strip()
        )

        decisions[
            decision or "PENDING"
        ] += 1

        if decision not in valid_decisions:
            errors.append(
                f"Row {number} ({domain}): "
                "invalid review decision."
            )
            continue

        if decision not in (
            "VERIFY_0",
            "VERIFY_1",
        ):
            if label:
                errors.append(
                    f"Row {number} ({domain}): "
                    "unresolved/pending domain "
                    "has a verified label."
                )
            continue

        expected = decision[-1]

        if label != expected:
            errors.append(
                f"Row {number} ({domain}): "
                "verified_label does not match "
                "the human decision."
            )
            continue

        reviewer = (
            row.get("reviewed_by", "")
            .strip()
        )

        second = (
            row.get("second_reviewer", "")
            .strip()
        )

        observation = (
            row.get("evidence_observation", "")
            .strip()
        )

        evidence = (
            row.get(
                "functionality_evidence_reference",
                "",
            ).strip()
        )

        ph_relevance = (
            row.get(
                "ph_relevance_checked", ""
            ).strip().upper()
        )

        wagering = (
            row.get(
                "direct_real_money_wagering_checked",
                "",
            ).strip().upper()
        )

        pagcor_checked = (
            row.get(
                "source_pdf_entry_checked", ""
            ).strip().upper()
        )

        issues = []

        if not reviewer:
            issues.append("reviewer missing")

        if not evidence:
            issues.append(
                "functionality evidence missing"
            )

        if len(observation) < 20:
            issues.append(
                "detailed evidence observation missing"
            )

        if ph_relevance != "YES":
            issues.append(
                "Philippine relevance not confirmed"
            )

        if expected == "1":
            if pagcor_checked != "YES":
                issues.append(
                    "PAGCOR source entry not confirmed"
                )

            if wagering != "YES":
                issues.append(
                    "direct real-money wagering "
                    "not confirmed"
                )

            official = (
                row.get(
                    "official_source_urls", ""
                ).strip()
            )

            if evidence == official:
                issues.append(
                    "PAGCOR PDF alone is not "
                    "functionality evidence"
                )

        else:
            if wagering != "NO":
                issues.append(
                    "non-wagering function "
                    "not confirmed"
                )

        # Label corrections require an additional
        # reviewer because they reverse the
        # candidate source suggestion.

        if expected != row["suggested_label"]:
            if not second:
                issues.append(
                    "second reviewer required "
                    "for label correction"
                )

            elif normalize(second) == normalize(
                reviewer
            ):
                issues.append(
                    "second reviewer must differ "
                    "from first reviewer"
                )

        if issues:
            errors.append(
                f"Row {number} ({domain}): "
                + "; ".join(issues)
            )
            continue

        item = {
            column: row.get(column, "")
            for column in APPROVED_COLUMNS
            if column != "validation_timestamp_utc"
        }

        item["validation_timestamp_utc"] = now()

        approved.append(item)

    if errors:
        print(
            "\nREVIEW VALIDATION FAILED"
        )

        print(
            "Errors:", len(errors)
        )

        for error in errors[:20]:
            print("-", error)

        print(
            "\nCorrect the review CSV and "
            "run --check again."
        )

        sys.exit(1)

    if not approved:
        print(
            "\nNo completed verified labels yet."
        )

        print(
            "Fill in the review decisions and "
            "supporting evidence first."
        )

        return

    approved_file = (
        OUTPUT / APPROVED_NAME
    )

    report_file = (
        OUTPUT / REPORT_NAME
    )

    if (
        approved_file.exists()
        or report_file.exists()
    ):
        raise RuntimeError(
            "Approved output already exists. "
            "Keep it as an audit snapshot; "
            "do not overwrite it."
        )

    report = {
        "validated_at_utc": now(),
        "reviewed_file": str(path),
        "reviewed_file_sha256": file_hash(path),
        "approved_labels": len(approved),
        "approved_positive": sum(
            row["verified_label"] == "1"
            for row in approved
        ),
        "approved_negative": sum(
            row["verified_label"] == "0"
            for row in approved
        ),
        "review_decisions": dict(decisions),
        "validation_errors": 0,
        "model_training_performed": False,
        "note": (
            "Checks completeness and consistency "
            "of recorded reviewer evidence; "
            "does not independently establish "
            "that the evidence is true."
        ),
    }

    write_csv(
        approved_file,
        approved,
        APPROVED_COLUMNS,
    )

    report_file.write_text(
        json.dumps(
            report,
            indent=2,
        ),
        encoding="utf-8",
    )

    print(
        "\nREVIEW VALIDATION COMPLETE"
    )

    print(
        "Approved positive:",
        report["approved_positive"]
    )

    print(
        "Approved negative:",
        report["approved_negative"]
    )

    print(
        "Saved:", approved_file
    )

    print(
        "Saved:", report_file
    )

    print(
        "\nNo training or deployment changes."
    )


def main():
    parser = argparse.ArgumentParser()

    parser.add_argument(
        "--check",
        type=Path,
        default=None,
        help="Validate an edited review CSV.",
    )

    args = parser.parse_args()

    if args.check:
        validate_review(
            args.check.resolve()
        )

    else:
        prepare()


if __name__ == "__main__":
    main()
