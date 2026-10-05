import json
from pathlib import Path

import joblib
import numpy as np
import pandas as pd

from sklearn.metrics import (
    accuracy_score,
    confusion_matrix,
    f1_score,
    precision_recall_curve,
    precision_score,
    recall_score,
)


# =========================================================
# BETGUARD
# RUNTIME ML THRESHOLD CALIBRATION
# =========================================================
#
# PURPOSE
#
# The development threshold (~0.5121) produced too many
# false positives during real-world testing.
#
# For a network blocker, false positives are expensive.
#
# Therefore we compare increasingly conservative operating
# policies:
#
#     90% precision
#     95% precision
#     97% precision
#     99% precision
#
#
# IMPORTANT:
#
# Threshold selection uses VALIDATION data only.
#
# Test data is displayed only for comparison.
#
# =========================================================


# =========================================================
# CONFIG
# =========================================================

PRECISION_TARGETS = [
    0.90,
    0.95,
    0.97,
    0.99,
]


# =========================================================
# PATHS
# =========================================================

DEPLOYMENT_CONFIG_FILE = Path(
    "models/deployment_candidate.json"
)

VALIDATION_FILE = Path(
    "data/processed/splits/baseline_validation.csv"
)

TEST_FILE = Path(
    "data/processed/splits/baseline_test.csv"
)

OUTPUT_CSV = Path(
    "reports/runtime_threshold_comparison.csv"
)

OUTPUT_JSON = Path(
    "models/runtime_threshold_candidates.json"
)


# =========================================================
# LOAD CONFIG
# =========================================================

def load_config():

    if not DEPLOYMENT_CONFIG_FILE.exists():

        raise FileNotFoundError(
            f"\nMissing:\n"
            f"{DEPLOYMENT_CONFIG_FILE}\n\n"
            "Run select_deployment_model.py first."
        )

    with open(
        DEPLOYMENT_CONFIG_FILE,
        "r",
        encoding="utf-8"
    ) as file:

        return json.load(
            file
        )


# =========================================================
# LOAD SPLIT
# =========================================================

def load_split(
    path,
    name
):

    if not path.exists():

        raise FileNotFoundError(
            f"\nMissing {name} split:\n"
            f"{path}"
        )

    df = pd.read_csv(
        path
    )

    required = [
        "domain",
        "label",
    ]

    missing = [
        column
        for column in required
        if column not in df.columns
    ]

    if missing:

        raise ValueError(
            f"{name} split missing "
            f"columns: {missing}"
        )

    df["label"] = pd.to_numeric(
        df["label"],
        errors="raise"
    ).astype(int)

    return df


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

    return joblib.load(
        model_path
    )


# =========================================================
# GET PROBABILITIES
# =========================================================

def predict_probabilities(
    model,
    model_name,
    df
):

    if model_name == "baseline":

        return (
            model.predict_proba(
                df[
                    "domain"
                ]
            )[:, 1]
        )

    if model_name == "hybrid":

        return (
            model.predict_proba(
                df
            )[:, 1]
        )

    raise ValueError(
        f"Unsupported model: {model_name}"
    )


# =========================================================
# EVALUATE THRESHOLD
# =========================================================

def evaluate_threshold(
    y_true,
    probabilities,
    threshold
):

    predictions = (
        probabilities
        >=
        threshold
    ).astype(int)

    matrix = confusion_matrix(
        y_true,
        predictions,
        labels=[
            0,
            1,
        ]
    )

    tn, fp, fn, tp = (
        matrix.ravel()
    )

    return {
        "threshold":
            float(
                threshold
            ),

        "accuracy":
            float(
                accuracy_score(
                    y_true,
                    predictions
                )
            ),

        "precision":
            float(
                precision_score(
                    y_true,
                    predictions,
                    zero_division=0
                )
            ),

        "recall":
            float(
                recall_score(
                    y_true,
                    predictions,
                    zero_division=0
                )
            ),

        "f1":
            float(
                f1_score(
                    y_true,
                    predictions,
                    zero_division=0
                )
            ),

        "true_negatives":
            int(
                tn
            ),

        "false_positives":
            int(
                fp
            ),

        "false_negatives":
            int(
                fn
            ),

        "true_positives":
            int(
                tp
            ),
    }


# =========================================================
# BUILD THRESHOLD TABLE
# =========================================================

def build_threshold_table(
    y_true,
    probabilities
):

    (
        precision_values,
        recall_values,
        thresholds,

    ) = precision_recall_curve(
        y_true,
        probabilities
    )

    rows = []

    for index, threshold in enumerate(
        thresholds
    ):

        precision = float(
            precision_values[
                index
            ]
        )

        recall = float(
            recall_values[
                index
            ]
        )

        if (
            precision
            +
            recall
        ) == 0:

            f1 = 0.0

        else:

            f1 = (
                2
                *
                precision
                *
                recall
                /
                (
                    precision
                    +
                    recall
                )
            )

        rows.append(
            {
                "threshold":
                    float(
                        threshold
                    ),

                "precision":
                    precision,

                "recall":
                    recall,

                "f1":
                    float(
                        f1
                    ),
            }
        )

    return pd.DataFrame(
        rows
    )


# =========================================================
# FIND THRESHOLD FOR TARGET PRECISION
# =========================================================

def find_precision_threshold(
    threshold_table,
    target_precision
):

    candidates = threshold_table[
        threshold_table[
            "precision"
        ]
        >=
        target_precision
    ].copy()

    if len(
        candidates
    ) == 0:

        return None

    # Among thresholds satisfying the precision target:
    #
    # 1. highest recall
    # 2. highest F1
    # 3. lowest threshold

    candidates = (
        candidates.sort_values(
            by=[
                "recall",
                "f1",
                "threshold",
            ],
            ascending=[
                False,
                False,
                True,
            ]
        )
    )

    return float(
        candidates.iloc[
            0
        ][
            "threshold"
        ]
    )


# =========================================================
# MAIN
# =========================================================

def main():

    print(
        "\n===================================="
    )

    print(
        " BETGUARD RUNTIME THRESHOLD"
    )

    print(
        "===================================="
    )

    # =====================================================
    # LOAD
    # =====================================================

    config = load_config()

    validation = load_split(
        VALIDATION_FILE,
        "validation"
    )

    test = load_split(
        TEST_FILE,
        "test"
    )

    model = load_model(
        config
    )

    model_name = (
        config[
            "model_name"
        ]
    )

    print(
        "\nModel:"
    )

    print(
        config.get(
            "display_name",
            model_name
        )
    )

    print(
        "\nCurrent deployment candidate threshold:"
    )

    print(
        f"{float(config['threshold']):.4f}"
    )

    # =====================================================
    # PROBABILITIES
    # =====================================================

    validation_probabilities = (
        predict_probabilities(
            model,
            model_name,
            validation
        )
    )

    test_probabilities = (
        predict_probabilities(
            model,
            model_name,
            test
        )
    )

    validation_y = (
        validation[
            "label"
        ].to_numpy()
    )

    test_y = (
        test[
            "label"
        ].to_numpy()
    )

    # =====================================================
    # VALIDATION THRESHOLD SEARCH
    # =====================================================

    threshold_table = (
        build_threshold_table(
            validation_y,
            validation_probabilities
        )
    )

    all_rows = []

    json_candidates = {}

    # =====================================================
    # CURRENT POLICY
    # =====================================================

    current_threshold = float(
        config[
            "threshold"
        ]
    )

    current_validation = (
        evaluate_threshold(
            validation_y,
            validation_probabilities,
            current_threshold
        )
    )

    current_test = (
        evaluate_threshold(
            test_y,
            test_probabilities,
            current_threshold
        )
    )

    all_rows.append(
        {
            "policy":
                "current_precision_90",

            "precision_target":
                0.90,

            "dataset":
                "validation",

            **current_validation,
        }
    )

    all_rows.append(
        {
            "policy":
                "current_precision_90",

            "precision_target":
                0.90,

            "dataset":
                "test",

            **current_test,
        }
    )

    # =====================================================
    # PRECISION TARGETS
    # =====================================================

    for target in (
        PRECISION_TARGETS
    ):

        threshold = (
            find_precision_threshold(
                threshold_table,
                target
            )
        )

        policy_name = (
            f"precision_"
            f"{int(target * 100)}"
        )

        if threshold is None:

            print(
                f"\n{policy_name}:"
            )

            print(
                "No validation threshold found."
            )

            json_candidates[
                policy_name
            ] = None

            continue

        validation_metrics = (
            evaluate_threshold(
                validation_y,
                validation_probabilities,
                threshold
            )
        )

        test_metrics = (
            evaluate_threshold(
                test_y,
                test_probabilities,
                threshold
            )
        )

        all_rows.append(
            {
                "policy":
                    policy_name,

                "precision_target":
                    target,

                "dataset":
                    "validation",

                **validation_metrics,
            }
        )

        all_rows.append(
            {
                "policy":
                    policy_name,

                "precision_target":
                    target,

                "dataset":
                    "test",

                **test_metrics,
            }
        )

        json_candidates[
            policy_name
        ] = {
            "precision_target":
                target,

            "threshold":
                threshold,

            "validation":
                validation_metrics,

            "test":
                test_metrics,
        }

    # =====================================================
    # SAVE
    # =====================================================

    results = pd.DataFrame(
        all_rows
    )

    OUTPUT_CSV.parent.mkdir(
        parents=True,
        exist_ok=True
    )

    results.to_csv(
        OUTPUT_CSV,
        index=False
    )

    OUTPUT_JSON.parent.mkdir(
        parents=True,
        exist_ok=True
    )

    with open(
        OUTPUT_JSON,
        "w",
        encoding="utf-8"
    ) as file:

        json.dump(
            {
                "model_name":
                    model_name,

                "model_file":
                    config[
                        "model_file"
                    ],

                "candidates":
                    json_candidates,
            },
            file,
            indent=4
        )

    # =====================================================
    # DISPLAY
    # =====================================================

    print(
        "\n===================================="
    )

    print(
        " THRESHOLD COMPARISON"
    )

    print(
        "===================================="
    )

    display_columns = [
        "policy",
        "dataset",
        "threshold",
        "precision",
        "recall",
        "f1",
        "false_positives",
        "false_negatives",
    ]

    print(
        results[
            display_columns
        ].to_string(
            index=False
        )
    )

    print(
        "\n===================================="
    )

    print(
        " FILES CREATED"
    )

    print(
        "===================================="
    )

    print(
        "\nComparison:"
    )

    print(
        OUTPUT_CSV
    )

    print(
        "\nThreshold candidates:"
    )

    print(
        OUTPUT_JSON
    )

    print(
        "\nIMPORTANT:"
    )

    print(
        "Do not automatically choose the "
        "highest precision threshold yet."
    )

    print(
        "We need to inspect how much gambling "
        "recall is lost as precision increases."
    )


# =========================================================
# ENTRY POINT
# =========================================================

if __name__ == "__main__":

    main()