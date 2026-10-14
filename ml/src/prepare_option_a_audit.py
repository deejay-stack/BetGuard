
import csv
from pathlib import Path
from collections import Counter


# =====================================================
# BETGUARD - OPTION A AUDIT TRIAGE
# Direct real-money gambling websites only.
#
# Does not modify original CSV or verified labels.
# =====================================================

ROOT = Path("data/expanded/partitions_v1")

INPUT = ROOT / "audit_review_template.csv"

OUTPUT = ROOT / "audit_review_option_a.csv"


# Evidence-backed proposals, NOT final verified labels.
# Each entry: (proposed_label, reason, evidence URL)

RESEARCH = {
    "rivieracasino.com": (
        "1",
        "Direct casino games and real-money wagering.",
        "https://www.rivieracasino.com/terms-and-conditions/",
    ),

    "licasinotransportation.com": (
        "0",
        "Casino transportation service; no direct gambling.",
        "https://licasinotransportation.com/",
    ),

    "bookmaker-ratings.kz": (
        "0",
        "Bookmaker review and information website.",
        "https://bookmaker-ratings.kz/ru/questions/rb/",
    ),

    "kansascity.com": (
        "0",
        "News publisher, not a gambling operator.",
        "https://www.kansascity.com/",
    ),

    "lonestarnationalbank.com": (
        "0",
        "Banking and financial services.",
        "https://www.lonestarnationalbank.com/banking/",
    ),

    "tinkerfcu.org": (
        "0",
        "Credit union and online banking.",
        "https://www.tinkerfcu.org/",
    ),

    "4nflpicks.com": (
        "exclude",
        "Parked or coming-soon domain. "
        "Current site function is unverified.",
        "https://www.4nflpicks.com/",
    ),

    "casino-wise.com": (
        "review",
        "Historical evidence suggests casino-review "
        "or affiliate content; verify current function.",
        "https://kontactr.com/website/site/casino-wise.com",
    ),
}


PRIORITY_DOMAINS = {
    "srp-malerbetrieb.ch",
    "lasvegasfestivalgrounds.com",
    "gamacasino20.com",
    "poolelizabeth.xyz",
    "4nflpicks.com",
    "casino-wise.com",
    "bookmaker-ratings.kz",
    "licasinotransportation.com",
    "emberfieldsolutions.mom",
    "eoskqt15.top",
    "ethereum-cormax.co",
    "dinamica-fortuna.pro",
    "cheap.toyan-jp.shop",
}


def get_priority(row):

    domain = row["domain"].strip().lower()
    category = row["category"].strip().lower()
    label = row["suggested_label"].strip()

    if domain in PRIORITY_DOMAINS:
        return "HIGH"

    if domain in RESEARCH:
        return "REVIEWED_PROPOSAL"

    if label == "0" and category == "jobsearch":
        return "HIGH"

    if label == "0" and category in (
        "games", "sports"
    ):
        return "MEDIUM"

    if label == "1" and (
        "hagezi_medium" == row["source"].strip()
    ):
        return "MEDIUM"

    return "NORMAL"


def main():

    if not INPUT.exists():
        raise FileNotFoundError(
            f"Missing audit file: {INPUT}"
        )

    with INPUT.open(
        "r",
        encoding="utf-8-sig",
        newline=""
    ) as handle:

        reader = csv.DictReader(handle)

        original_fields = list(reader.fieldnames or [])
        rows = list(reader)

    required = {
        "domain",
        "suggested_label",
        "category",
        "source",
        "review_status",
        "verified_label",
    }

    if not required.issubset(original_fields):
        raise RuntimeError(
            "Missing expected audit columns."
        )

    if len(rows) != 200:
        raise RuntimeError(
            f"Expected 200 audit rows; found {len(rows)}."
        )

    extra_fields = [
        "audit_priority",
        "provisional_label",
        "provisional_reason",
        "research_evidence_url",
    ]

    fieldnames = original_fields + [
        name
        for name in extra_fields
        if name not in original_fields
    ]

    for row in rows:

        domain = row["domain"].strip().lower()

        row["audit_priority"] = get_priority(row)

        row["provisional_label"] = ""
        row["provisional_reason"] = ""
        row["research_evidence_url"] = ""

        if domain in RESEARCH:

            proposal, reason, url = RESEARCH[domain]

            row["provisional_label"] = proposal
            row["provisional_reason"] = reason
            row["research_evidence_url"] = url

        # Preserve independent verification fields.
        # No record is auto-confirmed or auto-corrected.
        # Leave review_status and verified_label untouched.

    ranks = {
        "HIGH": 0,
        "REVIEWED_PROPOSAL": 1,
        "MEDIUM": 2,
        "NORMAL": 3,
    }

    rows.sort(
        key=lambda row: (
            ranks.get(row["audit_priority"], 4),
            row["domain"],
        )
    )

    with OUTPUT.open(
        "w",
        encoding="utf-8",
        newline=""
    ) as handle:

        writer = csv.DictWriter(
            handle,
            fieldnames=fieldnames
        )

        writer.writeheader()
        writer.writerows(rows)

    priorities = Counter(
        row["audit_priority"]
        for row in rows
    )

    print("\nBETGUARD OPTION A AUDIT PREPARED")
    print("================================")

    print("Total domains:", len(rows))

    for name in (
        "HIGH",
        "REVIEWED_PROPOSAL",
        "MEDIUM",
        "NORMAL",
    ):
        print(
            f"{name}: {priorities[name]}"
        )

    print(
        "Preliminary evidence proposals:",
        sum(
            bool(row["provisional_label"])
            for row in rows
        )
    )

    print("\nOutput:")
    print(OUTPUT)

    print(
        "\nNo verified labels, deployment files, "
        "or original datasets were changed."
    )


if __name__ == "__main__":
    main()
