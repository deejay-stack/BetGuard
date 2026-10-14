
"""
BETGUARD - PHILIPPINE BENIGN DATASET EXPANSION V1

Builds a more diverse Philippine non-gambling
CANDIDATE pool for human verification.

Input:
    pagcor_positive_candidates.csv
    ph_benign_candidates.csv
    baseline_train.csv
    baseline_validation.csv
    baseline_test.csv

Outputs:
    ph_benign_expansion_seeds.csv
    benign_expansion_v1/
        ph_benign_expanded_candidates.csv
        ph_benign_diverse_review_queue.csv
        ph_benign_excluded_conflicts.csv
        ph_benign_expansion_summary.json

IMPORTANT:
    Proposed negative labels are NOT verified.
    Candidate homepages are NOT evidence.
    No training or deployment takes place.
"""

import argparse
import csv
import hashlib
import json
import re

from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlsplit

import tldextract


ML_ROOT = Path(__file__).resolve().parents[1]

ROOT = (
    ML_ROOT / "data/expanded/pagcor_ph"
)

POSITIVE = (
    ROOT / "pagcor_positive_candidates.csv"
)

EXISTING_BENIGN = (
    ROOT / "ph_benign_candidates.csv"
)

SEED_FILE = (
    ROOT / "ph_benign_expansion_seeds.csv"
)

DEFAULT_OUTPUT = (
    ROOT / "benign_expansion_v1"
)

HISTORICAL_DIR = (
    ML_ROOT / "data/processed/splits"
)

HISTORICAL_FILES = [
    "baseline_train.csv",
    "baseline_validation.csv",
    "baseline_test.csv",
]

EXTRACTOR = tldextract.TLDExtract(
    suffix_list_urls=()
)

DOMAIN_RE = re.compile(
    r"(?i)^(?:[a-z0-9]"
    r"(?:[a-z0-9-]{0,61}[a-z0-9])?\.)+"
    r"[a-z]{2,63}$"
)


# ------------------------------------------------------
# DIVERSE PHILIPPINE CANDIDATE SEEDS
#
# These are research candidates, not confirmed
# active or independently verified benign sites.
# Their current ownership, purpose, and Philippine
# relevance must be reviewed.
# ------------------------------------------------------

SUGGESTED_SITES = {
    "news_media": [
        "inquirer.net",
        "philstar.com",
        "rappler.com",
        "gmanetwork.com",
        "abs-cbn.com",
        "mb.com.ph",
        "sunstar.com.ph",
        "manilatimes.net",
        "bworldonline.com",
    ],

    "shopping_retail": [
        "lazada.com.ph",
        "shopee.ph",
        "zalora.com.ph",
        "smstore.com",
        "abenson.com",
        "ansons.ph",
        "datablitz.com.ph",
        "powermaccenter.com",
        "nationalbookstore.com",
        "fullybookedonline.com",
        "watsons.com.ph",
        "allhome.com.ph",
    ],

    "food_restaurants": [
        "jollibee.com.ph",
        "chowking.com",
        "manginasal.com",
        "greenwich.com.ph",
        "goldilocks.com.ph",
        "redribbonbakeshop.com.ph",
        "yellowcabpizza.com",
        "shakeys.com.ph",
        "maxschicken.com",
    ],

    "telecommunications": [
        "globe.com.ph",
        "smart.com.ph",
        "dito.ph",
        "pldt.com",
        "convergeict.com",
        "sky.com.ph",
    ],

    "transport_logistics": [
        "cebupacificair.com",
        "philippineairlines.com",
        "2go.com.ph",
        "victoryliner.com",
        "lbc.com.ph",
        "jtexpress.ph",
        "barkota.com",
    ],

    "healthcare": [
        "stlukes.com.ph",
        "themedicalcity.com",
        "makatimed.net.ph",
        "asianhospital.com",
        "hi-precision.com.ph",
        "healthway.com.ph",
        "mercurydrug.com",
    ],

    "finance_fintech": [
        "gcash.com",
        "maya.ph",
        "coins.ph",
        "gotyme.com.ph",
        "unionbankph.com",
        "eastwestbanker.com",
        "rcbc.com",
        "chinabank.ph",
        "pnb.com.ph",
    ],

    "employment": [
        "jobstreet.com.ph",
        "kalibrr.com",
        "onlinejobs.ph",
        "bossjob.ph",
        "mynimo.com",
        "philjobnet.gov.ph",
    ],

    "real_estate": [
        "lamudi.com.ph",
        "property24.com.ph",
        "rentpad.com.ph",
        "dmcihomes.com",
        "ayalaland.com.ph",
        "filinvestland.com",
        "megaworldcorp.com",
    ],

    "entertainment": [
        "clickthecity.com",
        "spot.ph",
        "pep.ph",
        "iwanttfc.com",
    ],

    "gaming_esports_review": [
        "mineski.net",
        "tierone.ph",
        "pinoygamer.ph",
        "gamingph.com",
    ],
}


DATA_COLUMNS = [
    "domain",
    "domain_family",
    "suggested_label",
    "source",
    "category",
    "candidate_reference_url",
    "ph_relevance_status",
    "historical_overlap",
    "verification_status",
    "review_status",
    "verified_label",
    "evidence_reference",
    "reviewed_by",
    "review_notes",
    "training_eligible",
    "review_priority",
]


def now():
    return datetime.now(
        timezone.utc
    ).isoformat()


def normalize_domain(value):
    value = str(value or "").strip().lower()

    if "://" in value:
        value = urlsplit(value).hostname or ""

    value = value.rstrip(".")

    if value.startswith("www."):
        value = value[4:]

    return value


def domain_family(domain):
    result = EXTRACTOR(domain)

    return (
        result.top_domain_under_public_suffix
        or ""
    )


def valid_domain(domain):
    return bool(
        DOMAIN_RE.fullmatch(domain)
        and domain_family(domain)
    )


def read_csv(path):
    if not path.exists():
        raise FileNotFoundError(path)

    with path.open(
        "r",
        encoding="utf-8-sig",
        newline=""
    ) as handle:
        reader = csv.DictReader(handle)
        return list(reader)


def write_csv(path, columns, rows):
    with path.open(
        "x",
        encoding="utf-8-sig",
        newline=""
    ) as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=columns,
            extrasaction="ignore",
        )

        writer.writeheader()
        writer.writerows(rows)


def file_sha256(path):
    return hashlib.sha256(
        path.read_bytes()
    ).hexdigest()


def create_seeds():
    if SEED_FILE.exists():
        print(
            "Using existing expansion seed file."
        )
        return

    rows = []

    for category, domains in (
        SUGGESTED_SITES.items()
    ):
        for domain in domains:
            rows.append({
                "domain": domain,
                "category": category,
                "candidate_reference_url": (
                    f"https://{domain}/"
                ),
                "seed_origin": (
                    "curated_unverified_candidate"
                ),
            })

    write_csv(
        SEED_FILE,
        [
            "domain",
            "category",
            "candidate_reference_url",
            "seed_origin",
        ],
        rows,
    )

    print(
        "Created editable PH expansion seed file."
    )


def load_historical():
    families = set()
    metadata = {}

    for filename in HISTORICAL_FILES:
        path = HISTORICAL_DIR / filename

        if not path.exists():
            raise FileNotFoundError(
                f"Missing historical benchmark: {path}"
            )

        rows = read_csv(path)

        for row in rows:
            family = (
                row.get("domain_family", "")
                .strip()
                .lower()
            )

            if not family:
                raise RuntimeError(
                    f"Missing family in {filename}"
                )

            families.add(family)

        metadata[filename] = {
            "rows": len(rows),
            "sha256": file_sha256(path),
        }

    return families, metadata


def review_priority(category, historical_overlap):
    if historical_overlap:
        return "HIGH_HISTORICAL_OVERLAP"

    if category in (
        "gaming_esports_review",
        "finance_fintech",
        "entertainment",
    ):
        return "HIGH_HARD_NEGATIVE_REVIEW"

    return "STANDARD_REVIEW"


def make_candidate(
    domain,
    category,
    source,
    reference_url,
    historical,
):
    family = domain_family(domain)

    overlaps_history = (
        family in historical
    )

    return {
        "domain": domain,
        "domain_family": family,
        "suggested_label": "0",
        "source": source,
        "category": category,
        "candidate_reference_url": (
            reference_url
        ),
        "ph_relevance_status": (
            "needs_review"
        ),
        "historical_overlap": (
            "YES"
            if overlaps_history
            else "NO"
        ),
        "verification_status": (
            "needs_independent_benign_review"
        ),
        "review_status": "pending",
        "verified_label": "",
        "evidence_reference": "",
        "reviewed_by": "",
        "review_notes": "",
        "training_eligible": "NO",
        "review_priority": review_priority(
            category,
            overlaps_history,
        ),
    }


def main():
    parser = argparse.ArgumentParser()

    parser.add_argument(
        "--output-dir",
        type=Path,
        default=DEFAULT_OUTPUT,
    )

    args = parser.parse_args()

    output_dir = args.output_dir

    if not output_dir.is_absolute():
        output_dir = ML_ROOT / output_dir

    print(
        "\nBETGUARD - PH BENIGN EXPANSION V1"
    )

    print(
        "================================="
    )

    print(
        "Mode: Offline candidate preparation"
    )

    create_seeds()

    existing = read_csv(
        EXISTING_BENIGN
    )

    proposed = read_csv(
        SEED_FILE
    )

    positives = read_csv(
        POSITIVE
    )

    historical, historical_metadata = (
        load_historical()
    )

    # A domain family must never appear in both
    # proposed classes.

    positive_families = {
        row["domain_family"].strip().lower()
        for row in positives
    }

    candidates = []
    excluded = []

    seen_families = set()

    sources = [
        (
            existing,
            "existing_ph_benign_seed",
        ),
        (
            proposed,
            "diverse_ph_candidate_seed",
        ),
    ]

    for records, default_source in sources:

        for entry in records:
            domain = normalize_domain(
                entry.get("domain", "")
            )

            category = (
                entry.get("category", "unknown")
                .strip()
                or "unknown"
            )

            if not valid_domain(domain):
                excluded.append({
                    "domain": domain,
                    "reason": (
                        "invalid_domain"
                    ),
                })
                continue

            family = domain_family(domain)

            if family in positive_families:
                excluded.append({
                    "domain": domain,
                    "reason": (
                        "overlaps_pagcor_positive_family"
                    ),
                })
                continue

            if family in seen_families:
                excluded.append({
                    "domain": domain,
                    "reason": (
                        "duplicate_benign_family"
                    ),
                })
                continue

            seen_families.add(family)

            reference = (
                entry.get(
                    "candidate_reference_url",
                    ""
                )
                or f"https://{domain}/"
            )

            candidates.append(
                make_candidate(
                    domain=domain,
                    category=category,
                    source=default_source,
                    reference_url=reference,
                    historical=historical,
                )
            )

    # All entries are unverified.
    for row in candidates:
        assert row["verified_label"] == ""
        assert row["training_eligible"] == "NO"

    priority_order = {
        "HIGH_HISTORICAL_OVERLAP": 0,
        "HIGH_HARD_NEGATIVE_REVIEW": 1,
        "STANDARD_REVIEW": 2,
    }

    review_queue = sorted(
        candidates,
        key=lambda row: (
            priority_order[
                row["review_priority"]
            ],
            row["category"],
            row["domain"],
        ),
    )

    outputs = {
        "candidates": (
            output_dir
            / "ph_benign_expanded_candidates.csv"
        ),
        "review": (
            output_dir
            / "ph_benign_diverse_review_queue.csv"
        ),
        "excluded": (
            output_dir
            / "ph_benign_excluded_conflicts.csv"
        ),
        "summary": (
            output_dir
            / "ph_benign_expansion_summary.json"
        ),
    }

    # Never silently overwrite human review files.

    preexisting = [
        path
        for path in outputs.values()
        if path.exists()
    ]

    if preexisting:
        raise RuntimeError(
            "Output files already exist. "
            "Use --output-dir with a new folder."
        )

    output_dir.mkdir(
        parents=True,
        exist_ok=True,
    )

    write_csv(
        outputs["candidates"],
        DATA_COLUMNS,
        candidates,
    )

    write_csv(
        outputs["review"],
        DATA_COLUMNS,
        review_queue,
    )

    write_csv(
        outputs["excluded"],
        ["domain", "reason"],
        excluded,
    )

    categories = Counter(
        row["category"]
        for row in candidates
    )

    priorities = Counter(
        row["review_priority"]
        for row in candidates
    )

    summary = {
        "generated_at_utc": now(),
        "project": "BetGuard",
        "version": (
            "ph_benign_expansion_v1"
        ),
        "jurisdiction": "Philippines",
        "dataset_status": (
            "UNVERIFIED_CANDIDATES"
        ),
        "counts": {
            "existing_benign_inputs": len(
                existing
            ),
            "new_seed_inputs": len(
                proposed
            ),
            "expanded_candidates": len(
                candidates
            ),
            "unique_benign_families": len({
                row["domain_family"]
                for row in candidates
            }),
            "excluded_records": len(
                excluded
            ),
            "historical_overlap": sum(
                row["historical_overlap"] == "YES"
                for row in candidates
            ),
            "human_verified_labels": 0,
        },
        "category_counts": dict(
            sorted(categories.items())
        ),
        "review_priorities": dict(
            sorted(priorities.items())
        ),
        "historical_sources": (
            historical_metadata
        ),
        "source_checksums": {
            "pagcor_positive_candidates": (
                file_sha256(POSITIVE)
            ),
            "existing_benign_candidates": (
                file_sha256(EXISTING_BENIGN)
            ),
            "expansion_seeds": (
                file_sha256(SEED_FILE)
            ),
        },
        "outputs": {
            name: str(path)
            for name, path in outputs.items()
        },
        "limitations": [
            "Domains are proposed research "
            "candidates, not verified benign "
            "examples.",

            "Philippine relevance and current "
            "ownership have not been verified.",

            "A candidate homepage URL does "
            "not count as independent evidence.",

            "Gaming and esports websites "
            "require special review.",

            "Historical overlaps cannot be "
            "used in a virgin test set.",

            "Source and brand-family leakage "
            "must be addressed before evaluation.",

            "No model or production data "
            "has been changed.",
        ],
    }

    with outputs["summary"].open(
        "x",
        encoding="utf-8",
    ) as handle:
        json.dump(
            summary,
            handle,
            indent=2,
            ensure_ascii=False,
        )

    print(
        "\nPH BENIGN EXPANSION COMPLETE"
    )

    print(
        "================================="
    )

    for key, value in (
        summary["counts"].items()
    ):
        print(f"{key}: {value}")

    print(
        "\nCategories:"
    )

    for category, count in (
        sorted(categories.items())
    ):
        print(
            f"  {category}: {count}"
        )

    print(
        "\nSaved files:"
    )

    for path in outputs.values():
        print(path)

    print(
        "\nHuman verified labels: 0"
    )

    print(
        "ML models modified: 0"
    )


if __name__ == "__main__":
    main()
