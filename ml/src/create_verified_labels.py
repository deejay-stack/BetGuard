from pathlib import Path

import pandas as pd


# =========================================================
# BETGUARD
# CREATE INITIAL MANUAL VERIFIED LABEL FILE
# =========================================================


OUTPUT_FILE = Path(
    "data/manual/verified_labels.csv"
)


# =========================================================
# MANUALLY VERIFIED DOMAINS
# =========================================================
#
# LABELS:
#
# 0 = NON-GAMBLING
# 1 = GAMBLING
# blank = UNCERTAIN
#
# =========================================================

verified_domains = [

    {
        "domain": "redcross.org.uk",
        "verified_label": 0,
        "review_status": "verified",
        "verification_method": "official website",
        "notes": "British Red Cross humanitarian charity",
    },

    {
        "domain": "nustargame.ph",
        "verified_label": 1,
        "review_status": "verified",
        "verification_method": "official website",
        "notes": "Online casino and gaming website",
    },

    {
        "domain": "nustar.ph",
        "verified_label": 1,
        "review_status": "verified",
        "verification_method": "official website",
        "notes": "NUSTAR casino and gaming",
    },

    {
        "domain": "ghostmshop.mgame.com",
        "verified_label": 0,
        "review_status": "verified",
        "verification_method": "official website",
        "notes": "Mgame conventional video-game web shop",
    },

    {
        "domain": "ghostss.mgame.com",
        "verified_label": None,
        "review_status": "uncertain",
        "verification_method": "manual research",
        "notes": "Insufficient direct evidence",
    },

    {
        "domain": "mgame.com",
        "verified_label": 0,
        "review_status": "verified",
        "verification_method": "official website",
        "notes": "Conventional online gaming portal",
    },

    {
        "domain": "noc.mgame.com",
        "verified_label": None,
        "review_status": "uncertain",
        "verification_method": "manual research",
        "notes": "Specific subdomain remains unresolved",
    },

    {
        "domain": "red.mgame.com",
        "verified_label": None,
        "review_status": "uncertain",
        "verification_method": "manual research",
        "notes": "Specific subdomain remains unresolved",
    },

    {
        "domain": "endorphina.com",
        "verified_label": 1,
        "review_status": "verified",
        "verification_method": "official website",
        "notes": "B2B online slot and casino game provider",
    },

    {
        "domain": "linqapp.com",
        "verified_label": 0,
        "review_status": "verified",
        "verification_method": "official documentation",
        "notes": "Digital business card and CRM platform",
    },

    {
        "domain": "eeze.com",
        "verified_label": 1,
        "review_status": "verified",
        "verification_method": "official website",
        "notes": "Live casino and slot provider",
    },

    {
        "domain": "z8.com",
        "verified_label": None,
        "review_status": "uncertain",
        "verification_method": "manual research",
        "notes": "Gambling-related evidence exists but current status unresolved",
    },

    {
        "domain": "fruitkings.com",
        "verified_label": 1,
        "review_status": "verified",
        "verification_method": "official website",
        "notes": "Real-money online casino",
    },
]


# =========================================================
# MAIN
# =========================================================

def main():

    print(
        "\n===================================="
    )

    print(
        " BETGUARD VERIFIED LABEL FILE"
    )

    print(
        "===================================="
    )


    df = pd.DataFrame(
        verified_domains
    )


    # Use nullable integer type so labels
    # can contain:
    #
    # 0
    # 1
    # blank

    df["verified_label"] = pd.array(
        df["verified_label"],
        dtype="Int64"
    )


    # Create folder automatically

    OUTPUT_FILE.parent.mkdir(
        parents=True,
        exist_ok=True
    )


    # Save CSV

    df.to_csv(
        OUTPUT_FILE,
        index=False
    )


    print(
        "\nFile created:"
    )

    print(
        OUTPUT_FILE
    )


    print(
        "\nTotal review entries:",
        len(df)
    )


    print(
        "\nVerified labels:"
    )

    print(
        df["verified_label"]
        .value_counts(
            dropna=False
        )
    )


    print(
        "\nVerified non-gambling:"
    )

    print(
        int(
            (
                df["verified_label"] == 0
            ).sum()
        )
    )


    print(
        "\nVerified gambling:"
    )

    print(
        int(
            (
                df["verified_label"] == 1
            ).sum()
        )
    )


    print(
        "\nUncertain:"
    )

    print(
        int(
            df[
                "verified_label"
            ]
            .isna()
            .sum()
        )
    )


# =========================================================
# ENTRY POINT
# =========================================================

if __name__ == "__main__":

    main()