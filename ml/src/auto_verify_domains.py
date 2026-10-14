
"""
BETGUARD - AUTOMATED DOMAIN VERIFICATION V1

Purpose:
    Collect reviewable evidence for domain classifications.

Classification:
    0 = Non-direct-gambling website
    1 = Direct real-money gambling website

IMPORTANT:
    - Suggestions are NOT verified labels.
    - No automatic confirmation/correction.
    - No ML model changes.
    - No automatic website blocking.
    - No login, deposits, betting or browser execution.

Uses the Option A audit CSV produced previously.
"""

import argparse
import csv
import hashlib
import ipaddress
import json
import re
import socket

from collections import Counter
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urljoin, urlsplit

import requests
import tldextract
from bs4 import BeautifulSoup


# ======================================================
# CONFIGURATION
# ======================================================

DEFAULT_INPUT = Path(
    "data/expanded/partitions_v1/"
    "audit_review_option_a.csv"
)

DEFAULT_OUTPUT = Path(
    "data/expanded/partitions_v1/"
    "audit_review_option_a_auto.csv"
)

MAX_DOWNLOAD_BYTES = 256 * 1024
MAX_REDIRECTS = 3

USER_AGENT = (
    "BetGuardAcademicAudit/1.0 "
    "(read-only domain classification research)"
)

EXTRACT = tldextract.TLDExtract(
    suffix_list_urls=()
)

DOMAIN_PATTERN = re.compile(
    r"^(?=.{4,253}$)"
    r"(?:[a-z0-9]"
    r"(?:[a-z0-9-]{0,61}[a-z0-9])?\.)+"
    r"[a-z0-9-]{2,63}$"
)


# ======================================================
# EVIDENCE PATTERNS
# ======================================================
#
# These are indicators for review, not proof.
#
# A site can discuss betting without operating a
# real-money betting platform.
#
# ======================================================

GAMBLING_PATTERNS = [
    r"\bonline casino\b",
    r"\bsportsbook\b",
    r"\bsports betting\b",
    r"\breal.money casino\b",
    r"\bcasino games?\b",
    r"\bslot games?\b",
    r"\broulette\b",
    r"\bblackjack\b",
    r"\bpoker\b",
    r"\bbetting markets?\b",
    r"\bgambling\b",
]

TRANSACTION_PATTERNS = [
    r"\bplace (?:a |your )?bet\b",
    r"\bplace (?:a |your )?wager\b",
    r"\bbet slip\b",
    r"\breal.money\b",
    r"\bdeposit (?:money|funds)\b",
    r"\bwithdraw (?:money|funds|winnings)\b",
    r"\bcash (?:out|winnings)\b",
    r"\bplay for real money\b",
]

AFFILIATE_PATTERNS = [
    r"\bcasino reviews?\b",
    r"\bbookmaker reviews?\b",
    r"\bbetting reviews?\b",
    r"\bcasino comparisons?\b",
    r"\bcompare casinos?\b",
    r"\baffiliate links?\b",
    r"\bcasino rankings?\b",
    r"\bbetting guides?\b",
    r"\bbonus comparisons?\b",
]

NON_GAMBLING_SERVICE_PATTERNS = [
    r"\btransportation services?\b",
    r"\blimousine services?\b",
    r"\bcredit union\b",
    r"\bonline banking\b",
    r"\bpersonal banking\b",
    r"\bpainting services?\b",
    r"\bproperty maintenance\b",
    r"\bnewspaper\b",
    r"\bnews publisher\b",
    r"\bjob listings?\b",
    r"\bjob vacancies\b",
    r"\btranslation services?\b",
]


# ======================================================
# HELPERS
# ======================================================

def utc_now():
    return datetime.now(
        timezone.utc
    ).isoformat()


def matches_any(text, patterns):
    return any(
        re.search(pattern, text, re.I)
        for pattern in patterns
    )


def clean_text(value, maximum=600):
    value = re.sub(
        r"[\x00-\x1f\x7f]",
        " ",
        str(value or "")
    )

    value = re.sub(
        r"\s+",
        " ",
        value
    ).strip()

    value = value[:maximum]

    # Prevent spreadsheet formula injection.
    if value.startswith(("=", "+", "-", "@")):
        value = "'" + value

    return value


def hash_file(path):
    digest = hashlib.sha256()

    with path.open("rb") as file:
        for chunk in iter(
            lambda: file.read(65536),
            b""
        ):
            digest.update(chunk)

    return digest.hexdigest()


def get_family(domain):
    result = EXTRACT(domain)

    return (
        result.top_domain_under_public_suffix
    )


# ======================================================
# DOMAIN VALIDATION
# ======================================================

def validate_domain(domain):
    domain = domain.strip().lower().rstrip(".")

    if not DOMAIN_PATTERN.fullmatch(domain):
        raise ValueError(
            "Invalid domain syntax"
        )

    family = get_family(domain)

    if not family:
        raise ValueError(
            "Unknown registrable domain"
        )

    return domain, family


# ======================================================
# DNS / NETWORK SAFETY
# ======================================================
#
# Rejects local/private/reserved destinations.
#
# This is a useful precaution, but not a complete
# security boundary against malicious DNS rebinding.
#
# Run active inspection in an isolated environment
# when working with untrusted domains.
# ======================================================

def resolve_public_addresses(hostname):
    results = socket.getaddrinfo(
        hostname,
        443,
        type=socket.SOCK_STREAM
    )

    addresses = sorted({
        str(
            ipaddress.ip_address(
                result[4][0]
            )
        )
        for result in results
    })

    if not addresses:
        raise RuntimeError(
            "No DNS addresses"
        )

    for address in addresses:
        ip = ipaddress.ip_address(address)

        if not ip.is_global:
            raise RuntimeError(
                "Non-public DNS destination blocked"
            )

    return addresses


def validate_https_url(url, original_family):
    parsed = urlsplit(url)

    if parsed.scheme.lower() != "https":
        raise RuntimeError(
            "Only HTTPS fetching is allowed"
        )

    if parsed.username or parsed.password:
        raise RuntimeError(
            "URL credentials are not allowed"
        )

    if parsed.port not in (None, 443):
        raise RuntimeError(
            "Nonstandard HTTPS port rejected"
        )

    hostname = (
        parsed.hostname or ""
    ).lower()

    hostname, family = validate_domain(
        hostname
    )

    if family != original_family:
        raise RuntimeError(
            "Cross-family redirect blocked"
        )

    addresses = resolve_public_addresses(
        hostname
    )

    return hostname, addresses


# ======================================================
# READ LIMITED HTML
# ======================================================

def fetch_public_html(domain, timeout):
    original_family = get_family(domain)

    url = f"https://{domain}/"

    headers = {
        "User-Agent": USER_AGENT,
        "Accept": (
            "text/html,"
            "application/xhtml+xml"
        ),
        "Accept-Language": "en",
    }

    with requests.Session() as session:
        # Avoid silently using proxy settings.
        session.trust_env = False

        for _ in range(MAX_REDIRECTS + 1):

            validate_https_url(
                url,
                original_family
            )

            with session.get(
                url,
                headers=headers,
                timeout=(5, timeout),
                allow_redirects=False,
                stream=True,
                verify=True
            ) as response:

                status = response.status_code

                if status in (
                    301, 302, 303, 307, 308
                ):
                    location = response.headers.get(
                        "Location"
                    )

                    if not location:
                        raise RuntimeError(
                            "Redirect without Location"
                        )

                    url = urljoin(
                        url,
                        location
                    )

                    continue

                if status != 200:
                    return {
                        "state": "http_error",
                        "status": str(status),
                        "url": url,
                        "html": "",
                    }

                content_type = (
                    response.headers.get(
                        "Content-Type", ""
                    ).lower()
                )

                if (
                    "text/html" not in content_type
                    and
                    "application/xhtml+xml"
                    not in content_type
                ):
                    return {
                        "state": "not_html",
                        "status": str(status),
                        "url": url,
                        "html": "",
                    }

                content = bytearray()

                for chunk in response.iter_content(
                    chunk_size=16384
                ):
                    if not chunk:
                        continue

                    remaining = (
                        MAX_DOWNLOAD_BYTES
                        -
                        len(content)
                    )

                    if remaining <= 0:
                        break

                    content.extend(
                        chunk[:remaining]
                    )

                    if (
                        len(content)
                        >= MAX_DOWNLOAD_BYTES
                    ):
                        break

                encoding = (
                    response.encoding or "utf-8"
                )

                html = bytes(content).decode(
                    encoding,
                    errors="replace"
                )

                return {
                    "state": "fetched",
                    "status": "200",
                    "url": url,
                    "html": html,
                }

    raise RuntimeError(
        "Too many redirects"
    )


# ======================================================
# PARSE VISIBLE PAGE CONTENT
# ======================================================

def extract_page_content(html):
    soup = BeautifulSoup(
        html,
        "html.parser"
    )

    title = ""

    if soup.title:
        title = soup.title.get_text(
            " ",
            strip=True
        )

    description = ""

    meta = soup.find(
        "meta",
        attrs={"name": "description"}
    )

    if meta:
        description = meta.get(
            "content", ""
        )

    # Avoid scripts/styles affecting keyword evidence.
    for tag in soup(
        [
            "script",
            "style",
            "noscript",
            "svg",
        ]
    ):
        tag.decompose()

    visible = soup.get_text(
        " ",
        strip=True
    )

    return (
        clean_text(title, 250),
        clean_text(description, 500),
        clean_text(visible, 30000),
    )


# ======================================================
# EVIDENCE EXCERPT
# ======================================================

def evidence_excerpt(text):
    match = re.search(
        r"casino|betting|sportsbook|"
        r"real.money|deposit|wager|"
        r"affiliate|review|transportation|"
        r"banking",
        text,
        re.I
    )

    if match:
        start = max(
            0,
            match.start() - 100
        )

        end = min(
            len(text),
            match.end() + 220
        )

        return clean_text(
            text[start:end],
            350
        )

    return clean_text(
        text[:350],
        350
    )


# ======================================================
# AUTOMATED CLASSIFICATION SUGGESTION
# ======================================================

def suggest_from_content(
    title,
    description,
    body
):
    full_text = " ".join(
        [title, description, body]
    ).lower()

    headline = " ".join(
        [title, description]
    ).lower()

    gambling = matches_any(
        full_text,
        GAMBLING_PATTERNS
    )

    transaction = matches_any(
        full_text,
        TRANSACTION_PATTERNS
    )

    affiliate = matches_any(
        headline,
        AFFILIATE_PATTERNS
    )

    unrelated_service = matches_any(
        headline,
        NON_GAMBLING_SERVICE_PATTERNS
    )

    signals = []

    if gambling:
        signals.append(
            "gambling_terms"
        )

    if transaction:
        signals.append(
            "wagering_or_payment_terms"
        )

    if affiliate:
        signals.append(
            "affiliate_or_review_terms"
        )

    if unrelated_service:
        signals.append(
            "other_service_terms"
        )

    if affiliate and gambling:
        finding = "possible_affiliate_or_review"
        proposed = "0"

        reason = (
            "The page appears to provide gambling "
            "reviews or affiliate information. "
            "Check whether actual wagering is offered."
        )

    elif unrelated_service and not transaction:
        finding = "possible_non_gambling_service"
        proposed = "0"

        reason = (
            "The page describes an unrelated service. "
            "Confirm current site ownership and function."
        )

    elif gambling and transaction:
        finding = "possible_direct_gambling"
        proposed = "1"

        reason = (
            "Gambling and wagering/payment indicators "
            "were found together. This is not proof "
            "of real-money operation."
        )

    elif gambling:
        finding = "gambling_related_unconfirmed"
        proposed = ""

        reason = (
            "Gambling-related terms found without "
            "sufficient evidence of direct wagering."
        )

    else:
        finding = "insufficient_evidence"
        proposed = ""

        reason = (
            "No sufficiently specific classification "
            "evidence was found."
        )

    return {
        "finding": finding,
        "proposed_label": proposed,
        "signals": ";".join(signals),
        "reason": reason,
    }


# ======================================================
# REVIEW PRIORITY
# ======================================================

def determine_priority(
    original_label,
    result
):
    proposed = result["auto_proposed_label"]

    state = result["fetch_state"]

    if (
        proposed in ("0", "1")
        and proposed != original_label
    ):
        return "HIGH_LABEL_CONFLICT"

    if state != "fetched":
        return "NEEDS_EVIDENCE"

    if result["auto_finding"] in (
        "possible_affiliate_or_review",
        "gambling_related_unconfirmed",
    ):
        return "HIGH_AMBIGUITY"

    return "STANDARD_REVIEW"


# ======================================================
# PROCESS ONE DOMAIN
# ======================================================

def process_row(row, fetch_web, timeout):
    domain = (
        row.get("domain", "")
    ).strip().lower()

    result = dict(row)

    result.update({
        "fetch_state": "",
        "http_status": "",
        "evidence_url": "",
        "page_title": "",
        "meta_description": "",
        "evidence_excerpt": "",
        "auto_finding": "",
        "auto_proposed_label": "",
        "auto_signals": "",
        "auto_reason": "",
        "auto_review_priority": "",
        "checked_at_utc": utc_now(),
    })

    try:
        domain, _ = validate_domain(
            domain
        )

        addresses = resolve_public_addresses(
            domain
        )

        result["dns_addresses"] = ";".join(
            addresses
        )

        if not fetch_web:
            result["fetch_state"] = "dns_only"
            result["auto_finding"] = "not_checked"
            result["auto_reason"] = (
                "HTTPS fetching was not enabled."
            )

            result["auto_proposed_label"] = ""

        else:
            page = fetch_public_html(
                domain,
                timeout
            )

            result["fetch_state"] = (
                page["state"]
            )

            result["http_status"] = (
                page["status"]
            )

            result["evidence_url"] = (
                page["url"]
            )

            if page["state"] == "fetched":
                title, description, body = (
                    extract_page_content(
                        page["html"]
                    )
                )

                result["page_title"] = title
                result["meta_description"] = (
                    description
                )

                result["evidence_excerpt"] = (
                    evidence_excerpt(body)
                )

                suggestion = suggest_from_content(
                    title,
                    description,
                    body
                )

                result["auto_finding"] = (
                    suggestion["finding"]
                )

                result["auto_proposed_label"] = (
                    suggestion["proposed_label"]
                )

                result["auto_signals"] = (
                    suggestion["signals"]
                )

                result["auto_reason"] = (
                    suggestion["reason"]
                )

            else:
                result["auto_finding"] = (
                    "unresolved"
                )

                result["auto_proposed_label"] = ""

                result["auto_reason"] = (
                    "Page unavailable or not HTML."
                )

    except (
        requests.RequestException,
        RuntimeError,
        ValueError,
        OSError,
        UnicodeError,
    ) as error:

        result["fetch_state"] = "error"

        result["auto_finding"] = "unresolved"

        result["auto_proposed_label"] = ""

        result["auto_reason"] = clean_text(
            f"{type(error).__name__}: {error}",
            250
        )

    result["auto_review_priority"] = (
        determine_priority(
            row["suggested_label"],
            result
        )
    )

    # Do not modify these original human-review fields:
    #
    # review_status
    # verified_label
    # evidence_reference
    # reviewed_by
    # review_notes
    #
    # This script NEVER confirms a label automatically.

    return result


# ======================================================
# MAIN
# ======================================================

def main():
    parser = argparse.ArgumentParser(
        description=(
            "BetGuard Option A domain evidence collector"
        )
    )

    parser.add_argument(
        "--input",
        type=Path,
        default=DEFAULT_INPUT
    )

    parser.add_argument(
        "--output",
        type=Path,
        default=DEFAULT_OUTPUT
    )

    parser.add_argument(
        "--limit",
        type=int,
        default=0
    )

    parser.add_argument(
        "--workers",
        type=int,
        default=3
    )

    parser.add_argument(
        "--timeout",
        type=int,
        default=10
    )

    parser.add_argument(
        "--fetch-web",
        action="store_true",
        help=(
            "Explicitly enable read-only HTTPS requests "
            "to the listed domains."
        )
    )

    args = parser.parse_args()

    if args.limit < 0:
        parser.error(
            "--limit must be zero or positive"
        )

    if not 1 <= args.workers <= 5:
        parser.error(
            "--workers must be between 1 and 5"
        )

    if not 3 <= args.timeout <= 30:
        parser.error(
            "--timeout must be between 3 and 30"
        )

    if not args.input.exists():
        raise FileNotFoundError(
            args.input
        )

    print(
        "\nBETGUARD - AUTOMATED VERIFICATION V1"
    )

    print(
        "===================================="
    )

    print(
        "Option A: Direct gambling websites only"
    )

    with args.input.open(
        "r",
        newline="",
        encoding="utf-8-sig"
    ) as handle:
        reader = csv.DictReader(handle)

        fieldnames = list(
            reader.fieldnames or []
        )

        rows = list(reader)

    required = {
        "domain",
        "domain_family",
        "suggested_label",
        "review_status",
        "verified_label",
    }

    if not required.issubset(fieldnames):
        raise RuntimeError(
            "Input CSV is missing required columns"
        )

    if args.limit:
        rows = rows[:args.limit]

        args.output = args.output.with_name(
            f"{args.output.stem}"
            f"_sample{args.limit}"
            f"{args.output.suffix}"
        )

    print("Input domains:", len(rows))
    print("HTTPS collection:", args.fetch_web)

    if args.fetch_web:
        print(
            "Use an isolated machine/network "
            "for inspecting untrusted sites."
        )

    results = [None] * len(rows)

    with ThreadPoolExecutor(
        max_workers=args.workers
    ) as executor:

        futures = {
            executor.submit(
                process_row,
                row,
                args.fetch_web,
                args.timeout,
            ): index
            for index, row in enumerate(rows)
        }

        completed = 0

        for future in as_completed(futures):
            index = futures[future]

            results[index] = future.result()

            completed += 1

            if (
                completed % 10 == 0
                or completed == len(rows)
            ):
                print(
                    f"Processed: {completed}/{len(rows)}"
                )

    extra_fields = [
        "dns_addresses",
        "fetch_state",
        "http_status",
        "evidence_url",
        "page_title",
        "meta_description",
        "evidence_excerpt",
        "auto_finding",
        "auto_proposed_label",
        "auto_signals",
        "auto_reason",
        "auto_review_priority",
        "checked_at_utc",
    ]

    all_fields = fieldnames + [
        field
        for field in extra_fields
        if field not in fieldnames
    ]

    priority_order = {
        "HIGH_LABEL_CONFLICT": 0,
        "HIGH_AMBIGUITY": 1,
        "NEEDS_EVIDENCE": 2,
        "STANDARD_REVIEW": 3,
    }

    results.sort(
        key=lambda row: (
            priority_order.get(
                row["auto_review_priority"],
                99
            ),
            row["domain"],
        )
    )

    args.output.parent.mkdir(
        parents=True,
        exist_ok=True
    )

    with args.output.open(
        "w",
        newline="",
        encoding="utf-8"
    ) as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=all_fields
        )

        writer.writeheader()
        writer.writerows(results)

    findings = Counter(
        row["auto_finding"]
        for row in results
    )

    priorities = Counter(
        row["auto_review_priority"]
        for row in results
    )

    fetch_states = Counter(
        row["fetch_state"]
        for row in results
    )

    report = {
        "generated_at_utc": utc_now(),

        "definition": (
            "Option A - direct real-money "
            "gambling websites only"
        ),

        "input_file": str(args.input),
        "input_sha256": hash_file(args.input),

        "output_file": str(args.output),
        "processed_domains": len(results),

        "web_fetch_enabled": args.fetch_web,

        "findings": dict(findings),

        "review_priorities": dict(priorities),

        "fetch_states": dict(fetch_states),

        "human_verified_labels_created": 0,

        "warning": (
            "Automated suggestions are unverified. "
            "Human-reviewed evidence is required "
            "for final labels."
        ),
    }

    report_path = (
        args.output.with_suffix(
            ".summary.json"
        )
    )

    report_path.write_text(
        json.dumps(
            report,
            indent=2
        ),
        encoding="utf-8"
    )

    print(
        "\n===================================="
    )

    print("AUTOMATED AUDIT COMPLETE")

    print(
        "===================================="
    )

    print("\nFetch results:")

    for key, value in fetch_states.items():
        print(f"  {key}: {value}")

    print("\nSuggested findings:")

    for key, value in findings.items():
        print(f"  {key}: {value}")

    print("\nReview priorities:")

    for key, value in priorities.items():
        print(f"  {key}: {value}")

    print("\nSaved:")
    print(args.output)
    print(report_path)

    print(
        "\nVerified labels were NOT modified."
    )

    print(
        "Production model was NOT modified."
    )


if __name__ == "__main__":
    main()
