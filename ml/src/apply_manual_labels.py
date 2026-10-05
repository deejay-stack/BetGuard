from pathlib import Path

import pandas as pd


# =========================================================
# BETGUARD
# APPLY VERIFIED LABELS - V3
# =========================================================
#
# PURPOSE
#
# Combine:
#
# 1. External gambling verification
# 2. Manual human verification
#
# while safely handling domains that become duplicates
# after normalization.
#
#
# FINAL TARGET:
#
# final_verified_label
#
#     0 = verified non-gambling
#     1 = verified gambling
#     blank = unresolved
#
#
# IMPORTANT:
#
# The complete progress report preserves duplicate rows
# for investigation.
#
# The training-candidate output contains only ONE row per
# normalized domain to prevent ML data leakage later.
#
# =========================================================


# =========================================================
# PATHS
# =========================================================

BASE_REPORT = Path(
    "reports/benign_verification.csv"
)

MANUAL_LABELS_FILE = Path(
    "data/manual/verified_labels.csv"
)

OUTPUT_FILE = Path(
    "reports/verified_dataset_progress.csv"
)

TRAINABLE_FILE = Path(
    "data/processed/verified_training_candidates.csv"
)

UNRESOLVED_FILE = Path(
    "reports/unresolved_domains.csv"
)

DUPLICATE_REPORT_FILE = Path(
    "reports/duplicate_normalized_domains.csv"
)


# =========================================================
# DOMAIN NORMALIZATION
# =========================================================

def normalize_domain(domain):

    if pd.isna(domain):
        return ""

    domain = str(
        domain
    ).strip().lower()

    # Remove protocol
    if domain.startswith("https://"):

        domain = domain[
            len("https://"):
        ]

    elif domain.startswith("http://"):

        domain = domain[
            len("http://"):
        ]

    # Remove URL path
    domain = domain.split(
        "/"
    )[0]

    # Remove query
    domain = domain.split(
        "?"
    )[0]

    # Remove fragment
    domain = domain.split(
        "#"
    )[0]

    # Remove common www prefix
    if domain.startswith(
        "www."
    ):

        domain = domain[4:]

    # Remove trailing dot
    domain = domain.rstrip(
        "."
    )

    # Remove standard port
    #
    # example.com:443
    # ->
    # example.com

    if domain.count(":") == 1:

        hostname, possible_port = (
            domain.rsplit(
                ":",
                1
            )
        )

        if possible_port.isdigit():

            domain = hostname

    return domain


# =========================================================
# LOAD FILES
# =========================================================

def load_data():

    if not BASE_REPORT.exists():

        raise FileNotFoundError(
            f"\nCould not find:\n"
            f"{BASE_REPORT}\n\n"
            "Run verify_benign.py first."
        )

    if not MANUAL_LABELS_FILE.exists():

        raise FileNotFoundError(
            f"\nCould not find:\n"
            f"{MANUAL_LABELS_FILE}\n\n"
            "Run create_verified_labels.py first."
        )

    base = pd.read_csv(
        BASE_REPORT
    )

    manual = pd.read_csv(
        MANUAL_LABELS_FILE
    )

    return base, manual


# =========================================================
# VALIDATE BASE DATA
# =========================================================

def validate_base(base):

    required_columns = [
        "domain",
        "verified_label",
    ]

    missing = [
        column
        for column in required_columns
        if column not in base.columns
    ]

    if missing:

        raise ValueError(
            "Base report is missing required "
            f"columns: {missing}"
        )

    # Keep original value for investigation.
    base[
        "original_domain_before_merge"
    ] = base[
        "domain"
    ].astype(str)

    # Normalize domain used for matching.
    base[
        "domain"
    ] = base[
        "domain"
    ].apply(
        normalize_domain
    )

    return base


# =========================================================
# VALIDATE MANUAL DATA
# =========================================================

def validate_manual_labels(manual):

    required_columns = [
        "domain",
        "verified_label",
    ]

    missing = [
        column
        for column in required_columns
        if column not in manual.columns
    ]

    if missing:

        raise ValueError(
            "Manual label file is missing "
            f"required columns: {missing}"
        )

    manual[
        "domain"
    ] = manual[
        "domain"
    ].apply(
        normalize_domain
    )

    # Convert label to numeric.
    manual[
        "verified_label"
    ] = pd.to_numeric(
        manual[
            "verified_label"
        ],
        errors="coerce"
    )

    # Only allow:
    #
    # 0
    # 1
    # blank

    invalid = manual[
        manual[
            "verified_label"
        ].notna()
        &
        ~manual[
            "verified_label"
        ].isin(
            [0, 1]
        )
    ]

    if len(invalid) > 0:

        print(
            "\nInvalid manual labels:"
        )

        print(
            invalid[
                [
                    "domain",
                    "verified_label",
                ]
            ].to_string(
                index=False
            )
        )

        raise ValueError(
            "verified_label must be "
            "0, 1, or blank."
        )

    # -----------------------------------------------------
    # Manual file itself MUST have unique domains.
    # -----------------------------------------------------

    duplicates = manual[
        manual[
            "domain"
        ].duplicated(
            keep=False
        )
    ]

    if len(duplicates) > 0:

        print(
            "\nDuplicate domains exist inside "
            "verified_labels.csv:"
        )

        print(
            duplicates[
                [
                    "domain",
                    "verified_label",
                ]
            ]
            .sort_values(
                "domain"
            )
            .to_string(
                index=False
            )
        )

        raise ValueError(
            "Remove duplicate domains from "
            "verified_labels.csv."
        )

    return manual


# =========================================================
# PREPARE MANUAL COLUMNS
# =========================================================

def prepare_manual_data(manual):

    # Use names that cannot collide with existing
    # generated-report columns.

    rename_map = {

        "verified_label":
            "review_verified_label",

        "review_status":
            "review_status_manual",

        "verification_method":
            "review_verification_method",

        "notes":
            "review_notes",
    }

    manual = manual.rename(
        columns=rename_map
    )

    keep_columns = [
        "domain",
        "review_verified_label",
    ]

    optional = [
        "review_status_manual",
        "review_verification_method",
        "review_notes",
    ]

    for column in optional:

        if column in manual.columns:

            keep_columns.append(
                column
            )

    return manual[
        keep_columns
    ].copy()


# =========================================================
# FIND NORMALIZED DUPLICATES
# =========================================================

def create_duplicate_report(base):

    duplicate_mask = base[
        "domain"
    ].duplicated(
        keep=False
    )

    duplicates = base[
        duplicate_mask
    ].copy()

    if len(duplicates) == 0:

        return duplicates

    duplicates = (
        duplicates.sort_values(
            "domain"
        )
    )

    DUPLICATE_REPORT_FILE.parent.mkdir(
        parents=True,
        exist_ok=True
    )

    useful_columns = [
        "original_domain_before_merge",
        "domain",
        "label",
        "verified_label",
        "verification_status",
        "verification_source",
    ]

    useful_columns = [
        column
        for column in useful_columns
        if column in duplicates.columns
    ]

    duplicates[
        useful_columns
    ].to_csv(
        DUPLICATE_REPORT_FILE,
        index=False
    )

    return duplicates


# =========================================================
# MAIN
# =========================================================

def main():

    print(
        "\n===================================="
    )

    print(
        " BETGUARD VERIFIED LABEL MERGE V3"
    )

    print(
        "===================================="
    )

    # =====================================================
    # LOAD
    # =====================================================

    base, manual = load_data()

    base = validate_base(
        base
    )

    manual = validate_manual_labels(
        manual
    )

    manual = prepare_manual_data(
        manual
    )

    print(
        "\nDataset rows:",
        len(base)
    )

    print(
        "Manual review entries:",
        len(manual)
    )


    # =====================================================
    # CHECK NORMALIZED DUPLICATES
    # =====================================================

    duplicates = create_duplicate_report(
        base
    )

    duplicate_row_count = len(
        duplicates
    )

    duplicate_domain_count = (
        duplicates[
            "domain"
        ].nunique()
        if duplicate_row_count > 0
        else 0
    )

    print(
        "\nNormalized duplicate rows:",
        duplicate_row_count
    )

    print(
        "Normalized duplicate domains:",
        duplicate_domain_count
    )

    if duplicate_row_count > 0:

        print(
            "\nDuplicate report:"
        )

        print(
            DUPLICATE_REPORT_FILE
        )

        print(
            "\nExample duplicates:"
        )

        print(
            duplicates[
                [
                    "original_domain_before_merge",
                    "domain",
                ]
            ]
            .head(20)
            .to_string(
                index=False
            )
        )


    # =====================================================
    # MERGE
    # =====================================================
    #
    # many_to_one means:
    #
    # LEFT:
    # base dataset MAY contain duplicate normalized domains.
    #
    # RIGHT:
    # manual verified-label file MUST contain one entry
    # per domain.
    #
    # This is exactly what we need.
    #
    # =====================================================

    merged = base.merge(
        manual,
        on="domain",
        how="left",
        validate="many_to_one"
    )


    # =====================================================
    # LABEL COLUMNS
    # =====================================================

    external_verified = pd.to_numeric(
        merged[
            "verified_label"
        ],
        errors="coerce"
    )

    review_verified = pd.to_numeric(
        merged[
            "review_verified_label"
        ],
        errors="coerce"
    )


    # =====================================================
    # EXTERNAL VS MANUAL CONFLICT
    # =====================================================

    conflict_mask = (
        external_verified.notna()
        &
        review_verified.notna()
        &
        (
            external_verified
            !=
            review_verified
        )
    )

    merged[
        "label_conflict"
    ] = conflict_mask

    conflict_count = int(
        conflict_mask.sum()
    )

    if conflict_count > 0:

        print(
            "\nWARNING:"
        )

        print(
            "External/manual label "
            "conflicts detected:"
        )

        print(
            conflict_count
        )

        columns = [
            "domain",
            "verified_label",
            "review_verified_label",
            "verification_source",
        ]

        columns = [
            column
            for column in columns
            if column in merged.columns
        ]

        print(
            merged.loc[
                conflict_mask,
                columns
            ]
            .to_string(
                index=False
            )
        )


    # =====================================================
    # CREATE FINAL LABEL
    # =====================================================

    merged[
        "final_verified_label"
    ] = external_verified.copy()

    # Fill previously unresolved domains using
    # manual verification.

    manual_fill_mask = (
        merged[
            "final_verified_label"
        ].isna()
        &
        review_verified.notna()
    )

    merged.loc[
        manual_fill_mask,
        "final_verified_label"
    ] = review_verified[
        manual_fill_mask
    ]

    # External/manual conflicts remain unresolved.

    merged.loc[
        conflict_mask,
        "final_verified_label"
    ] = pd.NA

    merged[
        "final_verified_label"
    ] = merged[
        "final_verified_label"
    ].astype(
        "Int64"
    )


    # =====================================================
    # FINAL LABEL SOURCE
    # =====================================================

    merged[
        "final_label_source"
    ] = ""

    external_mask = (
        external_verified.notna()
        &
        ~conflict_mask
    )

    manual_only_mask = (
        external_verified.isna()
        &
        review_verified.notna()
        &
        ~conflict_mask
    )

    merged.loc[
        external_mask,
        "final_label_source"
    ] = (
        "external gambling verification"
    )

    merged.loc[
        manual_only_mask,
        "final_label_source"
    ] = (
        "manual verification"
    )

    merged.loc[
        conflict_mask,
        "final_label_source"
    ] = (
        "CONFLICT - requires review"
    )


    # =====================================================
    # CHECK DUPLICATE-DOMAIN LABEL CONSISTENCY
    # =====================================================
    #
    # A normalized domain must not have:
    #
    # one row = 0
    # another row = 1
    #
    # If that occurs, the entire normalized domain becomes
    # unresolved until investigated.
    #
    # =====================================================

    domain_label_counts = (
        merged[
            merged[
                "final_verified_label"
            ].notna()
        ]
        .groupby(
            "domain"
        )[
            "final_verified_label"
        ]
        .nunique()
    )

    conflicting_duplicate_domains = set(
        domain_label_counts[
            domain_label_counts > 1
        ].index
    )

    duplicate_label_conflict_mask = (
        merged[
            "domain"
        ].isin(
            conflicting_duplicate_domains
        )
    )

    merged[
        "duplicate_label_conflict"
    ] = duplicate_label_conflict_mask

    duplicate_label_conflict_count = len(
        conflicting_duplicate_domains
    )

    if duplicate_label_conflict_count > 0:

        print(
            "\nWARNING:"
        )

        print(
            "Normalized domains with "
            "conflicting final labels:"
        )

        print(
            duplicate_label_conflict_count
        )

        for domain in sorted(
            conflicting_duplicate_domains
        ):

            print(
                " -",
                domain
            )

        # Remove them from verified training labels.

        merged.loc[
            duplicate_label_conflict_mask,
            "final_verified_label"
        ] = pd.NA

        merged.loc[
            duplicate_label_conflict_mask,
            "final_label_source"
        ] = (
            "DUPLICATE LABEL CONFLICT - review required"
        )


    # =====================================================
    # MANUAL MATCH STATISTICS
    # =====================================================

    manual_match_rows = int(
        merged[
            "review_verified_label"
        ].notna().sum()
    )

    manual_match_domains = int(
        merged.loc[
            merged[
                "review_verified_label"
            ].notna(),
            "domain"
        ].nunique()
    )

    print(
        "\nManual verified rows matched:",
        manual_match_rows
    )

    print(
        "Manual verified domains matched:",
        manual_match_domains
    )


    # =====================================================
    # MANUAL DOMAINS NOT IN DATASET
    # =====================================================

    dataset_domains = set(
        base[
            "domain"
        ]
    )

    manual_domains = set(
        manual[
            "domain"
        ]
    )

    missing_manual_domains = (
        manual_domains
        -
        dataset_domains
    )

    if missing_manual_domains:

        print(
            "\nWARNING:"
        )

        print(
            "Manual domains not present "
            "in the dataset:"
        )

        for domain in sorted(
            missing_manual_domains
        ):

            print(
                " -",
                domain
            )


    # =====================================================
    # SAVE COMPLETE PROGRESS REPORT
    # =====================================================

    OUTPUT_FILE.parent.mkdir(
        parents=True,
        exist_ok=True
    )

    merged.to_csv(
        OUTPUT_FILE,
        index=False
    )


    # =====================================================
    # CREATE TRAINABLE DATASET
    # =====================================================
    #
    # First:
    #
    # retain only verified, non-conflicting rows.
    #
    # =====================================================

    trainable = merged[
        merged[
            "final_verified_label"
        ].notna()
        &
        ~merged[
            "label_conflict"
        ]
        &
        ~merged[
            "duplicate_label_conflict"
        ]
    ].copy()


    # =====================================================
    # REMOVE DUPLICATE NORMALIZED DOMAINS
    # =====================================================
    #
    # This is CRITICAL for machine-learning evaluation.
    #
    # A domain must not appear twice and accidentally
    # enter both training and testing.
    #
    # =====================================================

    before_dedup = len(
        trainable
    )

    trainable = (
        trainable.drop_duplicates(
            subset=[
                "domain"
            ],
            keep="first"
        )
    )

    after_dedup = len(
        trainable
    )

    removed_training_duplicates = (
        before_dedup
        -
        after_dedup
    )


    TRAINABLE_FILE.parent.mkdir(
        parents=True,
        exist_ok=True
    )

    trainable.to_csv(
        TRAINABLE_FILE,
        index=False
    )


    # =====================================================
    # UNRESOLVED
    # =====================================================

    unresolved = merged[
        merged[
            "final_verified_label"
        ].isna()
    ].copy()

    UNRESOLVED_FILE.parent.mkdir(
        parents=True,
        exist_ok=True
    )

    unresolved.to_csv(
        UNRESOLVED_FILE,
        index=False
    )


    # =====================================================
    # FINAL COUNTS - UNIQUE DOMAINS
    # =====================================================

    unique_verified = (
        trainable[
            [
                "domain",
                "final_verified_label",
            ]
        ]
        .drop_duplicates(
            subset=[
                "domain"
            ]
        )
    )

    verified_gambling = int(
        (
            unique_verified[
                "final_verified_label"
            ]
            == 1
        ).sum()
    )

    verified_benign = int(
        (
            unique_verified[
                "final_verified_label"
            ]
            == 0
        ).sum()
    )

    unresolved_unique = int(
        unresolved[
            "domain"
        ].nunique()
    )


    # =====================================================
    # RESULTS
    # =====================================================

    print(
        "\n===================================="
    )

    print(
        " VERIFIED LABEL RESULTS"
    )

    print(
        "===================================="
    )

    print(
        "\nVerified gambling domains:",
        verified_gambling
    )

    print(
        "Verified non-gambling domains:",
        verified_benign
    )

    print(
        "Unresolved unique domains:",
        unresolved_unique
    )

    print(
        "External/manual conflicts:",
        conflict_count
    )

    print(
        "Duplicate-domain label conflicts:",
        duplicate_label_conflict_count
    )

    print(
        "\nDuplicate training rows removed:",
        removed_training_duplicates
    )

    print(
        "Unique trainable domains:",
        len(trainable)
    )


    # =====================================================
    # SHOW BENIGN DOMAINS
    # =====================================================

    benign = trainable[
        trainable[
            "final_verified_label"
        ]
        ==
        0
    ]

    if len(
        benign
    ) > 0:

        print(
            "\nVerified non-gambling domains:"
        )

        columns = [
            "domain",
            "final_verified_label",
            "final_label_source",
        ]

        print(
            benign[
                columns
            ]
            .to_string(
                index=False
            )
        )


    # =====================================================
    # FILE OUTPUT
    # =====================================================

    print(
        "\n===================================="
    )

    print(
        " FILES CREATED"
    )

    print(
        "===================================="
    )

    print(
        "\nComplete progress:"
    )

    print(
        OUTPUT_FILE
    )

    print(
        "\nUnique verified training candidates:"
    )

    print(
        TRAINABLE_FILE
    )

    print(
        "\nUnresolved domains:"
    )

    print(
        UNRESOLVED_FILE
    )

    if duplicate_row_count > 0:

        print(
            "\nNormalized duplicate investigation:"
        )

        print(
            DUPLICATE_REPORT_FILE
        )

    print(
        "\nIMPORTANT:"
    )

    print(
        "Training candidates now contain "
        "one row per normalized domain."
    )

    print(
        "Do not train the final classifier "
        "until we build a sufficiently large "
        "verified non-gambling class."
    )


# =========================================================
# ENTRY POINT
# =========================================================

if __name__ == "__main__":

    main()