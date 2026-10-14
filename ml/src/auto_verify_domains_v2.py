
"""
BETGUARD - AUTOMATED DOMAIN VERIFIER V2

Option A: Direct real-money gambling websites only.

V2 analyzes previously collected V1 evidence OFFLINE.

It does NOT:
- Visit websites or make network requests
- Verify labels without human review
- Overwrite the V1 audit
- Modify any training dataset
- Retrain or replace the production ML model

Requirements:
    pip install ftfy

Run from the ml/ directory:
    python src/auto_verify_domains_v2.py
"""

import argparse
import csv
import hashlib
import json
import re

from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

from ftfy import fix_text


# ======================================================
# FILE LOCATIONS
# ======================================================

ROOT = Path("data/expanded/partitions_v1")

DEFAULT_INPUT = (
    ROOT / "audit_review_option_a_auto.csv"
)

DEFAULT_OUTPUT = (
    ROOT / "audit_review_option_a_v2.csv"
)


# ======================================================
# CLASSIFICATION PATTERNS
# ======================================================
#
# Important: Terms indicate evidence for REVIEW.
# They are not independent proof of direct wagering.
# ======================================================

GAMBLING = [
    r"\bcasino\b",
    r"\bcasinos\b",
    r"\bbetting\b",
    r"\bsportsbook\b",
    r"\bsports betting\b",
    r"\bgambling\b",
    r"\bonline slots?\b",
    r"\bpoker\b",
    r"\broulette\b",
    r"\bblackjack\b",
    r"\bjackpot\b",
    r"\bcazinou\b",
    r"\bkasyno\b",
    r"\bkasiino\b",
    r"\bparis sportifs\b",
    r"\bzakłady sportowe\b",
    r"\bcá cược\b",
    r"\bcược trực tuyến\b",
]

MONEY = [
    r"\breal.money\b",
    r"\bdeposit\b",
    r"\bdeposits\b",
    r"\bwithdraw\b",
    r"\bwithdrawal\b",
    r"\bwager\b",
    r"\bwinnings\b",
    r"\bcash out\b",
    r"\bbet slip\b",
    r"\bnạp tiền\b",
    r"\brút tiền\b",
    r"\bwpłata\b",
    r"\bwypłata\b",
    r"\bdépôt\b",
    r"\bretrait\b",
]

PARTICIPATION = [
    r"\blogin\b",
    r"\blog in\b",
    r"\bsign ?up\b",
    r"\bregister\b",
    r"\bregistration\b",
    r"\bcreate (?:an? |your )?account\b",
    r"\bplace (?:a |your )?bet\b",
    r"\bbet now\b",
    r"\bplay now\b",
    r"\bđăng ký\b",
    r"\bđăng nhập\b",
    r"\bdaftar\b",
    r"\bregistrieren\b",
    r"\bs.inscrire\b",
    r"\brejestracja\b",
]

AFFILIATE = [
    r"\bcasino reviews?\b",
    r"\bbookmaker reviews?\b",
    r"\breview(?:s|ed)?\b",
    r"\breview and gaming options guide\b",
    r"\bcasino rankings?\b",
    r"\bcomparisons?\b",
    r"\bcompare\b",
    r"\bcomparison guide\b",
    r"\baffiliate\b",
    r"\bindependent casino\b",
    r"\bindependent review\b",
    r"\bbest (?:online )?casinos\b",
    r"\bcasino guides?\b",
    r"\bgranskning\b",
    r"\brecenzja\b",
    r"\banálisis\b",
    r"\banalyse\b",
    r"\brecensione\b",
    r"\bvergleich\b",
    r"\bgranskning av casino\b",
]

UNRELATED_SERVICES = {
    "transportation": [
        r"\btransportation\b",
        r"\blimousine\b",
        r"\blimo service\b",
        r"\bchauffeur\b",
        r"\bshuttle service\b",
        r"\bairport transfer\b",
    ],
    "banking": [
        r"\bcredit union\b",
        r"\bfederal credit union\b",
        r"\bonline banking\b",
        r"\bpersonal banking\b",
        r"\bchecking accounts?\b",
        r"\bmortgage loans?\b",
    ],
    "news": [
        r"\bbreaking news\b",
        r"\bnewspaper\b",
        r"\bnews publisher\b",
        r"\bnews headlines\b",
        r"\bherald leader\b",
        r"\bhometown newspaper\b",
    ],
    "property_services": [
        r"\bimmobilien service\b",
        r"\bmalerbetrieb\b",
        r"\bproperty maintenance\b",
        r"\bpainting services\b",
        r"\bproperty management\b",
    ],
    "job_services": [
        r"\bjob listings\b",
        r"\bjob vacancies\b",
        r"\bjob search\b",
        r"\brecruitment agency\b",
    ],
}

LAND_BASED = [
    r"\bcasino hotel\b",
    r"\bland.based casino\b",
    r"\bcasino resort\b",
    r"\bhotel and casino\b",
    r"\brooms and suites\b",
]


# ======================================================
# UTILITY FUNCTIONS
# ======================================================

def utc_now():
    return datetime.now(
        timezone.utc
    ).isoformat()


def file_hash(path):
    digest = hashlib.sha256()

    with path.open("rb") as handle:
        for chunk in iter(
            lambda: handle.read(65536),
            b""
        ):
            digest.update(chunk)

    return digest.hexdigest()


def normalize_text(value):
    value = fix_text(
        str(value or "")
    )

    value = re.sub(
        r"\s+",
        " ",
        value
    )

    return value.strip()


def matches(text, expressions):
    return any(
        re.search(
            expression,
            text,
            flags=re.IGNORECASE
        )
        for expression in expressions
    )


def excel_safe(value):
    """
    Prevent spreadsheet formula execution when
    opening externally collected text in Excel.
    """
    value = str(value or "")

    if re.match(
        r"^\s*[=+\-@]",
        value
    ):
        return "'" + value

    return value


# ======================================================
# TECHNICAL FAILURE CLASSIFICATION
# ======================================================

def categorize_fetch(row):
    state = (
        row.get("fetch_state", "")
        .strip()
        .lower()
    )

    reason = (
        row.get("auto_reason", "")
        .lower()
    )

    status = str(
        row.get("http_status", "")
    ).strip()

    if state == "fetched":
        return "page_retrieved"

    if state == "dns_only":
        return "dns_only"

    if state == "http_error":

        if status == "403":
            return "access_denied_403"

        if status == "404":
            return "page_not_found_404"

        if status.startswith("5"):
            return "server_error_5xx"

        return "http_error_other"

    if "cross-family redirect" in reason:
        return "external_redirect_not_followed"

    if (
        "getaddrinfo failed" in reason
        or "gaierror" in reason
        or "name or service not known" in reason
        or "name resolution" in reason
    ):
        return "dns_resolution_failure"

    if (
        "certificate_verify_failed" in reason
        or "certificate verify failed" in reason
    ):
        return "tls_certificate_failure"

    if (
        "sslerror" in reason
        or "unexpected_eof" in reason
        or "tls" in reason
    ):
        return "tls_handshake_failure"

    if (
        "timeout" in reason
        or "timed out" in reason
    ):
        return "connection_timeout"

    if state == "not_html":
        return "non_html_response"

    return "other_network_failure"


# ======================================================
# OPTION A EVIDENCE CLASSIFIER
# ======================================================

def classify_evidence(row):

    title = normalize_text(
        row.get("page_title", "")
    )

    description = normalize_text(
        row.get("meta_description", "")
    )

    excerpt = normalize_text(
        row.get("evidence_excerpt", "")
    )

    headline = (
        title + " " + description
    ).strip()

    combined = (
        headline + " " + excerpt
    ).strip()

    gambling = matches(
        combined,
        GAMBLING
    )

    money = matches(
        combined,
        MONEY
    )

    participation = matches(
        combined,
        PARTICIPATION
    )

    signals = []

    if gambling:
        signals.append("gambling_content")

    if money:
        signals.append("financial_or_wager_terms")

    if participation:
        signals.append("participation_terms")

    # --------------------------------------------------
    # 1. UNRELATED SERVICE DETECTION
    #
    # Check the page title and description first.
    # For Option A, the actual service matters.
    # --------------------------------------------------

    for service, patterns in (
        UNRELATED_SERVICES.items()
    ):

        if matches(
            headline,
            patterns
        ):
            return {
                "finding": "non_gambling_service_candidate",
                "suggested_label": "0",
                "service_type": service,
                "signals": signals + [
                    f"service:{service}"
                ],
                "reason": (
                    "Page title or description identifies "
                    f"a {service} service. Review to "
                    "confirm that no direct real-money "
                    "gambling is offered."
                ),
            }

    # --------------------------------------------------
    # 2. GAMBLING REVIEW / AFFILIATE DETECTION
    # --------------------------------------------------

    if (
        gambling
        and matches(
            headline,
            AFFILIATE
        )
    ):
        return {
            "finding": "affiliate_or_review_candidate",
            "suggested_label": "0",
            "service_type": "gambling_information",
            "signals": signals + [
                "review_or_affiliate"
            ],
            "reason": (
                "Title or description suggests casino "
                "reviews, rankings, comparisons, or "
                "affiliate information. Direct wagering "
                "has not been established."
            ),
        }

    # --------------------------------------------------
    # 3. PHYSICAL CASINO / HOTEL DETECTION
    # --------------------------------------------------

    if matches(
        headline,
        LAND_BASED
    ):
        return {
            "finding": "physical_casino_venue_candidate",
            "suggested_label": "",
            "service_type": "land_based_venue",
            "signals": signals + [
                "physical_casino_venue"
            ],
            "reason": (
                "The site may describe a physical "
                "casino, hotel, or resort. Check whether "
                "this domain also offers online "
                "real-money wagering."
            ),
        }

    # --------------------------------------------------
    # 4. DIRECT GAMBLING CANDIDATE
    #
    # Even multiple signals do not prove that the
    # user can wager directly at this domain.
    # --------------------------------------------------

    if (
        gambling
        and money
        and participation
    ):
        return {
            "finding": "direct_gambling_candidate",
            "suggested_label": "1",
            "service_type": "possible_operator",
            "signals": signals,
            "reason": (
                "Gambling, financial/wagering and "
                "participation terms were found. "
                "Check independent evidence that "
                "real-money betting is actually "
                "offered on this domain."
            ),
        }

    # --------------------------------------------------
    # 5. GAMBLING CONTENT WITHOUT DIRECT PROOF
    # --------------------------------------------------

    if gambling:
        return {
            "finding": "gambling_content_only",
            "suggested_label": "",
            "service_type": "unconfirmed",
            "signals": signals,
            "reason": (
                "Gambling-related content appears on "
                "the page, but evidence of direct "
                "real-money wagering is insufficient."
            ),
        }

    # --------------------------------------------------
    # 6. INSUFFICIENT INFORMATION
    # --------------------------------------------------

    return {
        "finding": "insufficient_content_evidence",
        "suggested_label": "",
        "service_type": "unknown",
        "signals": signals,
        "reason": (
            "The retrieved excerpt does not contain "
            "enough evidence to establish the site's "
            "actual function."
        ),
    }


# ======================================================
# REVIEW PRIORITY
# ======================================================

def choose_priority(row, finding, proposed):

    original = row.get(
        "suggested_label",
        ""
    ).strip()

    if finding == "unresolved_fetch":
        return "P3_FETCH_EVIDENCE_NEEDED"

    if (
        proposed in ("0", "1")
        and proposed != original
    ):
        return "P1_POSSIBLE_LABEL_CONFLICT"

    if finding in (
        "affiliate_or_review_candidate",
        "physical_casino_venue_candidate",
    ):
        return "P1_POLICY_REVIEW"

    if finding == "direct_gambling_candidate":
        return "P2_CHECK_DIRECT_WAGERING"

    if finding == "gambling_content_only":
        return "P2_AMBIGUOUS_CONTENT"

    return "P4_ROUTINE_REVIEW"


# ======================================================
# PROCESS ONE RECORD
# ======================================================

def process_row(row):

    result = dict(row)

    fetch_issue = categorize_fetch(
        row
    )

    if fetch_issue != "page_retrieved":

        classification = {
            "finding": "unresolved_fetch",
            "suggested_label": "",
            "service_type": "unknown",
            "signals": [],
            "reason": (
                "The website could not be evaluated "
                f"from fetched content: {fetch_issue}. "
                "This does not establish either label."
            ),
        }

    else:
        classification = classify_evidence(
            row
        )

    finding = classification["finding"]

    proposed = classification[
        "suggested_label"
    ]

    original_label = (
        row.get("suggested_label", "")
        .strip()
    )

    v1_proposal = (
        row.get("auto_proposed_label", "")
        .strip()
    )

    prior_research = (
        row.get("provisional_label", "")
        .strip()
    )

    if proposed and proposed != original_label:
        disagreement = "conflicts_with_source_label"

    elif (
        proposed
        and v1_proposal
        and proposed != v1_proposal
    ):
        disagreement = "disagrees_with_v1"

    else:
        disagreement = ""

    if prior_research in ("0", "1"):

        if proposed and proposed != prior_research:
            disagreement = (
                "conflicts_with_prior_research"
            )

    result.update({
        "v2_fetch_category": fetch_issue,

        "v2_finding": finding,

        "v2_proposed_label": proposed,

        "v2_service_type":
            classification["service_type"],

        "v2_signals": ";".join(
            classification["signals"]
        ),

        "v2_reason": classification["reason"],

        "v2_disagreement": disagreement,

        "v2_review_priority": choose_priority(
            row,
            finding,
            proposed
        ),

        "v2_title_repaired": normalize_text(
            row.get("page_title", "")
        ),

        "v2_description_repaired": normalize_text(
            row.get("meta_description", "")
        ),

        "v2_evidence_url": (
            row.get("evidence_url", "")
            or row.get("research_evidence_url", "")
        ),

        "v2_verified": "NO",

        "v2_processed_at_utc": utc_now(),
    })

    # Human-review fields are never changed.
    #
    # review_status
    # verified_label
    # evidence_reference
    # reviewed_by
    # review_notes

    return result


# ======================================================
# CSV OUTPUT
# ======================================================

EXTRA_FIELDS = [
    "v2_fetch_category",
    "v2_finding",
    "v2_proposed_label",
    "v2_service_type",
    "v2_signals",
    "v2_reason",
    "v2_disagreement",
    "v2_review_priority",
    "v2_title_repaired",
    "v2_description_repaired",
    "v2_evidence_url",
    "v2_verified",
    "v2_processed_at_utc",
]


def write_csv(path, fieldnames, rows):

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
            fieldnames=fieldnames
        )

        writer.writeheader()

        for row in rows:
            safe_row = {
                key: excel_safe(value)
                for key, value in row.items()
            }

            writer.writerow(safe_row)


# ======================================================
# MAIN
# ======================================================

def main():

    parser = argparse.ArgumentParser()

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

    args = parser.parse_args()

    if not args.input.exists():
        raise FileNotFoundError(
            args.input
        )

    print(
        "\n===================================="
    )

    print(
        " BETGUARD AUTOMATED VERIFIER V2"
    )

    print(
        "===================================="
    )

    print(
        "\nClassification: Direct gambling only"
    )

    print(
        "Mode: OFFLINE evidence re-analysis"
    )

    with args.input.open(
        "r",
        encoding="utf-8-sig",
        newline=""
    ) as handle:

        reader = csv.DictReader(
            handle
        )

        original_fields = list(
            reader.fieldnames or []
        )

        records = list(reader)

    required = {
        "domain",
        "domain_family",
        "suggested_label",
        "fetch_state",
        "auto_finding",
        "review_status",
        "verified_label",
    }

    if not required.issubset(
        original_fields
    ):
        raise RuntimeError(
            "Input does not match the V1 audit format."
        )

    if not records:
        raise ValueError(
            "Input file is empty."
        )

    domains = [
        row["domain"]
        for row in records
    ]

    if len(domains) != len(set(domains)):
        raise RuntimeError(
            "Duplicate domains in audit."
        )

    if any(
        row["suggested_label"] not in ("0", "1")
        for row in records
    ):
        raise RuntimeError(
            "Invalid source labels."
        )

    results = [
        process_row(row)
        for row in records
    ]

    # --------------------------------------------------
    # SORT REVIEW QUEUE
    # --------------------------------------------------

    priority_order = {
        "P1_POSSIBLE_LABEL_CONFLICT": 0,
        "P1_POLICY_REVIEW": 1,
        "P2_CHECK_DIRECT_WAGERING": 2,
        "P2_AMBIGUOUS_CONTENT": 3,
        "P3_FETCH_EVIDENCE_NEEDED": 4,
        "P4_ROUTINE_REVIEW": 5,
    }

    results.sort(
        key=lambda row: (
            priority_order.get(
                row["v2_review_priority"],
                99
            ),
            row["domain"],
        )
    )

    fieldnames = original_fields + [
        name
        for name in EXTRA_FIELDS
        if name not in original_fields
    ]

    write_csv(
        args.output,
        fieldnames,
        results
    )

    # --------------------------------------------------
    # REVIEW-QUEUE OUTPUT
    # --------------------------------------------------

    queue_fields = [
        "domain",
        "suggested_label",
        "source",
        "category",
        "audit_priority",
        "provisional_label",
        "v2_fetch_category",
        "v2_finding",
        "v2_proposed_label",
        "v2_review_priority",
        "v2_reason",
        "v2_evidence_url",
        "review_status",
        "verified_label",
        "evidence_reference",
        "reviewed_by",
        "review_notes",
    ]

    review_queue_path = (
        args.output.with_name(
            args.output.stem
            + ".review_queue.csv"
        )
    )

    write_csv(
        review_queue_path,
        queue_fields,
        [
            {
                key: row.get(key, "")
                for key in queue_fields
            }
            for row in results
        ]
    )

    # --------------------------------------------------
    # COMPARISON SUMMARY
    # --------------------------------------------------

    v1_findings = Counter(
        row.get("auto_finding", "")
        for row in records
    )

    v2_findings = Counter(
        row["v2_finding"]
        for row in results
    )

    fetch_counts = Counter(
        row["v2_fetch_category"]
        for row in results
    )

    priority_counts = Counter(
        row["v2_review_priority"]
        for row in results
    )

    v1_proposals = Counter(
        row.get("auto_proposed_label", "")
        for row in records
    )

    v2_proposals = Counter(
        row["v2_proposed_label"]
        for row in results
    )

    changed_suggestions = [
        row
        for row in results
        if (
            row.get("auto_proposed_label", "")
            != row["v2_proposed_label"]
        )
    ]

    report = {
        "generated_at_utc": utc_now(),

        "classification_definition": (
            "Option A: direct real-money "
            "gambling websites only"
        ),

        "mode": "offline_v1_evidence_reanalysis",

        "input_path": str(args.input),

        "input_sha256": file_hash(args.input),

        "output_path": str(args.output),

        "processed_domains": len(results),

        "source_label_counts": dict(
            Counter(
                row["suggested_label"]
                for row in records
            )
        ),

        "v1_findings": dict(v1_findings),

        "v2_findings": dict(v2_findings),

        "v1_proposals": dict(v1_proposals),

        "v2_proposals": dict(v2_proposals),

        "technical_fetch_categories": dict(
            fetch_counts
        ),

        "review_priorities": dict(
            priority_counts
        ),

        "changed_automated_suggestions": (
            len(changed_suggestions)
        ),

        "changed_suggestion_domains": [
            row["domain"]
            for row in changed_suggestions
        ],

        "human_labels_created": 0,

        "notes": [
            "V2 makes no network requests.",
            "Existing source labels are unverified.",
            "A label proposal is not ground truth.",
            "Fetched evidence may be incomplete.",
            "Human reviewers must confirm labels.",
            "No training or production files changed.",
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

    # --------------------------------------------------
    # TERMINAL SUMMARY
    # --------------------------------------------------

    print(
        f"\nDomains processed: {len(results)}"
    )

    print(
        "\nV2 Findings:"
    )

    for label, count in (
        v2_findings.most_common()
    ):
        print(
            f"  {label}: {count}"
        )

    print(
        "\nV2 Review Priorities:"
    )

    for label, count in (
        priority_counts.most_common()
    ):
        print(
            f"  {label}: {count}"
        )

    print(
        "\nTechnical Fetch Categories:"
    )

    for label, count in (
        fetch_counts.most_common()
    ):
        print(
            f"  {label}: {count}"
        )

    print(
        "\nChanged automated suggestions:",
        len(changed_suggestions)
    )

    # --------------------------------------------------
    # CHECK CRITICAL PREVIOUS ERROR
    # --------------------------------------------------

    indexed = {
        row["domain"]: row
        for row in results
    }

    sample_domain = (
        "licasinotransportation.com"
    )

    if sample_domain in indexed:

        item = indexed[sample_domain]

        print(
            "\nTransportation regression check:"
        )

        print(
            "  Domain:",
            sample_domain
        )

        print(
            "  V1:",
            item.get("auto_finding", "")
        )

        print(
            "  V2:",
            item["v2_finding"]
        )

        if (
            item["v2_finding"]
            == "direct_gambling_candidate"
        ):
            raise RuntimeError(
                "V2 still incorrectly treats "
                "casino transportation as direct "
                "gambling. Review rules before use."
            )

    print(
        "\nSaved files:"
    )

    print(args.output)
    print(review_queue_path)
    print(summary_path)

    print(
        "\nHuman verified labels created: 0"
    )

    print(
        "Existing ML models modified: 0"
    )

    print(
        "\nV2 evaluation complete."
    )


if __name__ == "__main__":
    main()
