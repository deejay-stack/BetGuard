
"""
BETGUARD - PHILIPPINE VERIFICATION DATASET MERGER V1

Combines:
    544 existing PAGCOR verification records
    106 expanded benign candidates

Expected result for current inputs:
    518 PAGCOR positive candidates
    106 benign candidates
    624 total candidate domains

SAFETY
------
- Existing master rows and review fields are preserved.
- Only genuinely new benign domains are appended.
- Original CSV files are never changed.
- Conflicting labels and families cause an error.
- Output folders are never overwritten.
- Existing random audit selection is not changed.
- No labels are automatically verified.
- No machine learning model is trained or deployed.
"""

import argparse
import csv
import hashlib
import json
import os
import shutil
import tempfile

from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path


# ====================================================
# PATHS
# ====================================================

ML_ROOT = Path(__file__).resolve().parents[1]

PH_ROOT = (
    ML_ROOT / "data" / "expanded" / "pagcor_ph"
)

DEFAULT_MASTER = (
    PH_ROOT
    / "audit_v1"
    / "verification_v1"
    / "ph_verification_master.csv"
)

DEFAULT_BENIGN = (
    PH_ROOT
    / "benign_expansion_v1"
    / "ph_benign_expanded_candidates.csv"
)

DEFAULT_OUTPUT = (
    PH_ROOT
    / "audit_v1"
    / "verification_v2"
)

HISTORICAL_DIR = (
    ML_ROOT / "data" / "processed" / "splits"
)

HISTORICAL_SPLITS = {
    "train": "baseline_train.csv",
    "validation": "baseline_validation.csv",
    "test": "baseline_test.csv",
}


# ====================================================
# OUTPUT COLUMNS
# ====================================================

ADDED_COLUMNS = [
    "benign_candidate_reference_url",
    "benign_ph_relevance_status",
    "benign_review_priority",
    "benign_historical_overlap",
    "merged_excel_row",
]

QUEUE_COLUMNS = [
    "merged_excel_row",
    "domain",
    "domain_family",
    "suggested_label",
    "category",
    "source",
    "benign_candidate_reference_url",
    "benign_review_priority",
    "verification_status",
    "review_status",
    "verified_label",
    "evidence_reference",
    "reviewed_by",
    "historical_exact_family_overlap",
    "potential_holdout_status",
    "verification_groups",
]


# ====================================================
# HELPERS
# ====================================================

def now_utc():
    return datetime.now(
        timezone.utc
    ).isoformat()


def normalized(value):
    return (
        str(value or "")
        .strip()
        .lower()
        .rstrip(".")
    )


def read_csv(path):
    if not path.exists():
        raise FileNotFoundError(
            f"Missing input: {path}"
        )

    with path.open(
        "r",
        encoding="utf-8-sig",
        newline=""
    ) as handle:

        reader = csv.DictReader(handle)

        columns = list(
            reader.fieldnames or []
        )

        rows = list(reader)

    if not columns:
        raise RuntimeError(
            f"Missing CSV header: {path}"
        )

    return rows, columns


def write_csv(path, rows, columns):
    with path.open(
        "x",
        encoding="utf-8-sig",
        newline=""
    ) as handle:

        writer = csv.DictWriter(
            handle,
            fieldnames=columns,
            extrasaction="ignore",
        )

        writer.writeheader()
        writer.writerows(rows)


def file_hash(path):
    digest = hashlib.sha256()

    with path.open("rb") as handle:

        while True:
            chunk = handle.read(65536)

            if not chunk:
                break

            digest.update(chunk)

    return digest.hexdigest()


def require_columns(columns, required, name):
    missing = set(required) - set(columns)

    if missing:
        raise RuntimeError(
            f"Missing columns in {name}: "
            f"{sorted(missing)}"
        )


def review_has_progress(row):
    if normalized(
        row.get("review_status", "")
    ) not in ("", "pending"):
        return True

    for field in [
        "verified_label",
        "evidence_reference",
        "reviewed_by",
        "review_notes",
    ]:
        if str(
            row.get(field, "")
        ).strip():
            return True

    return False


# ====================================================
# HISTORICAL BENCHMARK CHECK
# ====================================================

def load_historical_families():
    family_splits = defaultdict(set)

    for split, filename in (
        HISTORICAL_SPLITS.items()
    ):
        path = HISTORICAL_DIR / filename

        rows, columns = read_csv(path)

        require_columns(
            columns,
            ["domain_family"],
            filename,
        )

        for row in rows:
            family = normalized(
                row.get("domain_family", "")
            )

            if family:
                family_splits[family].add(split)

    return family_splits


# ====================================================
# INPUT VALIDATION
# ====================================================

def validate_master(rows, columns):
    require_columns(
        columns,
        [
            "domain",
            "domain_family",
            "suggested_label",
            "review_status",
            "verified_label",
            "evidence_reference",
            "reviewed_by",
            "review_notes",
            "training_eligible",
            "verification_groups",
            "historical_exact_family_overlap",
            "historical_split_membership",
            "potential_holdout_status",
            "master_excel_row",
        ],
        "verification master",
    )

    found = set()

    for row in rows:
        domain = normalized(row["domain"])
        family = normalized(row["domain_family"])

        if not domain or not family:
            raise RuntimeError(
                "Master contains an empty "
                "domain or domain family."
            )

        if domain in found:
            raise RuntimeError(
                f"Duplicate master domain: {domain}"
            )

        found.add(domain)

        if row["suggested_label"] not in (
            "0", "1"
        ):
            raise RuntimeError(
                f"Invalid label: {domain}"
            )


def validate_expansion(rows, columns):
    require_columns(
        columns,
        [
            "domain",
            "domain_family",
            "suggested_label",
            "source",
            "category",
            "candidate_reference_url",
            "ph_relevance_status",
            "historical_overlap",
            "verification_status",
            "review_status",
            "verified_label",
            "evidence_reference",
            "reviewed_by",
            "review_notes",
            "training_eligible",
            "review_priority",
        ],
        "benign expansion",
    )

    found = set()

    for row in rows:
        domain = normalized(row["domain"])

        if not domain:
            raise RuntimeError(
                "Expanded candidate has no domain."
            )

        if domain in found:
            raise RuntimeError(
                f"Duplicate expanded domain: {domain}"
            )

        found.add(domain)

        if row["suggested_label"] != "0":
            raise RuntimeError(
                "Expanded benign dataset contains "
                f"a non-benign candidate: {domain}"
            )

        if normalized(
            row["training_eligible"]
        ) != "no":
            raise RuntimeError(
                "Expansion contains a training-"
                f"eligible record: {domain}"
            )

        if row["verified_label"] not in (
            "", "0", "1"
        ):
            raise RuntimeError(
                f"Invalid verified label: {domain}"
            )


# ====================================================
# PRESERVE EXISTING REVIEW RECORDS
# ====================================================

def check_overlapping_record(
    master_row,
    benign_row,
):
    domain = normalized(
        master_row["domain"]
    )

    if (
        normalized(master_row["domain_family"])
        != normalized(benign_row["domain_family"])
    ):
        raise RuntimeError(
            f"Family conflict: {domain}"
        )

    if (
        master_row["suggested_label"]
        != benign_row["suggested_label"]
    ):
        raise RuntimeError(
            f"Label conflict: {domain}"
        )

    # A reviewer might have edited either file.
    #
    # The existing master is authoritative,
    # but we must not silently discard work
    # found only in the expansion file.

    if review_has_progress(benign_row):

        fields = [
            "review_status",
            "verified_label",
            "evidence_reference",
            "reviewed_by",
            "review_notes",
        ]

        differences = [
            field
            for field in fields
            if (
                master_row.get(field, "")
                != benign_row.get(field, "")
            )
        ]

        if differences:
            raise RuntimeError(
                "Conflicting review entries for "
                f"{domain}: {differences}. "
                "Reconcile the two files manually "
                "before merging."
            )


# ====================================================
# BUILD NEW BENIGN ROW
# ====================================================

def create_new_row(
    benign_row,
    original_columns,
    historical_families,
):
    domain = normalized(
        benign_row["domain"]
    )

    family = normalized(
        benign_row["domain_family"]
    )

    splits = sorted(
        historical_families.get(
            family, set()
        )
    )

    overlap = bool(splits)

    priority = (
        benign_row.get(
            "review_priority", ""
        )
    )

    high_priority = priority.startswith(
        "HIGH"
    )

    groups = [
        "benign_review",
        "benign_expansion_v1",
    ]

    if high_priority:
        groups.append(
            "hard_negative_candidate_review"
        )

    if overlap:
        groups.append(
            "historical_overlap_review"
        )

    # Build the new row with the exact columns
    # expected by the existing master.

    row = {
        column: ""
        for column in original_columns
    }

    row.update({
        "domain": domain,

        "domain_family": family,

        "suggested_label": "0",

        "source": benign_row["source"],

        "source_pages": "",

        "document_dates": "",

        "category": benign_row["category"],

        "verification_status": (
            benign_row["verification_status"]
        ),

        "review_status": benign_row.get(
            "review_status", "pending"
        ),

        "verified_label": benign_row.get(
            "verified_label", ""
        ),

        "evidence_reference": benign_row.get(
            "evidence_reference", ""
        ),

        "reviewed_by": benign_row.get(
            "reviewed_by", ""
        ),

        "review_notes": benign_row.get(
            "review_notes", ""
        ),

        "training_eligible": "NO",

        "audit_flags": (
            "needs_careful_benign_review"
            if high_priority
            else ""
        ),

        "audit_priority": (
            "HIGH"
            if high_priority
            else "NORMAL"
        ),

        "canonical_www_host": (
            domain.removeprefix("www.")
        ),

        "family_host_count": "1",

        "official_source_urls": "",

        "review_scope": (
            "OPTION_A_DIRECT_REAL_MONEY_ONLINE"
        ),

        "verification_groups": (
            ";".join(groups)
        ),

        "historical_exact_family_overlap": (
            "YES" if overlap else "NO"
        ),

        "historical_split_membership": (
            ";".join(splits)
        ),

        "possible_same_name_brand_families": "",

        "potential_holdout_status": (
            "EXCLUDE_EXACT_HISTORICAL_FAMILY"
            if overlap
            else "UNVERIFIED_NOT_ASSIGNED"
        ),

        "source_pdf_entry_checked": "",

        "direct_real_money_wagering_checked": "",

        "review_evidence_type": "",

        "review_decision": "",

        "reviewed_at_utc": "",

        "second_reviewer": "",

        "master_excel_row": "",
    })

    # Additional columns specific to the new
    # benign expansion.

    row.update({
        "benign_candidate_reference_url": (
            benign_row.get(
                "candidate_reference_url", ""
            )
        ),

        "benign_ph_relevance_status": (
            benign_row.get(
                "ph_relevance_status", ""
            )
        ),

        "benign_review_priority": priority,

        "benign_historical_overlap": (
            benign_row.get(
                "historical_overlap", ""
            )
        ),
    })

    return row


# ====================================================
# MERGE DATASETS
# ====================================================

def merge_datasets(
    master_rows,
    master_columns,
    benign_rows,
    historical_families,
):

    # Copy every original row.
    # Original fields remain untouched.

    merged = [
        dict(row)
        for row in master_rows
    ]

    original_by_domain = {
        normalized(row["domain"]): row
        for row in merged
    }

    all_families = {
        normalized(row["domain_family"])
        for row in merged
    }

    existing_positive_families = {
        normalized(row["domain_family"])
        for row in merged
        if row["suggested_label"] == "1"
    }

    existing_benign_families = {
        normalized(row["domain_family"])
        for row in merged
        if row["suggested_label"] == "0"
    }

    additions = []
    overlap_count = 0

    for candidate in benign_rows:

        domain = normalized(
            candidate["domain"]
        )

        family = normalized(
            candidate["domain_family"]
        )

        if not family:
            raise RuntimeError(
                f"Missing family: {domain}"
            )

        if domain in original_by_domain:

            overlap_count += 1

            original = original_by_domain[domain]

            check_overlapping_record(
                original,
                candidate,
            )

            # Append new candidate metadata only
            # in NEW columns, without touching
            # any existing master review fields.

            original[
                "benign_candidate_reference_url"
            ] = candidate.get(
                "candidate_reference_url", ""
            )

            original[
                "benign_ph_relevance_status"
            ] = candidate.get(
                "ph_relevance_status", ""
            )

            original[
                "benign_review_priority"
            ] = candidate.get(
                "review_priority", ""
            )

            original[
                "benign_historical_overlap"
            ] = candidate.get(
                "historical_overlap", ""
            )

            continue

        if family in existing_positive_families:
            raise RuntimeError(
                "New benign domain shares a "
                "PAGCOR-positive family: "
                f"{domain}"
            )

        if family in existing_benign_families:
            raise RuntimeError(
                "New benign hostname shares an "
                "existing benign family: "
                f"{domain}"
            )

        if family in all_families:
            raise RuntimeError(
                "Repeated new domain family: "
                f"{family}"
            )

        new_row = create_new_row(
            candidate,
            master_columns,
            historical_families,
        )

        merged.append(new_row)
        additions.append(new_row)

        all_families.add(family)
        existing_benign_families.add(family)

    # Update only appended rows' legacy position
    # field. Original master_excel_row is preserved.
    #
    # merged_excel_row always records the correct
    # row in the newly generated output CSV.

    for index, row in enumerate(
        merged,
        start=2,
    ):
        row["merged_excel_row"] = str(index)

        if row in additions:
            row["master_excel_row"] = str(index)

    return merged, additions, overlap_count


# ====================================================
# INTEGRITY CHECKS
# ====================================================

def verify_merged_dataset(
    original_rows,
    original_columns,
    merged_rows,
):

    if len(merged_rows) < len(original_rows):
        raise RuntimeError(
            "Original records were removed."
        )

    for index, old_row in enumerate(
        original_rows
    ):

        new_row = merged_rows[index]

        for column in original_columns:
            if (
                old_row.get(column, "")
                != new_row.get(column, "")
            ):
                raise RuntimeError(
                    "Original review data changed "
                    f"at row {index + 2}: {column}"
                )

    domains = [
        normalized(row["domain"])
        for row in merged_rows
    ]

    if len(domains) != len(set(domains)):
        raise RuntimeError(
            "Duplicate domains in merged dataset."
        )

    positive_families = {
        normalized(row["domain_family"])
        for row in merged_rows
        if row["suggested_label"] == "1"
    }

    negative_families = {
        normalized(row["domain_family"])
        for row in merged_rows
        if row["suggested_label"] == "0"
    }

    if positive_families & negative_families:
        raise RuntimeError(
            "Cross-class family overlap "
            "in merged dataset."
        )

    print(
        "\nIntegrity checks: PASSED"
    )

    print(
        "Original master records preserved."
    )

    print(
        "Cross-class family overlap: 0"
    )


# ====================================================
# QUEUES AND REPORT
# ====================================================

def queue_sort_key(row):
    return (
        0 if row.get(
            "benign_review_priority", ""
        ).startswith("HIGH") else 1,

        row.get("category", ""),

        row["domain"],
    )


def build_summary(
    merged,
    additions,
    overlapping,
    original,
    master_path,
    benign_path,
):

    label_counts = Counter(
        row["suggested_label"]
        for row in merged
    )

    category_counts = Counter(
        row["category"]
        for row in merged
        if row["suggested_label"] == "0"
    )

    historic_new = sum(
        row["historical_exact_family_overlap"]
        == "YES"
        for row in additions
    )

    prior_reviews = sum(
        review_has_progress(row)
        for row in original
    )

    new_review_progress = sum(
        review_has_progress(row)
        for row in additions
    )

    return {
        "generated_at_utc": now_utc(),

        "project": "BetGuard",

        "version": (
            "ph_verification_merge_v1"
        ),

        "jurisdiction": "Philippines",

        "dataset_status": (
            "UNVERIFIED_CANDIDATES_WITH_"
            "PRESERVED_REVIEW_FIELDS"
        ),

        "counts": {
            "original_master_records": len(
                original
            ),

            "benign_expansion_inputs": (
                len(additions) + overlapping
            ),

            "already_present_benign_records": (
                overlapping
            ),

            "new_benign_records_added": (
                len(additions)
            ),

            "merged_total": len(merged),

            "positive_candidates": (
                label_counts["1"]
            ),

            "benign_candidates": (
                label_counts["0"]
            ),

            "original_review_progress_preserved": (
                prior_reviews
            ),

            "new_benign_review_progress_imported": (
                new_review_progress
            ),

            "new_benign_historical_overlap": (
                historic_new
            ),

            "new_verified_labels_automatically_"
            "created": 0,
        },

        "benign_category_counts": dict(
            sorted(category_counts.items())
        ),

        "input_checksums": {
            "verification_master_sha256": (
                file_hash(master_path)
            ),

            "benign_expansion_sha256": (
                file_hash(benign_path)
            ),
        },

        "verification_rules": [
            "Only human-supported labels "
            "are eligible for future training.",

            "PAGCOR registration by itself "
            "is not proof of direct wagering.",

            "Unresolved domains must not be "
            "automatically labeled benign.",

            "Previous evaluation families must "
            "not enter a virgin holdout.",

            "Original random audit remains fixed.",

            "Original reviewer fields remain "
            "unchanged.",

            "No training or deployment performed.",
        ],
    }


# ====================================================
# MAIN
# ====================================================

def main():

    parser = argparse.ArgumentParser()

    parser.add_argument(
        "--master",
        type=Path,
        default=DEFAULT_MASTER,
    )

    parser.add_argument(
        "--expanded",
        type=Path,
        default=DEFAULT_BENIGN,
    )

    parser.add_argument(
        "--output-dir",
        type=Path,
        default=DEFAULT_OUTPUT,
    )

    args = parser.parse_args()

    master_path = args.master.resolve()
    benign_path = args.expanded.resolve()

    output_dir = args.output_dir

    if not output_dir.is_absolute():
        output_dir = (
            ML_ROOT / output_dir
        ).resolve()

    else:
        output_dir = output_dir.resolve()

    print(
        "\nBETGUARD - PH VERIFICATION MERGER V1"
    )

    print(
        "===================================="
    )

    print(
        "No ML models will be modified."
    )

    if output_dir.exists():
        raise RuntimeError(
            "Output folder already exists: "
            f"{output_dir}\n"
            "Use --output-dir with a NEW folder."
        )

    master, master_columns = read_csv(
        master_path
    )

    benign, benign_columns = read_csv(
        benign_path
    )

    validate_master(
        master,
        master_columns
    )

    validate_expansion(
        benign,
        benign_columns
    )

    historical = load_historical_families()

    merged, additions, overlapping = (
        merge_datasets(
            master,
            master_columns,
            benign,
            historical,
        )
    )

    verify_merged_dataset(
        master,
        master_columns,
        merged,
    )

    merged_columns = list(
        master_columns
    )

    for column in ADDED_COLUMNS:
        if column not in merged_columns:
            merged_columns.append(column)

    new_queue = sorted(
        additions,
        key=queue_sort_key
    )

    all_benign_queue = sorted(
        [
            row
            for row in merged
            if row["suggested_label"] == "0"
        ],
        key=queue_sort_key
    )

    summary = build_summary(
        merged,
        additions,
        overlapping,
        master,
        master_path,
        benign_path,
    )

    filenames = {
        "merged_master": (
            "ph_verification_master_merged.csv"
        ),

        "new_benign_review": (
            "ph_new_benign_80_review_queue.csv"
        ),

        "all_benign_review": (
            "ph_all_benign_106_review_queue.csv"
        ),

        "summary": (
            "ph_merge_summary.json"
        ),
    }

    summary["output_filenames"] = filenames

    # Write to a temporary staging folder first.
    # Publish only when every file is complete.

    output_dir.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    stage = Path(
        tempfile.mkdtemp(
            prefix=".ph_verification_stage_",
            dir=output_dir.parent,
        )
    )

    try:

        write_csv(
            stage / filenames["merged_master"],
            merged,
            merged_columns,
        )

        write_csv(
            stage / filenames["new_benign_review"],
            new_queue,
            QUEUE_COLUMNS,
        )

        write_csv(
            stage / filenames["all_benign_review"],
            all_benign_queue,
            QUEUE_COLUMNS,
        )

        with (
            stage / filenames["summary"]
        ).open(
            "x",
            encoding="utf-8",
        ) as handle:

            json.dump(
                summary,
                handle,
                indent=2,
                ensure_ascii=False,
            )

        # Verify written master can be read back.

        written_rows, written_columns = read_csv(
            stage / filenames["merged_master"]
        )

        if (
            len(written_rows) != len(merged)
            or written_columns != merged_columns
        ):
            raise RuntimeError(
                "Output read-back validation failed."
            )

        # Output folder must not exist.
        # Prevent replacing any previous review work.

        if output_dir.exists():
            raise RuntimeError(
                "Output folder appeared during "
                "generation; refusing to overwrite."
            )

        os.rename(
            stage,
            output_dir,
        )

    except Exception:
        if stage.exists():
            shutil.rmtree(stage)
        raise

    print(
        "\n===================================="
    )

    print(
        "PHILIPPINE VERIFICATION MERGE COMPLETE"
    )

    print(
        "===================================="
    )

    for name, count in (
        summary["counts"].items()
    ):
        print(
            f"{name}: {count}"
        )

    print(
        "\nSaved files:"
    )

    for filename in filenames.values():
        print(
            output_dir / filename
        )

    print(
        "\nIMPORTANT:"
    )

    print(
        "Use ph_verification_master_merged.csv "
        "for human review."
    )

    print(
        "The two review queues are reference "
        "views only."
    )

    print(
        "No candidate labels were "
        "automatically verified."
    )

    print(
        "Original models and datasets unchanged."
    )


if __name__ == "__main__":
    main()
