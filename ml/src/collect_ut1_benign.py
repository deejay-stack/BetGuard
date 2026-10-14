
import csv
import hashlib
import json
import random
import re
import urllib.request

from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

import tldextract


# =========================================================
# BETGUARD - UT1 BENIGN DATASET RECOVERY
# =========================================================
#
# Downloads UT1 categories from the publicly available
# GitHub mirror, using normal HTTPS certificate validation.
#
# Reuses previously collected gambling candidates.
#
# Outputs are REVIEW CANDIDATES, not verified labels.
#
# Does not alter models, training splits or deployment.
# =========================================================


ROOT = Path("data/expanded")
SPLITS = Path("data/processed/splits")

GAMBLING_INPUT = ROOT / "candidate_gambling.csv"

GAMBLING_OUTPUT = (
    ROOT / "candidate_gambling_v2.csv"
)

BENIGN_OUTPUT = (
    ROOT / "candidate_benign_v2.csv"
)

REVIEW_OUTPUT = (
    ROOT / "balanced_review_queue_v2.csv"
)

MANIFEST_OUTPUT = (
    ROOT / "ut1_mirror_manifest.json"
)

MIRROR_BASE = (
    "https://raw.githubusercontent.com/"
    "olbat/ut1-blacklists/master/"
    "blacklists"
)

CATEGORIES = [
    "bank",
    "press",
    "jobsearch",
    "cooking",
    "translation",
    "webmail",
    "social_networks",
    "sports",
    "games",
]

REVIEW_PER_CLASS = 5000
RANDOM_SEED = 42

EXTRACT = tldextract.TLDExtract(
    suffix_list_urls=()
)

DOMAIN_RE = re.compile(
    r"^(?=.{4,253}$)"
    r"(?:[a-z0-9]"
    r"(?:[a-z0-9-]{0,61}[a-z0-9])?\.)+"
    r"[a-z0-9-]{2,63}$"
)

COLUMNS = [
    "domain",
    "domain_family",
    "suggested_label",
    "source",
    "category",
    "verification_status",
]


# =========================================================
# DOMAIN NORMALIZATION
# =========================================================

def normalize_domain(value):

    if value is None:
        return None

    domain = str(value).strip().lower()

    if not domain:
        return None

    if domain.startswith(("#", "!", ";")):
        return None

    if len(domain.split()) != 1:
        return None

    if domain.startswith("*."):
        domain = domain[2:]

    if domain.startswith("www."):
        domain = domain[4:]

    domain = domain.rstrip(".")

    if not DOMAIN_RE.fullmatch(domain):
        return None

    parsed = EXTRACT(domain)

    if not parsed.domain or not parsed.suffix:
        return None

    return domain


def get_family(domain):

    return EXTRACT(
        domain
    ).top_domain_under_public_suffix


# =========================================================
# HISTORICAL BENCHMARK FAMILIES
# =========================================================

def load_historical_families():

    filenames = [
        "baseline_train.csv",
        "baseline_validation.csv",
        "baseline_test.csv",
    ]

    families = set()

    for filename in filenames:

        path = SPLITS / filename

        if not path.exists():
            raise FileNotFoundError(path)

        with path.open(
            "r",
            encoding="utf-8-sig",
            newline=""
        ) as handle:

            reader = csv.DictReader(handle)

            for row in reader:

                domain = normalize_domain(
                    row.get("domain")
                )

                if not domain:
                    raise ValueError(
                        f"Invalid historical domain "
                        f"in {path}"
                    )

                families.add(
                    get_family(domain)
                )

    return families


# =========================================================
# LOAD EXISTING GAMBLING CANDIDATES
# =========================================================

def load_gambling_candidates(historical):

    if not GAMBLING_INPUT.exists():
        raise FileNotFoundError(
            GAMBLING_INPUT
        )

    candidates = {}

    with GAMBLING_INPUT.open(
        "r",
        encoding="utf-8-sig",
        newline=""
    ) as handle:

        reader = csv.DictReader(handle)

        for row in reader:

            domain = normalize_domain(
                row.get("domain")
            )

            if not domain:
                continue

            family = (
                row.get("domain_family")
                or get_family(domain)
            )

            if family in historical:
                continue

            candidates[domain] = {
                "domain": domain,
                "domain_family": family,
                "suggested_label": 1,
                "source": row.get(
                    "source", "previous_gambling_source"
                ),
                "category": "gambling",
                "verification_status":
                    "needs_manual_review",
            }

    return candidates


# =========================================================
# DOWNLOAD UT1 FROM GITHUB MIRROR
# =========================================================

def download_category(category):

    url = (
        f"{MIRROR_BASE}/{category}/domains"
    )

    request = urllib.request.Request(
        url,
        headers={
            "User-Agent":
                "BetGuardAcademicDataset/1.0"
        }
    )

    with urllib.request.urlopen(
        request,
        timeout=120
    ) as response:

        payload = response.read()

    digest = hashlib.sha256(
        payload
    ).hexdigest()

    content = payload.decode(
        "utf-8-sig",
        errors="replace"
    )

    domains = set()

    for line in content.splitlines():

        domain = normalize_domain(
            line
        )

        if domain:
            domains.add(domain)

    if not domains:
        raise RuntimeError(
            f"No valid domains in {category}"
        )

    return domains, url, digest


# =========================================================
# COLLECT BENIGN CANDIDATES
# =========================================================

def collect_benign(historical):

    candidates = {}

    source_manifest = []

    for category in CATEGORIES:

        print(
            f"\nDownloading UT1: {category}"
        )

        # Fail rather than silently create a partial
        # supposedly balanced dataset.

        domains, url, digest = (
            download_category(category)
        )

        print(
            f"Parsed domains: {len(domains)}"
        )

        source_manifest.append({
            "category": category,
            "url": url,
            "sha256": digest,
            "parsed_domains": len(domains),
        })

        for domain in domains:

            family = get_family(domain)

            if family in historical:
                continue

            if domain not in candidates:

                candidates[domain] = {
                    "domain": domain,
                    "domain_family": family,
                    "suggested_label": 0,
                    "sources": set(),
                    "categories": set(),
                }

            candidates[domain][
                "sources"
            ].add(
                f"ut1_mirror_{category}"
            )

            candidates[domain][
                "categories"
            ].add(category)

    result = []

    for item in candidates.values():

        result.append({
            "domain":
                item["domain"],

            "domain_family":
                item["domain_family"],

            "suggested_label":
                0,

            "source":
                ";".join(
                    sorted(item["sources"])
                ),

            "category":
                ";".join(
                    sorted(item["categories"])
                ),

            "verification_status":
                "needs_manual_review",
        })

    return result, source_manifest


# =========================================================
# SAVE CSV
# =========================================================

def save_csv(path, rows):

    path.parent.mkdir(
        parents=True,
        exist_ok=True
    )

    with path.open(
        "w",
        encoding="utf-8",
        newline=""
    ) as handle:

        writer = csv.DictWriter(
            handle,
            fieldnames=COLUMNS
        )

        writer.writeheader()

        writer.writerows(
            sorted(
                rows,
                key=lambda x: x["domain"]
            )
        )


# =========================================================
# GAMBLING REVIEW SAMPLE
# =========================================================

def sample_unique_families(
    rows,
    limit,
    seed
):

    rng = random.Random(seed)

    shuffled = list(rows)
    rng.shuffle(shuffled)

    result = []
    seen = set()

    for row in shuffled:

        family = row["domain_family"]

        if family in seen:
            continue

        seen.add(family)
        result.append(row)

        if len(result) >= limit:
            break

    return result


# =========================================================
# CATEGORY-DIVERSIFIED BENIGN SAMPLE
# =========================================================

def diversified_benign_sample(
    rows,
    limit
):

    buckets = defaultdict(list)

    for row in rows:

        first_category = (
            row["category"].split(";")[0]
        )

        buckets[first_category].append(row)

    rng = random.Random(RANDOM_SEED + 1)

    for values in buckets.values():
        rng.shuffle(values)

    categories = sorted(buckets)

    positions = {
        category: 0
        for category in categories
    }

    selected = []
    seen_families = set()

    while len(selected) < limit:

        progress = False

        for category in categories:

            values = buckets[category]

            while (
                positions[category] < len(values)
            ):

                row = values[
                    positions[category]
                ]

                positions[category] += 1

                family = row[
                    "domain_family"
                ]

                if family in seen_families:
                    continue

                seen_families.add(family)

                selected.append(row)

                progress = True

                break

            if len(selected) >= limit:
                break

        if not progress:
            break

    return selected


# =========================================================
# MAIN
# =========================================================

def main():

    print(
        "\nBETGUARD - UT1 BENIGN RECOVERY"
    )

    print(
        "================================"
    )

    historical = load_historical_families()

    print(
        "\nHistorical benchmark families:",
        len(historical)
    )

    gambling_dict = (
        load_gambling_candidates(historical)
    )

    gambling = list(
        gambling_dict.values()
    )

    print(
        "Existing gambling candidates:",
        len(gambling)
    )

    benign, sources = collect_benign(
        historical
    )

    print(
        "\nRaw benign candidates:",
        len(benign)
    )

    # A domain family found in both proposed classes
    # is ambiguous. Remove that entire family from
    # BOTH usable candidate pools.

    gambling_families = {
        row["domain_family"]
        for row in gambling
    }

    benign_families = {
        row["domain_family"]
        for row in benign
    }

    conflicting_families = (
        gambling_families
        &
        benign_families
    )

    gambling_clean = [
        row
        for row in gambling
        if row["domain_family"]
        not in conflicting_families
    ]

    benign_clean = [
        row
        for row in benign
        if row["domain_family"]
        not in conflicting_families
    ]

    # These are candidate data, not verified labels.

    gambling_sample = sample_unique_families(
        gambling_clean,
        REVIEW_PER_CLASS,
        RANDOM_SEED
    )

    benign_sample = diversified_benign_sample(
        benign_clean,
        REVIEW_PER_CLASS
    )

    review_queue = (
        gambling_sample
        +
        benign_sample
    )

    random.Random(
        RANDOM_SEED
    ).shuffle(
        review_queue
    )

    # All downloads and consistency checks have
    # succeeded before writing new output files.

    save_csv(
        GAMBLING_OUTPUT,
        gambling_clean
    )

    save_csv(
        BENIGN_OUTPUT,
        benign_clean
    )

    save_csv(
        REVIEW_OUTPUT,
        review_queue
    )

    manifest = {
        "created_at_utc":
            datetime.now(
                timezone.utc
            ).isoformat(),

        "source":
            "UT1 GitHub mirror",

        "historical_benchmark_families":
            len(historical),

        "conflicting_domain_families":
            len(conflicting_families),

        "gambling_candidates":
            len(gambling_clean),

        "benign_candidates":
            len(benign_clean),

        "gambling_review_rows":
            len(gambling_sample),

        "benign_review_rows":
            len(benign_sample),

        "sources":
            sources,

        "label_status":
            "unverified_candidates",
    }

    MANIFEST_OUTPUT.write_text(
        json.dumps(
            manifest,
            indent=2
        ),
        encoding="utf-8"
    )

    print(
        "\n================================"
    )

    print(
        "RECOVERY COMPLETE"
    )

    print(
        "================================"
    )

    print(
        "Conflicting families:",
        len(conflicting_families)
    )

    print(
        "Gambling candidates:",
        len(gambling_clean)
    )

    print(
        "Benign candidates:",
        len(benign_clean)
    )

    print(
        "Gambling review samples:",
        len(gambling_sample)
    )

    print(
        "Benign review samples:",
        len(benign_sample)
    )

    print(
        "\nSaved files:"
    )

    for path in [
        GAMBLING_OUTPUT,
        BENIGN_OUTPUT,
        REVIEW_OUTPUT,
        MANIFEST_OUTPUT,
    ]:
        print(path)

    print(
        "\nWARNING:"
    )

    print(
        "All labels still require verification."
    )

    print(
        "Do not use these files as a final "
        "training or independent test set yet."
    )


if __name__ == "__main__":
    main()
