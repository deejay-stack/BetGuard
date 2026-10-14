
"""
BETGUARD - INDEPENDENT EVIDENCE VERIFIER V1

Classification policy:
    Option A - direct real-money online gambling only.

Independent sources:
    1. PAGCOR official registered gaming domains (PDF)
    2. UK Gambling Commission official business domains (CSV)
    3. UK Gambling Commission business-licence data (CSV)

Features:
    - Exact domain matching
    - Official source provenance and SHA256
    - Offline cache of downloaded registries
    - Manual research search links
    - Evidence review priority
    - Source availability reporting

Does NOT:
    - Visit suspicious domains
    - Automatically verify or modify any label
    - Train, tune, or deploy ML models
    - Treat a missing registry match as non-gambling

Run from the BetGuard ml directory.
"""

import argparse
import csv
import hashlib
import io
import json
import re

from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import quote, urljoin, urlsplit

import requests
from pypdf import PdfReader


# =====================================================
# PATHS
# =====================================================

ROOT = Path("data/expanded/partitions_v1")

INPUT = ROOT / "audit_review_option_a_v2.csv"

OUTPUT = ROOT / "independent_evidence_report.csv"

CACHE = Path("data/expanded/official_registry_cache")

CACHE_INDEX = CACHE / "source_cache.json"


# =====================================================
# OFFICIAL SOURCES
# =====================================================

SOURCES = {
    "pagcor": {
        "url": (
            "https://www.pagcor.ph/regulatory/pdf/"
            "App%20Kits/List-of-PAGCOR-Accredited-"
            "Gaming-System-Administrators-and-"
            "Registered-Brands-and-Domain-Names-URLs.pdf"
        ),
        "extension": "pdf",
        "max_bytes": 15_000_000,
    },

    "ukgc_domains": {
        "url": (
            "https://www.gamblingcommission.gov.uk/"
            "downloads/business-licence-register-"
            "domain-names.csv"
        ),
        "extension": "csv",
        "max_bytes": 5_000_000,
    },

    "ukgc_businesses": {
        "url": (
            "https://www.gamblingcommission.gov.uk/"
            "downloads/business-licence-register-"
            "businesses.csv"
        ),
        "extension": "csv",
        "max_bytes": 5_000_000,
    },
}


DOMAIN_RE = re.compile(
    r"(?<![A-Za-z0-9_-])"
    r"(?:[A-Za-z0-9]"
    r"(?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?\.)+"
    r"[A-Za-z]{2,63}"
    r"(?![A-Za-z0-9-])",
    re.I,
)


# =====================================================
# UTILITIES
# =====================================================

def now():
    return datetime.now(
        timezone.utc
    ).isoformat()


def sha256(data):
    return hashlib.sha256(
        data
    ).hexdigest()


def normalize_host(value):
    value = str(value or "").strip().lower()

    if "://" in value:
        value = urlsplit(value).hostname or ""

    value = value.split("/")[0]
    value = value.split(":")[0]
    value = value.strip(" .")

    if value.startswith("www."):
        value = value[4:]

    return value


def extract_domains(text):
    found = set()

    for match in DOMAIN_RE.finditer(str(text)):
        host = normalize_host(match.group())

        if DOMAIN_RE.fullmatch(host):
            found.add(host)

    return found


def normalize_heading(value):
    return re.sub(
        r"[^a-z0-9]+",
        " ",
        str(value).lower()
    ).strip()


def find_column(headers, choices):
    normalized = {
        normalize_heading(h): h
        for h in headers
    }

    for choice in choices:
        found = normalized.get(
            normalize_heading(choice)
        )

        if found:
            return found

    return None


def read_csv_bytes(data):
    text = data.decode(
        "utf-8-sig",
        errors="replace"
    )

    reader = csv.DictReader(
        io.StringIO(text)
    )

    return (
        list(reader.fieldnames or []),
        list(reader),
    )


def read_local(path):
    return Path(path).read_bytes()


# =====================================================
# SAFE OFFICIAL-SOURCE DOWNLOAD
# =====================================================

def download_official(source_name):
    source = SOURCES[source_name]
    original = source["url"]
    expected_host = urlsplit(original).hostname

    url = original

    with requests.Session() as session:

        for _ in range(5):

            parsed = urlsplit(url)

            if (
                parsed.scheme != "https"
                or parsed.hostname != expected_host
                or parsed.port not in (None, 443)
            ):
                raise RuntimeError(
                    "Official-source redirect "
                    "left the approved HTTPS host."
                )

            with session.get(
                url,
                timeout=(10, 30),
                allow_redirects=False,
                stream=True,
                verify=True,
            ) as response:

                if response.status_code in (
                    301, 302, 303, 307, 308
                ):

                    location = response.headers.get(
                        "Location"
                    )

                    if not location:
                        raise RuntimeError(
                            "Redirect missing Location."
                        )

                    url = urljoin(url, location)
                    continue

                response.raise_for_status()

                content = bytearray()

                for chunk in response.iter_content(
                    chunk_size=65536
                ):
                    content.extend(chunk)

                    if (
                        len(content)
                        > source["max_bytes"]
                    ):
                        raise RuntimeError(
                            "Official download size limit "
                            "exceeded."
                        )

                data = bytes(content)

                if (
                    source["extension"] == "pdf"
                    and not data.startswith(b"%PDF")
                ):
                    raise RuntimeError(
                        "Expected an official PDF."
                    )

                if (
                    source["extension"] == "csv"
                    and b"<html" in data[:1000].lower()
                ):
                    raise RuntimeError(
                        "Received HTML instead of CSV."
                    )

                return data

    raise RuntimeError(
        "Too many official-source redirects."
    )


# =====================================================
# SOURCE CACHE
# =====================================================

def load_cache_index():
    if not CACHE_INDEX.exists():
        return {}

    return json.loads(
        CACHE_INDEX.read_text(
            encoding="utf-8"
        )
    )


def save_cache_index(index):
    CACHE.mkdir(
        parents=True,
        exist_ok=True
    )

    CACHE_INDEX.write_text(
        json.dumps(index, indent=2),
        encoding="utf-8"
    )


def load_official_source(name, local_path, download, index):
    source = SOURCES[name]

    if local_path:
        data = read_local(local_path)

        return data, {
            "available": True,
            "origin": str(local_path),
            "sha256": sha256(data),
            "retrieved_at_utc": "local_file",
        }

    if download:

        try:
            data = download_official(name)

            digest = sha256(data)

            filename = (
                f"{name}_{digest[:16]}."
                f"{source['extension']}"
            )

            path = CACHE / filename

            CACHE.mkdir(
                parents=True,
                exist_ok=True
            )

            if not path.exists():
                path.write_bytes(data)

            index[name] = {
                "path": str(path),
                "sha256": digest,
                "source_url": source["url"],
                "retrieved_at_utc": now(),
            }

            save_cache_index(index)

            print(
                f"  Downloaded {name}: "
                f"{len(data)} bytes"
            )

            return data, {
                "available": True,
                "origin": source["url"],
                "sha256": digest,
                "retrieved_at_utc":
                    index[name]["retrieved_at_utc"],
            }

        except (
            requests.RequestException,
            RuntimeError,
            OSError,
        ) as error:
            print(
                f"  WARNING - {name}: {error}"
            )
            print(
                "  Trying a cached snapshot."
            )

    cached = index.get(name, {})

    if cached:
        path = Path(cached["path"])

        if path.exists():
            data = path.read_bytes()

            if sha256(data) != cached["sha256"]:
                raise RuntimeError(
                    f"Cache checksum mismatch: {name}"
                )

            print(
                f"  Using cached {name}"
            )

            return data, {
                "available": True,
                "origin": cached["path"],
                "sha256": sha256(data),
                "retrieved_at_utc": cached.get(
                    "retrieved_at_utc",
                    "unknown"
                ),
            }

    print(
        f"  UNAVAILABLE: {name}"
    )

    return None, {
        "available": False,
        "origin": source["url"],
    }


# =====================================================
# PAGCOR PDF DOMAIN EXTRACTION
# =====================================================

def parse_pagcor_pdf(data):
    reader = PdfReader(
        io.BytesIO(data)
    )

    domain_pages = defaultdict(set)

    page_texts = []

    for page_number, page in enumerate(
        reader.pages,
        start=1
    ):

        text = page.extract_text() or ""

        page_texts.append(text)

        for domain in extract_domains(text):
            domain_pages[domain].add(page_number)

    full_text = "\n".join(
        page_texts
    )

    match = re.search(
        r"\bas\s+of\s+"
        r"([A-Za-z]+\s+\d{1,2},\s*\d{4})",
        full_text,
        re.I,
    )

    document_date = (
        match.group(1)
        if match
        else "date_not_extracted"
    )

    if not domain_pages:
        raise RuntimeError(
            "No domains extracted from PAGCOR PDF. "
            "The document may need a different parser."
        )

    return {
        "domains": domain_pages,
        "document_date": document_date,
        "page_count": len(reader.pages),
    }


# =====================================================
# UKGC DOMAIN REGISTER
# =====================================================

def parse_ukgc_domains(data):
    headers, rows = read_csv_bytes(data)

    domain_column = find_column(
        headers,
        [
            "Domain name",
            "Domain",
            "Domain URL",
            "Website",
            "URL",
        ]
    )

    if not domain_column:
        raise RuntimeError(
            "UKGC domain column not recognized. "
            f"CSV headers: {headers}"
        )

    account_column = find_column(
        headers,
        [
            "Account number",
            "Account no",
            "Account",
        ]
    )

    status_column = find_column(
        headers,
        [
            "Domain name status",
            "Domain status",
        ]
    )

    matches = defaultdict(list)

    for row in rows:

        for domain in extract_domains(
            row.get(domain_column, "")
        ):
            matches[domain].append({
                "account": (
                    row.get(account_column, "").strip()
                    if account_column
                    else ""
                ),
                "domain_status": (
                    row.get(status_column, "").strip()
                    if status_column
                    else "not_provided"
                ),
            })

    if not matches:
        raise RuntimeError(
            "UKGC domain register had no "
            "recognizable domain records."
        )

    return matches


# =====================================================
# UKGC BUSINESS LICENCE STATUS
# =====================================================

def parse_ukgc_businesses(data):
    headers, rows = read_csv_bytes(data)

    account_column = find_column(
        headers,
        [
            "Account number",
            "Account no",
            "Account",
        ]
    )

    status_column = find_column(
        headers,
        [
            "Licence status",
            "License status",
        ]
    )

    if not account_column:
        raise RuntimeError(
            "UKGC account column not recognized. "
            f"CSV headers: {headers}"
        )

    accounts = defaultdict(set)

    for row in rows:
        account = row.get(
            account_column, ""
        ).strip()

        if not account:
            continue

        status = (
            row.get(status_column, "").strip()
            if status_column
            else "not_provided"
        )

        accounts[account].add(
            status or "not_provided"
        )

    return accounts


# =====================================================
# REVIEW DECISION SUPPORT
# =====================================================

def make_search_url(domain):
    query = (
        f'"{domain}" '
        'online gambling operator registration '
        'wagering casino sportsbook'
    )

    return (
        "https://www.google.com/search?q="
        + quote(query)
    )


def choose_priority(row, official_match):
    old = row.get(
        "v2_review_priority", ""
    )

    if old.startswith("P1"):
        return "P1_SOURCE_CONFLICT_OR_POLICY"

    if official_match:
        return "P1_OFFICIAL_MATCH_VERIFY_FUNCTION"

    if old.startswith("P2"):
        return "P2_VERIFY_DIRECT_WAGERING"

    if old.startswith("P3"):
        return "P3_FIND_INDEPENDENT_EVIDENCE"

    return "P4_ROUTINE_EVIDENCE_REVIEW"


def enrich_row(
    row,
    pagcor,
    ukgc,
    businesses,
    source_status,
):
    result = dict(row)

    domain = normalize_host(
        row.get("domain", "")
    )

    pagcor_match = (
        pagcor.get("domains", {}).get(
            domain, set()
        )
    )

    ukgc_matches = ukgc.get(
        domain, []
    )

    page_numbers = ",".join(
        str(page)
        for page in sorted(pagcor_match)
    )

    accounts = sorted({
        item["account"]
        for item in ukgc_matches
        if item["account"]
    })

    domain_statuses = sorted({
        item["domain_status"]
        for item in ukgc_matches
    })

    business_statuses = sorted({
        status
        for account in accounts
        for status in businesses.get(
            account, set()
        )
    })

    pagcor_available = source_status[
        "pagcor"
    ]["available"]

    ukgc_available = source_status[
        "ukgc_domains"
    ]["available"]

    if pagcor_match:
        pagcor_check = "exact_domain_listed"
    elif pagcor_available:
        pagcor_check = "not_listed"
    else:
        pagcor_check = "source_unavailable"

    if ukgc_matches:
        ukgc_check = "exact_domain_listed"
    elif ukgc_available:
        ukgc_check = "not_listed"
    else:
        ukgc_check = "source_unavailable"

    official_match = bool(
        pagcor_match or ukgc_matches
    )

    source_links = []

    if pagcor_match:
        source_links.append(
            SOURCES["pagcor"]["url"]
        )

    if ukgc_matches:
        source_links.append(
            SOURCES["ukgc_domains"]["url"]
        )

    if official_match:
        finding = (
            "OFFICIAL_REGISTRY_MATCH_"
            "DIRECT_WAGERING_NOT_YET_VERIFIED"
        )

        notes = (
            "Exact domain appears in an official "
            "registry. Confirm current operating "
            "status and whether real-money online "
            "wagering occurs through this domain. "
            "A registry match alone is not a "
            "verified Option A label."
        )

    else:
        finding = "NO_POSITIVE_REGISTRY_EVIDENCE"

        notes = (
            "No positive exact-domain match was "
            "obtained from the available official "
            "registries. This does NOT mean the "
            "domain is non-gambling, unlicensed "
            "worldwide, or inactive."
        )

    result.update({
        "independent_pagcor_check":
            pagcor_check,

        "independent_pagcor_pages":
            page_numbers,

        "independent_ukgc_check":
            ukgc_check,

        "independent_ukgc_accounts":
            ";".join(accounts),

        "independent_ukgc_domain_status":
            ";".join(domain_statuses),

        "independent_ukgc_business_status":
            ";".join(business_statuses),

        "independent_finding":
            finding,

        "independent_source_urls":
            ";".join(source_links),

        "independent_manual_search_url":
            make_search_url(domain),

        "independent_review_priority":
            choose_priority(
                row,
                official_match
            ),

        "independent_notes":
            notes,

        "independent_human_verified":
            "NO",

        "independent_checked_at_utc":
            now(),
    })

    return result


# =====================================================
# MAIN
# =====================================================

def main():
    parser = argparse.ArgumentParser()

    parser.add_argument(
        "--input",
        type=Path,
        default=INPUT
    )

    parser.add_argument(
        "--output",
        type=Path,
        default=OUTPUT
    )

    parser.add_argument(
        "--download-official",
        action="store_true",
        help="Download official PAGCOR/UKGC data."
    )

    parser.add_argument(
        "--pagcor-pdf",
        type=Path
    )

    parser.add_argument(
        "--ukgc-domains-csv",
        type=Path
    )

    parser.add_argument(
        "--ukgc-businesses-csv",
        type=Path
    )

    args = parser.parse_args()

    print(
        "\nBETGUARD - INDEPENDENT EVIDENCE V1"
    )

    print(
        "=================================="
    )

    if not args.input.exists():
        raise FileNotFoundError(
            args.input
        )

    with args.input.open(
        "r",
        encoding="utf-8-sig",
        newline=""
    ) as handle:

        reader = csv.DictReader(handle)

        input_fields = list(
            reader.fieldnames or []
        )

        records = list(reader)

    required = {
        "domain",
        "suggested_label",
        "review_status",
        "verified_label",
        "v2_finding",
    }

    if not required.issubset(
        input_fields
    ):
        raise RuntimeError(
            "Input is not the expected V2 audit."
        )

    if len({
        normalize_host(row["domain"])
        for row in records
    }) != len(records):
        raise RuntimeError(
            "Duplicate audit domains detected."
        )

    print(
        "\nAudit records:",
        len(records)
    )

    cache_index = load_cache_index()

    local_files = {
        "pagcor": args.pagcor_pdf,
        "ukgc_domains":
            args.ukgc_domains_csv,
        "ukgc_businesses":
            args.ukgc_businesses_csv,
    }

    data = {}
    status = {}

    print(
        "\nLoading official sources..."
    )

    for name in SOURCES:

        data[name], status[name] = (
            load_official_source(
                name,
                local_files[name],
                args.download_official,
                cache_index,
            )
        )

    pagcor = {
        "domains": {},
        "document_date": "unavailable",
    }

    ukgc = {}
    businesses = {}

    # Parse sources separately. A parser failure means
    # the source must be reported as unavailable.

    if data["pagcor"] is not None:
        try:
            pagcor = parse_pagcor_pdf(
                data["pagcor"]
            )

        except Exception as error:
            status["pagcor"]["available"] = False
            status["pagcor"]["parse_error"] = (
                str(error)
            )
            print(
                "PAGCOR parsing failed:",
                error
            )

    if data["ukgc_domains"] is not None:
        try:
            ukgc = parse_ukgc_domains(
                data["ukgc_domains"]
            )

        except Exception as error:
            status["ukgc_domains"][
                "available"
            ] = False

            status["ukgc_domains"][
                "parse_error"
            ] = str(error)

            print(
                "UKGC domain parsing failed:",
                error
            )

    if data["ukgc_businesses"] is not None:
        try:
            businesses = parse_ukgc_businesses(
                data["ukgc_businesses"]
            )

        except Exception as error:
            status["ukgc_businesses"][
                "available"
            ] = False

            status["ukgc_businesses"][
                "parse_error"
            ] = str(error)

            print(
                "UKGC business parsing failed:",
                error
            )

    print(
        "\nPAGCOR domains extracted:",
        len(pagcor.get("domains", {}))
    )

    print(
        "PAGCOR document date:",
        pagcor.get(
            "document_date",
            "unavailable"
        )
    )

    print(
        "UKGC domains extracted:",
        len(ukgc)
    )

    print(
        "UKGC accounts extracted:",
        len(businesses)
    )

    # -------------------------------------------------
    # Enrich the original audit
    # -------------------------------------------------

    results = [
        enrich_row(
            row,
            pagcor,
            ukgc,
            businesses,
            status,
        )
        for row in records
    ]

    priority_order = {
        "P1_SOURCE_CONFLICT_OR_POLICY": 0,
        "P1_OFFICIAL_MATCH_VERIFY_FUNCTION": 1,
        "P2_VERIFY_DIRECT_WAGERING": 2,
        "P3_FIND_INDEPENDENT_EVIDENCE": 3,
        "P4_ROUTINE_EVIDENCE_REVIEW": 4,
    }

    results.sort(
        key=lambda row: (
            priority_order.get(
                row[
                    "independent_review_priority"
                ],
                9
            ),
            row["domain"],
        )
    )

    added = [
        "independent_pagcor_check",
        "independent_pagcor_pages",
        "independent_ukgc_check",
        "independent_ukgc_accounts",
        "independent_ukgc_domain_status",
        "independent_ukgc_business_status",
        "independent_finding",
        "independent_source_urls",
        "independent_manual_search_url",
        "independent_review_priority",
        "independent_notes",
        "independent_human_verified",
        "independent_checked_at_utc",
    ]

    fields = input_fields + [
        name
        for name in added
        if name not in input_fields
    ]

    args.output.parent.mkdir(
        parents=True,
        exist_ok=True
    )

    with args.output.open(
        "w",
        encoding="utf-8-sig",
        newline=""
    ) as handle:

        writer = csv.DictWriter(
            handle,
            fieldnames=fields
        )

        writer.writeheader()
        writer.writerows(results)

    # -------------------------------------------------
    # Compact review queue
    # -------------------------------------------------

    review_fields = [
        "domain",
        "suggested_label",
        "source",
        "v2_finding",
        "v2_proposed_label",
        "v2_review_priority",
        "independent_pagcor_check",
        "independent_pagcor_pages",
        "independent_ukgc_check",
        "independent_ukgc_domain_status",
        "independent_ukgc_business_status",
        "independent_finding",
        "independent_source_urls",
        "independent_manual_search_url",
        "independent_review_priority",
        "independent_notes",
        "review_status",
        "verified_label",
        "evidence_reference",
        "reviewed_by",
        "review_notes",
    ]

    queue_path = args.output.with_name(
        args.output.stem
        + ".review_queue.csv"
    )

    with queue_path.open(
        "w",
        encoding="utf-8-sig",
        newline=""
    ) as handle:

        writer = csv.DictWriter(
            handle,
            fieldnames=review_fields
        )

        writer.writeheader()

        for row in results:
            writer.writerow({
                name: row.get(name, "")
                for name in review_fields
            })

    # -------------------------------------------------
    # Summary and source provenance
    # -------------------------------------------------

    finding_counts = Counter(
        row["independent_finding"]
        for row in results
    )

    priority_counts = Counter(
        row["independent_review_priority"]
        for row in results
    )

    report = {
        "generated_at_utc": now(),

        "classification": (
            "Option A - direct real-money "
            "online gambling only"
        ),

        "mode": (
            "official_registry_matching_"
            "and_manual_evidence_triage"
        ),

        "input": str(args.input),

        "input_sha256": sha256(
            args.input.read_bytes()
        ),

        "processed_domains": len(results),

        "source_status": status,

        "pagcor_document_date":
            pagcor.get(
                "document_date",
                "unavailable"
            ),

        "pagcor_registry_domains":
            len(
                pagcor.get("domains", {})
            ),

        "ukgc_registry_domains":
            len(ukgc),

        "findings":
            dict(finding_counts),

        "review_priorities":
            dict(priority_counts),

        "human_labels_created": 0,

        "deployed_models_changed": 0,

        "limitations": [
            "Exact registry matches are evidence, "
            "not final classifications.",

            "A missing registry match is not "
            "negative evidence of gambling.",

            "Official registries cover only "
            "their respective jurisdictions.",

            "Current real-money functionality "
            "still requires confirmation.",

            "Search URLs are research shortcuts, "
            "not evidence that searches occurred.",

            "Original audit and production "
            "model remain unchanged.",
        ],
    }

    summary_path = (
        args.output.with_suffix(
            ".summary.json"
        )
    )

    summary_path.write_text(
        json.dumps(
            report,
            indent=2,
            ensure_ascii=False
        ),
        encoding="utf-8"
    )

    print(
        "\n=================================="
    )

    print(
        "INDEPENDENT EVIDENCE CHECK COMPLETE"
    )

    print(
        "=================================="
    )

    for label, count in (
        finding_counts.most_common()
    ):
        print(
            f"{label}: {count}"
        )

    print(
        "\nReview priorities:"
    )

    for label, count in (
        priority_counts.most_common()
    ):
        print(
            f"{label}: {count}"
        )

    print(
        "\nSaved files:"
    )

    print(args.output)
    print(queue_path)
    print(summary_path)

    print(
        "\nHuman verified labels created: 0"
    )

    print(
        "Existing ML models changed: 0"
    )


if __name__ == "__main__":
    main()
