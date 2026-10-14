
import hashlib
import json
import random

from datetime import datetime, timezone
from pathlib import Path

import pandas as pd


# ======================================================
# BETGUARD - EXPANDED DATASET REVIEW PREPARATION
# ======================================================
#
# IMPORTANT:
#
# Input labels are PUBLIC-LIST SUGGESTIONS.
# They are not automatically verified labels.
#
# No existing training, test, or deployment files
# will be modified.
#
# ======================================================


SEED = 42

ROOT = Path("data/expanded")

INPUT_FILE = (
    ROOT / "balanced_review_queue_v2.csv"
)

OUTPUT_DIR = (
    ROOT / "partitions_v1"
)

SPLIT_DIR = Path(
    "data/processed/splits"
)

HOLDOUT_PER_CLASS = 200
AUDIT_PER_CLASS = 100


# ======================================================
# HASH FILE
# ======================================================

def file_sha256(path):

    digest = hashlib.sha256()

    with path.open("rb") as handle:

        for chunk in iter(
            lambda: handle.read(1024 * 1024),
            b""
        ):
            digest.update(chunk)

    return digest.hexdigest()


# ======================================================
# LOAD DATA
# ======================================================

def load_csv(path):

    if not path.exists():
        raise FileNotFoundError(
            f"Missing file: {path}"
        )

    return pd.read_csv(
        path,
        dtype=str,
        keep_default_na=False,
    )


# ======================================================
# CHECK EXISTING BENCHMARK FAMILIES
# ======================================================

def load_old_families():

    files = [
        "baseline_train.csv",
        "baseline_validation.csv",
        "baseline_test.csv",
    ]

    old = set()

    for filename in files:

        df = load_csv(
            SPLIT_DIR / filename
        )

        if "domain_family" not in df.columns:
            raise ValueError(
                f"Missing domain_family in {filename}"
            )

        families = (
            df["domain_family"]
            .str.strip()
            .str.lower()
        )

        if (families == "").any():
            raise ValueError(
                f"Empty domain family in {filename}"
            )

        old.update(families)

    return old


# ======================================================
# VALIDATE NEW REVIEW QUEUE
# ======================================================

def validate_queue(df, old_families):

    required = {
        "domain",
        "domain_family",
        "suggested_label",
        "source",
        "category",
    }

    missing = required - set(df.columns)

    if missing:
        raise ValueError(
            f"Missing columns: {sorted(missing)}"
        )

    for column in [
        "domain",
        "domain_family",
        "suggested_label",
    ]:
        df[column] = (
            df[column]
            .str.strip()
            .str.lower()
        )

    if (df["domain"] == "").any():
        raise ValueError(
            "Empty domain detected."
        )

    if (df["domain_family"] == "").any():
        raise ValueError(
            "Empty domain family detected."
        )

    if not df["suggested_label"].isin(
        ["0", "1"]
    ).all():
        raise ValueError(
            "Invalid suggested label."
        )

    if df["domain"].duplicated().any():
        raise ValueError(
            "Duplicate domain detected."
        )

    if df["domain_family"].duplicated().any():
        raise ValueError(
            "Duplicate domain family detected. "
            "Review group collisions before splitting."
        )

    overlap = (
        set(df["domain_family"])
        &
        old_families
    )

    if overlap:
        raise RuntimeError(
            "Existing benchmark family overlap: "
            f"{len(overlap)}"
        )

    counts = df[
        "suggested_label"
    ].value_counts()

    gambling_count = int(
        counts.get("1", 0)
    )

    benign_count = int(
        counts.get("0", 0)
    )

    expected = (
        HOLDOUT_PER_CLASS
        +
        AUDIT_PER_CLASS
    )

    if min(
        gambling_count,
        benign_count
    ) <= expected:
        raise ValueError(
            "Insufficient examples for partitions."
        )

    print(
        "\nDataset integrity check: PASSED"
    )

    print(
        "Existing family overlap: 0"
    )

    print(
        "Unique domain families:",
        df["domain_family"].nunique()
    )

    print(
        "Gambling candidates:",
        gambling_count
    )

    print(
        "Benign candidates:",
        benign_count
    )

    return df


# ======================================================
# PARTITION ONE CLASS
# ======================================================

def partition_class(df, label):

    subset = (
        df[
            df["suggested_label"] == label
        ]
        .sort_values("domain")
        .reset_index(drop=True)
    )

    records = subset.to_dict(
        orient="records"
    )

    rng = random.Random(
        SEED + int(label)
    )

    rng.shuffle(records)

    holdout = records[
        :HOLDOUT_PER_CLASS
    ]

    audit_start = HOLDOUT_PER_CLASS

    audit_end = (
        audit_start + AUDIT_PER_CLASS
    )

    audit = records[
        audit_start:audit_end
    ]

    development = records[
        audit_end:
    ]

    return development, audit, holdout


# ======================================================
# REVIEW TEMPLATE
# ======================================================

def create_review_template(records):

    df = pd.DataFrame(
        records
    )

    df["review_status"] = "pending"
    df["verified_label"] = ""
    df["evidence_reference"] = ""
    df["reviewed_by"] = ""
    df["review_notes"] = ""

    return df


# ======================================================
# CHECK PARTITION LEAKAGE
# ======================================================

def check_partition_leakage(
    development,
    audit,
    holdout
):

    groups = [
        set(df["domain_family"])
        for df in (
            development,
            audit,
            holdout
        )
    ]

    if (
        groups[0] & groups[1]
        or groups[0] & groups[2]
        or groups[1] & groups[2]
    ):
        raise RuntimeError(
            "Domain-family leakage "
            "between new partitions."
        )

    print(
        "\nNew partition leakage check: PASSED"
    )


# ======================================================
# MAIN
# ======================================================

def main():

    print(
        "\nBETGUARD - EXPANDED DATASET AUDIT"
    )

    print(
        "================================"
    )

    old_families = load_old_families()

    df = load_csv(
        INPUT_FILE
    )

    df = validate_queue(
        df,
        old_families
    )

    development = []
    audit = []
    holdout = []

    for label in ["0", "1"]:

        dev_part, audit_part, hold_part = (
            partition_class(
                df,
                label
            )
        )

        development.extend(dev_part)
        audit.extend(audit_part)
        holdout.extend(hold_part)

    dev_df = pd.DataFrame(
        development
    )

    audit_df = create_review_template(
        audit
    )

    holdout_df = create_review_template(
        holdout
    )

    check_partition_leakage(
        dev_df,
        audit_df,
        holdout_df
    )

    OUTPUT_DIR.mkdir(
        parents=True,
        exist_ok=True
    )

    output_files = {
        "development":
            OUTPUT_DIR / "development_candidates.csv",

        "audit":
            OUTPUT_DIR / "audit_review_template.csv",

        "holdout":
            OUTPUT_DIR / "holdout_review_template.csv",
    }

    dev_df.to_csv(
        output_files["development"],
        index=False
    )

    audit_df.to_csv(
        output_files["audit"],
        index=False
    )

    holdout_df.to_csv(
        output_files["holdout"],
        index=False
    )

    manifest = {
        "created_at_utc":
            datetime.now(
                timezone.utc
            ).isoformat(),

        "random_seed": SEED,

        "source_file":
            str(INPUT_FILE),

        "source_sha256":
            file_sha256(INPUT_FILE),

        "label_type":
            "unverified_source_suggestion",

        "counts": {
            "development": len(dev_df),
            "audit": len(audit_df),
            "holdout": len(holdout_df),
        },

        "partitions": {
            name: {
                "path": str(path),
                "sha256": file_sha256(path),
            }
            for name, path in output_files.items()
        },

        "holdout_policy":
            "Reserve before model development. "
            "Do not tune models or thresholds on "
            "holdout predictions.",
    }

    manifest_file = (
        OUTPUT_DIR / "partition_manifest.json"
    )

    manifest_file.write_text(
        json.dumps(
            manifest,
            indent=2
        ),
        encoding="utf-8"
    )

    print(
        "\n================================"
    )

    print(
        "PARTITIONING COMPLETE"
    )

    print(
        "================================"
    )

    for name, part in [
        ("Development", dev_df),
        ("Audit", audit_df),
        ("Holdout", holdout_df),
    ]:

        counts = (
            part["suggested_label"]
            .value_counts()
        )

        print(
            f"\n{name}: {len(part)}"
        )

        print(
            "  Gambling:",
            counts.get("1", 0)
        )

        print(
            "  Non-gambling:",
            counts.get("0", 0)
        )

    print(
        "\nFiles:"
    )

    for path in output_files.values():
        print(path)

    print(manifest_file)

    print(
        "\nIMPORTANT:"
    )

    print(
        "Development labels are unverified."
    )

    print(
        "No models or original splits changed."
    )

    print(
        "Holdout candidates are reserved "
        "and must be independently reviewed."
    )


if __name__ == "__main__":
    main()
