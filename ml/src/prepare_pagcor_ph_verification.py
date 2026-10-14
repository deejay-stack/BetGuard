
"""
BETGUARD - PAGCOR PH VERIFICATION PREPARATION V1

PURPOSE
-------
Prepare Philippine domain candidates for human review.

Classification policy:
    1 = Direct real-money online gambling
    0 = No direct real-money online gambling

INPUTS
------
data/expanded/pagcor_ph/audit_v1/
    ph_candidate_inventory.csv
    ph_random_100_family_audit.csv
    ph_targeted_priority_review.csv
    ph_benign_26_review.csv

Historical benchmark inputs:
data/processed/splits/
    baseline_train.csv
    baseline_validation.csv
    baseline_test.csv

OUTPUTS
-------
One editable master review CSV, separate review queues,
and a JSON report.

IMPORTANT
---------
- Does not automatically confirm any domain labels.
- Does not access gambling websites.
- Does not retrain or deploy an ML model.
- Does not overwrite previously generated review sheets.
- Does not create or contaminate a new test set.
"""

import argparse
import csv
import hashlib
import json
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path


# ======================================================
# PROJECT PATHS
# ======================================================

ML_ROOT = Path(__file__).resolve().parents[1]

PH_ROOT = (
    ML_ROOT
    / "data"
    / "expanded"
    / "pagcor_ph"
)

AUDIT_ROOT = PH_ROOT / "audit_v1"

DEFAULT_OUTPUT = (
    AUDIT_ROOT / "verification_v1"
)

INVENTORY_FILE = (
    AUDIT_ROOT / "ph_candidate_inventory.csv"
)

RANDOM_FILE = (
    AUDIT_ROOT / "ph_random_100_family_audit.csv"
)

TARGETED_FILE = (
    AUDIT_ROOT / "ph_targeted_priority_review.csv"
)

BENIGN_FILE = (
    AUDIT_ROOT / "ph_benign_26_review.csv"
)

QUALITY_REPORT = (
    AUDIT_ROOT / "ph_quality_report.json"
)

PAGCOR_MANIFEST = (
    PH_ROOT / "ph_dataset_manifest.json"
)

HISTORICAL_DIR = (
    ML_ROOT / "data" / "processed" / "splits"
)

HISTORICAL_SPLITS = {
    "train": "baseline_train.csv",
    "validation": "baseline_validation.csv",
    "test": "baseline_test.csv",
}


# ======================================================
# VERIFICATION COLUMNS
# ======================================================

NEW_COLUMNS = [
    "verification_groups",
    "historical_exact_family_overlap",
    "historical_split_membership",
    "possible_same_name_brand_families",
    "potential_holdout_status",
    "source_pdf_entry_checked",
    "direct_real_money_wagering_checked",
    "review_evidence_type",
    "review_decision",
    "reviewed_at_utc",
    "second_reviewer",
    "master_excel_row",
]

QUEUE_COLUMNS = [
    "master_excel_row",
    "domain",
    "domain_family",
    "suggested_label",
    "source",
    "source_pages",
    "document_dates",
    "audit_priority",
    "audit_flags",
    "historical_exact_family_overlap",
    "historical_split_membership",
    "possible_same_name_brand_families",
    "official_source_urls",
    "verification_groups",
    "review_reason",
]


# ======================================================
# UTILITIES
# ======================================================

def utc_now():
    return datetime.now(
        timezone.utc
    ).isoformat()


def sha256_file(path):
    digest = hashlib.sha256()

    with path.open("rb") as handle:
        for chunk in iter(
            lambda: handle.read(65536),
            b"",
        ):
            digest.update(chunk)

    return digest.hexdigest()


def normalize(value):
    return (
        str(value or "")
        .strip()
        .lower()
        .rstrip(".")
    )


def read_csv(path):
    if not path.exists():
        raise FileNotFoundError(
            f"Required file missing: {path}"
        )

    with path.open(
        "r",
        encoding="utf-8-sig",
        newline="",
    ) as handle:

        reader = csv.DictReader(handle)

        fieldnames = list(
            reader.fieldnames or []
        )

        records = list(reader)

    if not fieldnames:
        raise RuntimeError(
            f"CSV has no columns: {path}"
        )

    return records, fieldnames


def csv_safe(value):
    """
    Avoid spreadsheet-formula execution when
    displaying imported text in spreadsheet apps.
    """

    value = str(
        value if value is not None else ""
    )

    if value.lstrip().startswith(
        ("=", "+", "-", "@")
    ):
        return "'" + value

    return value


def write_new_csv(path, rows, columns):
    """
    File creation is exclusive.

    If a reviewer has already edited a sheet,
    running the generator again cannot silently
    destroy their changes.
    """

    path.parent.mkdir(
        parents=True,
        exist_ok=True
    )

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


def write_new_json(path, data):
    with path.open(
        "x",
        encoding="utf-8",
    ) as handle:

        json.dump(
            data,
            handle,
            indent=2,
            ensure_ascii=False,
        )


def require_columns(
    fields,
    required,
    filename,
):
    missing = set(required) - set(fields)

    if missing:
        raise RuntimeError(
            f"Missing columns in {filename}: "
            f"{sorted(missing)}"
        )


# ======================================================
# LOAD HISTORICAL BENCHMARK FAMILIES
# ======================================================

def load_historical_families():

    family_to_splits = defaultdict(set)

    source_metadata = {}

    for split_name, filename in (
        HISTORICAL_SPLITS.items()
    ):

        path = HISTORICAL_DIR / filename

        rows, columns = read_csv(path)

        require_columns(
            columns,
            {"domain_family"},
            filename,
        )

        for row in rows:
            family = normalize(
                row.get("domain_family", "")
            )

            if family:
                family_to_splits[
                    family
                ].add(split_name)

        source_metadata[split_name] = {
            "path": str(path),
            "rows": len(rows),
            "sha256": sha256_file(path),
        }

    return (
        family_to_splits,
        source_metadata,
    )


# ======================================================
# VALIDATE INPUT DATA
# ======================================================

def validate_input(
    inventory,
    random_sample,
    targeted_sample,
    benign_sample,
):

    required = {
        "domain",
        "domain_family",
        "suggested_label",
        "source",
        "source_pages",
        "review_status",
        "verified_label",
        "training_eligible",
        "audit_flags",
        "audit_priority",
    }

    for row in inventory:

        if not required.issubset(
            row.keys()
        ):
            raise RuntimeError(
                "Inventory does not match the "
                "expected PAGCOR audit format."
            )

        if row["suggested_label"] not in (
            "0", "1"
        ):
            raise RuntimeError(
                "Unexpected candidate label."
            )

        if not normalize(
            row["domain_family"]
        ):
            raise RuntimeError(
                "Empty domain family."
            )

        if (
            row["review_status"].strip()
            != "pending"
            or row["verified_label"].strip()
        ):
            raise RuntimeError(
                "Input inventory contains review "
                "decisions. This generator expects "
                "the original unreviewed inventory."
            )

        if (
            row["training_eligible"].strip()
            != "NO"
        ):
            raise RuntimeError(
                "Unverified domain marked as "
                "training-eligible."
            )

    inventory_domains = [
        normalize(row["domain"])
        for row in inventory
    ]

    if len(inventory_domains) != len(
        set(inventory_domains)
    ):
        raise RuntimeError(
            "Duplicate domain in inventory."
        )

    index = {
        normalize(row["domain"]): row
        for row in inventory
    }

    def check_subset(
        name,
        subset,
        expected_label=None,
    ):

        seen = set()

        for row in subset:

            domain = normalize(
                row["domain"]
            )

            if domain in seen:
                raise RuntimeError(
                    f"Duplicate in {name}: {domain}"
                )

            seen.add(domain)

            if domain not in index:
                raise RuntimeError(
                    f"{name} contains an unknown "
                    f"domain: {domain}"
                )

            original = index[domain]

            if (
                normalize(
                    row["domain_family"]
                )
                != normalize(
                    original["domain_family"]
                )
            ):
                raise RuntimeError(
                    f"Family mismatch: {domain}"
                )

            if (
                row["suggested_label"]
                != original["suggested_label"]
            ):
                raise RuntimeError(
                    f"Label mismatch: {domain}"
                )

            if (
                expected_label is not None
                and row["suggested_label"]
                != expected_label
            ):
                raise RuntimeError(
                    f"Wrong source label in {name}."
                )

    check_subset(
        "random audit",
        random_sample,
        "1",
    )

    check_subset(
        "targeted review",
        targeted_sample,
        "1",
    )

    check_subset(
        "benign review",
        benign_sample,
        "0",
    )

    random_families = [
        normalize(row["domain_family"])
        for row in random_sample
    ]

    if len(random_sample) != 100:
        raise RuntimeError(
            "Expected the frozen 100-family "
            "PAGCOR audit sample."
        )

    if len(set(random_families)) != 100:
        raise RuntimeError(
            "Random sample repeats domain families."
        )

    positives = {
        normalize(row["domain_family"])
        for row in inventory
        if row["suggested_label"] == "1"
    }

    negatives = {
        normalize(row["domain_family"])
        for row in inventory
        if row["suggested_label"] == "0"
    }

    if positives & negatives:
        raise RuntimeError(
            "Cross-label domain-family conflict."
        )

    return index


# ======================================================
# SAME-NAME BRAND HINTS
# ======================================================

def get_brand_name(family):
    """
    Lightweight possible-brand hint.

    buenas.pro -> buenas
    buenas.bet -> buenas

    Identical base names across TLDs can suggest
    an association, but they do NOT prove that
    domains share ownership or an operator.
    """

    family = normalize(family)

    return family.split(".")[0]


def build_brand_hints(inventory):

    brand_to_families = defaultdict(set)

    for row in inventory:

        family = normalize(
            row["domain_family"]
        )

        brand = get_brand_name(family)

        if len(brand) < 3:
            continue

        brand_to_families[
            brand
        ].add(family)

    family_hints = {}

    for brand, families in (
        brand_to_families.items()
    ):

        if len(families) < 2:
            continue

        for family in families:

            siblings = sorted(
                families - {family}
            )

            family_hints[family] = (
                ";".join(siblings)
            )

    return family_hints


# ======================================================
# SECONDARY-DOMAIN REVIEW FLAGS
# ======================================================

SECONDARY_FLAGS = {
    "possible_promotion_or_support",
    "www_alias_also_listed",
    "deep_hostname_review",
}


def is_secondary_candidate(row):
    flags = set(
        row.get("audit_flags", "")
        .split(";")
    )

    return bool(
        flags & SECONDARY_FLAGS
    )


# ======================================================
# BUILD MASTER REVIEW SHEET
# ======================================================

def build_master(
    inventory,
    random_domains,
    targeted_domains,
    historical,
    brand_hints,
):

    master = []

    for row_number, original in enumerate(
        inventory,
        start=2,
    ):

        row = dict(original)

        domain = normalize(
            row["domain"]
        )

        family = normalize(
            row["domain_family"]
        )

        split_membership = sorted(
            historical.get(
                family, set()
            )
        )

        has_historical_overlap = bool(
            split_membership
        )

        groups = []

        if domain in random_domains:
            groups.append(
                "random_100_audit"
            )

        if domain in targeted_domains:
            groups.append(
                "targeted_priority_review"
            )

        if is_secondary_candidate(row):
            groups.append(
                "secondary_domain_review"
            )

        if has_historical_overlap:
            groups.append(
                "historical_overlap_review"
            )

        if row["suggested_label"] == "0":
            groups.append(
                "benign_review"
            )

        if family in brand_hints:
            groups.append(
                "possible_brand_alias_review"
            )

        row["verification_groups"] = (
            ";".join(groups)
        )

        row[
            "historical_exact_family_overlap"
        ] = (
            "YES"
            if has_historical_overlap
            else "NO"
        )

        row["historical_split_membership"] = (
            ";".join(split_membership)
        )

        row[
            "possible_same_name_brand_families"
        ] = brand_hints.get(
            family, ""
        )

        if has_historical_overlap:

            row["potential_holdout_status"] = (
                "EXCLUDE_EXACT_HISTORICAL_FAMILY"
            )

        else:

            row["potential_holdout_status"] = (
                "UNVERIFIED_NOT_ASSIGNED"
            )

        # These fields are exclusively for human review.
        # They must remain blank until a reviewer
        # actually checks the supporting evidence.

        row["source_pdf_entry_checked"] = ""
        row["direct_real_money_wagering_checked"] = ""
        row["review_evidence_type"] = ""
        row["review_decision"] = ""
        row["reviewed_at_utc"] = ""
        row["second_reviewer"] = ""

        row["master_excel_row"] = row_number

        master.append(row)

    return master


# ======================================================
# GENERATE NAVIGATION REVIEW QUEUES
# ======================================================

def build_queue(
    master_lookup,
    domains,
    reason,
):

    queue = []

    for domain in domains:

        domain = normalize(domain)

        if domain not in master_lookup:
            raise RuntimeError(
                f"Domain not in master: {domain}"
            )

        row = master_lookup[domain]

        entry = {
            name: row.get(name, "")
            for name in QUEUE_COLUMNS
        }

        entry["review_reason"] = reason

        queue.append(entry)

    return queue


# ======================================================
# SUMMARY REPORT
# ======================================================

def summarize(
    master,
    random_domains,
    targeted_domains,
    historical_metadata,
    input_paths,
):

    positive = [
        row for row in master
        if row["suggested_label"] == "1"
    ]

    benign = [
        row for row in master
        if row["suggested_label"] == "0"
    ]

    overlap = [
        row for row in positive
        if row[
            "historical_exact_family_overlap"
        ] == "YES"
    ]

    unique_overlap_families = {
        normalize(row["domain_family"])
        for row in overlap
    }

    random_rows = [
        row for row in master
        if normalize(
            row["domain"]
        ) in random_domains
    ]

    secondary = [
        row for row in positive
        if is_secondary_candidate(row)
    ]

    brand_hint_rows = [
        row for row in positive
        if row[
            "possible_same_name_brand_families"
        ]
    ]

    flags = Counter()

    for row in positive:
        for flag in (
            row.get("audit_flags", "")
            .split(";")
        ):
            if flag:
                flags[flag] += 1

    return {
        "generated_at_utc": utc_now(),

        "project": "BetGuard",

        "version": (
            "pagcor_ph_verification_preparation_v1"
        ),

        "jurisdiction": "Philippines",

        "classification_definition": {
            "1": (
                "Direct real-money online gambling"
            ),
            "0": (
                "No direct real-money online gambling"
            ),
        },

        "counts": {
            "total_candidates": len(master),

            "positive_candidates": len(positive),

            "benign_candidates": len(benign),

            "random_sample_domains": len(
                random_domains
            ),

            "random_sample_unique_families": len({
                normalize(
                    row["domain_family"]
                )
                for row in random_rows
            }),

            "targeted_priority_domains": len(
                targeted_domains
            ),

            "historical_overlap_hosts": len(
                overlap
            ),

            "historical_overlap_families": len(
                unique_overlap_families
            ),

            "random_historical_overlap": sum(
                row[
                    "historical_exact_family_overlap"
                ] == "YES"
                for row in random_rows
            ),

            "secondary_domain_review_hosts": len(
                secondary
            ),

            "possible_brand_alias_hosts": len(
                brand_hint_rows
            ),

            "human_verified_labels_created": 0,
        },

        "audit_flag_counts": dict(flags),

        "historical_benchmark_sources": (
            historical_metadata
        ),

        "input_sha256": {
            path.name: sha256_file(path)
            for path in input_paths
        },

        "verification_policy": [
            "PAGCOR PDF membership must be "
            "checked against the actual table.",

            "Positive labels require independently "
            "supported direct real-money wagering.",

            "A registered promotional domain is "
            "not automatically a direct operator.",

            "A negative label requires positive "
            "evidence of non-gambling function.",

            "Uncertain cases must remain unresolved "
            "or be excluded, not guessed.",

            "Domains already in historical "
            "benchmark families cannot be used "
            "as an untouched holdout.",

            "Brand name hints are unverified "
            "and must not be treated as proof "
            "of shared ownership.",

            "The random audit is fixed and "
            "must not be replaced after review.",

            "No labels are verified automatically.",

            "No model training or deployment "
            "changes are performed.",
        ],
    }


# ======================================================
# MAIN
# ======================================================

def main():

    parser = argparse.ArgumentParser(
        description=(
            "Prepare PAGCOR Philippine candidate "
            "domains for human verification."
        )
    )

    parser.add_argument(
        "--output-dir",
        type=Path,
        default=DEFAULT_OUTPUT,
        help=(
            "Use a different directory for a new "
            "review generation. Existing reviewer "
            "files are never overwritten."
        ),
    )

    args = parser.parse_args()

    output_dir = args.output_dir

    if not output_dir.is_absolute():
        output_dir = ML_ROOT / output_dir

    print(
        "\nBETGUARD - PAGCOR PH VERIFICATION V1"
    )

    print(
        "======================================"
    )

    print(
        "Jurisdiction: Philippines"
    )

    print(
        "Policy: Direct real-money gambling only"
    )

    print(
        "Mode: Offline review preparation"
    )

    # --------------------------------------------------
    # INPUT
    # --------------------------------------------------

    inventory, inventory_fields = read_csv(
        INVENTORY_FILE
    )

    random_sample, _ = read_csv(
        RANDOM_FILE
    )

    targeted_sample, _ = read_csv(
        TARGETED_FILE
    )

    benign_sample, _ = read_csv(
        BENIGN_FILE
    )

    validate_input(
        inventory,
        random_sample,
        targeted_sample,
        benign_sample,
    )

    historical, historical_metadata = (
        load_historical_families()
    )

    random_domains = {
        normalize(row["domain"])
        for row in random_sample
    }

    targeted_domains = {
        normalize(row["domain"])
        for row in targeted_sample
    }

    brand_hints = build_brand_hints(
        inventory
    )

    master = build_master(
        inventory,
        random_domains,
        targeted_domains,
        historical,
        brand_hints,
    )

    master_lookup = {
        normalize(row["domain"]): row
        for row in master
    }

    # --------------------------------------------------
    # REVIEW QUEUES
    # --------------------------------------------------

    random_queue = build_queue(
        master_lookup,
        [
            row["domain"]
            for row in random_sample
        ],
        "Frozen random family audit",
    )

    historical_queue = build_queue(
        master_lookup,
        [
            row["domain"]
            for row in master
            if row["suggested_label"] == "1"
            and row[
                "historical_exact_family_overlap"
            ] == "YES"
        ],
        "Exact historical benchmark family",
    )

    secondary_queue = build_queue(
        master_lookup,
        [
            row["domain"]
            for row in master
            if row["suggested_label"] == "1"
            and is_secondary_candidate(row)
        ],
        "Possible secondary or supporting domain",
    )

    targeted_queue = build_queue(
        master_lookup,
        [
            row["domain"]
            for row in targeted_sample
        ],
        "Previously flagged high-priority domain",
    )

    benign_queue = build_queue(
        master_lookup,
        [
            row["domain"]
            for row in benign_sample
        ],
        "Philippine benign candidate review",
    )

    brand_queue = build_queue(
        master_lookup,
        [
            row["domain"]
            for row in master
            if row[
                "possible_same_name_brand_families"
            ]
        ],
        "Possible same-name cross-TLD brand",
    )

    # --------------------------------------------------
    # OUTPUT FILES
    # --------------------------------------------------

    outputs = {
        "master": (
            output_dir
            / "ph_verification_master.csv"
        ),

        "random": (
            output_dir
            / "ph_random_100_review_queue.csv"
        ),

        "historical": (
            output_dir
            / "ph_historical_overlap_review_queue.csv"
        ),

        "secondary": (
            output_dir
            / "ph_secondary_domain_review_queue.csv"
        ),

        "targeted": (
            output_dir
            / "ph_targeted_priority_review_queue.csv"
        ),

        "benign": (
            output_dir
            / "ph_benign_26_review_queue.csv"
        ),

        "brand": (
            output_dir
            / "ph_possible_brand_aliases.csv"
        ),

        "summary": (
            output_dir
            / "ph_verification_summary.json"
        ),
    }

    # Check every target before writing anything.
    # This protects human reviewer edits.

    existing = [
        path
        for path in outputs.values()
        if path.exists()
    ]

    if existing:
        print(
            "\nExisting reviewer files detected:"
        )

        for path in existing:
            print(path)

        raise SystemExit(
            "\nStopped to protect existing work. "
            "Use --output-dir with a NEW folder "
            "if you want to regenerate templates."
        )

    output_dir.mkdir(
        parents=True,
        exist_ok=True
    )

    # --------------------------------------------------
    # WRITE REVIEW TEMPLATES
    # --------------------------------------------------

    master_columns = (
        inventory_fields
        +
        [
            name
            for name in NEW_COLUMNS
            if name not in inventory_fields
        ]
    )

    write_new_csv(
        outputs["master"],
        master,
        master_columns,
    )

    queues = {
        "random": random_queue,
        "historical": historical_queue,
        "secondary": secondary_queue,
        "targeted": targeted_queue,
        "benign": benign_queue,
        "brand": brand_queue,
    }

    for name, rows in queues.items():
        write_new_csv(
            outputs[name],
            rows,
            QUEUE_COLUMNS,
        )

    # --------------------------------------------------
    # SUMMARY
    # --------------------------------------------------

    report = summarize(
        master,
        random_domains,
        targeted_domains,
        historical_metadata,
        [
            INVENTORY_FILE,
            RANDOM_FILE,
            TARGETED_FILE,
            BENIGN_FILE,
        ],
    )

    report["outputs"] = {
        name: str(path)
        for name, path in outputs.items()
    }

    if QUALITY_REPORT.exists():
        report["prior_quality_report_sha256"] = (
            sha256_file(QUALITY_REPORT)
        )

    if PAGCOR_MANIFEST.exists():
        report["pagcor_manifest_sha256"] = (
            sha256_file(PAGCOR_MANIFEST)
        )

    report["master_review_instructions"] = {
        "editable_file": (
            "ph_verification_master.csv"
        ),

        "queue_files": (
            "Reference views only; edit the "
            "corresponding row in the master."
        ),

        "review_status_options": [
            "pending",
            "confirmed",
            "corrected",
            "excluded",
        ],

        "verified_label_options": [
            "0",
            "1",
            "blank_if_unresolved",
        ],

        "source_pdf_entry_checked_options": [
            "YES",
            "NO",
            "UNCERTAIN",
        ],

        "direct_real_money_wagering_checked_options": [
            "YES",
            "NO",
            "UNCERTAIN",
        ],

        "evidence_required": True,

        "no_automatic_acceptance": True,
    }

    write_new_json(
        outputs["summary"],
        report,
    )

    # --------------------------------------------------
    # TERMINAL REPORT
    # --------------------------------------------------

    print(
        "\n======================================"
    )

    print(
        "PAGCOR PH VERIFICATION PREPARATION COMPLETE"
    )

    print(
        "======================================"
    )

    for key, value in (
        report["counts"].items()
    ):
        print(f"{key}: {value}")

    print(
        "\nGenerated review files:"
    )

    for name, path in (
        outputs.items()
    ):
        print(f"  {name}: {path.name}")

    print(
        "\nIMPORTANT:"
    )

    print(
        "Edit ph_verification_master.csv "
        "only for human decisions."
    )

    print(
        "Other CSV files are navigation queues."
    )

    print(
        "Human labels created: 0"
    )

    print(
        "Production models modified: 0"
    )


if __name__ == "__main__":
    main()
