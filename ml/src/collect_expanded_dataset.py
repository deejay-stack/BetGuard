
import csv
import hashlib
import io
import ipaddress
import json
import random
import re
import tarfile
import urllib.request
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlsplit

import pandas as pd
import tldextract


# ==========================================================
# BETGUARD - EXPANDED DATASET CANDIDATE COLLECTION
# ==========================================================
#
# This script does NOT assign verified labels.
#
# Output labels are SOURCE-SUGGESTED labels and must be
# reviewed before inclusion in an ML training dataset.
#
# 0 = suggested non-gambling
# 1 = suggested gambling
#
# Does not modify baseline splits, models or deployment.
# ==========================================================

ROOT = Path("data/expanded")
ROOT.mkdir(parents=True, exist_ok=True)

SPLIT_DIR = Path("data/processed/splits")

EXTRACT = tldextract.TLDExtract(
    suffix_list_urls=()
)

GAMBLING_SOURCES = {
    "hagezi_medium": (
        "https://cdn.jsdelivr.net/gh/"
        "hagezi/dns-blocklists@latest/"
        "wildcard/gambling.medium-onlydomains.txt"
    ),
    "shadowwhisperer": (
        "https://raw.githubusercontent.com/"
        "ShadowWhisperer/BlockLists/master/"
        "Lists/Gambling"
    ),
    "anti_gambling_indonesia": (
        "https://raw.githubusercontent.com/"
        "arfshl/anti-gambling-domains/main/domains.txt"
    ),
    "bet_blocker": (
        "https://raw.githubusercontent.com/"
        "bet-blocker/bet-blocker/main/blocklist.txt"
    ),
}

UT1_BASE = (
    "https://dsi.ut-capitole.fr/"
    "blacklists/download/"
)

BENIGN_CATEGORIES = [
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

# One-family-per-row preview for controlled manual review.
REVIEW_TARGET_PER_CLASS = 5000

RANDOM_SEED = 42

DOMAIN_PATTERN = re.compile(
    r"^(?=.{4,253}$)"
    r"(?:[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\.)+"
    r"[a-z0-9-]{2,63}$"
)


def download_bytes(url):
    request = urllib.request.Request(
        url,
        headers={
            "User-Agent": "BetGuardAcademicDataset/1.0"
        },
    )

    with urllib.request.urlopen(
        request,
        timeout=120
    ) as response:
        return response.read()


def normalize_domain(value):
    value = str(value).strip().lower()

    if not value:
        return None

    if value.startswith(("#", "!", ";", "[")):
        return None

    # Handle standard hosts-file entries.
    parts = value.split()

    if len(parts) >= 2 and parts[0] in (
        "0.0.0.0",
        "127.0.0.1",
        "::1",
    ):
        value = parts[1]
    elif len(parts) > 1:
        return None

    # Handle Adblock-style domains.
    if value.startswith("||"):
        value = value[2:].split("^")[0]

    value = value.removeprefix("*.")
    value = value.removeprefix(".")

    if "://" in value:
        value = urlsplit(value).hostname or ""

    value = value.split("/")[0]
    value = value.split("?")[0]
    value = value.split("#")[0]

    value = value.rstrip(".")

    if value.startswith("www."):
        value = value[4:]

    if ":" in value:
        return None

    try:
        ipaddress.ip_address(value)
        return None
    except ValueError:
        pass

    if not DOMAIN_PATTERN.fullmatch(value):
        return None

    extracted = EXTRACT(value)

    if not extracted.domain or not extracted.suffix:
        return None

    return value


def domain_family(domain):
    extracted = EXTRACT(domain)
    return extracted.top_domain_under_public_suffix


def parse_plain_list(payload):
    result = set()

    text = payload.decode(
        "utf-8-sig",
        errors="replace"
    )

    for line in text.splitlines():
        domain = normalize_domain(line)

        if domain:
            result.add(domain)

    return result


def parse_ut1_archive(payload):
    with tarfile.open(
        fileobj=io.BytesIO(payload),
        mode="r:gz"
    ) as archive:

        members = [
            member
            for member in archive.getmembers()
            if member.isfile()
            and member.name.endswith("/domains")
        ]

        if not members:
            raise ValueError(
                "UT1 archive has no domains file"
            )

        stream = archive.extractfile(members[0])

        if stream is None:
            raise ValueError(
                "Unable to read UT1 domains"
            )

        return parse_plain_list(stream.read())


def original_families():
    files = [
        SPLIT_DIR / "baseline_train.csv",
        SPLIT_DIR / "baseline_validation.csv",
        SPLIT_DIR / "baseline_test.csv",
    ]

    families = set()

    for path in files:
        if not path.exists():
            raise FileNotFoundError(
                f"Original split missing: {path}"
            )

        df = pd.read_csv(path)

        if "domain" not in df.columns:
            raise ValueError(
                f"Missing domain column: {path}"
            )

        for value in df["domain"]:
            domain = normalize_domain(value)

            if domain:
                families.add(domain_family(domain))

    return families


def write_csv(path, rows):
    columns = [
        "domain",
        "domain_family",
        "suggested_label",
        "source",
        "category",
        "verification_status",
    ]

    with open(
        path,
        "w",
        newline="",
        encoding="utf-8"
    ) as handle:

        writer = csv.DictWriter(
            handle,
            fieldnames=columns
        )

        writer.writeheader()
        writer.writerows(rows)


def main():
    print("\nBETGUARD - DATASET EXPANSION")
    print("============================")

    old_families = original_families()

    print(
        "Existing benchmark families:",
        len(old_families)
    )

    collected = defaultdict(
        lambda: {
            "labels": set(),
            "sources": set(),
            "categories": set(),
        }
    )

    manifest = {
        "collected_at_utc": (
            datetime.now(timezone.utc).isoformat()
        ),
        "sources": [],
    }

    source_definitions = []

    for name, url in GAMBLING_SOURCES.items():
        source_definitions.append(
            (name, url, 1, "gambling", False)
        )

    for category in BENIGN_CATEGORIES:
        source_definitions.append(
            (
                f"ut1_{category}",
                UT1_BASE + category + ".tar.gz",
                0,
                category,
                True,
            )
        )

    for name, url, label, category, archived in (
        source_definitions
    ):
        print(f"\nDownloading: {name}")

        try:
            payload = download_bytes(url)

            sha256 = hashlib.sha256(
                payload
            ).hexdigest()

            if archived:
                domains = parse_ut1_archive(payload)
            else:
                domains = parse_plain_list(payload)

            print("Parsed domains:", len(domains))

            manifest["sources"].append({
                "name": name,
                "url": url,
                "sha256": sha256,
                "parsed_domain_count": len(domains),
                "status": "downloaded",
            })

            for domain in domains:
                item = collected[domain]

                item["labels"].add(label)
                item["sources"].add(name)
                item["categories"].add(category)

        except Exception as exc:
            print("DOWNLOAD ERROR:", exc)

            manifest["sources"].append({
                "name": name,
                "url": url,
                "status": "failed",
                "error": str(exc),
            })

    rows = []
    rejected_existing = 0

    for domain, info in collected.items():
        family = domain_family(domain)

        if family in old_families:
            rejected_existing += 1
            continue

        rows.append({
            "domain": domain,
            "domain_family": family,
            "suggested_label": next(
                iter(info["labels"])
            ) if len(info["labels"]) == 1 else -1,
            "source": ";".join(
                sorted(info["sources"])
            ),
            "category": ";".join(
                sorted(info["categories"])
            ),
            "verification_status": "needs_manual_review",
        })

    # Remove every family represented in BOTH proposed
    # classes. This is stricter than exact-domain dedup.
    family_labels = defaultdict(set)

    for row in rows:
        family_labels[
            row["domain_family"]
        ].add(row["suggested_label"])

    conflicting_families = {
        family
        for family, labels in family_labels.items()
        if len(labels) != 1 or -1 in labels
    }

    accepted = [
        row for row in rows
        if row["domain_family"]
        not in conflicting_families
    ]

    gambling = sorted(
        (
            row for row in accepted
            if row["suggested_label"] == 1
        ),
        key=lambda row: row["domain"]
    )

    benign = sorted(
        (
            row for row in accepted
            if row["suggested_label"] == 0
        ),
        key=lambda row: row["domain"]
    )

    write_csv(
        ROOT / "candidate_gambling.csv",
        gambling
    )

    write_csv(
        ROOT / "candidate_benign.csv",
        benign
    )

    # Construct a manageable diversified review queue.
    # One candidate per registrable domain family.

    def unique_family_sample(candidates, limit, seed):
        rng = random.Random(seed)

        shuffled = candidates.copy()
        rng.shuffle(shuffled)

        seen = set()
        selected = []

        for row in shuffled:
            family = row["domain_family"]

            if family in seen:
                continue

            seen.add(family)
            selected.append(row)

            if len(selected) >= limit:
                break

        return selected

    gambling_sample = unique_family_sample(
        gambling,
        REVIEW_TARGET_PER_CLASS,
        RANDOM_SEED,
    )

    benign_sample = unique_family_sample(
        benign,
        REVIEW_TARGET_PER_CLASS,
        RANDOM_SEED + 1,
    )

    review_queue = (
        gambling_sample + benign_sample
    )

    random.Random(RANDOM_SEED).shuffle(
        review_queue
    )

    write_csv(
        ROOT / "balanced_review_queue.csv",
        review_queue
    )

    manifest["counts"] = {
        "original_benchmark_families": len(old_families),
        "excluded_existing_domains": rejected_existing,
        "conflicting_families": len(conflicting_families),
        "gambling_candidates": len(gambling),
        "benign_candidates": len(benign),
        "review_queue": len(review_queue),
    }

    (ROOT / "source_manifest.json").write_text(
        json.dumps(manifest, indent=2),
        encoding="utf-8"
    )

    print("\n================================")
    print("EXPANSION COMPLETE")
    print("================================")

    for key, value in manifest["counts"].items():
        print(f"{key}: {value}")

    print("\nFiles:")
    print(ROOT / "candidate_gambling.csv")
    print(ROOT / "candidate_benign.csv")
    print(ROOT / "balanced_review_queue.csv")
    print(ROOT / "source_manifest.json")

    print(
        "\nWARNING: These are unverified candidate "
        "labels, NOT a training-ready dataset."
    )

    print(
        "Do not overwrite the existing baseline "
        "dataset or train on this output yet."
    )


if __name__ == "__main__":
    main()
