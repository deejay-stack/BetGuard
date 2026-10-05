import argparse
import json
from pathlib import Path
from urllib.parse import urlparse

import joblib
import pandas as pd


# =========================================================
# BETGUARD
# DOMAIN PREDICTION
# =========================================================
#
# PURPOSE
#
# Load the deployment candidate selected by:
#
#     select_deployment_model.py
#
# and predict whether a domain is:
#
#     0 = non-gambling
#     1 = gambling
#
#
# IMPORTANT
#
# This is currently the ML-only prediction layer.
#
# Later BetGuard's final blocking engine will use:
#
#     Allowlist
#         ↓
#     Known gambling blocklist
#         ↓
#     Prediction cache
#         ↓
#     ML classifier
#         ↓
#     Block / Allow
#
# =========================================================


# =========================================================
# PATHS
# =========================================================

DEPLOYMENT_CONFIG_FILE = Path(
    "models/deployment_candidate.json"
)

TRAINING_DATASET_FILE = Path(
    "data/processed/balanced_domain_dataset.csv"
)


# =========================================================
# DOMAIN NORMALIZATION
# =========================================================

def normalize_domain(value):

    if value is None:
        return ""

    value = str(
        value
    ).strip().lower()

    if not value:
        return ""

    # -----------------------------------------------------
    # If full URL was provided
    # -----------------------------------------------------

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

        # -------------------------------------------------
        # User may give:
        #
        # example.com/page
        #
        # Add // temporarily so urlparse understands
        # it as a network location.
        # -------------------------------------------------

        if "/" in value:

            parsed = urlparse(
                "//" + value
            )

            domain = (
                parsed.hostname
                or value.split("/")[0]
            )

        else:

            domain = value


    domain = domain.strip().lower()


    # -----------------------------------------------------
    # Remove www
    # -----------------------------------------------------

    if domain.startswith(
        "www."
    ):

        domain = domain[4:]


    # -----------------------------------------------------
    # Remove trailing dot
    # -----------------------------------------------------

    domain = domain.rstrip(
        "."
    )


    # -----------------------------------------------------
    # Remove port if manually supplied
    # -----------------------------------------------------

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
# LOAD DEPLOYMENT CONFIG
# =========================================================

def load_deployment_config():

    if not DEPLOYMENT_CONFIG_FILE.exists():

        raise FileNotFoundError(
            "\nDeployment configuration not found:\n"
            f"{DEPLOYMENT_CONFIG_FILE}\n\n"
            "Run:\n"
            "python src\\select_deployment_model.py"
        )


    with open(
        DEPLOYMENT_CONFIG_FILE,
        "r",
        encoding="utf-8"
    ) as file:

        config = json.load(
            file
        )


    required = [
        "model_name",
        "model_file",
        "threshold",
    ]


    missing = [
        key
        for key in required
        if key not in config
    ]


    if missing:

        raise ValueError(
            "Deployment configuration is "
            f"missing: {missing}"
        )


    return config


# =========================================================
# LOAD MODEL
# =========================================================

def load_model(
    config
):

    model_path = Path(
        config[
            "model_file"
        ]
    )


    if not model_path.exists():

        raise FileNotFoundError(
            "\nSelected model file not found:\n"
            f"{model_path}"
        )


    # -----------------------------------------------------
    # Import custom transformer if hybrid model gets
    # selected in a future experiment.
    #
    # joblib requires the class definition to exist when
    # loading the serialized model.
    # -----------------------------------------------------

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


    return model


# =========================================================
# LOAD TRAINING DOMAINS
# =========================================================

def load_training_domains():

    if not TRAINING_DATASET_FILE.exists():

        return {}


    try:

        df = pd.read_csv(
            TRAINING_DATASET_FILE
        )

    except Exception:

        return {}


    if (
        "domain"
        not in df.columns
    ):

        return {}


    training_domains = {}


    for _, row in df.iterrows():

        domain = normalize_domain(
            row[
                "domain"
            ]
        )


        label = (
            int(
                row[
                    "label"
                ]
            )
            if (
                "label" in df.columns
                and
                pd.notna(
                    row[
                        "label"
                    ]
                )
            )
            else None
        )


        training_domains[
            domain
        ] = label


    return training_domains


# =========================================================
# MODEL PROBABILITY
# =========================================================

def get_probability(
    model_name,
    model,
    domain
):

    # -----------------------------------------------------
    # Baseline
    #
    # Pipeline expects domain strings.
    # -----------------------------------------------------

    if model_name == "baseline":

        probabilities = (
            model.predict_proba(
                [
                    domain
                ]
            )
        )


    # -----------------------------------------------------
    # Hybrid
    #
    # Pipeline uses ColumnTransformer and expects
    # a dataframe containing the "domain" column.
    # -----------------------------------------------------

    elif model_name == "hybrid":

        input_df = pd.DataFrame(
            {
                "domain": [
                    domain
                ]
            }
        )


        probabilities = (
            model.predict_proba(
                input_df
            )
        )


    else:

        raise ValueError(
            "Unsupported deployment model: "
            f"{model_name}"
        )


    gambling_probability = float(
        probabilities[
            0,
            1
        ]
    )


    return gambling_probability


# =========================================================
# MODEL SCORE BAND
# =========================================================
#
# IMPORTANT:
#
# These are score descriptions only.
#
# They are NOT calibrated probabilities of certainty.
#
# =========================================================

def get_score_band(
    probability,
    threshold
):

    distance = abs(
        probability
        -
        threshold
    )


    if distance < 0.05:

        return "borderline"


    if distance < 0.15:

        return "moderate-margin"


    return "strong-margin"


# =========================================================
# PREDICT ONE DOMAIN
# =========================================================

def predict_domain(
    raw_value,
    model,
    config,
    training_domains
):

    domain = normalize_domain(
        raw_value
    )


    if not domain:

        return {
            "input":
                raw_value,

            "error":
                "Invalid or empty domain",
        }


    model_name = (
        config[
            "model_name"
        ]
    )


    threshold = float(
        config[
            "threshold"
        ]
    )


    probability = (
        get_probability(
            model_name,
            model,
            domain
        )
    )


    predicted_label = int(
        probability
        >=
        threshold
    )


    action = (
        "BLOCK"
        if predicted_label == 1
        else "ALLOW"
    )


    classification = (
        "gambling"
        if predicted_label == 1
        else "non-gambling"
    )


    # -----------------------------------------------------
    # Was this domain part of model development?
    # -----------------------------------------------------

    seen_in_training_dataset = (
        domain
        in
        training_domains
    )


    training_label = (
        training_domains.get(
            domain
        )
    )


    distance_from_threshold = abs(
        probability
        -
        threshold
    )


    result = {

        "input":
            raw_value,

        "domain":
            domain,

        "classification":
            classification,

        "predicted_label":
            predicted_label,

        "action":
            action,

        "gambling_probability":
            round(
                probability,
                6
            ),

        "decision_threshold":
            round(
                threshold,
                6
            ),

        "distance_from_threshold":
            round(
                distance_from_threshold,
                6
            ),

        "score_band":
            get_score_band(
                probability,
                threshold
            ),

        "model":
            config.get(
                "display_name",
                model_name
            ),

        "operating_policy":
            config.get(
                "operating_policy"
            ),

        "seen_in_training_dataset":
            seen_in_training_dataset,

        "training_label":
            training_label,
    }


    return result


# =========================================================
# DISPLAY HUMAN-READABLE RESULT
# =========================================================

def display_result(
    result
):

    if "error" in result:

        print(
            "\n===================================="
        )

        print(
            " PREDICTION ERROR"
        )

        print(
            "===================================="
        )

        print(
            "\nInput:",
            result[
                "input"
            ]
        )

        print(
            "Error:",
            result[
                "error"
            ]
        )

        return


    print(
        "\n===================================="
    )

    print(
        f" {result['domain']}"
    )

    print(
        "===================================="
    )


    print(
        "\nClassification:"
    )

    print(
        result[
            "classification"
        ].upper()
    )


    print(
        "\nAction:"
    )

    print(
        result[
            "action"
        ]
    )


    print(
        "\nGambling probability:"
    )

    print(
        f"{result['gambling_probability']:.4f}"
    )


    print(
        "\nDecision threshold:"
    )

    print(
        f"{result['decision_threshold']:.4f}"
    )


    print(
        "\nDistance from threshold:"
    )

    print(
        f"{result['distance_from_threshold']:.4f}"
    )


    print(
        "\nScore band:"
    )

    print(
        result[
            "score_band"
        ]
    )


    print(
        "\nModel:"
    )

    print(
        result[
            "model"
        ]
    )


    print(
        "\nOperating policy:"
    )

    print(
        result[
            "operating_policy"
        ]
    )


    print(
        "\nSeen in training dataset:"
    )

    print(
        (
            "YES"
            if result[
                "seen_in_training_dataset"
            ]
            else "NO"
        )
    )


    if result[
        "seen_in_training_dataset"
    ]:

        label = result[
            "training_label"
        ]


        if label == 1:

            meaning = "gambling"

        elif label == 0:

            meaning = "non-gambling"

        else:

            meaning = "unknown"


        print(
            "\nTraining dataset label:"
        )

        print(
            f"{label} ({meaning})"
        )


    else:

        print(
            "\nThis domain was not found in "
            "balanced_domain_dataset.csv."
        )

        print(
            "That makes it more useful for "
            "real-world model testing."
        )


# =========================================================
# ARGUMENT PARSER
# =========================================================

def create_argument_parser():

    parser = argparse.ArgumentParser(

        description=(
            "BetGuard gambling-domain "
            "prediction tool"
        )
    )


    parser.add_argument(

        "domains",

        nargs="+",

        help=(
            "One or more domains or URLs "
            "to classify."
        ),
    )


    parser.add_argument(

        "--json",

        action="store_true",

        help=(
            "Return predictions as JSON "
            "instead of formatted text."
        ),
    )


    return parser


# =========================================================
# MAIN
# =========================================================

def main():

    parser = create_argument_parser()

    args = parser.parse_args()


    # =====================================================
    # CONFIG
    # =====================================================

    config = load_deployment_config()


    # =====================================================
    # MODEL
    # =====================================================

    model = load_model(
        config
    )


    # =====================================================
    # TRAINING DATASET LOOKUP
    # =====================================================

    training_domains = (
        load_training_domains()
    )


    # =====================================================
    # PREDICTIONS
    # =====================================================

    results = []


    for raw_domain in (
        args.domains
    ):

        result = predict_domain(

            raw_domain,

            model,

            config,

            training_domains,
        )


        results.append(
            result
        )


    # =====================================================
    # JSON MODE
    # =====================================================

    if args.json:

        print(
            json.dumps(
                results,
                indent=4
            )
        )

        return


    # =====================================================
    # HUMAN MODE
    # =====================================================

    print(
        "\n===================================="
    )

    print(
        " BETGUARD DOMAIN PREDICTOR"
    )

    print(
        "===================================="
    )


    print(
        "\nDeployment model:"
    )

    print(
        config.get(
            "display_name",
            config[
                "model_name"
            ]
        )
    )


    print(
        "\nThreshold:"
    )

    print(
        f"{float(config['threshold']):.4f}"
    )


    print(
        "\nDomains requested:"
    )

    print(
        len(
            results
        )
    )


    for result in results:

        display_result(
            result
        )


    print(
        "\n===================================="
    )

    print(
        " NOTE"
    )

    print(
        "===================================="
    )


    print(
        "\nThe displayed probability is the "
        "model's score, not a guarantee that "
        "the domain is actually gambling."
    )


    print(
        "\nDomains near the threshold should "
        "eventually be handled cautiously by "
        "BetGuard's blocklist + ML decision "
        "pipeline."
    )


# =========================================================
# ENTRY POINT
# =========================================================

if __name__ == "__main__":

    main()