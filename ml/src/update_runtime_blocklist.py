import json
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd
import requests


# =========================================================
# BETGUARD
# RUNTIME GAMBLING BLOCKLIST BUILDER
# =========================================================

OUTPUT_FILE = Path(
    "data/runtime/gambling_blocklist.csv"
)

METADATA_FILE = Path(
    "data/runtime/gambling_blocklist_metadata.json"
)


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
# NORMALIZATION
# =========================================================

def normalize_domain(value):

    if value is None:
        return ""

    value = str(value).strip().lower()

    if not value:
        return ""

    if value.startswith("https://"):
        value = value[len("https://"):]

    elif value.startswith("http://"):
        value = value[len("http://"):]

    value = value.split("/")[0]
    value = value.split("?")[0]
    value = value.split("#")[0]

    if value.startswith("www."):
        value = value[4:]

    value = value.rstrip(".")

    return value


# =========================================================
# PARSER
# =========================================================

def parse_blocklist(text):

    domains = set()

    for line in text.splitlines():

        line = line.strip()

        if not line:
            continue

        if line.startswith("#"):
            continue

        parts = line.split()

        if len(parts) >= 2:
            candidate = parts[-1]
        else:
            candidate = parts[0]

        candidate = candidate.replace(
            "*.",
            ""
        )

        domain = normalize_domain(
            candidate
        )

        if not domain:
            continue

        if "." not in domain:
            continue

        domains.add(
            domain
        )

    return domains


# =========================================================
# DOWNLOAD
# =========================================================

def download_source(
    source_name,
    url
):

    print(
        f"Downloading {source_name}..."
    )

    response = requests.get(
        url,
        timeout=90,
        headers={
            "User-Agent":
                "BetGuard-ML-Research/1.0"
        }
    )

    response.raise_for_status()

    domains = parse_blocklist(
        response.text
    )

    print(
        f"  Loaded {len(domains):,} domains"
    )

    return domains


# =========================================================
# MAIN
# =========================================================

def main():

    print(
        "\n===================================="
    )

    print(
        " BETGUARD RUNTIME BLOCKLIST UPDATE"
    )

    print(
        "===================================="
    )

    source_map = defaultdict(
        set
    )

    source_counts = {}

    successful_sources = []

    failed_sources = []


    for source_name, url in (
        BLOCKLIST_SOURCES.items()
    ):

        try:

            domains = download_source(
                source_name,
                url
            )

        except requests.RequestException as error:

            print(
                f"\nWARNING: {source_name} failed"
            )

            print(
                error
            )

            failed_sources.append(
                source_name
            )

            continue


        source_counts[
            source_name
        ] = len(
            domains
        )

        successful_sources.append(
            source_name
        )


        for domain in domains:

            source_map[
                domain
            ].add(
                source_name
            )


    if not successful_sources:

        raise RuntimeError(
            "No gambling blocklist source "
            "could be downloaded."
        )


    # =====================================================
    # CREATE DATAFRAME
    # =====================================================

    rows = []

    for domain in sorted(
        source_map
    ):

        sources = sorted(
            source_map[
                domain
            ]
        )

        rows.append(
            {
                "domain":
                    domain,

                "sources":
                    " | ".join(
                        sources
                    ),

                "source_count":
                    len(
                        sources
                    ),
            }
        )


    df = pd.DataFrame(
        rows
    )


    # =====================================================
    # SAVE
    # =====================================================

    OUTPUT_FILE.parent.mkdir(
        parents=True,
        exist_ok=True
    )

    df.to_csv(
        OUTPUT_FILE,
        index=False
    )


    metadata = {
        "updated_at_utc":
            datetime.now(
                timezone.utc
            ).isoformat(),

        "total_unique_domains":
            int(
                len(df)
            ),

        "successful_sources":
            successful_sources,

        "failed_sources":
            failed_sources,

        "source_counts":
            source_counts,
    }


    with open(
        METADATA_FILE,
        "w",
        encoding="utf-8"
    ) as file:

        json.dump(
            metadata,
            file,
            indent=4
        )


    # =====================================================
    # RESULT
    # =====================================================

    print(
        "\n===================================="
    )

    print(
        " UPDATE COMPLETED"
    )

    print(
        "===================================="
    )

    print(
        "\nUnique gambling domains:"
    )

    print(
        f"{len(df):,}"
    )

    print(
        "\nRuntime blocklist:"
    )

    print(
        OUTPUT_FILE
    )

    print(
        "\nMetadata:"
    )

    print(
        METADATA_FILE
    )


if __name__ == "__main__":
    main()