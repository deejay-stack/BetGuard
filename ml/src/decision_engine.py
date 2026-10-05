import argparse
import json
from pathlib import Path
from urllib.parse import urlparse

import joblib
import pandas as pd
import tldextract

if __package__:
    from .runtime_paths import resource_path
else:
    from runtime_paths import resource_path


# =========================================================
# BETGUARD
# RUNTIME DOMAIN DECISION ENGINE V3
# =========================================================
#
# ENFORCEMENT:
#
#     ALLOW
#     BLOCK
#
# INTERVENTION:
#
#     NONE
#     WARN
#     BLOCK
#
#
# POLICY
#
# User allowlist
#       ↓
# User blocklist
#       ↓
# Verified gambling blocklist
#       ↓
# ML
#
# score >= 0.70
#       → BLOCK
#
# score >= 0.512117
#       → ALLOW + WARN
#
# score < 0.512117
#       → ALLOW
#
# =========================================================


# =========================================================
# THRESHOLDS
# =========================================================

WARNING_THRESHOLD = 0.512117

AUTO_BLOCK_THRESHOLD = 0.70


# =========================================================
# FILES
# =========================================================

DEPLOYMENT_CONFIG_FILE = resource_path(
    "models/deployment_candidate.json"
)

RUNTIME_BLOCKLIST_FILE = resource_path(
    "data/runtime/gambling_blocklist.csv"
)

USER_ALLOWLIST_FILE = resource_path(
    "data/runtime/user_allowlist.txt"
)

USER_BLOCKLIST_FILE = resource_path(
    "data/runtime/user_blocklist.txt"
)


# =========================================================
# TLD
# =========================================================

TLD_EXTRACTOR = tldextract.TLDExtract(
    suffix_list_urls=(), cache_dir=None
)


# =========================================================
# NORMALIZE
# =========================================================

def normalize_domain(value):

    if value is None:
        return ""

    value = str(
        value
    ).strip().lower()

    if not value:
        return ""

    if (
        value.startswith("http://")
        or
        value.startswith("https://")
    ):

        parsed = urlparse(
            value
        )

        domain = (
            parsed.hostname
            or ""
        )

    else:

        if "/" in value:

            parsed = urlparse(
                "//" + value
            )

            domain = (
                parsed.hostname
                or
                value.split("/")[0]
            )

        else:

            domain = value


    domain = domain.strip().lower()


    if domain.startswith(
        "www."
    ):

        domain = domain[4:]


    domain = domain.rstrip(
        "."
    )


    if domain.count(":") == 1:

        hostname, possible_port = (
            domain.rsplit(
                ":",
                1
            )
        )

        if possible_port.isdigit():
            domain = hostname


    return domain


# =========================================================
# DOMAIN FAMILY
# =========================================================

def get_domain_family(domain):

    domain = normalize_domain(
        domain
    )

    extracted = TLD_EXTRACTOR(
        domain
    )

    registered = (
        extracted.top_domain_under_public_suffix
    )

    if registered:
        return registered

    return domain


# =========================================================
# DOMAIN MATCH CANDIDATES
# =========================================================

def generate_domain_candidates(
    domain
):

    domain = normalize_domain(
        domain
    )

    if not domain:
        return []


    registered = get_domain_family(
        domain
    )


    candidates = []

    current = domain


    while True:

        candidates.append(
            current
        )

        if current == registered:
            break

        parts = current.split(
            "."
        )

        if len(parts) <= 2:
            break

        current = ".".join(
            parts[1:]
        )


    return candidates


# =========================================================
# TEXT LIST
# =========================================================

def load_text_list(path):

    if not path.exists():

        path.parent.mkdir(
            parents=True,
            exist_ok=True
        )

        path.write_text(
            "",
            encoding="utf-8"
        )

        return set()


    domains = set()


    for line in path.read_text(
        encoding="utf-8"
    ).splitlines():

        line = line.strip()

        if not line:
            continue

        if line.startswith("#"):
            continue


        domain = normalize_domain(
            line
        )


        if domain:

            domains.add(
                domain
            )


    return domains


# =========================================================
# GAMBLING BLOCKLIST
# =========================================================

def load_gambling_blocklist():

    if not RUNTIME_BLOCKLIST_FILE.exists():

        raise FileNotFoundError(
            "\nRuntime gambling blocklist "
            "does not exist.\n\n"
            "Run:\n"
            "python src\\update_runtime_blocklist.py"
        )


    df = pd.read_csv(
        RUNTIME_BLOCKLIST_FILE
    )


    lookup = {}


    for _, row in df.iterrows():

        domain = normalize_domain(
            row[
                "domain"
            ]
        )


        lookup[
            domain
        ] = str(
            row.get(
                "sources",
                ""
            )
        )


    return lookup


# =========================================================
# FIND LIST MATCH
# =========================================================

def find_list_match(
    domain,
    lookup
):

    for candidate in generate_domain_candidates(
        domain
    ):

        if candidate in lookup:

            return candidate


    return None


# =========================================================
# MODEL
# =========================================================

def load_model():

    if not DEPLOYMENT_CONFIG_FILE.exists():

        raise FileNotFoundError(
            f"\nMissing:\n"
            f"{DEPLOYMENT_CONFIG_FILE}"
        )


    with open(
        DEPLOYMENT_CONFIG_FILE,
        "r",
        encoding="utf-8"
    ) as file:

        config = json.load(
            file
        )


    model_path = resource_path(
        config[
            "model_file"
        ]
    )


    if not model_path.exists():

        raise FileNotFoundError(
            f"\nModel not found:\n"
            f"{model_path}"
        )


    if (
        config[
            "model_name"
        ]
        ==
        "hybrid"
    ):

        from domain_features import (
            DomainLexicalTransformer,
        )

        _ = DomainLexicalTransformer


    model = joblib.load(
        model_path
    )


    return (
        model,
        config
    )


# =========================================================
# ML SCORE
# =========================================================

def predict_ml_score(
    domain,
    model,
    config
):

    model_name = config[
        "model_name"
    ]


    if model_name == "baseline":

        return float(

            model.predict_proba(
                [
                    domain
                ]
            )[0][1]
        )


    if model_name == "hybrid":

        input_df = pd.DataFrame(
            {
                "domain": [
                    domain
                ]
            }
        )


        return float(

            model.predict_proba(
                input_df
            )[0][1]
        )


    raise ValueError(
        "Unsupported model: "
        f"{model_name}"
    )


# =========================================================
# DECISION
# =========================================================

def decide_domain(
    raw_input,
    model,
    config,
    gambling_lookup,
    allowlist,
    user_blocklist
):

    domain = normalize_domain(
        raw_input
    )


    if not domain:

        return {
            "input":
                raw_input,

            "error":
                "Invalid domain",
        }


    # =====================================================
    # 1. USER ALLOWLIST
    # =====================================================

    match = find_list_match(
        domain,
        allowlist
    )


    if match:

        return {
            "input":
                raw_input,

            "domain":
                domain,

            "enforcement_action":
                "ALLOW",

            "intervention":
                "NONE",

            "risk_status":
                "trusted",

            "decision_source":
                "user_allowlist",

            "matched_domain":
                match,

            "ml_score":
                None,
        }


    # =====================================================
    # 2. USER BLOCKLIST
    # =====================================================

    match = find_list_match(
        domain,
        user_blocklist
    )


    if match:

        return {
            "input":
                raw_input,

            "domain":
                domain,

            "enforcement_action":
                "BLOCK",

            "intervention":
                "BLOCK",

            "risk_status":
                "user_blocked",

            "decision_source":
                "user_blocklist",

            "matched_domain":
                match,

            "ml_score":
                None,
        }


    # =====================================================
    # 3. VERIFIED GAMBLING BLOCKLIST
    # =====================================================

    match = find_list_match(
        domain,
        gambling_lookup
    )


    if match:

        return {
            "input":
                raw_input,

            "domain":
                domain,

            "enforcement_action":
                "BLOCK",

            "intervention":
                "BLOCK",

            "risk_status":
                "verified_gambling",

            "decision_source":
                "verified_gambling_blocklist",

            "matched_domain":
                match,

            "matched_sources":
                gambling_lookup[
                    match
                ],

            "ml_score":
                None,
        }


    # =====================================================
    # 4. ML FALLBACK
    # =====================================================

    score = predict_ml_score(
        domain,
        model,
        config
    )


    # =====================================================
    # ML HIGH RISK
    # =====================================================

    if score >= AUTO_BLOCK_THRESHOLD:

        return {
            "input":
                raw_input,

            "domain":
                domain,

            "enforcement_action":
                "BLOCK",

            "intervention":
                "BLOCK",

            "risk_status":
                "high",

            "decision_source":
                "ml_high_risk",

            "ml_score":
                round(
                    score,
                    6
                ),

            "warning_threshold":
                WARNING_THRESHOLD,

            "auto_block_threshold":
                AUTO_BLOCK_THRESHOLD,
        }


    # =====================================================
    # ML WARNING
    # =====================================================

    if score >= WARNING_THRESHOLD:

        return {
            "input":
                raw_input,

            "domain":
                domain,

            # Network remains permitted.
            "enforcement_action":
                "ALLOW",

            # UI should intervene.
            "intervention":
                "WARN",

            "risk_status":
                "suspicious",

            "decision_source":
                "ml_warning",

            "ml_score":
                round(
                    score,
                    6
                ),

            "warning_threshold":
                WARNING_THRESHOLD,

            "auto_block_threshold":
                AUTO_BLOCK_THRESHOLD,

            "needs_user_confirmation":
                True,
        }


    # =====================================================
    # LOW RISK
    # =====================================================

    return {
        "input":
            raw_input,

        "domain":
            domain,

        "enforcement_action":
            "ALLOW",

        "intervention":
            "NONE",

        "risk_status":
            "low",

        "decision_source":
            "ml_low_risk",

        "ml_score":
            round(
                score,
                6
            ),

        "warning_threshold":
            WARNING_THRESHOLD,

        "auto_block_threshold":
            AUTO_BLOCK_THRESHOLD,

        "needs_user_confirmation":
            False,
    }


# =========================================================
# DISPLAY
# =========================================================

def display_result(result):

    print(
        "\n===================================="
    )


    if "error" in result:

        print(
            " ERROR"
        )

        print(
            "===================================="
        )

        print(
            result[
                "error"
            ]
        )

        return


    print(
        f" {result['domain']}"
    )

    print(
        "===================================="
    )


    print(
        "\nEnforcement:"
    )

    print(
        result[
            "enforcement_action"
        ]
    )


    print(
        "\nIntervention:"
    )

    print(
        result[
            "intervention"
        ]
    )


    print(
        "\nRisk status:"
    )

    print(
        result[
            "risk_status"
        ]
    )


    print(
        "\nDecision source:"
    )

    print(
        result[
            "decision_source"
        ]
    )


    if result.get(
        "matched_domain"
    ):

        print(
            "\nMatched domain:"
        )

        print(
            result[
                "matched_domain"
            ]
        )


    if result.get(
        "matched_sources"
    ):

        print(
            "\nBlocklist source:"
        )

        print(
            result[
                "matched_sources"
            ]
        )


    if result.get(
        "ml_score"
    ) is not None:

        print(
            "\nML score:"
        )

        print(
            f"{result['ml_score']:.4f}"
        )


    if result.get(
        "needs_user_confirmation"
    ):

        print(
            "\nUser experience:"
        )

        print(
            "Show gambling-risk warning "
            "before continuing."
        )


# =========================================================
# CLI
# =========================================================

def main():

    parser = argparse.ArgumentParser(
        description=(
            "BetGuard runtime domain "
            "decision engine"
        )
    )


    parser.add_argument(
        "domains",
        nargs="+",
        help=(
            "Domains or URLs to evaluate"
        )
    )


    parser.add_argument(
        "--json",
        action="store_true",
        help="Return JSON output"
    )


    args = parser.parse_args()


    gambling_lookup = (
        load_gambling_blocklist()
    )


    allowlist = load_text_list(
        USER_ALLOWLIST_FILE
    )


    user_blocklist = load_text_list(
        USER_BLOCKLIST_FILE
    )


    model, config = load_model()


    results = []


    for domain in args.domains:

        results.append(
            decide_domain(
                domain,
                model,
                config,
                gambling_lookup,
                allowlist,
                user_blocklist
            )
        )


    if args.json:

        print(
            json.dumps(
                results,
                indent=4
            )
        )

        return


    print(
        "\n===================================="
    )

    print(
        " BETGUARD DECISION ENGINE V3"
    )

    print(
        "===================================="
    )


    print(
        "\nVerified gambling domains:"
    )

    print(
        f"{len(gambling_lookup):,}"
    )


    print(
        "\nWarning threshold:"
    )

    print(
        WARNING_THRESHOLD
    )


    print(
        "\nAutomatic blocking threshold:"
    )

    print(
        AUTO_BLOCK_THRESHOLD
    )


    for result in results:

        display_result(
            result
        )


if __name__ == "__main__":

    main()
