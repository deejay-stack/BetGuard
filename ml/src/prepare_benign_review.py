from pathlib import Path

import pandas as pd
import requests


# =========================================================
# BETGUARD
# EXTERNAL-CATEGORY BENIGN REVIEW PREPARATION
# =========================================================
#
# PURPOSE
# ---------------------------------------------------------
#
# We need trustworthy:
#
#     0 = NON-GAMBLING
#
# We already have externally confirmed gambling domains.
#
# We DO NOT use:
#
#     SSL
#     DNS
#     domain age
#     entropy
#     digit count
#     suspicious TLD
#
# to decide the ground-truth label.
#
# Why?
#
# Those are features that the ML model may later learn.
#
# Using them to CREATE the labels could bias the training
# dataset and make model evaluation misleading.
#
#
# Instead, this script uses:
#
#     1. Existing gambling verification
#     2. UT1 external website categories
#     3. Independent lexical risk terms
#     4. Tranco only as supporting evidence
#
#
# IMPORTANT:
#
# This script STILL DOES NOT automatically assign label 0.
#
# It produces candidates for human verification.
#
# =========================================================


# =========================================================
# PATHS
# =========================================================

INPUT_FILE = Path(
    "reports/benign_verification.csv"
)

OUTPUT_FILE = Path(
    "reports/manual_benign_review.csv"
)

TOP_BENIGN_FILE = Path(
    "reports/manual_benign_top_candidates.csv"
)

GAMBLING_RISK_FILE = Path(
    "reports/gambling_risk_review.csv"
)


# =========================================================
# UT1 SOURCE
# =========================================================

UT1_BASE_URL = (
    "https://raw.githubusercontent.com/"
    "olbat/ut1-blacklists/master/"
    "blacklists/{category}/domains"
)


# =========================================================
# STRONG NON-GAMBLING CATEGORIES
# =========================================================
#
# These categories provide comparatively useful evidence
# that a website has a clearly different primary purpose
# from gambling.
#
# They are NOT automatically converted into label 0.
#
# =========================================================

STRONG_BENIGN_CATEGORIES = [

    "ai",

    "bank",

    "child",

    "cooking",

    "educational_games",

    "jobsearch",

    "liste_bu",

    "press",

    "social_networks",

    "translation",

    "webmail",
]


# =========================================================
# SUPPORTING NON-GAMBLING CATEGORIES
# =========================================================
#
# These categories are useful but broader.
#
# They should receive human review before becoming label 0.
#
# =========================================================

SUPPORTING_BENIGN_CATEGORIES = [

    "audio-video",

    "blog",

    "financial",

    "forums",

    "mobile-phone",

    "radio",

    "shopping",

    "sports",
]


# =========================================================
# INDEPENDENT GAMBLING RISK TERMS
# =========================================================
#
# IMPORTANT:
#
# We do NOT trust the dataset's existing
# has_gambling_keyword column by itself.
#
# The previous output showed that obvious domains such as
# poker-related sites could still have that feature = 0.
#
# Therefore we independently scan the domain name.
#
#
# These terms DO NOT automatically create label 1.
#
# They only send the domain into a gambling-review queue.
#
# =========================================================

GAMBLING_RISK_TERMS = [

    "bet",

    "bets",

    "betting",

    "casino",

    "casinos",

    "slot",

    "slots",

    "poker",

    "bingo",

    "jackpot",

    "sportsbook",

    "wager",

    "roulette",

    "blackjack",

    "gambling",

    "igaming",

    "sportsbet",

    "spins",

    "spin",

    # Frequently appears in betting domains
    "bahis",
]


# =========================================================
# GAMBLING-INDUSTRY CONTEXT TERMS
# =========================================================
#
# These terms are weaker.
#
# Example:
#
#     gaming
#
# can mean:
#
#     video gaming
#
# OR
#
#     casino / iGaming
#
# So they should trigger review but NOT an automatic
# gambling classification.
#
# =========================================================

AMBIGUOUS_RISK_TERMS = [

    "gaming",

    "games",

    "play",

    "win",

    "lucky",
]


# =========================================================
# NORMALIZE DOMAIN
# =========================================================

def normalize_domain(domain):

    if pd.isna(domain):

        return ""

    domain = str(
        domain
    ).strip().lower()


    if domain.startswith(
        "https://"
    ):

        domain = domain[
            len("https://"):
        ]


    elif domain.startswith(
        "http://"
    ):

        domain = domain[
            len("http://"):
        ]


    domain = domain.split(
        "/"
    )[0]


    domain = domain.split(
        "?"
    )[0]


    domain = domain.split(
        "#"
    )[0]


    if domain.startswith(
        "www."
    ):

        domain = domain[4:]


    domain = domain.rstrip(
        "."
    )


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
# GENERATE DOMAIN CANDIDATES
# =========================================================

def generate_domain_candidates(
    domain
):

    domain = normalize_domain(
        domain
    )


    if not domain:

        return []


    parts = domain.split(
        "."
    )


    candidates = [
        domain
    ]


    # Example:
    #
    # news.example.com
    #
    # candidates:
    #
    # news.example.com
    # example.com
    #
    # Never:
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
# DOWNLOAD ONE UT1 CATEGORY
# =========================================================

def download_ut1_category(
    category
):

    url = UT1_BASE_URL.format(
        category=category
    )


    print(
        f"Downloading UT1 category: "
        f"{category}"
    )


    try:

        response = requests.get(
            url,
            timeout=60,
            headers={
                "User-Agent":
                    "BetGuard-ML-Research/1.0"
            }
        )


        response.raise_for_status()


    except requests.RequestException as error:

        print(
            f"WARNING: Could not download "
            f"{category}"
        )

        print(
            f"Reason: {error}"
        )

        return set()


    domains = set()


    for line in response.text.splitlines():

        line = line.strip()


        if not line:

            continue


        if line.startswith(
            "#"
        ):

            continue


        domain = normalize_domain(
            line
        )


        if not domain:

            continue


        # Ignore obvious IP-only rows.
        #
        # Our ML dataset focuses primarily on domains.

        if "." not in domain:

            continue


        domains.add(
            domain
        )


    print(
        f"  Loaded {len(domains):,} domains"
    )


    return domains


# =========================================================
# DOWNLOAD ALL NON-GAMBLING CATEGORIES
# =========================================================

def download_category_database():

    category_database = {}


    all_categories = (

        STRONG_BENIGN_CATEGORIES

        +

        SUPPORTING_BENIGN_CATEGORIES
    )


    print(
        "\n===================================="
    )

    print(
        " DOWNLOADING UT1 CATEGORIES"
    )

    print(
        "====================================\n"
    )


    for category in all_categories:

        domains = download_ut1_category(
            category
        )


        for domain in domains:

            if domain not in (
                category_database
            ):

                category_database[
                    domain
                ] = set()


            category_database[
                domain
            ].add(
                category
            )


    print(
        "\nUnique categorized domains loaded:"
    )


    print(
        f"{len(category_database):,}"
    )


    return category_database


# =========================================================
# FIND CATEGORY MATCH
# =========================================================

def find_category_match(
    domain,
    category_database
):

    categories = set()

    matched_domain = None

    match_type = None


    candidates = (
        generate_domain_candidates(
            domain
        )
    )


    for candidate in candidates:

        if candidate not in (
            category_database
        ):

            continue


        categories.update(
            category_database[
                candidate
            ]
        )


        if matched_domain is None:

            matched_domain = (
                candidate
            )


            if candidate == normalize_domain(
                domain
            ):

                match_type = (
                    "exact"
                )

            else:

                match_type = (
                    "parent_domain"
                )


    return (
        matched_domain,
        categories,
        match_type,
    )


# =========================================================
# FIND GAMBLING RISK TERMS
# =========================================================

def find_risk_terms(
    domain
):

    domain = normalize_domain(
        domain
    )


    compact_domain = (
        domain
        .replace(
            ".",
            ""
        )
        .replace(
            "-",
            ""
        )
        .replace(
            "_",
            ""
        )
    )


    strong_terms = []


    for term in (
        GAMBLING_RISK_TERMS
    ):

        if term in compact_domain:

            strong_terms.append(
                term
            )


    ambiguous_terms = []


    for term in (
        AMBIGUOUS_RISK_TERMS
    ):

        if term in compact_domain:

            ambiguous_terms.append(
                term
            )


    return (
        sorted(
            set(
                strong_terms
            )
        ),
        sorted(
            set(
                ambiguous_terms
            )
        ),
    )


# =========================================================
# CLASSIFY REVIEW STATUS
# =========================================================

def classify_review_status(
    row
):

    # -----------------------------------------------------
    # Already externally confirmed gambling
    # -----------------------------------------------------

    if (
        row[
            "verification_status"
        ]
        ==
        "confirmed_gambling"
    ):

        return (
            "confirmed_gambling",
            99,
            "Already externally confirmed gambling"
        )


    strong_risk = str(
        row.get(
            "strong_risk_terms",
            ""
        )
    ).strip()


    ambiguous_risk = str(
        row.get(
            "ambiguous_risk_terms",
            ""
        )
    ).strip()


    strong_categories = str(
        row.get(
            "strong_benign_categories",
            ""
        )
    ).strip()


    supporting_categories = str(
        row.get(
            "supporting_benign_categories",
            ""
        )
    ).strip()


    tranco_rank = row.get(
        "tranco_rank"
    )


    # -----------------------------------------------------
    # Strong gambling lexical evidence
    # -----------------------------------------------------

    if strong_risk:

        return (
            "priority_gambling_review",
            5,
            (
                "Domain contains gambling-related "
                "term(s): "
                f"{strong_risk}"
            )
        )


    # -----------------------------------------------------
    # Strong external non-gambling category
    # -----------------------------------------------------

    if strong_categories:

        return (
            "strong_benign_review_candidate",
            1,
            (
                "Matched UT1 non-gambling "
                "category: "
                f"{strong_categories}"
            )
        )


    # -----------------------------------------------------
    # Supporting external category
    # -----------------------------------------------------

    if supporting_categories:

        # Ambiguous words such as gaming/play/win
        # make us more cautious.

        if ambiguous_risk:

            return (
                "category_conflict_review",
                4,
                (
                    "Non-gambling category match "
                    "but ambiguous domain term(s): "
                    f"{ambiguous_risk}"
                )
            )


        return (
            "supporting_benign_review_candidate",
            2,
            (
                "Matched supporting UT1 "
                "category: "
                f"{supporting_categories}"
            )
        )


    # -----------------------------------------------------
    # Tranco-only evidence
    # -----------------------------------------------------

    if not pd.isna(
        tranco_rank
    ):

        if ambiguous_risk:

            return (
                "tranco_with_risk_review",
                4,
                (
                    "Popular domain but contains "
                    "ambiguous term(s): "
                    f"{ambiguous_risk}"
                )
            )


        return (
            "tranco_only_review_candidate",
            3,
            (
                "Appears in Tranco but has no "
                "external category match"
            )
        )


    # -----------------------------------------------------
    # Ambiguous lexical term only
    # -----------------------------------------------------

    if ambiguous_risk:

        return (
            "ambiguous_domain_review",
            4,
            (
                "Contains ambiguous term(s): "
                f"{ambiguous_risk}"
            )
        )


    # -----------------------------------------------------
    # No evidence
    # -----------------------------------------------------

    return (
        "needs_manual_review",
        6,
        "No external category evidence"
    )


# =========================================================
# MAIN
# =========================================================

def main():

    print(
        "\n===================================="
    )

    print(
        " BETGUARD BENIGN REVIEW V2"
    )

    print(
        "===================================="
    )


    # =====================================================
    # LOAD PREVIOUS REPORT
    # =====================================================

    if not INPUT_FILE.exists():

        raise FileNotFoundError(

            "\nCould not find:\n"
            f"{INPUT_FILE}\n\n"

            "Run verify_benign.py first."
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
    # DOWNLOAD EXTERNAL CATEGORIES
    # =====================================================

    category_database = (
        download_category_database()
    )


    # =====================================================
    # MATCH CATEGORIES
    # =====================================================

    category_match_domains = []

    category_match_types = []

    all_category_matches = []

    strong_category_matches = []

    supporting_category_matches = []


    print(
        "\nMatching dataset against "
        "UT1 categories..."
    )


    for domain in df[
        "domain"
    ]:

        (
            matched_domain,
            categories,
            match_type,
        ) = find_category_match(

            domain,
            category_database
        )


        category_match_domains.append(
            matched_domain
        )


        category_match_types.append(
            match_type
        )


        sorted_categories = sorted(
            categories
        )


        all_category_matches.append(

            ", ".join(
                sorted_categories
            )
        )


        strong_matches = [

            category

            for category in (
                sorted_categories
            )

            if category in (
                STRONG_BENIGN_CATEGORIES
            )
        ]


        supporting_matches = [

            category

            for category in (
                sorted_categories
            )

            if category in (
                SUPPORTING_BENIGN_CATEGORIES
            )
        ]


        strong_category_matches.append(

            ", ".join(
                strong_matches
            )
        )


        supporting_category_matches.append(

            ", ".join(
                supporting_matches
            )
        )


    df[
        "ut1_category_match"
    ] = category_match_domains


    df[
        "ut1_category_match_type"
    ] = category_match_types


    df[
        "ut1_categories"
    ] = all_category_matches


    df[
        "strong_benign_categories"
    ] = strong_category_matches


    df[
        "supporting_benign_categories"
    ] = supporting_category_matches


    # =====================================================
    # INDEPENDENT DOMAIN RISK SCAN
    # =====================================================

    strong_risk_column = []

    ambiguous_risk_column = []


    for domain in df[
        "domain"
    ]:

        (
            strong_terms,
            ambiguous_terms,
        ) = find_risk_terms(
            domain
        )


        strong_risk_column.append(

            ", ".join(
                strong_terms
            )
        )


        ambiguous_risk_column.append(

            ", ".join(
                ambiguous_terms
            )
        )


    df[
        "strong_risk_terms"
    ] = strong_risk_column


    df[
        "ambiguous_risk_terms"
    ] = ambiguous_risk_column


    # =====================================================
    # CLASSIFY REVIEW QUEUE
    # =====================================================

    statuses = []

    priorities = []

    reasons = []


    for _, row in df.iterrows():

        (
            status,
            priority,
            reason,
        ) = classify_review_status(
            row
        )


        statuses.append(
            status
        )


        priorities.append(
            priority
        )


        reasons.append(
            reason
        )


    df[
        "review_status_v2"
    ] = statuses


    df[
        "review_priority"
    ] = priorities


    df[
        "review_reason"
    ] = reasons


    # =====================================================
    # HUMAN REVIEW FIELDS
    # =====================================================
    #
    # manual_verified_label:
    #
    #     0 = confirmed non-gambling
    #     1 = confirmed gambling
    #
    # Leave blank when uncertain.
    #
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
    ] = "pending"


    df[
        "verification_method"
    ] = ""


    df[
        "manual_notes"
    ] = ""


    # =====================================================
    # REMOVE ALREADY CONFIRMED GAMBLING
    # =====================================================

    unresolved = df[

        df[
            "verification_status"
        ]

        !=

        "confirmed_gambling"

    ].copy()


    # =====================================================
    # SORT
    # =====================================================

    unresolved = (
        unresolved.sort_values(

            by=[
                "review_priority",
                "tranco_rank",
                "domain",
            ],

            ascending=[
                True,
                True,
                True,
            ],

            na_position="last"
        )
    )


    # =====================================================
    # OUTPUT COLUMNS
    # =====================================================

    preferred_columns = [

        "domain",

        # Original untrusted label
        "label",

        # Externally verified positive label
        "verified_label",

        "verification_status",
        "verification_source",

        # V2 verification evidence
        "review_status_v2",
        "review_priority",
        "review_reason",

        # UT1 evidence
        "ut1_category_match",
        "ut1_category_match_type",
        "ut1_categories",
        "strong_benign_categories",
        "supporting_benign_categories",

        # Independent lexical review
        "strong_risk_terms",
        "ambiguous_risk_terms",

        # Popularity evidence only
        "tranco_rank",
        "tranco_match",
        "tranco_match_type",

        # Existing feature shown for reference,
        # but NOT used for labeling
        "has_gambling_keyword",

        # Human work
        "manual_verified_label",
        "manual_review_status",
        "verification_method",
        "manual_notes",
    ]


    output_columns = [

        column

        for column in preferred_columns

        if column in unresolved.columns
    ]


    # =====================================================
    # SAVE FULL REVIEW QUEUE
    # =====================================================

    OUTPUT_FILE.parent.mkdir(

        parents=True,

        exist_ok=True
    )


    unresolved[
        output_columns
    ].to_csv(

        OUTPUT_FILE,

        index=False
    )


    # =====================================================
    # TOP BENIGN CANDIDATES
    # =====================================================
    #
    # Only external-category-backed candidates.
    #
    # No SSL, DNS, age or other ML feature determines
    # inclusion here.
    #
    # =====================================================

    benign_statuses = [

        "strong_benign_review_candidate",

        "supporting_benign_review_candidate",

        "tranco_only_review_candidate",
    ]


    top_benign = unresolved[

        unresolved[
            "review_status_v2"
        ].isin(
            benign_statuses
        )

    ].copy()


    top_benign = top_benign.head(
        150
    )


    top_benign[
        output_columns
    ].to_csv(

        TOP_BENIGN_FILE,

        index=False
    )


    # =====================================================
    # GAMBLING-RISK QUEUE
    # =====================================================

    gambling_review_statuses = [

        "priority_gambling_review",

        "category_conflict_review",

        "tranco_with_risk_review",

        "ambiguous_domain_review",
    ]


    gambling_risk = unresolved[

        unresolved[
            "review_status_v2"
        ].isin(
            gambling_review_statuses
        )

    ].copy()


    gambling_risk[
        output_columns
    ].to_csv(

        GAMBLING_RISK_FILE,

        index=False
    )


    # =====================================================
    # SUMMARY
    # =====================================================

    print(
        "\n===================================="
    )

    print(
        " REVIEW RESULTS"
    )

    print(
        "===================================="
    )


    print(
        "\nReview status counts:"
    )


    print(

        unresolved[
            "review_status_v2"
        ].value_counts()
    )


    # =====================================================
    # CATEGORY COVERAGE
    # =====================================================

    category_match_count = int(

        unresolved[
            "ut1_categories"
        ]
        .fillna("")
        .str.strip()
        .ne("")
        .sum()
    )


    print(
        "\nUnresolved domains with "
        "UT1 category evidence:"
    )


    print(
        category_match_count
    )


    # =====================================================
    # RISK COUNT
    # =====================================================

    strong_risk_count = int(

        unresolved[
            "strong_risk_terms"
        ]
        .fillna("")
        .str.strip()
        .ne("")
        .sum()
    )


    print(
        "\nDomains containing strong "
        "gambling-risk terms:"
    )


    print(
        strong_risk_count
    )


    # =====================================================
    # FILE COUNTS
    # =====================================================

    print(
        "\nBenign review candidates:"
    )


    print(
        len(
            top_benign
        )
    )


    print(
        "\nGambling-risk review candidates:"
    )


    print(
        len(
            gambling_risk
        )
    )


    # =====================================================
    # SAMPLE BENIGN CANDIDATES
    # =====================================================

    if len(
        top_benign
    ) > 0:

        print(
            "\nTop 20 benign-review candidates:"
        )


        display_columns = [

            "domain",

            "review_status_v2",

            "ut1_categories",

            "tranco_rank",

            "strong_risk_terms",
        ]


        display_columns = [

            column

            for column in display_columns

            if column in (
                top_benign.columns
            )
        ]


        print(

            top_benign[
                display_columns
            ]

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
        " FILES CREATED"
    )

    print(
        "===================================="
    )


    print(
        "\nFull unresolved review:"
    )


    print(
        OUTPUT_FILE
    )


    print(
        "\nBenign candidate batch:"
    )


    print(
        TOP_BENIGN_FILE
    )


    print(
        "\nGambling-risk review:"
    )


    print(
        GAMBLING_RISK_FILE
    )


    print(
        "\nIMPORTANT:"
    )


    print(
        "No unresolved domain was "
        "automatically assigned label 0."
    )


    print(
        "\nSSL, DNS, domain age, entropy and "
        "other future ML features were NOT "
        "used to create benign labels."
    )


    print(
        "\nNext step:"
    )


    print(
        "Review the external-category-backed "
        "benign candidates."
    )


# =========================================================
# ENTRY POINT
# =========================================================

if __name__ == "__main__":

    main()