from pathlib import Path

import pandas as pd
import tldextract


# =========================================================
# BETGUARD
# EXTERNAL HOLDOUT BUILDER
# =========================================================
#
# This dataset is NOT used for:
#
#     training
#     threshold selection
#     feature engineering
#
# It is used only for external evaluation.
#
#
# LABEL:
#
#     0 = non-gambling
#     1 = gambling
#
# =========================================================


TRAINING_DATASET = Path(
    "data/processed/balanced_domain_dataset.csv"
)

OUTPUT_FILE = Path(
    "data/processed/external_holdout.csv"
)

EXCLUDED_FILE = Path(
    "reports/external_holdout_excluded.csv"
)


TLD_EXTRACTOR = tldextract.TLDExtract(
    suffix_list_urls=()
)


# =========================================================
# DOMAINS ALREADY USED DURING MANUAL DEVELOPMENT TESTING
# =========================================================

DEVELOPMENT_TESTED = {
    "bet365.com",
    "wikipedia.org",

    "google.com",
    "github.com",
    "microsoft.com",
    "youtube.com",
    "reddit.com",
    "stackoverflow.com",

    "stake.com",
    "pokerstars.com",
    "betfair.com",
    "betway.com",
    "888casino.com",
    "draftkings.com",
}


# =========================================================
# EXTERNAL GAMBLING HOLDOUT
# =========================================================
#
# Main sources:
#
# New Jersey Division of Gaming Enforcement
# PAGCOR public gaming-domain information
#
# =========================================================

GAMBLING_DOMAINS = [

    # New Jersey DGE

    ("play.ballybet.com", "NJ DGE"),
    ("casino.fanatics.com", "NJ DGE"),
    ("play.monopolycasinous.com", "NJ DGE"),

    ("borgataonline.com", "NJ DGE"),
    ("nj.partycasino.com", "NJ DGE"),
    ("nj.partypoker.com", "NJ DGE"),
    ("nj.betmgm.com", "NJ DGE"),
    ("wheeloffortunecasino.com", "NJ DGE"),
    ("stardustcasino.com", "NJ DGE"),

    ("nj.embercasino.com", "NJ DGE"),
    ("nj.betinia.com", "NJ DGE"),
    ("nj.playvegasclub.com", "NJ DGE"),

    ("casino.jackpocket.com", "NJ DGE"),
    ("nj.betparx.com", "NJ DGE"),

    ("caesarspalaceonline.com", "NJ DGE"),
    ("horseshoeonlinecasino.com", "NJ DGE"),
    ("wsop.com", "NJ DGE"),
    ("tropicanacasino.com", "NJ DGE"),

    ("casino.fanduel.com", "NJ DGE"),
    ("poker.fanduel.com", "NJ DGE"),
    ("goldennuggetcasino.com", "NJ DGE"),
    ("nj-casino.goldennuggetcasino.com", "NJ DGE"),
    ("nj.betrivers.com", "NJ DGE"),

    ("hardrock.bet", "NJ DGE"),

    ("betocean.com", "NJ DGE"),
    ("nj.playstar.com", "NJ DGE"),
    ("jackiecasino.playstar.com", "NJ DGE"),
    ("rwbetnj.com", "NJ DGE"),

    ("resortscasino.com", "NJ DGE"),
    ("thescore.bet", "NJ DGE"),
    ("hollywoodcasino.com", "NJ DGE"),
    ("casino.draftkings.com", "NJ DGE"),
    ("mohegansuncasino.com", "NJ DGE"),
    ("pokerstarsnj.com", "NJ DGE"),

    ("sportsbook.caesars.com", "NJ DGE"),
    ("sportsbook.fanduel.com", "NJ DGE"),
    ("sportsbook.draftkings.com", "NJ DGE"),
    ("nj.primesports.com", "NJ DGE"),

    # PAGCOR-published gambling domains

    ("midoricasino.com", "PAGCOR"),
    ("solaireonlinecasino.com", "PAGCOR"),
    ("dheightscasino.com", "PAGCOR"),
    ("thunderbirdonlinerizal.com", "PAGCOR"),
    ("hannliveonline.com", "PAGCOR"),
    ("laviergp.com", "PAGCOR"),
    ("winfordonline.com", "PAGCOR"),
    ("casinoplus.com.ph", "PAGCOR"),
    ("fortunegatecasino.com", "PAGCOR"),
    ("casinofortunegate.com", "PAGCOR"),
    ("fgc88.com", "PAGCOR"),
    ("livebet.ph", "PAGCOR"),
    ("peryaplus.com", "PAGCOR"),
    ("okadaonlinecasino.com", "PAGCOR"),

    # PAGCOR public warning about illegal gaming sites

    ("efesbetcasino514.com", "PAGCOR warning"),
    ("og7777.org", "PAGCOR warning"),
    ("mpo500.com", "PAGCOR warning"),
    ("qq88.com", "PAGCOR warning"),
    ("mpo2121.com", "PAGCOR warning"),
    ("lgolive.com", "PAGCOR warning"),
    ("napolibet.com", "PAGCOR warning"),
    ("kratosbet.com", "PAGCOR warning"),
    ("mpossport.com", "PAGCOR warning"),
    ("efsanebahis434.com", "PAGCOR warning"),
    ("cazeus2.com", "PAGCOR warning"),
]


# =========================================================
# BENIGN CONTROL HOLDOUT
# =========================================================
#
# Independently curated high-recognition domains whose
# primary purpose is unrelated to gambling.
#
# None should be manually added because of model results.
#
# =========================================================

BENIGN_DOMAINS = [

    ("apple.com", "technology"),
    ("adobe.com", "technology"),
    ("oracle.com", "technology"),
    ("ibm.com", "technology"),
    ("intel.com", "technology"),
    ("amd.com", "technology"),
    ("nvidia.com", "technology"),

    ("python.org", "software"),
    ("pypi.org", "software"),
    ("nodejs.org", "software"),
    ("npmjs.com", "software"),
    ("docker.com", "software"),
    ("kubernetes.io", "software"),
    ("apache.org", "software"),
    ("nginx.org", "software"),
    ("ubuntu.com", "software"),
    ("debian.org", "software"),
    ("mozilla.org", "software"),

    ("cloudflare.com", "internet infrastructure"),
    ("digitalocean.com", "cloud"),
    ("heroku.com", "cloud"),

    ("zoom.us", "productivity"),
    ("slack.com", "productivity"),
    ("notion.so", "productivity"),
    ("dropbox.com", "productivity"),
    ("box.com", "productivity"),
    ("canva.com", "design"),
    ("figma.com", "design"),

    ("coursera.org", "education"),
    ("edx.org", "education"),
    ("khanacademy.org", "education"),
    ("mit.edu", "education"),
    ("stanford.edu", "education"),
    ("harvard.edu", "education"),
    ("cam.ac.uk", "education"),
    ("ox.ac.uk", "education"),

    ("who.int", "health"),
    ("cdc.gov", "health"),
    ("nih.gov", "health"),
    ("unicef.org", "international organization"),
    ("un.org", "international organization"),
    ("worldbank.org", "finance institution"),
    ("imf.org", "finance institution"),

    ("nasa.gov", "government/science"),
    ("noaa.gov", "government/science"),

    ("bbc.com", "news"),
    ("reuters.com", "news"),
    ("apnews.com", "news"),
    ("nytimes.com", "news"),
    ("theguardian.com", "news"),

    ("soundcloud.com", "media"),
    ("vimeo.com", "media"),
    ("archive.org", "archive"),

    ("medium.com", "publishing"),
    ("wordpress.org", "publishing"),
    ("wordpress.com", "publishing"),

    ("openstreetmap.org", "mapping"),

    ("etsy.com", "shopping"),
    ("ikea.com", "shopping"),
    ("ebay.com", "shopping"),

    ("linkedin.com", "professional networking"),

    ("booking.com", "travel"),
    ("tripadvisor.com", "travel"),
]


# =========================================================
# NORMALIZE
# =========================================================

def normalize_domain(
    domain
):

    domain = str(
        domain
    ).strip().lower()

    if domain.startswith("www."):
        domain = domain[4:]

    return domain.rstrip(".")


# =========================================================
# DOMAIN FAMILY
# =========================================================

def get_family(
    domain
):

    domain = normalize_domain(
        domain
    )

    extracted = TLD_EXTRACTOR(
        domain
    )

    registered = (
        extracted.top_domain_under_public_suffix
    )

    return (
        registered
        if registered
        else domain
    )


# =========================================================
# LOAD TRAINING FAMILIES
# =========================================================

def load_training_families():

    if not TRAINING_DATASET.exists():

        raise FileNotFoundError(
            f"\nCould not find:\n"
            f"{TRAINING_DATASET}"
        )

    df = pd.read_csv(
        TRAINING_DATASET
    )

    return set(
        df[
            "domain"
        ].apply(
            get_family
        )
    )


# =========================================================
# MAIN
# =========================================================

def main():

    print(
        "\n===================================="
    )

    print(
        " BETGUARD EXTERNAL HOLDOUT BUILDER"
    )

    print(
        "===================================="
    )


    training_families = (
        load_training_families()
    )

    development_families = set(
        get_family(domain)
        for domain in DEVELOPMENT_TESTED
    )


    candidates = []


    for domain, source in GAMBLING_DOMAINS:

        candidates.append(
            {
                "domain":
                    normalize_domain(
                        domain
                    ),

                "label":
                    1,

                "meaning":
                    "gambling",

                "source":
                    source,
            }
        )


    for domain, category in BENIGN_DOMAINS:

        candidates.append(
            {
                "domain":
                    normalize_domain(
                        domain
                    ),

                "label":
                    0,

                "meaning":
                    "non-gambling",

                "source":
                    (
                        "curated benign control - "
                        f"{category}"
                    ),
            }
        )


    candidate_df = pd.DataFrame(
        candidates
    )


    candidate_df[
        "domain_family"
    ] = candidate_df[
        "domain"
    ].apply(
        get_family
    )


    # =====================================================
    # REMOVE DUPLICATES
    # =====================================================

    candidate_df = (
        candidate_df.drop_duplicates(
            subset=[
                "domain"
            ],
            keep="first"
        )
    )


    # =====================================================
    # EXCLUDE TRAINING / DEVELOPMENT LEAKAGE
    # =====================================================

    excluded_rows = []

    accepted_rows = []


    for _, row in candidate_df.iterrows():

        family = row[
            "domain_family"
        ]


        if family in training_families:

            excluded = row.to_dict()

            excluded[
                "exclusion_reason"
            ] = (
                "domain family already "
                "present in training dataset"
            )

            excluded_rows.append(
                excluded
            )

            continue


        if family in development_families:

            excluded = row.to_dict()

            excluded[
                "exclusion_reason"
            ] = (
                "domain family already "
                "used during manual "
                "development testing"
            )

            excluded_rows.append(
                excluded
            )

            continue


        accepted_rows.append(
            row.to_dict()
        )


    holdout = pd.DataFrame(
        accepted_rows
    )

    excluded = pd.DataFrame(
        excluded_rows
    )


    # =====================================================
    # SAFETY CHECK
    # =====================================================

    overlap = (
        set(
            holdout[
                "domain_family"
            ]
        )
        &
        training_families
    )


    if overlap:

        raise RuntimeError(
            "Training-family leakage "
            "detected in external holdout."
        )


    # =====================================================
    # SAVE
    # =====================================================

    OUTPUT_FILE.parent.mkdir(
        parents=True,
        exist_ok=True
    )


    holdout.to_csv(
        OUTPUT_FILE,
        index=False
    )


    EXCLUDED_FILE.parent.mkdir(
        parents=True,
        exist_ok=True
    )


    excluded.to_csv(
        EXCLUDED_FILE,
        index=False
    )


    # =====================================================
    # REPORT
    # =====================================================

    print(
        "\nAccepted external holdout:"
    )

    print(
        len(
            holdout
        )
    )


    print(
        "\nClass distribution:"
    )

    print(
        holdout[
            "label"
        ].value_counts()
        .sort_index()
    )


    print(
        "\nUnique domain families:"
    )

    print(
        holdout[
            "domain_family"
        ].nunique()
    )


    print(
        "\nExcluded because of previous exposure:"
    )

    print(
        len(
            excluded
        )
    )


    print(
        "\nHoldout file:"
    )

    print(
        OUTPUT_FILE
    )


    print(
        "\nExcluded file:"
    )

    print(
        EXCLUDED_FILE
    )


if __name__ == "__main__":
    main()