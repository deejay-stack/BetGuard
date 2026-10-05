from pathlib import Path

import ipaddress
import math
import random

import pandas as pd
import requests


# =========================================================
# BETGUARD
# BUILD BALANCED DOMAIN TRAINING DATASET
# =========================================================
#
# PURPOSE
#
# Build a clean binary dataset:
#
#     0 = NON-GAMBLING
#     1 = GAMBLING
#
#
# POSITIVE CLASS:
#
# Existing externally/manual verified gambling domains.
#
#
# NEGATIVE CLASS:
#
# Independently categorized non-gambling domains from
# selected UT1 categories.
#
#
# IMPORTANT:
#
# This is the dataset for our FIRST BASELINE MODEL.
#
# It intentionally uses DOMAIN TEXT ONLY.
#
# SSL, DNS, domain age and other network features will
# be collected later for BOTH classes.
#
# =========================================================


# =========================================================
# RANDOM SEED
# =========================================================

RANDOM_SEED = 42

random.seed(
    RANDOM_SEED
)


# =========================================================
# PATHS
# =========================================================

VERIFIED_INPUT = Path(
    "data/processed/verified_training_candidates.csv"
)

OUTPUT_FILE = Path(
    "data/processed/balanced_domain_dataset.csv"
)

POSITIVE_FILE = Path(
    "data/processed/gambling_domains_verified.csv"
)

NEGATIVE_FILE = Path(
    "data/processed/non_gambling_domains_verified.csv"
)

SUMMARY_FILE = Path(
    "reports/balanced_dataset_summary.csv"
)

CONFLICT_FILE = Path(
    "reports/benign_gambling_conflicts.csv"
)


# =========================================================
# EXTERNAL SOURCES
# =========================================================

UT1_BASE_URL = (
    "https://raw.githubusercontent.com/"
    "olbat/ut1-blacklists/master/"
    "blacklists/{category}/domains"
)


BLOCKLIST_SOURCES = {

    "Block List Project": (
        "https://raw.githubusercontent.com/"
        "blocklistproject/Lists/master/"
        "gambling.txt"
    ),

    "UT1 Gambling": (
        "https://raw.githubusercontent.com/"
        "olbat/ut1-blacklists/master/"
        "blacklists/gambling/domains"
    ),
}


# =========================================================
# NON-GAMBLING CATEGORIES
# =========================================================
#
# These were chosen because their primary purposes are
# clearly different from gambling.
#
# We intentionally include:
#
#     games
#     sports
#
# because they are useful HARD NEGATIVES.
#
# The model must learn that:
#
#     game != gambling
#     sports != sports betting
#
# =========================================================

BENIGN_CATEGORIES = [

    "bank",

    "jobsearch",

    "press",

    "social_networks",

    "webmail",

    "translation",

    "cooking",

    "child",

    "educational_games",

    "games",

    "sports",

    "shopping",

    "audio-video",
]


# =========================================================
# GAMBLING RISK TERMS
# =========================================================
#
# External category candidates containing one of these
# terms are NOT automatically accepted as negative.
#
# They go into a conflict report instead.
#
# =========================================================

GAMBLING_RISK_TERMS = [

    "casino",

    "casinos",

    "bet",

    "betting",

    "sportsbook",

    "poker",

    "slot",

    "slots",

    "bingo",

    "jackpot",

    "roulette",

    "blackjack",

    "wager",

    "gambling",

    "igaming",

    "bahis",
]


# =========================================================
# DOMAIN NORMALIZATION
# =========================================================

def normalize_domain(domain):

    if pd.isna(domain):

        return ""

    domain = str(
        domain
    ).strip().lower()


    # Remove protocols

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


    # Remove path

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


    # Remove www

    if domain.startswith(
        "www."
    ):

        domain = domain[4:]


    # Remove trailing dot

    domain = domain.rstrip(
        "."
    )


    # Remove hostname port

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
# CHECK IP ADDRESS
# =========================================================

def is_ip_address(value):

    try:

        ipaddress.ip_address(
            value
        )

        return True

    except ValueError:

        return False


# =========================================================
# VALID DOMAIN CHECK
# =========================================================

def is_valid_domain(domain):

    if not domain:

        return False


    if is_ip_address(
        domain
    ):

        return False


    if "." not in domain:

        return False


    if len(domain) > 253:

        return False


    if " " in domain:

        return False


    return True


# =========================================================
# DOMAIN CANDIDATES
# =========================================================
#
# Used for parent-domain blocklist matching.
#
# Example:
#
# casino.example.com
#
# generates:
#
# casino.example.com
# example.com
#
# =========================================================

def generate_domain_candidates(domain):

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
# PARSE DOMAIN LIST
# =========================================================

def parse_domain_list(text):

    domains = set()


    for line in text.splitlines():

        line = line.strip()


        if not line:

            continue


        if line.startswith(
            "#"
        ):

            continue


        # Some blocklists:
        #
        # 0.0.0.0 example.com

        parts = line.split()


        if len(parts) >= 2:

            possible_domain = parts[-1]

        else:

            possible_domain = parts[0]


        possible_domain = (
            possible_domain.replace(
                "*.",
                ""
            )
        )


        domain = normalize_domain(
            possible_domain
        )


        if not is_valid_domain(
            domain
        ):

            continue


        domains.add(
            domain
        )


    return domains


# =========================================================
# DOWNLOAD URL
# =========================================================

def download_text(
    url,
    description
):

    print(
        f"Downloading: {description}"
    )


    try:

        response = requests.get(

            url,

            timeout=90,

            headers={

                "User-Agent":
                    "BetGuard-ML-Research/1.0"
            }
        )


        response.raise_for_status()


    except requests.RequestException as error:

        raise RuntimeError(

            f"\nCould not download "
            f"{description}\n"

            f"Reason: {error}"
        )


    return response.text


# =========================================================
# DOWNLOAD GAMBLING DATABASE
# =========================================================

def download_gambling_database():

    gambling_database = set()


    print(
        "\n===================================="
    )

    print(
        " DOWNLOADING GAMBLING BLOCKLISTS"
    )

    print(
        "====================================\n"
    )


    for source_name, url in (
        BLOCKLIST_SOURCES.items()
    ):

        text = download_text(
            url,
            source_name
        )


        domains = parse_domain_list(
            text
        )


        print(
            f"  {len(domains):,} domains loaded"
        )


        gambling_database.update(
            domains
        )


    print(
        "\nUnique gambling domains:"
    )

    print(
        f"{len(gambling_database):,}"
    )


    return gambling_database


# =========================================================
# CHECK GAMBLING BLOCKLIST MATCH
# =========================================================

def matches_gambling_database(
    domain,
    gambling_database
):

    candidates = (
        generate_domain_candidates(
            domain
        )
    )


    for candidate in candidates:

        if candidate in (
            gambling_database
        ):

            return True


    return False


# =========================================================
# FIND GAMBLING RISK TERMS
# =========================================================

def find_gambling_terms(
    domain
):

    compact = (
        normalize_domain(
            domain
        )
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


    matches = []


    for term in (
        GAMBLING_RISK_TERMS
    ):

        if term in compact:

            matches.append(
                term
            )


    return sorted(
        set(
            matches
        )
    )


# =========================================================
# DOWNLOAD BENIGN CATEGORY DATABASE
# =========================================================

def download_benign_categories():

    database = {}


    print(
        "\n===================================="
    )

    print(
        " DOWNLOADING BENIGN CATEGORIES"
    )

    print(
        "====================================\n"
    )


    for category in (
        BENIGN_CATEGORIES
    ):

        url = UT1_BASE_URL.format(
            category=category
        )


        text = download_text(
            url,
            f"UT1 {category}"
        )


        domains = parse_domain_list(
            text
        )


        print(
            f"  {category}: "
            f"{len(domains):,}"
        )


        for domain in domains:

            if domain not in database:

                database[
                    domain
                ] = set()


            database[
                domain
            ].add(
                category
            )


    print(
        "\nUnique benign-category domains:"
    )

    print(
        f"{len(database):,}"
    )


    return database


# =========================================================
# LOAD VERIFIED POSITIVES
# =========================================================

def load_verified_domains():

    if not VERIFIED_INPUT.exists():

        raise FileNotFoundError(

            f"\nCould not find:\n"
            f"{VERIFIED_INPUT}\n\n"

            "Run apply_manual_labels.py first."
        )


    df = pd.read_csv(
        VERIFIED_INPUT
    )


    required = [

        "domain",

        "final_verified_label",
    ]


    missing = [

        column

        for column in required

        if column not in df.columns
    ]


    if missing:

        raise ValueError(

            "Verified dataset is missing "
            f"columns: {missing}"
        )


    df[
        "domain"
    ] = df[
        "domain"
    ].apply(
        normalize_domain
    )


    df[
        "final_verified_label"
    ] = pd.to_numeric(

        df[
            "final_verified_label"
        ],

        errors="coerce"
    )


    df = df[
        df[
            "final_verified_label"
        ].isin(
            [0, 1]
        )
    ].copy()


    df = (
        df.drop_duplicates(
            subset=[
                "domain"
            ]
        )
    )


    positive = df[
        df[
            "final_verified_label"
        ]
        ==
        1
    ].copy()


    negative = df[
        df[
            "final_verified_label"
        ]
        ==
        0
    ].copy()


    return (
        positive,
        negative
    )


# =========================================================
# BUILD BENIGN POOL
# =========================================================

def build_benign_pool(
    category_database,
    gambling_database,
    positive_domains
):

    accepted_rows = []

    conflict_rows = []


    print(
        "\nFiltering benign candidate pool..."
    )


    for domain, categories in (
        category_database.items()
    ):

        # -----------------------------------------
        # Already positive
        # -----------------------------------------

        if domain in positive_domains:

            conflict_rows.append({

                "domain": domain,

                "categories":
                    ", ".join(
                        sorted(categories)
                    ),

                "reason":
                    "Already verified gambling",
            })

            continue


        # -----------------------------------------
        # Gambling-list overlap
        # -----------------------------------------

        if matches_gambling_database(
            domain,
            gambling_database
        ):

            conflict_rows.append({

                "domain": domain,

                "categories":
                    ", ".join(
                        sorted(categories)
                    ),

                "reason":
                    "Also found in gambling blocklist",
            })

            continue


        # -----------------------------------------
        # Gambling lexical risk
        # -----------------------------------------

        risk_terms = (
            find_gambling_terms(
                domain
            )
        )


        if risk_terms:

            conflict_rows.append({

                "domain": domain,

                "categories":
                    ", ".join(
                        sorted(categories)
                    ),

                "reason":
                    (
                        "Gambling-risk term: "
                        +
                        ", ".join(
                            risk_terms
                        )
                    ),
            })

            continue


        # -----------------------------------------
        # Accepted external negative candidate
        # -----------------------------------------

        accepted_rows.append({

            "domain": domain,

            "categories":
                ", ".join(
                    sorted(categories)
                ),
        })


    accepted = pd.DataFrame(
        accepted_rows
    )


    conflicts = pd.DataFrame(
        conflict_rows
    )


    return (
        accepted,
        conflicts
    )


# =========================================================
# DIVERSE CATEGORY SAMPLING
# =========================================================

def select_diverse_negatives(
    pool,
    number_needed,
    already_selected
):

    rng = random.Random(
        RANDOM_SEED
    )


    selected_domains = set(
        already_selected
    )


    selected_rows = []


    if number_needed <= 0:

        return pd.DataFrame(
            columns=[
                "domain",
                "categories",
            ]
        )


    # -----------------------------------------------------
    # Approximate equal contribution from categories
    # -----------------------------------------------------

    category_quota = math.ceil(

        number_needed

        /

        len(
            BENIGN_CATEGORIES
        )
    )


    print(
        "\nTarget external negatives:",
        number_needed
    )


    print(
        "Approximate per-category quota:",
        category_quota
    )


    # -----------------------------------------------------
    # First pass: balanced across categories
    # -----------------------------------------------------

    for category in (
        BENIGN_CATEGORIES
    ):

        category_candidates = []


        for _, row in pool.iterrows():

            domain = row[
                "domain"
            ]


            if domain in selected_domains:

                continue


            categories = [

                item.strip()

                for item in str(
                    row[
                        "categories"
                    ]
                ).split(",")
            ]


            if category in categories:

                category_candidates.append(
                    row.to_dict()
                )


        rng.shuffle(
            category_candidates
        )


        chosen = (
            category_candidates[
                :category_quota
            ]
        )


        for row in chosen:

            domain = row[
                "domain"
            ]


            if domain in selected_domains:

                continue


            selected_rows.append(
                row
            )


            selected_domains.add(
                domain
            )


            if len(
                selected_rows
            ) >= number_needed:

                break


        if len(
            selected_rows
        ) >= number_needed:

            break


    # -----------------------------------------------------
    # Second pass: fill remaining space
    # -----------------------------------------------------

    if len(
        selected_rows
    ) < number_needed:

        remaining_rows = []


        for _, row in pool.iterrows():

            domain = row[
                "domain"
            ]


            if domain in selected_domains:

                continue


            remaining_rows.append(
                row.to_dict()
            )


        rng.shuffle(
            remaining_rows
        )


        remaining_needed = (
            number_needed
            -
            len(
                selected_rows
            )
        )


        for row in (
            remaining_rows[
                :remaining_needed
            ]
        ):

            selected_rows.append(
                row
            )


            selected_domains.add(
                row[
                    "domain"
                ]
            )


    selected = pd.DataFrame(
        selected_rows
    )


    if len(
        selected
    ) < number_needed:

        raise RuntimeError(

            "\nNot enough verified benign candidates.\n"

            f"Needed: {number_needed}\n"

            f"Found: {len(selected)}"
        )


    return selected


# =========================================================
# MAIN
# =========================================================

def main():

    print(
        "\n===================================="
    )

    print(
        " BETGUARD TRAINING DATASET BUILDER"
    )

    print(
        "===================================="
    )


    # =====================================================
    # LOAD VERIFIED DATA
    # =====================================================

    (
        positive_df,
        existing_negative_df,

    ) = load_verified_domains()


    positive_domains = set(
        positive_df[
            "domain"
        ]
    )


    existing_negative_domains = set(
        existing_negative_df[
            "domain"
        ]
    )


    positive_count = len(
        positive_domains
    )


    existing_negative_count = len(
        existing_negative_domains
    )


    print(
        "\nVerified gambling domains:",
        positive_count
    )


    print(
        "Existing verified non-gambling:",
        existing_negative_count
    )


    # =====================================================
    # TARGET BALANCED DATASET
    # =====================================================

    target_negative_count = (
        positive_count
    )


    external_negatives_needed = max(

        0,

        target_negative_count
        -
        existing_negative_count
    )


    # =====================================================
    # DOWNLOAD SOURCES
    # =====================================================

    gambling_database = (
        download_gambling_database()
    )


    benign_database = (
        download_benign_categories()
    )


    # =====================================================
    # FILTER BENIGN POOL
    # =====================================================

    (
        benign_pool,
        conflicts,

    ) = build_benign_pool(

        benign_database,

        gambling_database,

        positive_domains
    )


    print(
        "\nSafe benign candidate pool:",
        len(
            benign_pool
        )
    )


    print(
        "Rejected/conflicting candidates:",
        len(
            conflicts
        )
    )


    # =====================================================
    # SAVE CONFLICT REPORT
    # =====================================================

    CONFLICT_FILE.parent.mkdir(

        parents=True,

        exist_ok=True
    )


    conflicts.to_csv(

        CONFLICT_FILE,

        index=False
    )


    # =====================================================
    # SELECT EXTERNAL NEGATIVES
    # =====================================================

    external_negative_df = (
        select_diverse_negatives(

            benign_pool,

            external_negatives_needed,

            already_selected=(
                existing_negative_domains
                |
                positive_domains
            ),
        )
    )


    # =====================================================
    # PREPARE POSITIVE DATASET
    # =====================================================

    positives = pd.DataFrame({

        "domain":
            sorted(
                positive_domains
            ),

        "label":
            1,

        "source":
            "verified_gambling",
    })


    positives[
        "category"
    ] = "gambling"


    # =====================================================
    # PREPARE EXISTING MANUAL NEGATIVES
    # =====================================================

    existing_negatives = pd.DataFrame({

        "domain":
            sorted(
                existing_negative_domains
            ),

        "label":
            0,

        "source":
            "manual_verified_non_gambling",
    })


    existing_negatives[
        "category"
    ] = "manual"


    # =====================================================
    # PREPARE EXTERNAL NEGATIVES
    # =====================================================

    external_negatives = pd.DataFrame({

        "domain":
            external_negative_df[
                "domain"
            ],

        "label":
            0,

        "source":
            "UT1_non_gambling_category",

        "category":
            external_negative_df[
                "categories"
            ],
    })


    # =====================================================
    # COMBINE NEGATIVES
    # =====================================================

    negatives = pd.concat(

        [
            existing_negatives,
            external_negatives,
        ],

        ignore_index=True
    )


    negatives = (
        negatives.drop_duplicates(
            subset=[
                "domain"
            ]
        )
    )


    # =====================================================
    # VALIDATE NEGATIVE COUNT
    # =====================================================

    if len(
        negatives
    ) != positive_count:

        raise RuntimeError(

            "\nClass balancing failed.\n"

            f"Positive domains: {positive_count}\n"

            f"Negative domains: {len(negatives)}"
        )


    # =====================================================
    # CHECK POSITIVE / NEGATIVE OVERLAP
    # =====================================================

    overlap = (
        set(
            positives[
                "domain"
            ]
        )

        &

        set(
            negatives[
                "domain"
            ]
        )
    )


    if overlap:

        print(
            "\nERROR:"
        )

        print(
            "Positive/negative domain overlap:"
        )


        for domain in sorted(
            overlap
        ):

            print(
                " -",
                domain
            )


        raise RuntimeError(
            "Dataset contains class overlap."
        )


    # =====================================================
    # COMBINE FULL TRAINING DATASET
    # =====================================================

    final_df = pd.concat(

        [
            positives,
            negatives,
        ],

        ignore_index=True
    )


    # Shuffle reproducibly

    final_df = (

        final_df.sample(

            frac=1,

            random_state=(
                RANDOM_SEED
            )

        )

        .reset_index(
            drop=True
        )
    )


    # =====================================================
    # FINAL DUPLICATE CHECK
    # =====================================================

    duplicate_count = int(

        final_df[
            "domain"
        ].duplicated().sum()
    )


    if duplicate_count > 0:

        raise RuntimeError(

            f"Final dataset contains "
            f"{duplicate_count} duplicate domains."
        )


    # =====================================================
    # SAVE DATASETS
    # =====================================================

    OUTPUT_FILE.parent.mkdir(

        parents=True,

        exist_ok=True
    )


    positives.to_csv(

        POSITIVE_FILE,

        index=False
    )


    negatives.to_csv(

        NEGATIVE_FILE,

        index=False
    )


    final_df.to_csv(

        OUTPUT_FILE,

        index=False
    )


    # =====================================================
    # SUMMARY
    # =====================================================

    summary = (

        final_df[
            "label"
        ]

        .value_counts()

        .rename_axis(
            "label"
        )

        .reset_index(
            name="count"
        )
    )


    summary[
        "meaning"
    ] = summary[
        "label"
    ].map({

        0:
            "non-gambling",

        1:
            "gambling",
    })


    SUMMARY_FILE.parent.mkdir(

        parents=True,

        exist_ok=True
    )


    summary.to_csv(

        SUMMARY_FILE,

        index=False
    )


    # =====================================================
    # DISPLAY RESULTS
    # =====================================================

    print(
        "\n===================================="
    )

    print(
        " FINAL DATASET"
    )

    print(
        "===================================="
    )


    print(
        "\nClass distribution:"
    )


    print(
        final_df[
            "label"
        ].value_counts()
    )


    print(
        "\nTotal domains:",
        len(
            final_df
        )
    )


    print(
        "Unique domains:",
        final_df[
            "domain"
        ].nunique()
    )


    print(
        "Duplicate domains:",
        duplicate_count
    )


    # =====================================================
    # CATEGORY DISTRIBUTION
    # =====================================================

    print(
        "\nNon-gambling source distribution:"
    )


    print(
        negatives[
            "source"
        ].value_counts()
    )


    print(
        "\nExample non-gambling domains:"
    )


    print(

        negatives[

            [
                "domain",
                "category",
            ]

        ]

        .head(20)

        .to_string(
            index=False
        )
    )


    # =====================================================
    # FILES
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
        "\nBalanced training dataset:"
    )

    print(
        OUTPUT_FILE
    )


    print(
        "\nGambling class:"
    )

    print(
        POSITIVE_FILE
    )


    print(
        "\nNon-gambling class:"
    )

    print(
        NEGATIVE_FILE
    )


    print(
        "\nBenign/gambling conflicts:"
    )

    print(
        CONFLICT_FILE
    )


    print(
        "\nSummary:"
    )

    print(
        SUMMARY_FILE
    )


    print(
        "\nNEXT STEP:"
    )


    print(
        "Train the character TF-IDF + "
        "Logistic Regression baseline."
    )


# =========================================================
# ENTRY POINT
# =========================================================

if __name__ == "__main__":

    main()