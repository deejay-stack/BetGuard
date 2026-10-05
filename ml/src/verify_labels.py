import pandas as pd
import requests

from pathlib import Path


# =========================================================
# PATHS
# =========================================================

DATA_FILE = Path(
    "data/processed/dataset_cleaned.csv"
)

OUTPUT_FILE = Path(
    "reports/label_verification.csv"
)


# =========================================================
# PUBLIC GAMBLING BLOCKLIST SOURCES
# =========================================================
#
# We use multiple independent sources so that we are not
# depending on only one gambling-domain database.
#
# Block List Project currently maintains a large dedicated
# gambling list.
#
# UT1 also maintains a gambling category containing betting,
# casino, and poker-related domains.
#
# =========================================================

BLOCKLIST_SOURCES = {
    "Block List Project": (
        "https://raw.githubusercontent.com/"
        "blocklistproject/Lists/master/gambling.txt"
    ),

    "UT1 Gambling": (
        "https://raw.githubusercontent.com/"
        "olbat/ut1-blacklists/master/"
        "blacklists/gambling/domains"
    ),
}


# =========================================================
# MANUALLY VERIFIED GAMBLING DOMAINS
# =========================================================
#
# These domains were independently verified during our
# dataset review.
#
# Keep this section for manually researched domains that
# you are confident are gambling websites.
#
# =========================================================

MANUALLY_CONFIRMED_GAMBLING = {
    "bet88.com",
    "casino.jackpocket.com",
    "slotmojo.com",
    "sailorbingo.com",
}


# =========================================================
# DOMAIN NORMALIZATION
# =========================================================

def normalize_domain(domain):
    """
    Convert a URL/domain into a consistent domain format.

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
    domain = domain.replace(
        "https://",
        ""
    )

    domain = domain.replace(
        "http://",
        ""
    )

    # Remove path
    domain = domain.split("/")[0]

    # Remove query strings if somehow present
    domain = domain.split("?")[0]

    # Remove fragments
    domain = domain.split("#")[0]

    # Remove port
    #
    # example.com:443
    # ->
    # example.com

    if ":" in domain:

        # Avoid breaking IPv6 addresses.
        # Our dataset is mainly domain based, so this
        # handles standard hostname:port cases.

        parts = domain.split(":")

        if len(parts) == 2:
            domain = parts[0]

    # Remove www.
    if domain.startswith("www."):
        domain = domain[4:]

    # Remove trailing dot
    domain = domain.rstrip(".")

    return domain


# =========================================================
# PARSE BLOCKLIST CONTENT
# =========================================================

def parse_blocklist(text):
    """
    Convert blocklist text into a Python set of domains.

    Supports formats such as:

    example.com

    or:

    0.0.0.0 example.com

    Comments and blank lines are ignored.
    """

    domains = set()

    for line in text.splitlines():

        line = line.strip()

        # Ignore empty lines
        if not line:
            continue

        # Ignore comments
        if line.startswith("#"):
            continue

        # Some blocklists use:
        #
        # 0.0.0.0 example.com
        #
        # Others simply use:
        #
        # example.com

        parts = line.split()

        if len(parts) >= 2:

            domain = parts[-1]

        else:

            domain = parts[0]

        domain = normalize_domain(
            domain
        )

        # Ignore invalid-looking entries
        if not domain:
            continue

        if "." not in domain:
            continue

        # Ignore localhost entries
        if domain == "localhost":
            continue

        # Ignore common wildcard syntax
        domain = domain.replace(
            "*.",
            ""
        )

        domains.add(
            domain
        )

    return domains


# =========================================================
# DOWNLOAD ALL BLOCKLISTS
# =========================================================

def download_blocklists():
    """
    Download all configured gambling blocklists.

    Returns:

    {
        "example.com": {
            "Block List Project",
            "UT1 Gambling"
        }
    }
    """

    combined_domains = {}

    successful_sources = 0

    print(
        "\nDownloading gambling blocklists..."
    )

    print(
        "------------------------------------"
    )

    for source_name, url in BLOCKLIST_SOURCES.items():

        print(
            f"\nDownloading: {source_name}"
        )

        try:

            response = requests.get(
                url,
                timeout=60,
                headers={
                    "User-Agent": (
                        "BetGuard-ML-Research/1.0"
                    )
                }
            )

            response.raise_for_status()

        except requests.RequestException as error:

            print(
                f"WARNING: Could not download "
                f"{source_name}"
            )

            print(
                f"Reason: {error}"
            )

            continue

        source_domains = parse_blocklist(
            response.text
        )

        successful_sources += 1

        print(
            f"Loaded {len(source_domains):,} "
            f"domains from {source_name}"
        )

        for domain in source_domains:

            if domain not in combined_domains:

                combined_domains[
                    domain
                ] = set()

            combined_domains[
                domain
            ].add(
                source_name
            )

    # -----------------------------------------
    # Make sure at least one source worked
    # -----------------------------------------

    if successful_sources == 0:

        raise RuntimeError(
            "\nNo gambling blocklist could be "
            "downloaded.\n"
            "Check your internet connection "
            "and try again."
        )

    print(
        "\n------------------------------------"
    )

    print(
        "Unique gambling domains loaded:",
        f"{len(combined_domains):,}"
    )

    print(
        "Successful sources:",
        successful_sources
    )

    return combined_domains


# =========================================================
# GET POSSIBLE DOMAIN PARENTS
# =========================================================

def generate_domain_candidates(domain):
    """
    Generate domain and parent-domain candidates.

    Example:

    casino.example.com

    returns:

    casino.example.com
    example.com

    Another example:

    play.casino.example.com

    returns:

    play.casino.example.com
    casino.example.com
    example.com
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

    # Require at least two labels to remain.
    #
    # Example:
    #
    # casino.example.com
    #
    # casino.example.com
    # example.com
    #
    # But NOT:
    #
    # com

    for index in range(
        1,
        len(parts) - 1
    ):

        parent = ".".join(
            parts[index:]
        )

        candidates.append(
            parent
        )

    return candidates


# =========================================================
# FIND BLOCKLIST MATCH
# =========================================================

def find_blocklist_match(
    domain,
    gambling_domains
):
    """
    Search for an exact domain or parent-domain match.

    Returns:

    matched_domain
    sources
    """

    candidates = generate_domain_candidates(
        domain
    )

    matched_domain = None

    matched_sources = set()

    # Search from most specific domain
    # toward the parent domain.
    #
    # Example:
    #
    # casino.betway.com
    #
    # first:
    # casino.betway.com
    #
    # then:
    # betway.com

    for candidate in candidates:

        if candidate in gambling_domains:

            if matched_domain is None:

                matched_domain = candidate

            matched_sources.update(
                gambling_domains[
                    candidate
                ]
            )

    return (
        matched_domain,
        matched_sources
    )


# =========================================================
# ADD MANUAL VERIFICATION
# =========================================================

def apply_manual_verification(
    domain,
    sources
):
    """
    Add our manually researched confirmations.
    """

    normalized = normalize_domain(
        domain
    )

    updated_sources = set(
        sources
    )

    if normalized in (
        MANUALLY_CONFIRMED_GAMBLING
    ):

        updated_sources.add(
            "Manual research"
        )

    return updated_sources


# =========================================================
# MAIN
# =========================================================

def main():

    print(
        "\n===================================="
    )

    print(
        " BETGUARD DATASET LABEL VERIFICATION"
    )

    print(
        "===================================="
    )


    # =====================================================
    # LOAD DATASET
    # =====================================================

    print(
        "\nLoading dataset..."
    )

    if not DATA_FILE.exists():

        raise FileNotFoundError(
            f"\nDataset not found:\n"
            f"{DATA_FILE}\n\n"
            f"Run audit_dataset.py first."
        )

    df = pd.read_csv(
        DATA_FILE
    )

    print(
        "Dataset rows:",
        len(df)
    )


    # =====================================================
    # CHECK REQUIRED COLUMNS
    # =====================================================

    required_columns = [
        "domain",
        "label",
        "has_gambling_keyword",
    ]

    missing_columns = [
        column
        for column in required_columns
        if column not in df.columns
    ]

    if missing_columns:

        raise ValueError(
            "Dataset is missing required "
            f"columns: {missing_columns}"
        )


    # =====================================================
    # NORMALIZE DOMAINS
    # =====================================================

    print(
        "\nNormalizing domains..."
    )

    df["domain"] = (
        df["domain"]
        .apply(
            normalize_domain
        )
    )


    # =====================================================
    # DOWNLOAD GAMBLING LISTS
    # =====================================================

    gambling_domains = (
        download_blocklists()
    )


    # =====================================================
    # MATCH DATASET AGAINST BLOCKLISTS
    # =====================================================

    print(
        "\nMatching dataset domains "
        "against gambling lists..."
    )

    blocklist_matches = []

    matched_sources_column = []

    source_counts = []


    for domain in df["domain"]:

        matched_domain, sources = (
            find_blocklist_match(
                domain,
                gambling_domains
            )
        )

        # Add manually confirmed
        # research results.

        sources = apply_manual_verification(
            domain,
            sources
        )

        # If manually confirmed but no
        # blocklist domain matched,
        # use the domain itself as match.

        if (
            "Manual research" in sources
            and matched_domain is None
        ):

            matched_domain = domain


        blocklist_matches.append(
            matched_domain
        )

        sorted_sources = sorted(
            sources
        )

        matched_sources_column.append(
            ", ".join(
                sorted_sources
            )
        )

        source_counts.append(
            len(sources)
        )


    df[
        "blocklist_match"
    ] = blocklist_matches

    df[
        "matched_sources"
    ] = matched_sources_column

    df[
        "source_count"
    ] = source_counts


    # =====================================================
    # CREATE NEW VERIFIED LABEL
    # =====================================================
    #
    # Important:
    #
    # We DO NOT automatically trust the
    # original label column.
    #
    # verified_label is our new target.
    #
    # 1 = externally/manual confirmed gambling
    #
    # Blank = still unresolved
    #
    # We are NOT assigning label 0 yet.
    #
    # =====================================================

    df[
        "verified_label"
    ] = pd.Series(
        pd.NA,
        index=df.index,
        dtype="Int64"
    )


    df[
        "verification_status"
    ] = "needs_review"


    df[
        "verification_source"
    ] = ""


    df[
        "confirmation_strength"
    ] = ""


    # =====================================================
    # CONFIRMED GAMBLING
    # =====================================================

    confirmed_mask = (
        df["source_count"] > 0
    )


    df.loc[
        confirmed_mask,
        "verified_label"
    ] = 1


    df.loc[
        confirmed_mask,
        "verification_status"
    ] = "confirmed_gambling"


    df.loc[
        confirmed_mask,
        "verification_source"
    ] = df.loc[
        confirmed_mask,
        "matched_sources"
    ]


    # =====================================================
    # CONFIRMATION STRENGTH
    # =====================================================

    single_source_mask = (
        confirmed_mask
        &
        (df["source_count"] == 1)
    )

    multi_source_mask = (
        confirmed_mask
        &
        (df["source_count"] >= 2)
    )


    df.loc[
        single_source_mask,
        "confirmation_strength"
    ] = "single_source"


    df.loc[
        multi_source_mask,
        "confirmation_strength"
    ] = "multi_source"


    # =====================================================
    # PRIORITY MANUAL REVIEW
    # =====================================================
    #
    # These were not found in an external
    # gambling list but contain a gambling
    # keyword.
    #
    # They are NOT automatically gambling.
    #
    # =====================================================

    priority_review_mask = (
        (~confirmed_mask)
        &
        (
            df[
                "has_gambling_keyword"
            ] == 1
        )
    )


    df.loc[
        priority_review_mask,
        "verification_status"
    ] = "priority_review"


    # =====================================================
    # ADD MANUAL REVIEW COLUMNS
    # =====================================================

    df[
        "manual_verified_label"
    ] = pd.Series(
        pd.NA,
        index=df.index,
        dtype="Int64"
    )


    df[
        "manual_review_status"
    ] = ""


    df[
        "manual_notes"
    ] = ""


    # =====================================================
    # SELECT REPORT COLUMNS
    # =====================================================

    preferred_columns = [
        "domain",

        # Original dataset label
        "label",

        # Our new verified label
        "verified_label",

        "verification_status",
        "verification_source",
        "confirmation_strength",

        # Blocklist evidence
        "blocklist_match",
        "matched_sources",
        "source_count",

        # Manual review
        "manual_verified_label",
        "manual_review_status",
        "manual_notes",

        # Existing features
        "has_gambling_keyword",
        "url_length",
        "digit_count",
        "special_char_count",
        "dot_count",
        "has_hyphen",
        "is_ip",
        "entropy",
        "suspicious_tld",
        "domain_age_days",
        "has_domain_info",
        "ssl_valid",
        "dns_resolves",
    ]


    # Only include columns that actually
    # exist in the dataset.

    report_columns = [
        column
        for column in preferred_columns
        if column in df.columns
    ]


    # =====================================================
    # SAVE REPORT
    # =====================================================

    OUTPUT_FILE.parent.mkdir(
        parents=True,
        exist_ok=True
    )


    df[
        report_columns
    ].to_csv(
        OUTPUT_FILE,
        index=False
    )


    # =====================================================
    # SUMMARY
    # =====================================================

    confirmed_count = int(
        confirmed_mask.sum()
    )

    priority_count = int(
        priority_review_mask.sum()
    )

    needs_review_count = int(
        (
            df[
                "verification_status"
            ] == "needs_review"
        ).sum()
    )

    single_source_count = int(
        single_source_mask.sum()
    )

    multi_source_count = int(
        multi_source_mask.sum()
    )


    print(
        "\n===================================="
    )

    print(
        " VERIFICATION RESULTS"
    )

    print(
        "===================================="
    )


    print(
        "\nVerification status:"
    )

    print(
        df[
            "verification_status"
        ].value_counts()
    )


    print(
        "\nConfirmed gambling:",
        confirmed_count
    )


    print(
        "  Single-source confirmations:",
        single_source_count
    )


    print(
        "  Multi-source confirmations:",
        multi_source_count
    )


    print(
        "\nPriority manual review:",
        priority_count
    )


    print(
        "Needs review:",
        needs_review_count
    )


    print(
        "\nOriginal dataset size:",
        len(df)
    )


    print(
        "\nVerification coverage:"
    )

    coverage = (
        confirmed_count
        /
        len(df)
        *
        100
    )

    print(
        f"{coverage:.2f}% confirmed gambling"
    )


    # =====================================================
    # ORIGINAL LABEL DISAGREEMENTS
    # =====================================================

    disagreement_mask = (
        confirmed_mask
        &
        (
            df["label"] != 1
        )
    )

    disagreement_count = int(
        disagreement_mask.sum()
    )


    print(
        "\nConfirmed gambling domains "
        "originally labeled 0:"
    )

    print(
        disagreement_count
    )


    # Show up to 20 examples

    if disagreement_count > 0:

        print(
            "\nExample label disagreements:"
        )

        example_columns = [
            "domain",
            "label",
            "verified_label",
            "verification_source",
        ]

        print(
            df.loc[
                disagreement_mask,
                example_columns
            ]
            .head(20)
            .to_string(
                index=False
            )
        )


    # =====================================================
    # FINISHED
    # =====================================================

    print(
        "\n===================================="
    )

    print(
        " REPORT SAVED"
    )

    print(
        "===================================="
    )

    print(
        OUTPUT_FILE
    )

    print(
        "\nDo NOT train the model yet."
    )

    print(
        "The next step is verification of "
        "non-gambling domains."
    )


# =========================================================
# ENTRY POINT
# =========================================================

if __name__ == "__main__":
    main()