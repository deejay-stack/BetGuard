
"""
BETGUARD - PAGCOR PHILIPPINE DATASET BUILDER V2

PURPOSE
-------
Build a Philippines-focused candidate dataset using
official PAGCOR registered gaming-domain documents.

CLASSIFICATION
--------------
1 = Direct real-money online gambling
0 = No direct real-money online gambling

IMPORTANT
---------
All generated labels are PROVISIONAL.

A PAGCOR-listed domain is NOT automatically proof
that visitors can directly place real-money bets.

This module:
- Downloads and caches official PAGCOR PDFs
- Extracts candidate domains
- Groups related domains by registrable family
- Preserves PDF source and page information
- Creates a Philippine benign candidate list
- Detects family overlap between the classes
- Generates CSV files and a source manifest

This module DOES NOT:
- Train ML models
- Replace existing datasets
- Modify the deployed BetGuard classifier
- Verify gambling functionality automatically
- Create a final independent test set
"""

import argparse
import csv
import hashlib
import io
import json
import re

from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urljoin, urlsplit

import requests
import tldextract

from pypdf import PdfReader


# =====================================================
# PROJECT PATHS
# =====================================================

# Automatically finds the ml project folder.
# Works even when the script is started from
# a different working directory.

ML_ROOT = Path(__file__).resolve().parents[1]

DATA_DIR = (
    ML_ROOT
    / "data"
    / "expanded"
    / "pagcor_ph"
)

PDF_DIR = DATA_DIR / "source_snapshots"

BENIGN_SEEDS = DATA_DIR / "ph_benign_seeds.csv"

POSITIVE_OUTPUT = (
    DATA_DIR / "pagcor_positive_candidates.csv"
)

BENIGN_OUTPUT = (
    DATA_DIR / "ph_benign_candidates.csv"
)

REVIEW_OUTPUT = (
    DATA_DIR / "ph_review_queue_unreviewed.csv"
)

CONFLICT_OUTPUT = (
    DATA_DIR / "ph_family_conflicts.csv"
)

MANIFEST_OUTPUT = (
    DATA_DIR / "ph_dataset_manifest.json"
)


# =====================================================
# DOMAIN EXTRACTOR
# =====================================================

# FIX:
# The previous script declared EXTRACTOR but tried
# to call EXTRACT, causing a NameError.
#
# All functions now use EXTRACTOR consistently.
#
# suffix_list_urls=() prevents runtime downloading
# of the public suffix list.

EXTRACTOR = tldextract.TLDExtract(
    suffix_list_urls=()
)


# =====================================================
# OFFICIAL PAGCOR DOCUMENTS
# =====================================================

PAGCOR_SOURCES = {
    "pagcor_gsa": {
        "url": (
            "https://www.pagcor.ph/regulatory/pdf/"
            "App%20Kits/"
            "List-of-PAGCOR-Accredited-Gaming-"
            "System-Administrators-and-Registered-"
            "Brands-and-Domain-Names-URLs.pdf"
        ),
        "filename": "pagcor_gsa.pdf",
    },

    "pagcor_licensed_casinos": {
        "url": (
            "https://www.pagcor.ph/regulatory/pdf/"
            "App%20Kits/"
            "List-of-Registered-Brands-and-"
            "Domain-Names-URLs-of-Licensed-Casinos.pdf"
        ),
        "filename": "pagcor_licensed_casinos.pdf",
    },
}

MAX_PDF_BYTES = 20 * 1024 * 1024


# =====================================================
# PHILIPPINE BENIGN CANDIDATE STARTERS
# =====================================================

# These are starter candidates only.
# The actual websites must still be reviewed.

BENIGN_STARTERS = [
    ("deped.gov.ph", "government"),
    ("dost.gov.ph", "government"),
    ("dti.gov.ph", "government"),
    ("doh.gov.ph", "government"),
    ("ched.gov.ph", "government"),
    ("bsp.gov.ph", "government"),
    ("psa.gov.ph", "government"),
    ("dfa.gov.ph", "government"),
    ("bir.gov.ph", "government"),
    ("comelec.gov.ph", "government"),
    ("sss.gov.ph", "government"),
    ("gsis.gov.ph", "government"),
    ("philhealth.gov.ph", "government"),
    ("pagibigfund.gov.ph", "government"),

    ("up.edu.ph", "education"),
    ("dlsu.edu.ph", "education"),
    ("ust.edu.ph", "education"),
    ("pup.edu.ph", "education"),
    ("ateneo.edu", "education"),
    ("mapua.edu.ph", "education"),
    ("feu.edu.ph", "education"),

    ("bpi.com.ph", "banking"),
    ("bdo.com.ph", "banking"),
    ("metrobank.com.ph", "banking"),
    ("securitybank.com", "banking"),
    ("landbank.com", "banking"),
]


# =====================================================
# DOMAIN MATCHING
# =====================================================

DOMAIN_PATTERN = re.compile(
    r"(?<![A-Za-z0-9@_-])"
    r"(?:[A-Za-z0-9]"
    r"(?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?\.)+"
    r"[A-Za-z]{2,63}"
    r"(?![A-Za-z0-9-])",
    re.IGNORECASE,
)

DATE_PATTERN = re.compile(
    r"\bas\s+of\s+"
    r"([A-Za-z]+\s+\d{1,2},?\s*\d{4})",
    re.IGNORECASE,
)

EXCLUDED_DOMAINS = {
    "pagcor.ph",
    "www.pagcor.ph",
}


# =====================================================
# SHARED UTILITIES
# =====================================================

def current_time():
    return datetime.now(
        timezone.utc
    ).isoformat()


def calculate_sha256(data):
    return hashlib.sha256(
        data
    ).hexdigest()


def normalize_domain(value):
    value = str(value or "").strip().lower()

    if "://" in value:
        value = (
            urlsplit(value).hostname
            or ""
        )

    value = value.strip(
        " \t\r\n<>(),;:'\""
    )

    return value.rstrip(".")


def domain_family(host):
    """
    Get the registrable domain.

    Examples:
        www.example.com -> example.com
        shop.example.com -> example.com
        university.edu.ph -> university.edu.ph
    """

    host = normalize_domain(host)

    # FIXED: use EXTRACTOR, not EXTRACT.
    parsed = EXTRACTOR(host)

    if not parsed.suffix:
        return ""

    return (
        parsed.top_domain_under_public_suffix
        or ""
    )


def is_valid_domain(host):
    host = normalize_domain(host)

    if not DOMAIN_PATTERN.fullmatch(host):
        return False

    if host in EXCLUDED_DOMAINS:
        return False

    return bool(domain_family(host))


def extract_domains(text):
    """
    Extract possible domain names from PDF text.

    These are candidates, not verified gaming URLs.
    PDF layout and non-gaming references can produce
    additional domains that require review.
    """

    results = set()

    for match in DOMAIN_PATTERN.finditer(
        text or ""
    ):
        domain = normalize_domain(
            match.group()
        )

        if is_valid_domain(domain):
            results.add(domain)

    return results


def save_csv(path, fieldnames, rows):
    path.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    with path.open(
        "w",
        encoding="utf-8-sig",
        newline="",
    ) as file:
        writer = csv.DictWriter(
            file,
            fieldnames=fieldnames,
            extrasaction="ignore",
        )

        writer.writeheader()
        writer.writerows(rows)


# =====================================================
# OFFICIAL PDF DOWNLOAD
# =====================================================

def download_pagcor_pdf(url):
    """
    Download an official PAGCOR PDF.

    Security:
    - HTTPS only
    - TLS certificate validation enabled
    - Redirects restricted to PAGCOR
    - Maximum download size enforced
    """

    current_url = url

    with requests.Session() as session:

        for _ in range(5):

            parsed = urlsplit(current_url)

            if parsed.scheme != "https":
                raise RuntimeError(
                    "Only HTTPS sources are allowed."
                )

            if parsed.hostname not in (
                "pagcor.ph",
                "www.pagcor.ph",
            ):
                raise RuntimeError(
                    "PDF redirect left the PAGCOR domain."
                )

            if parsed.port not in (None, 443):
                raise RuntimeError(
                    "Unexpected HTTPS port."
                )

            with session.get(
                current_url,
                timeout=(10, 45),
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
                            "Redirect has no Location header."
                        )

                    current_url = urljoin(
                        current_url,
                        location,
                    )

                    continue

                response.raise_for_status()

                content = bytearray()

                for chunk in response.iter_content(
                    chunk_size=65536
                ):
                    if not chunk:
                        continue

                    content.extend(chunk)

                    if len(content) > MAX_PDF_BYTES:
                        raise RuntimeError(
                            "PDF exceeds allowed size."
                        )

                data = bytes(content)

                if not data.startswith(b"%PDF"):
                    raise RuntimeError(
                        "Downloaded content is not a PDF."
                    )

                return data

    raise RuntimeError(
        "Too many redirects while downloading PDF."
    )


# =====================================================
# LOAD OFFICIAL PDF
# =====================================================

def load_pagcor_pdf(
    source_id,
    local_pdf=None,
    refresh=False,
):
    source = PAGCOR_SOURCES[source_id]

    PDF_DIR.mkdir(
        parents=True,
        exist_ok=True,
    )

    cache_path = (
        PDF_DIR / source["filename"]
    )

    if local_pdf is not None:

        local_pdf = Path(local_pdf)

        if not local_pdf.exists():
            raise FileNotFoundError(
                local_pdf
            )

        print(
            f"Using local PDF: {local_pdf}"
        )

        data = local_pdf.read_bytes()
        loaded_from = str(local_pdf)

    elif cache_path.exists() and not refresh:

        print(
            f"Using cached PDF: {cache_path}"
        )

        data = cache_path.read_bytes()
        loaded_from = str(cache_path)

    else:

        print(
            f"Downloading: {source_id}"
        )

        data = download_pagcor_pdf(
            source["url"]
        )

        cache_path.write_bytes(data)

        loaded_from = source["url"]

    if not data.startswith(b"%PDF"):
        raise RuntimeError(
            f"Invalid cached/source PDF: {source_id}. "
            "Use --refresh or supply a valid local PDF."
        )

    metadata = {
        "source_id": source_id,
        "official_url": source["url"],
        "loaded_from": loaded_from,
        "sha256": calculate_sha256(data),
        "size_bytes": len(data),
        "loaded_at_utc": current_time(),
    }

    return data, metadata


# =====================================================
# EXTRACT DOMAINS FROM PAGCOR PDF
# =====================================================

def parse_pagcor_pdf(source_id, data):

    try:
        reader = PdfReader(
            io.BytesIO(data)
        )

    except Exception as error:
        raise RuntimeError(
            f"Unable to read {source_id} PDF: {error}"
        ) from error

    domains_by_page = defaultdict(set)

    document_dates = set()

    pages_with_text = 0

    for page_number, page in enumerate(
        reader.pages,
        start=1,
    ):

        text = page.extract_text() or ""

        if text.strip():
            pages_with_text += 1

        date_match = DATE_PATTERN.search(
            text
        )

        if date_match:
            document_dates.add(
                date_match.group(1).strip()
            )

        found_domains = extract_domains(
            text
        )

        for domain in found_domains:
            domains_by_page[domain].add(
                page_number
            )

    if pages_with_text == 0:
        raise RuntimeError(
            f"{source_id} contains no extractable text. "
            "Inspect the PDF; it may be scanned."
        )

    if not domains_by_page:
        raise RuntimeError(
            f"No domains extracted from {source_id}. "
            "Check the PDF layout and domain parser."
        )

    return {
        "source_id": source_id,

        "document_date": (
            ";".join(sorted(document_dates))
            if document_dates
            else "not_extracted"
        ),

        "page_count": len(
            reader.pages
        ),

        "pages_with_text": pages_with_text,

        "domains": domains_by_page,
    }


# =====================================================
# BUILD POSITIVE CANDIDATES
# =====================================================

def build_positive_candidates(documents):

    combined = {}

    for document in documents:

        source_id = document["source_id"]

        for domain, pages in (
            document["domains"].items()
        ):

            family = domain_family(domain)

            if not family:
                continue

            if domain not in combined:

                combined[domain] = {
                    "domain": domain,
                    "domain_family": family,
                    "suggested_label": "1",

                    "source_set": set(),
                    "pages_set": set(),
                    "dates_set": set(),

                    "category": (
                        "pagcor_pdf_domain_candidate"
                    ),

                    "verification_status": (
                        "needs_direct_wagering_review"
                    ),

                    "review_status": "pending",
                    "verified_label": "",
                    "evidence_reference": "",
                    "reviewed_by": "",
                    "review_notes": "",
                    "training_eligible": "NO",
                }

            item = combined[domain]

            item["source_set"].add(
                source_id
            )

            item["dates_set"].add(
                document["document_date"]
            )

            for page in pages:
                item["pages_set"].add(
                    f"{source_id}:page_{page}"
                )

    records = []

    for domain in sorted(combined):

        item = combined[domain]

        records.append({
            "domain": item["domain"],
            "domain_family": item["domain_family"],
            "suggested_label": "1",

            "source": ";".join(
                sorted(item["source_set"])
            ),

            "source_pages": ";".join(
                sorted(item["pages_set"])
            ),

            "document_dates": ";".join(
                sorted(item["dates_set"])
            ),

            "category": item["category"],

            "verification_status": (
                item["verification_status"]
            ),

            "review_status": "pending",
            "verified_label": "",
            "evidence_reference": "",
            "reviewed_by": "",
            "review_notes": "",
            "training_eligible": "NO",
        })

    return records


# =====================================================
# CREATE BENIGN SEED FILE
# =====================================================

def create_benign_seed_file():

    # Preserve user edits when the file already exists.
    if BENIGN_SEEDS.exists():

        print(
            "Using existing Philippine benign seeds."
        )

        return

    records = []

    for domain, category in BENIGN_STARTERS:

        records.append({
            "domain": domain,
            "category": category,
            "reference_url": (
                f"https://{domain}/"
            ),
        })

    save_csv(
        BENIGN_SEEDS,
        [
            "domain",
            "category",
            "reference_url",
        ],
        records,
    )

    print(
        "Created Philippine benign seed file."
    )


# =====================================================
# BUILD BENIGN CANDIDATES
# =====================================================

def build_benign_candidates(positives):

    positive_families = {
        item["domain_family"]
        for item in positives
    }

    benign = []
    conflicts = []

    seen_domains = set()

    with BENIGN_SEEDS.open(
        "r",
        encoding="utf-8-sig",
        newline="",
    ) as file:

        reader = csv.DictReader(file)

        seed_rows = list(reader)

    for row in seed_rows:

        domain = normalize_domain(
            row.get("domain", "")
        )

        if not is_valid_domain(domain):

            print(
                f"Skipping invalid benign seed: {domain}"
            )

            continue

        if domain in seen_domains:
            continue

        seen_domains.add(domain)

        family = domain_family(domain)

        if family in positive_families:

            conflicts.append({
                "domain": domain,
                "domain_family": family,
                "reason": (
                    "Domain family appears "
                    "in PAGCOR candidate list"
                ),
            })

            continue

        benign.append({
            "domain": domain,
            "domain_family": family,
            "suggested_label": "0",

            "source": (
                "ph_institutional_seed_candidate"
            ),

            "source_pages": "",
            "document_dates": "",

            "category": row.get(
                "category",
                "unknown",
            ),

            "verification_status": (
                "needs_non_gambling_review"
            ),

            "review_status": "pending",
            "verified_label": "",
            "evidence_reference": "",
            "reviewed_by": "",
            "review_notes": "",
            "training_eligible": "NO",
        })

    return benign, conflicts


# =====================================================
# OUTPUT FORMAT
# =====================================================

DATA_FIELDS = [
    "domain",
    "domain_family",
    "suggested_label",
    "source",
    "source_pages",
    "document_dates",
    "category",
    "verification_status",
    "review_status",
    "verified_label",
    "evidence_reference",
    "reviewed_by",
    "review_notes",
    "training_eligible",
]


# =====================================================
# DATASET INTEGRITY CHECKS
# =====================================================

def check_dataset_integrity(
    positives,
    benign,
):
    all_rows = positives + benign

    domains = [
        item["domain"]
        for item in all_rows
    ]

    if len(domains) != len(set(domains)):
        raise RuntimeError(
            "Duplicate domains detected."
        )

    positive_families = {
        item["domain_family"]
        for item in positives
    }

    benign_families = {
        item["domain_family"]
        for item in benign
    }

    overlap = (
        positive_families
        &
        benign_families
    )

    if overlap:
        raise RuntimeError(
            "Cross-label family conflict: "
            f"{len(overlap)}"
        )

    for row in all_rows:

        if row["review_status"] != "pending":
            raise RuntimeError(
                "Unexpected verified review state."
            )

        if row["verified_label"] != "":
            raise RuntimeError(
                "Candidate has an unexpected "
                "verified label."
            )

        if row["training_eligible"] != "NO":
            raise RuntimeError(
                "Unverified candidate marked "
                "as training eligible."
            )

    print(
        "\nDataset integrity: PASSED"
    )

    print(
        "Cross-class family overlap: 0"
    )

    print(
        "Automatically verified labels: 0"
    )


# =====================================================
# MAIN
# =====================================================

def main():

    parser = argparse.ArgumentParser(
        description=(
            "Build Philippines-focused PAGCOR "
            "gambling-domain candidate dataset."
        )
    )

    parser.add_argument(
        "--gsa-pdf",
        type=Path,
        default=None,
        help="Optional local PAGCOR GSA PDF."
    )

    parser.add_argument(
        "--casino-pdf",
        type=Path,
        default=None,
        help="Optional local licensed casino PDF."
    )

    parser.add_argument(
        "--refresh",
        action="store_true",
        help=(
            "Download fresh official PAGCOR PDFs "
            "instead of using cached files."
        ),
    )

    args = parser.parse_args()

    print(
        "\nBETGUARD - PAGCOR PH DATASET BUILDER V2"
    )

    print(
        "======================================"
    )

    print(
        "Jurisdiction: Philippines"
    )

    print(
        "Classification: Direct real-money "
        "online gambling only"
    )

    print(
        "Dataset stage: UNVERIFIED CANDIDATES"
    )

    DATA_DIR.mkdir(
        parents=True,
        exist_ok=True,
    )

    source_paths = {
        "pagcor_gsa": args.gsa_pdf,
        "pagcor_licensed_casinos": args.casino_pdf,
    }

    documents = []
    metadata = {}

    # -------------------------------------------------
    # LOAD AND PARSE OFFICIAL DOCUMENTS
    # -------------------------------------------------

    for source_id in PAGCOR_SOURCES:

        pdf_data, source_metadata = (
            load_pagcor_pdf(
                source_id=source_id,
                local_pdf=source_paths[source_id],
                refresh=args.refresh,
            )
        )

        document = parse_pagcor_pdf(
            source_id,
            pdf_data,
        )

        documents.append(
            document
        )

        source_metadata.update({
            "document_date": (
                document["document_date"]
            ),

            "page_count": (
                document["page_count"]
            ),

            "pages_with_text": (
                document["pages_with_text"]
            ),

            "extracted_hosts": len(
                document["domains"]
            ),
        })

        metadata[source_id] = (
            source_metadata
        )

        print(
            f"\nSource: {source_id}"
        )

        print(
            "  Document date:",
            document["document_date"]
        )

        print(
            "  PDF pages:",
            document["page_count"]
        )

        print(
            "  Extracted candidate hosts:",
            len(document["domains"])
        )

    # -------------------------------------------------
    # BUILD CANDIDATE DATASETS
    # -------------------------------------------------

    print(
        "\nBuilding PAGCOR positive candidates..."
    )

    positives = build_positive_candidates(
        documents
    )

    print(
        "Building Philippine benign candidates..."
    )

    create_benign_seed_file()

    benign, conflicts = (
        build_benign_candidates(
            positives
        )
    )

    # -------------------------------------------------
    # VALIDATE
    # -------------------------------------------------

    check_dataset_integrity(
        positives,
        benign,
    )

    # -------------------------------------------------
    # SAVE CSV FILES
    # -------------------------------------------------

    review_queue = (
        positives + benign
    )

    save_csv(
        POSITIVE_OUTPUT,
        DATA_FIELDS,
        positives,
    )

    save_csv(
        BENIGN_OUTPUT,
        DATA_FIELDS,
        benign,
    )

    save_csv(
        REVIEW_OUTPUT,
        DATA_FIELDS,
        review_queue,
    )

    save_csv(
        CONFLICT_OUTPUT,
        [
            "domain",
            "domain_family",
            "reason",
        ],
        conflicts,
    )

    # -------------------------------------------------
    # COUNTS
    # -------------------------------------------------

    counts = {
        "positive_candidate_hosts": len(
            positives
        ),

        "positive_domain_families": len({
            row["domain_family"]
            for row in positives
        }),

        "benign_candidate_hosts": len(
            benign
        ),

        "benign_domain_families": len({
            row["domain_family"]
            for row in benign
        }),

        "conflicting_benign_families": len(
            conflicts
        ),

        "total_review_candidates": len(
            review_queue
        ),

        "human_verified_labels": 0,
    }

    # -------------------------------------------------
    # MANIFEST
    # -------------------------------------------------

    manifest = {
        "generated_at_utc": current_time(),

        "project": "BetGuard",

        "version": "pagcor_ph_builder_v2",

        "jurisdiction": "Philippines",

        "label_definition": {
            "1": (
                "Direct real-money online gambling"
            ),

            "0": (
                "No direct real-money online gambling"
            ),
        },

        "dataset_status": (
            "UNVERIFIED_CANDIDATES"
        ),

        "official_sources": metadata,

        "benign_seed_file": str(
            BENIGN_SEEDS
        ),

        "benign_seed_sha256": (
            calculate_sha256(
                BENIGN_SEEDS.read_bytes()
            )
        ),

        "counts": counts,

        "outputs": {
            "positive_candidates": str(
                POSITIVE_OUTPUT
            ),

            "benign_candidates": str(
                BENIGN_OUTPUT
            ),

            "review_queue": str(
                REVIEW_OUTPUT
            ),

            "family_conflicts": str(
                CONFLICT_OUTPUT
            ),
        },

        "limitations": [
            "PDF text extraction may include "
            "domains outside registered gaming "
            "entries and requires source review.",

            "PAGCOR registration alone does not "
            "prove direct real-money wagering.",

            "The dataset does not represent all "
            "illegal gambling domains in the "
            "Philippines.",

            "Benign starters require independent "
            "verification.",

            "Future training splits must exclude "
            "historical benchmark families and "
            "prevent train-test family overlap.",

            "No new independent test set "
            "has been created.",

            "No deployed BetGuard model "
            "has been modified.",
        ],
    }

    MANIFEST_OUTPUT.write_text(
        json.dumps(
            manifest,
            indent=2,
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    # -------------------------------------------------
    # TERMINAL SUMMARY
    # -------------------------------------------------

    print(
        "\n======================================"
    )

    print(
        "PHILIPPINE CANDIDATE COLLECTION COMPLETE"
    )

    print(
        "======================================"
    )

    for key, value in counts.items():
        print(
            f"{key}: {value}"
        )

    print(
        "\nSaved files:"
    )

    print(POSITIVE_OUTPUT)
    print(BENIGN_OUTPUT)
    print(REVIEW_OUTPUT)
    print(CONFLICT_OUTPUT)
    print(MANIFEST_OUTPUT)

    print(
        "\nIMPORTANT:"
    )

    print(
        "Candidate labels are not yet verified."
    )

    print(
        "No ML training or deployment changes."
    )


if __name__ == "__main__":
    main()
