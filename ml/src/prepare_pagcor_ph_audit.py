
"""
BETGUARD - PAGCOR PH DATASET AUDIT PREPARATION

Creates:
1. Complete candidate inventory with review flags
2. Random 100-family PAGCOR audit sample
3. Targeted priority review queue
4. Philippine benign review queue
5. Dataset quality report

All labels remain UNVERIFIED.

No old datasets or ML models are changed.
"""

import csv
import json
import random
import re

from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path


ML_ROOT = Path(__file__).resolve().parents[1]

ROOT = ML_ROOT / "data/expanded/pagcor_ph"

AUDIT_DIR = ROOT / "audit_v1"

POSITIVE = ROOT / "pagcor_positive_candidates.csv"

BENIGN = ROOT / "ph_benign_candidates.csv"

OLD_SPLITS = ML_ROOT / "data/processed/splits"

SEED = 42

RANDOM_AUDIT_FAMILIES = 100


OFFICIAL_URLS = {
    "pagcor_gsa": (
        "https://www.pagcor.ph/regulatory/pdf/"
        "App%20Kits/"
        "List-of-PAGCOR-Accredited-Gaming-"
        "System-Administrators-and-Registered-"
        "Brands-and-Domain-Names-URLs.pdf"
    ),
    "pagcor_licensed_casinos": (
        "https://www.pagcor.ph/regulatory/pdf/"
        "App%20Kits/"
        "List-of-Registered-Brands-and-"
        "Domain-Names-URLs-of-Licensed-Casinos.pdf"
    ),
}


# Names suggesting secondary or promotional purposes.
# These are REVIEW FLAGS, not classifications.

SECONDARY_PATTERN = re.compile(
    r"promo|bonus|rewards?|deals?|"
    r"offers?|freebie|events?|"
    r"android[0-9]*|ios[0-9]*|"
    r"download|support|help|chat|"
    r"links?",
    re.IGNORECASE,
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

        fields = list(reader.fieldnames or [])
        rows = list(reader)

    required = {
        "domain",
        "domain_family",
        "suggested_label",
        "source",
        "source_pages",
        "review_status",
        "verified_label",
    }

    if not required.issubset(fields):
        raise RuntimeError(
            f"Missing expected columns: {path}"
        )

    return rows, fields


def save_csv(path, rows, fields):
    path.parent.mkdir(
        parents=True,
        exist_ok=True
    )

    with path.open(
        "w",
        encoding="utf-8-sig",
        newline=""
    ) as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=fields,
            extrasaction="ignore"
        )

        writer.writeheader()
        writer.writerows(rows)


def host_name(row):
    return row["domain"].strip().lower().rstrip(".")


def family_name(row):
    return (
        row["domain_family"]
        .strip()
        .lower()
        .rstrip(".")
    )


def canonical_www(host):
    if host.startswith("www."):
        return host[4:]

    return host


def old_benchmark_families():
    filenames = [
        "baseline_train.csv",
        "baseline_validation.csv",
        "baseline_test.csv",
    ]

    available = []
    families = set()

    for filename in filenames:
        path = OLD_SPLITS / filename

        if not path.exists():
            continue

        available.append(filename)

        with path.open(
            "r",
            encoding="utf-8-sig",
            newline=""
        ) as handle:
            reader = csv.DictReader(handle)

            if (
                "domain_family"
                not in (reader.fieldnames or [])
            ):
                raise RuntimeError(
                    "Missing domain_family in "
                    f"{filename}"
                )

            for row in reader:
                family = (
                    row.get("domain_family", "")
                    .strip()
                    .lower()
                )

                if family:
                    families.add(family)

    return families, available


def source_links(source):
    result = []

    for name in source.split(";"):
        name = name.strip()

        if name in OFFICIAL_URLS:
            result.append(
                OFFICIAL_URLS[name]
            )

    return ";".join(result)


def validate_inputs(positive, benign):
    for row in positive:
        if row["suggested_label"] != "1":
            raise RuntimeError(
                "Invalid positive candidate label."
            )

    for row in benign:
        if row["suggested_label"] != "0":
            raise RuntimeError(
                "Invalid benign candidate label."
            )

    all_rows = positive + benign

    hosts = [
        host_name(row)
        for row in all_rows
    ]

    if len(hosts) != len(set(hosts)):
        raise RuntimeError(
            "Duplicate hostname detected."
        )

    if any(
        not family_name(row)
        for row in all_rows
    ):
        raise RuntimeError(
            "Empty domain family detected."
        )

    positive_families = {
        family_name(row)
        for row in positive
    }

    benign_families = {
        family_name(row)
        for row in benign
    }

    if positive_families & benign_families:
        raise RuntimeError(
            "Cross-class family overlap."
        )

    for row in all_rows:
        if row["verified_label"].strip():
            raise RuntimeError(
                "Unexpected existing verified label. "
                "This script expects unreviewed inputs."
            )


def enrich_rows(
    positive,
    benign,
    historical_families
):
    all_rows = positive + benign

    positive_hosts = {
        host_name(row)
        for row in positive
    }

    family_counts = Counter(
        family_name(row)
        for row in positive
    )

    enriched = []

    for item in all_rows:
        row = dict(item)

        host = host_name(row)
        family = family_name(row)

        is_positive = (
            row["suggested_label"] == "1"
        )

        flags = []

        if is_positive:

            if SECONDARY_PATTERN.search(host):
                flags.append(
                    "possible_promotion_or_support"
                )

            if (
                host.startswith("www.")
                and canonical_www(host)
                in positive_hosts
            ):
                flags.append(
                    "www_alias_also_listed"
                )

            if host.count(".") >= 4:
                flags.append(
                    "deep_hostname_review"
                )

            if family_counts[family] > 1:
                flags.append(
                    "multiple_hosts_in_family"
                )

        if family in historical_families:
            flags.append(
                "historical_benchmark_family"
            )

        high_risk = any(
            name in flags
            for name in [
                "possible_promotion_or_support",
                "deep_hostname_review",
                "historical_benchmark_family",
            ]
        )

        row["audit_flags"] = ";".join(flags)

        if high_risk:
            row["audit_priority"] = "HIGH"

        elif flags:
            row["audit_priority"] = "MEDIUM"

        else:
            row["audit_priority"] = "NORMAL"

        row["canonical_www_host"] = (
            canonical_www(host)
        )

        row["family_host_count"] = (
            family_counts[family]
            if is_positive
            else 1
        )

        row["official_source_urls"] = (
            source_links(
                row["source"]
            )
        )

        row["review_scope"] = (
            "OPTION_A_DIRECT_REAL_MONEY_ONLINE"
        )

        # Original review columns remain untouched.
        enriched.append(row)

    return enriched


def choose_representative(rows):
    """
    Prefer ordinary root-like hostnames when selecting
    one representative per domain family.

    This does NOT prove the representative is an
    actual wagering platform.
    """

    def rank(row):
        host = host_name(row)
        family = family_name(row)

        return (
            "possible_promotion_or_support"
            in row["audit_flags"],

            host != family,

            host.startswith("www."),

            host.count("."),

            len(host),

            host,
        )

    return min(rows, key=rank)


def main():
    print(
        "\nBETGUARD - PAGCOR PH AUDIT PREPARATION"
    )

    print(
        "======================================"
    )

    positive, pos_fields = read_csv(
        POSITIVE
    )

    benign, benign_fields = read_csv(
        BENIGN
    )

    validate_inputs(
        positive,
        benign
    )

    historical, available = (
        old_benchmark_families()
    )

    print(
        "PAGCOR candidates:",
        len(positive)
    )

    print(
        "Benign candidates:",
        len(benign)
    )

    print(
        "Historical benchmark files found:",
        len(available),
        "/ 3"
    )

    enriched = enrich_rows(
        positive,
        benign,
        historical
    )

    extra_fields = [
        "audit_flags",
        "audit_priority",
        "canonical_www_host",
        "family_host_count",
        "official_source_urls",
        "review_scope",
    ]

    fields = pos_fields + [
        name
        for name in extra_fields
        if name not in pos_fields
    ]

    enriched_positive = [
        row
        for row in enriched
        if row["suggested_label"] == "1"
    ]

    enriched_benign = [
        row
        for row in enriched
        if row["suggested_label"] == "0"
    ]

    # ----------------------------------------------
    # GROUP BY REGISTRABLE DOMAIN FAMILY
    # ----------------------------------------------

    family_groups = defaultdict(list)

    for row in enriched_positive:
        family_groups[
            family_name(row)
        ].append(row)

    representatives = {
        family: choose_representative(rows)
        for family, rows in family_groups.items()
    }

    # ----------------------------------------------
    # RANDOM FAMILY AUDIT
    #
    # This is a reproducible audit sample.
    # Do not use it for model/threshold tuning.
    # ----------------------------------------------

    rng = random.Random(SEED)

    families = sorted(
        representatives
    )

    sample_count = min(
        RANDOM_AUDIT_FAMILIES,
        len(families)
    )

    selected = rng.sample(
        families,
        sample_count
    )

    random_audit = [
        representatives[family]
        for family in selected
    ]

    # ----------------------------------------------
    # TARGETED PRIORITY REVIEW
    #
    # Keep separate from the random sample
    # so its error rate is not mistaken for an
    # unbiased sample estimate.
    # ----------------------------------------------

    targeted = [
        row
        for row in enriched_positive
        if row["audit_priority"] == "HIGH"
    ]

    # ----------------------------------------------
    # OUTPUTS
    # ----------------------------------------------

    AUDIT_DIR.mkdir(
        parents=True,
        exist_ok=True
    )

    inventory_path = (
        AUDIT_DIR / "ph_candidate_inventory.csv"
    )

    random_path = (
        AUDIT_DIR
        / "ph_random_100_family_audit.csv"
    )

    targeted_path = (
        AUDIT_DIR
        / "ph_targeted_priority_review.csv"
    )

    benign_path = (
        AUDIT_DIR
        / "ph_benign_26_review.csv"
    )

    save_csv(
        inventory_path,
        enriched,
        fields
    )

    save_csv(
        random_path,
        random_audit,
        fields
    )

    save_csv(
        targeted_path,
        targeted,
        fields
    )

    save_csv(
        benign_path,
        enriched_benign,
        fields
    )

    # ----------------------------------------------
    # QUALITY REPORT
    # ----------------------------------------------

    flag_counts = Counter()

    for row in enriched_positive:
        for flag in row["audit_flags"].split(";"):
            if flag:
                flag_counts[flag] += 1

    report = {
        "generated_at_utc": (
            datetime.now(
                timezone.utc
            ).isoformat()
        ),

        "project": "BetGuard",

        "jurisdiction": "Philippines",

        "source": "PAGCOR official PDFs",

        "classification": (
            "Option A: direct real-money "
            "online gambling only"
        ),

        "audit_seed": SEED,

        "counts": {
            "positive_hosts": len(positive),

            "positive_families": len(
                family_groups
            ),

            "benign_hosts": len(benign),

            "random_audit_families": len(
                random_audit
            ),

            "targeted_review_hosts": len(
                targeted
            ),

            "historical_family_overlap": len({
                family
                for family in family_groups
                if family in historical
            }),
        },

        "historical_benchmark_files_checked":
            available,

        "historical_check_complete": (
            len(available) == 3
        ),

        "review_flag_counts": dict(
            flag_counts
        ),

        "outputs": [
            str(inventory_path),
            str(random_path),
            str(targeted_path),
            str(benign_path),
        ],

        "warnings": [
            "Candidate labels are not verified.",

            "Audit flags are not classification decisions.",

            "Random audit samples domain families; "
            "it does not verify all hosts per family.",

            "Targeted review cannot be used as "
            "an unbiased label-error estimate.",

            "PDF table-entry membership and actual "
            "direct wagering remain to be confirmed.",

            "Existing benchmark overlap must be "
            "accounted for in any new evaluation.",

            "No production ML model changed.",
        ],
    }

    report_path = (
        AUDIT_DIR / "ph_quality_report.json"
    )

    report_path.write_text(
        json.dumps(
            report,
            indent=2,
            ensure_ascii=False
        ),
        encoding="utf-8"
    )

    print(
        "\n======================================"
    )

    print(
        "PHILIPPINE AUDIT PREPARATION COMPLETE"
    )

    print(
        "======================================"
    )

    for name, value in (
        report["counts"].items()
    ):
        print(
            f"{name}: {value}"
        )

    print(
        "\nReview flag counts:"
    )

    for name, value in (
        flag_counts.most_common()
    ):
        print(
            f"  {name}: {value}"
        )

    print(
        "\nSaved files:"
    )

    for path in report["outputs"]:
        print(path)

    print(report_path)

    print(
        "\nVerified labels created: 0"
    )

    print(
        "Deployed models modified: 0"
    )


if __name__ == "__main__":
    main()
