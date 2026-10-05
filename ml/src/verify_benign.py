import csv
import io
import zipfile
from pathlib import Path

import pandas as pd
import requests


# =========================================================
# BETGUARD - NON-GAMBLING CANDIDATE VERIFICATION
# =========================================================
#
# IMPORTANT:
#
# This script DOES NOT automatically assign label 0.
#
# Tranco is a popularity ranking, NOT a guaranteed
# non-gambling or benign-domain database.
#
# The goal of this script is to:
#
# 1. Preserve already-confirmed gambling domains.
# 2. Find unresolved domains that also appear in Tranco.
# 3. Rank those domains as potential non-gambling candidates.
# 4. Produce a smaller manual-review queue.
#
# Final label 0 will only be assigned after additional
# verification/manual review.
#
# =========================================================


# =========================================================
# PATHS
# =========================================================

INPUT_FILE = Path(
    "reports/label_verification.csv"
)

OUTPUT_FILE = Path(
    "reports/benign_verification.csv"
)

REVIEW_QUEUE_FILE = Path(
    "reports/benign_review_queue.csv"
)


# =========================================================
# TRANCO SOURCE
# =========================================================
#
# Official permanent URL for the latest Tranco Top 1M.
#
# ZIP contains:
#
# top-1m.csv
#
# Format:
#
# rank,domain
#
# Example:
#
# 1,google.com
# 2,example.com
#
# =========================================================

TRANCO_URL = (
    "https://tranco-list.eu/top-1m.csv.zip"
)


# =========================================================
# TRANCO RANK THRESHOLDS
# =========================================================
#
# These thresholds are NOT labels.
#
# They are only used to prioritize manual verification.
#
# =========================================================

TRANCO_STRONG_RANK = 10_000

TRANCO_MEDIUM_RANK = 100_000

TRANCO_MAX_RANK = 1_000_000


# =========================================================
# DOMAIN NORMALIZATION
# =========================================================

def normalize_domain(domain):
    """
    Convert domains/URLs into a consistent format.

    Examples:

    HTTPS://WWW.Example.com/page
        -> example.com

    http://example.com
        -> example.com
    """

    if pd.isna(domain):
        return ""

    domain = str(domain)

    domain = domain.strip().lower()

    # Remove protocols
    if domain.startswith("https://"):
        domain = domain[len("https://"):]

    elif domain.startswith("http://"):
        domain = domain[len("http://"):]

    # Remove URL path
    domain = domain.split("/")[0]

    # Remove query string
    domain = domain.split("?")[0]

    # Remove fragments
    domain = domain.split("#")[0]

    # Remove www.
    if domain.startswith("www."):
        domain = domain[4:]

    # Remove trailing dot
    domain = domain.rstrip(".")

    # Remove hostname port
    #
    # example.com:443
    #
    # Do not attempt to modify IPv6 addresses.

    if domain.count(":") == 1:

        hostname, possible_port = domain.rsplit(
            ":",
            1
        )

        if possible_port.isdigit():
            domain = hostname

    return domain


# =========================================================
# DOMAIN CANDIDATES
# =========================================================

def generate_domain_candidates(domain):
    """
    Generate possible parent-domain matches.

    Example:

    login.example.com

    becomes:

    login.example.com
    example.com

    This helps match subdomains against Tranco entries.
    """

    domain = normalize_domain(
        domain
    )

    if not domain:
        return []

    parts = domain.split(".")

    candidates = [
        domain
    ]

    # Keep at least two domain components.
    #
    # Example:
    #
    # casino.example.com
    #
    # casino.example.com
    # example.com
    #
    # NOT:
    #
    # com

    for index in range(
        1,
        len(parts) - 1
    ):

        candidate = ".".join(
            parts[index:]
        )

        candidates.append(
            candidate
        )

    return candidates


# =========================================================
# DOWNLOAD TRANCO
# =========================================================

def download_tranco():
    """
    Download the latest Tranco Top 1M ZIP file.
    """

    print(
        "\nDownloading Tranco Top 1M..."
    )

    try:

        response = requests.get(
            TRANCO_URL,
            timeout=120,
            headers={
                "User-Agent": (
                    "BetGuard-ML-Research/1.0"
                )
            }
        )

        response.raise_for_status()

    except requests.RequestException as error:

        raise RuntimeError(
            "\nCould not download Tranco.\n"
            f"Reason: {error}"
        )

    print(
        "Tranco download completed."
    )

    print(
        "Downloaded size:",
        f"{len(response.content) / 1024 / 1024:.2f} MB"
    )

    return response.content


# =========================================================
# FIND TRANCO MATCHES
# =========================================================

def find_tranco_matches(
    zip_bytes,
    domains
):
    """
    Find dataset domains or their parent domains
    inside the Tranco Top 1M ranking.

    This implementation avoids storing all one million
    Tranco domains in a huge Python dictionary.

    Instead:

    1. Build candidate names only for our dataset.
    2. Stream through Tranco.
    3. Store ranks only when there is a match.
    """

    # -----------------------------------------------------
    # Generate candidate domains from our dataset
    # -----------------------------------------------------

    candidate_domains = set()

    for domain in domains:

        candidates = generate_domain_candidates(
            domain
        )

        candidate_domains.update(
            candidates
        )

    print(
        "\nUnique dataset domain candidates:",
        len(candidate_domains)
    )


    # -----------------------------------------------------
    # Store only relevant Tranco matches
    # -----------------------------------------------------

    candidate_rank_map = {}


    try:

        zip_buffer = io.BytesIO(
            zip_bytes
        )

        with zipfile.ZipFile(
            zip_buffer
        ) as archive:

            filenames = archive.namelist()

            if not filenames:

                raise RuntimeError(
                    "Tranco ZIP archive is empty."
                )

            csv_filename = None

            for filename in filenames:

                if filename.endswith(
                    ".csv"
                ):

                    csv_filename = filename
                    break

            if csv_filename is None:

                raise RuntimeError(
                    "Could not find CSV inside "
                    "Tranco ZIP archive."
                )


            print(
                "Reading:",
                csv_filename
            )


            with archive.open(
                csv_filename
            ) as csv_file:

                text_stream = (
                    io.TextIOWrapper(
                        csv_file,
                        encoding="utf-8",
                        errors="replace"
                    )
                )

                reader = csv.reader(
                    text_stream
                )


                for row in reader:

                    if len(row) < 2:
                        continue


                    try:

                        rank = int(
                            row[0]
                        )

                    except ValueError:

                        continue


                    ranked_domain = normalize_domain(
                        row[1]
                    )


                    if (
                        ranked_domain
                        in candidate_domains
                    ):

                        existing_rank = (
                            candidate_rank_map.get(
                                ranked_domain
                            )
                        )


                        if (
                            existing_rank is None
                            or
                            rank < existing_rank
                        ):

                            candidate_rank_map[
                                ranked_domain
                            ] = rank


    except zipfile.BadZipFile:

        raise RuntimeError(
            "Downloaded Tranco file "
            "is not a valid ZIP archive."
        )


    print(
        "Relevant Tranco matches found:",
        len(candidate_rank_map)
    )


    # -----------------------------------------------------
    # Determine best match for each original domain
    # -----------------------------------------------------

    results = {}


    for domain in domains:

        normalized = normalize_domain(
            domain
        )

        best_rank = None
        best_match = None
        match_type = None


        candidates = generate_domain_candidates(
            normalized
        )


        for candidate in candidates:

            if candidate not in candidate_rank_map:
                continue


            rank = candidate_rank_map[
                candidate
            ]


            if (
                best_rank is None
                or
                rank < best_rank
            ):

                best_rank = rank

                best_match = candidate


                if candidate == normalized:

                    match_type = "exact"

                else:

                    match_type = "parent_domain"


        results[
            normalized
        ] = {
            "rank": best_rank,
            "match": best_match,
            "match_type": match_type,
        }


    return results


# =========================================================
# NUMERIC VALUE HELPER
# =========================================================

def numeric_value(
    row,
    column,
    default=0
):
    """
    Safely retrieve numeric dataset features.
    """

    if column not in row:
        return default

    value = row[column]

    if pd.isna(value):
        return default

    try:

        return float(
            value
        )

    except (
        TypeError,
        ValueError
    ):

        return default


# =========================================================
# CLASSIFY BENIGN CANDIDATE
# =========================================================

def classify_candidate(row):
    """
    Determine review priority.

    IMPORTANT:

    This does NOT create label 0.

    It only determines how promising a domain is as a
    potential non-gambling candidate.
    """


    # -----------------------------------------------------
    # Already confirmed gambling
    # -----------------------------------------------------

    if row["verification_status"] == (
        "confirmed_gambling"
    ):

        return (
            "confirmed_gambling",
            "Already confirmed by gambling "
            "blocklist/manual research"
        )


    # -----------------------------------------------------
    # Gambling-keyword candidates remain high priority
    # gambling reviews even if they appear in Tranco.
    #
    # Example:
    #
    # bet365.com
    #
    # Popularity does NOT make a gambling site benign.
    # -----------------------------------------------------

    has_keyword = (
        numeric_value(
            row,
            "has_gambling_keyword"
        )
        == 1
    )


    if has_keyword:

        return (
            "priority_gambling_review",
            "Contains gambling-related keyword"
        )


    # -----------------------------------------------------
    # Tranco information
    # -----------------------------------------------------

    tranco_rank = row.get(
        "tranco_rank"
    )


    if pd.isna(
        tranco_rank
    ):

        return (
            "needs_manual_review",
            "No gambling-list match and "
            "no Tranco match"
        )


    tranco_rank = int(
        tranco_rank
    )


    # -----------------------------------------------------
    # Existing technical indicators
    # -----------------------------------------------------

    suspicious_tld = (
        numeric_value(
            row,
            "suspicious_tld"
        )
        == 1
    )

    ssl_valid = (
        numeric_value(
            row,
            "ssl_valid"
        )
        == 1
    )

    dns_resolves = (
        numeric_value(
            row,
            "dns_resolves"
        )
        == 1
    )

    has_domain_info = (
        numeric_value(
            row,
            "has_domain_info"
        )
        == 1
    )

    domain_age = numeric_value(
        row,
        "domain_age_days"
    )


    # =====================================================
    # STRONG BENIGN CANDIDATE
    # =====================================================
    #
    # Requirements:
    #
    # - Top 10K Tranco
    # - no gambling keyword
    # - non-suspicious TLD
    # - valid SSL
    # - DNS resolves
    # - domain information exists
    # - domain is at least one year old
    #
    # Still NOT automatically label 0.
    #
    # =====================================================

    if (
        tranco_rank
        <= TRANCO_STRONG_RANK

        and not suspicious_tld

        and ssl_valid

        and dns_resolves

        and has_domain_info

        and domain_age >= 365
    ):

        return (
            "strong_benign_candidate",
            "Top 10K Tranco + established "
            "technical indicators"
        )


    # =====================================================
    # MEDIUM BENIGN CANDIDATE
    # =====================================================

    if (
        tranco_rank
        <= TRANCO_MEDIUM_RANK

        and not suspicious_tld
    ):

        return (
            "medium_benign_candidate",
            "Top 100K Tranco and no "
            "gambling keyword"
        )


    # =====================================================
    # WEAK BENIGN CANDIDATE
    # =====================================================

    if (
        tranco_rank
        <= TRANCO_MAX_RANK
    ):

        return (
            "weak_benign_candidate",
            "Appears in Tranco Top 1M"
        )


    # =====================================================
    # FALLBACK
    # =====================================================

    return (
        "needs_manual_review",
        "Insufficient evidence"
    )


# =========================================================
# REVIEW PRIORITY
# =========================================================

def get_review_priority(
    candidate_status
):
    """
    Lower number = should be reviewed first.
    """

    priorities = {

        "strong_benign_candidate": 1,

        "medium_benign_candidate": 2,

        "priority_gambling_review": 3,

        "weak_benign_candidate": 4,

        "needs_manual_review": 5,

        "confirmed_gambling": 99,
    }


    return priorities.get(
        candidate_status,
        50
    )


# =========================================================
# MAIN
# =========================================================

def main():

    print(
        "\n===================================="
    )

    print(
        " BETGUARD BENIGN VERIFICATION"
    )

    print(
        "===================================="
    )


    # =====================================================
    # LOAD PREVIOUS VERIFICATION REPORT
    # =====================================================

    if not INPUT_FILE.exists():

        raise FileNotFoundError(
            "\nCould not find:\n"
            f"{INPUT_FILE}\n\n"
            "Run verify_labels.py first."
        )


    print(
        "\nLoading:"
    )

    print(
        INPUT_FILE
    )


    df = pd.read_csv(
        INPUT_FILE
    )


    print(
        "\nDataset rows:",
        len(df)
    )


    # =====================================================
    # REQUIRED COLUMNS
    # =====================================================

    required_columns = [
        "domain",
        "verification_status",
        "verified_label",
        "has_gambling_keyword",
    ]


    missing_columns = [

        column

        for column in required_columns

        if column not in df.columns
    ]


    if missing_columns:

        raise ValueError(
            "\nMissing required columns:\n"
            f"{missing_columns}"
        )


    # =====================================================
    # NORMALIZE DOMAINS
    # =====================================================

    df[
        "domain"
    ] = df[
        "domain"
    ].apply(
        normalize_domain
    )


    # =====================================================
    # DOWNLOAD TRANCO
    # =====================================================

    tranco_zip = download_tranco()


    # =====================================================
    # FIND TRANCO MATCHES
    # =====================================================

    print(
        "\nMatching dataset against Tranco..."
    )


    tranco_results = (
        find_tranco_matches(
            tranco_zip,
            df["domain"].tolist()
        )
    )


    # =====================================================
    # ADD TRANCO COLUMNS
    # =====================================================

    ranks = []
    matches = []
    match_types = []


    for domain in df["domain"]:

        result = tranco_results.get(
            domain,
            {}
        )

        ranks.append(
            result.get(
                "rank"
            )
        )

        matches.append(
            result.get(
                "match"
            )
        )

        match_types.append(
            result.get(
                "match_type"
            )
        )


    df[
        "tranco_rank"
    ] = ranks

    df[
        "tranco_match"
    ] = matches

    df[
        "tranco_match_type"
    ] = match_types


    # =====================================================
    # CLASSIFY CANDIDATES
    # =====================================================

    candidate_statuses = []

    candidate_reasons = []


    for _, row in df.iterrows():

        status, reason = (
            classify_candidate(
                row
            )
        )

        candidate_statuses.append(
            status
        )

        candidate_reasons.append(
            reason
        )


    df[
        "benign_candidate_status"
    ] = candidate_statuses

    df[
        "benign_candidate_reason"
    ] = candidate_reasons


    # =====================================================
    # REVIEW PRIORITY
    # =====================================================

    df[
        "review_priority"
    ] = df[
        "benign_candidate_status"
    ].apply(
        get_review_priority
    )


    # =====================================================
    # MANUAL REVIEW COLUMNS
    # =====================================================
    #
    # DO NOT put labels into these automatically.
    #
    # Later:
    #
    # manual_verified_label:
    #
    # 0 = verified non-gambling
    # 1 = verified gambling
    #
    # Leave blank if uncertain.
    #
    # =====================================================

    if (
        "manual_verified_label"
        not in df.columns
    ):

        df[
            "manual_verified_label"
        ] = pd.Series(
            pd.NA,
            index=df.index,
            dtype="Int64"
        )


    if (
        "manual_review_status"
        not in df.columns
    ):

        df[
            "manual_review_status"
        ] = ""


    if (
        "manual_notes"
        not in df.columns
    ):

        df[
            "manual_notes"
        ] = ""


    # =====================================================
    # SAVE COMPLETE REPORT
    # =====================================================

    OUTPUT_FILE.parent.mkdir(
        parents=True,
        exist_ok=True
    )


    df.to_csv(
        OUTPUT_FILE,
        index=False
    )


    # =====================================================
    # CREATE MANUAL REVIEW QUEUE
    # =====================================================

    review_queue = df[
        df[
            "benign_candidate_status"
        ]
        !=
        "confirmed_gambling"
    ].copy()


    review_queue = (
        review_queue.sort_values(
            by=[
                "review_priority",
                "tranco_rank",
            ],
            ascending=[
                True,
                True,
            ],
            na_position="last"
        )
    )


    review_columns = [
        "domain",

        "label",

        "verified_label",

        "verification_status",

        "verification_source",

        "benign_candidate_status",

        "benign_candidate_reason",

        "tranco_rank",

        "tranco_match",

        "tranco_match_type",

        "has_gambling_keyword",

        "suspicious_tld",

        "domain_age_days",

        "has_domain_info",

        "ssl_valid",

        "dns_resolves",

        "manual_verified_label",

        "manual_review_status",

        "manual_notes",
    ]


    review_columns = [

        column

        for column in review_columns

        if column in review_queue.columns
    ]


    review_queue[
        review_columns
    ].to_csv(
        REVIEW_QUEUE_FILE,
        index=False
    )


    # =====================================================
    # COUNTS
    # =====================================================

    status_counts = df[
        "benign_candidate_status"
    ].value_counts()


    print(
        "\n===================================="
    )

    print(
        " BENIGN CANDIDATE RESULTS"
    )

    print(
        "===================================="
    )


    print(
        "\nCandidate status:"
    )

    print(
        status_counts
    )


    # =====================================================
    # TRANCO COVERAGE
    # =====================================================

    tranco_match_count = int(
        df[
            "tranco_rank"
        ].notna().sum()
    )


    print(
        "\nDomains appearing in Tranco:"
    )

    print(
        tranco_match_count
    )


    print(
        "\nTranco coverage:"
    )

    print(
        f"{(
            tranco_match_count
            /
            len(df)
            *
            100
        ):.2f}%"
    )


    # =====================================================
    # STRONG CANDIDATE COUNT
    # =====================================================

    strong_count = int(
        (
            df[
                "benign_candidate_status"
            ]
            ==
            "strong_benign_candidate"
        ).sum()
    )


    medium_count = int(
        (
            df[
                "benign_candidate_status"
            ]
            ==
            "medium_benign_candidate"
        ).sum()
    )


    weak_count = int(
        (
            df[
                "benign_candidate_status"
            ]
            ==
            "weak_benign_candidate"
        ).sum()
    )


    gambling_review_count = int(
        (
            df[
                "benign_candidate_status"
            ]
            ==
            "priority_gambling_review"
        ).sum()
    )


    remaining_count = int(
        (
            df[
                "benign_candidate_status"
            ]
            ==
            "needs_manual_review"
        ).sum()
    )


    print(
        "\nStrong benign candidates:",
        strong_count
    )


    print(
        "Medium benign candidates:",
        medium_count
    )


    print(
        "Weak benign candidates:",
        weak_count
    )


    print(
        "Priority gambling reviews:",
        gambling_review_count
    )


    print(
        "Other manual reviews:",
        remaining_count
    )


    # =====================================================
    # SHOW EXAMPLES
    # =====================================================

    strong_examples = df[
        df[
            "benign_candidate_status"
        ]
        ==
        "strong_benign_candidate"
    ]


    if len(
        strong_examples
    ) > 0:

        print(
            "\nExample strong benign candidates:"
        )


        display_columns = [
            "domain",
            "tranco_rank",
            "domain_age_days",
            "ssl_valid",
            "dns_resolves",
        ]


        display_columns = [

            column

            for column in display_columns

            if column in strong_examples.columns
        ]


        print(
            strong_examples[
                display_columns
            ]
            .sort_values(
                "tranco_rank"
            )
            .head(20)
            .to_string(
                index=False
            )
        )


    # =====================================================
    # SAVE INFORMATION
    # =====================================================

    print(
        "\n===================================="
    )

    print(
        " REPORTS SAVED"
    )

    print(
        "===================================="
    )


    print(
        "\nComplete report:"
    )

    print(
        OUTPUT_FILE
    )


    print(
        "\nManual review queue:"
    )

    print(
        REVIEW_QUEUE_FILE
    )


    # =====================================================
    # WARNING
    # =====================================================

    print(
        "\nIMPORTANT:"
    )

    print(
        "No domain was automatically assigned "
        "verified_label = 0."
    )


    print(
        "\nTranco matches are candidate evidence "
        "only."
    )


    print(
        "\nDo NOT train the model yet."
    )


    print(
        "\nNext step:"
    )

    print(
        "Review strong benign candidates and "
        "create verified non-gambling labels."
    )


# =========================================================
# ENTRY POINT
# =========================================================

if __name__ == "__main__":
    main()