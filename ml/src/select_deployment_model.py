import json
from pathlib import Path

import joblib
import numpy as np
import pandas as pd

from sklearn.metrics import (
    accuracy_score,
    average_precision_score,
    confusion_matrix,
    f1_score,
    precision_recall_curve,
    precision_score,
    recall_score,
    roc_auc_score,
)

# Required so joblib can load the hybrid model correctly.
from domain_features import DomainLexicalTransformer


# =========================================================
# BETGUARD
# DEPLOYMENT MODEL COMPARISON
# =========================================================
#
# PURPOSE
#
# Compare:
#
# 1. Character TF-IDF baseline
# 2. Character TF-IDF + lexical hybrid
#
# using the SAME validation and test datasets.
#
#
# DEPLOYMENT OBJECTIVE
#
# For a blocking application, false positives are costly.
#
# Therefore:
#
#     Primary target:
#         precision >= 90%
#
#     Then maximize:
#         recall
#
#     Then:
#         F1
#
#
# IMPORTANT
#
# Thresholds are selected ONLY on validation data.
#
# The selected thresholds are then evaluated on test data.
#
# =========================================================


# =========================================================
# CONFIGURATION
# =========================================================

TARGET_PRECISION = 0.90

FIXED_THRESHOLDS = [
    0.40,
    0.50,
    0.60,
    0.70,
    0.80,
]


# =========================================================
# INPUT FILES
# =========================================================

VALIDATION_FILE = Path(
    "data/processed/splits/baseline_validation.csv"
)

TEST_FILE = Path(
    "data/processed/splits/baseline_test.csv"
)


BASELINE_MODEL_FILE = Path(
    "models/baseline_domain_classifier.joblib"
)

HYBRID_MODEL_FILE = Path(
    "models/hybrid_evaluation_model.joblib"
)


# =========================================================
# OUTPUT FILES
# =========================================================

VALIDATION_RESULTS_FILE = Path(
    "reports/model_validation_operating_points.csv"
)

TEST_RESULTS_FILE = Path(
    "reports/model_test_operating_points.csv"
)

THRESHOLD_CURVES_FILE = Path(
    "reports/model_threshold_comparison.csv"
)

DEPLOYMENT_CANDIDATE_FILE = Path(
    "models/deployment_candidate.json"
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
            f"\nMissing {name} dataset:\n"
            f"{path}"
        )


    df = pd.read_csv(
        path
    )


    required_columns = [
        "domain",
        "label",
    ]


    missing = [
        column
        for column in required_columns
        if column not in df.columns
    ]


    if missing:

        raise ValueError(
            f"{name} dataset missing "
            f"columns: {missing}"
        )


    df[
        "label"
    ] = pd.to_numeric(
        df[
            "label"
        ],
        errors="raise"
    ).astype(int)


    return df


# =========================================================
# LOAD MODELS
# =========================================================

def load_models():

    if not BASELINE_MODEL_FILE.exists():

        raise FileNotFoundError(
            f"\nBaseline model not found:\n"
            f"{BASELINE_MODEL_FILE}"
        )


    if not HYBRID_MODEL_FILE.exists():

        raise FileNotFoundError(
            f"\nHybrid model not found:\n"
            f"{HYBRID_MODEL_FILE}"
        )


    print(
        "\nLoading baseline model..."
    )


    baseline = joblib.load(
        BASELINE_MODEL_FILE
    )


    print(
        "Loading hybrid model..."
    )


    hybrid = joblib.load(
        HYBRID_MODEL_FILE
    )


    return {
        "baseline": {
            "display_name":
                "TF-IDF Baseline",

            "model":
                baseline,

            "model_file":
                str(
                    BASELINE_MODEL_FILE
                ),
        },

        "hybrid": {
            "display_name":
                "TF-IDF + Lexical Hybrid",

            "model":
                hybrid,

            "model_file":
                str(
                    HYBRID_MODEL_FILE
                ),
        },
    }


# =========================================================
# PREDICT PROBABILITY
# =========================================================

def predict_probabilities(
    model_name,
    model,
    df
):

    # -----------------------------------------------------
    # Baseline expects domain strings.
    # -----------------------------------------------------

    if model_name == "baseline":

        probabilities = (
            model.predict_proba(
                df[
                    "domain"
                ]
            )[:, 1]
        )


    # -----------------------------------------------------
    # Hybrid expects the dataframe because its
    # ColumnTransformer selects "domain".
    # -----------------------------------------------------

    elif model_name == "hybrid":

        probabilities = (
            model.predict_proba(
                df
            )[:, 1]
        )


    else:

        raise ValueError(
            f"Unknown model: {model_name}"
        )


    return probabilities


# =========================================================
# CALCULATE METRICS
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


    accuracy = accuracy_score(
        y_true,
        predictions
    )


    precision = precision_score(
        y_true,
        predictions,
        zero_division=0
    )


    recall = recall_score(
        y_true,
        predictions,
        zero_division=0
    )


    f1 = f1_score(
        y_true,
        predictions,
        zero_division=0
    )


    specificity = (
        tn
        /
        (
            tn
            +
            fp
        )
        if (
            tn
            +
            fp
        ) > 0
        else 0
    )


    false_positive_rate = (
        fp
        /
        (
            fp
            +
            tn
        )
        if (
            fp
            +
            tn
        ) > 0
        else 0
    )


    false_negative_rate = (
        fn
        /
        (
            fn
            +
            tp
        )
        if (
            fn
            +
            tp
        ) > 0
        else 0
    )


    return {

        "threshold":
            float(
                threshold
            ),

        "accuracy":
            float(
                accuracy
            ),

        "precision":
            float(
                precision
            ),

        "recall":
            float(
                recall
            ),

        "f1":
            float(
                f1
            ),

        "specificity":
            float(
                specificity
            ),

        "false_positive_rate":
            float(
                false_positive_rate
            ),

        "false_negative_rate":
            float(
                false_negative_rate
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
# CREATE THRESHOLD SEARCH
# =========================================================

def create_threshold_search(
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


        metrics = evaluate_threshold(
            y_true,
            probabilities,
            threshold
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

                "false_positives":
                    metrics[
                        "false_positives"
                    ],

                "false_negatives":
                    metrics[
                        "false_negatives"
                    ],
            }
        )


    return pd.DataFrame(
        rows
    )


# =========================================================
# FIND F1 THRESHOLD
# =========================================================

def find_f1_threshold(
    threshold_df
):

    ordered = (
        threshold_df.sort_values(
            by=[
                "f1",
                "precision",
                "recall",
            ],
            ascending=[
                False,
                False,
                False,
            ]
        )
    )


    return float(
        ordered.iloc[
            0
        ][
            "threshold"
        ]
    )


# =========================================================
# FIND PRECISION TARGET THRESHOLD
# =========================================================

def find_precision_threshold(
    threshold_df,
    target_precision
):

    candidates = threshold_df[
        threshold_df[
            "precision"
        ]
        >=
        target_precision
    ].copy()


    if len(
        candidates
    ) == 0:

        return None


    # -----------------------------------------------------
    # Among thresholds satisfying our precision target:
    #
    # 1. maximize recall
    # 2. maximize F1
    # 3. minimize false positives
    # -----------------------------------------------------

    candidates = (
        candidates.sort_values(
            by=[
                "recall",
                "f1",
                "false_positives",
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
# ADD GLOBAL RANKING METRICS
# =========================================================

def calculate_ranking_metrics(
    y_true,
    probabilities
):

    return {

        "roc_auc":
            float(
                roc_auc_score(
                    y_true,
                    probabilities
                )
            ),

        "average_precision":
            float(
                average_precision_score(
                    y_true,
                    probabilities
                )
            ),
    }


# =========================================================
# EVALUATE MODEL OPERATING POINTS
# =========================================================

def evaluate_model(
    model_name,
    model_info,
    validation,
    test
):

    model = model_info[
        "model"
    ]


    # =====================================================
    # VALIDATION PROBABILITIES
    # =====================================================

    validation_probabilities = (
        predict_probabilities(
            model_name,
            model,
            validation
        )
    )


    validation_y = (
        validation[
            "label"
        ].to_numpy()
    )


    validation_ranking = (
        calculate_ranking_metrics(
            validation_y,
            validation_probabilities
        )
    )


    threshold_search = (
        create_threshold_search(
            validation_y,
            validation_probabilities
        )
    )


    # =====================================================
    # SELECT THRESHOLDS
    # =====================================================

    f1_threshold = (
        find_f1_threshold(
            threshold_search
        )
    )


    precision_threshold = (
        find_precision_threshold(
            threshold_search,
            TARGET_PRECISION
        )
    )


    # =====================================================
    # TEST PROBABILITIES
    # =====================================================

    test_probabilities = (
        predict_probabilities(
            model_name,
            model,
            test
        )
    )


    test_y = (
        test[
            "label"
        ].to_numpy()
    )


    test_ranking = (
        calculate_ranking_metrics(
            test_y,
            test_probabilities
        )
    )


    # =====================================================
    # VALIDATION OPERATING POINTS
    # =====================================================

    validation_rows = []


    f1_validation_metrics = (
        evaluate_threshold(
            validation_y,
            validation_probabilities,
            f1_threshold
        )
    )


    validation_rows.append(
        {
            "model":
                model_name,

            "display_name":
                model_info[
                    "display_name"
                ],

            "operating_policy":
                "best_validation_f1",

            **f1_validation_metrics,

            **validation_ranking,
        }
    )


    if precision_threshold is not None:

        precision_validation_metrics = (
            evaluate_threshold(
                validation_y,
                validation_probabilities,
                precision_threshold
            )
        )


        validation_rows.append(
            {
                "model":
                    model_name,

                "display_name":
                    model_info[
                        "display_name"
                    ],

                "operating_policy":
                    (
                        f"precision_"
                        f"{int(TARGET_PRECISION * 100)}"
                    ),

                **precision_validation_metrics,

                **validation_ranking,
            }
        )


    # =====================================================
    # TEST OPERATING POINTS
    # =====================================================

    test_rows = []


    f1_test_metrics = evaluate_threshold(
        test_y,
        test_probabilities,
        f1_threshold
    )


    test_rows.append(
        {
            "model":
                model_name,

            "display_name":
                model_info[
                    "display_name"
                ],

            "operating_policy":
                "best_validation_f1",

            **f1_test_metrics,

            **test_ranking,
        }
    )


    if precision_threshold is not None:

        precision_test_metrics = (
            evaluate_threshold(
                test_y,
                test_probabilities,
                precision_threshold
            )
        )


        test_rows.append(
            {
                "model":
                    model_name,

                "display_name":
                    model_info[
                        "display_name"
                    ],

                "operating_policy":
                    (
                        f"precision_"
                        f"{int(TARGET_PRECISION * 100)}"
                    ),

                **precision_test_metrics,

                **test_ranking,
            }
        )


    # =====================================================
    # FIXED THRESHOLDS
    # =====================================================

    for threshold in (
        FIXED_THRESHOLDS
    ):

        metrics = evaluate_threshold(
            test_y,
            test_probabilities,
            threshold
        )


        test_rows.append(
            {
                "model":
                    model_name,

                "display_name":
                    model_info[
                        "display_name"
                    ],

                "operating_policy":
                    f"fixed_{threshold:.2f}",

                **metrics,

                **test_ranking,
            }
        )


    threshold_search[
        "model"
    ] = model_name


    return (
        validation_rows,
        test_rows,
        threshold_search,
        f1_threshold,
        precision_threshold,
    )


# =========================================================
# SELECT DEPLOYMENT CANDIDATE
# =========================================================

def select_candidate(
    validation_results
):

    target_policy = (
        f"precision_"
        f"{int(TARGET_PRECISION * 100)}"
    )


    candidates = validation_results[
        validation_results[
            "operating_policy"
        ]
        ==
        target_policy
    ].copy()


    # -----------------------------------------------------
    # If no model meets target precision,
    # fall back to F1-optimized candidates.
    # -----------------------------------------------------

    if len(
        candidates
    ) == 0:

        print(
            "\nWARNING:"
        )

        print(
            "No model satisfied target precision."
        )

        print(
            "Falling back to F1 selection."
        )


        candidates = validation_results[
            validation_results[
                "operating_policy"
            ]
            ==
            "best_validation_f1"
        ].copy()


        objective = (
            "best validation F1"
        )


    else:

        objective = (
            f"precision >= "
            f"{TARGET_PRECISION:.0%}, "
            f"then maximum recall"
        )


    # -----------------------------------------------------
    # Rank candidates
    # -----------------------------------------------------

    candidates = (
        candidates.sort_values(
            by=[
                "recall",
                "f1",
                "precision",
                "average_precision",
            ],
            ascending=[
                False,
                False,
                False,
                False,
            ]
        )
    )


    winner = (
        candidates.iloc[
            0
        ]
    )


    return (
        winner,
        objective
    )


# =========================================================
# PRINT TABLE
# =========================================================

def print_results_table(
    title,
    df
):

    print(
        "\n===================================="
    )

    print(
        f" {title}"
    )

    print(
        "===================================="
    )


    columns = [
        "display_name",
        "operating_policy",
        "threshold",
        "accuracy",
        "precision",
        "recall",
        "f1",
        "roc_auc",
        "average_precision",
        "false_positives",
        "false_negatives",
    ]


    print(
        df[
            columns
        ].to_string(
            index=False
        )
    )


# =========================================================
# MAIN
# =========================================================

def main():

    print(
        "\n===================================="
    )

    print(
        " BETGUARD DEPLOYMENT MODEL SELECTION"
    )

    print(
        "===================================="
    )


    # =====================================================
    # LOAD DATA
    # =====================================================

    validation = load_split(
        VALIDATION_FILE,
        "validation"
    )


    test = load_split(
        TEST_FILE,
        "test"
    )


    print(
        "\nValidation samples:",
        len(validation)
    )


    print(
        "Test samples:",
        len(test)
    )


    # =====================================================
    # LOAD MODELS
    # =====================================================

    models = load_models()


    # =====================================================
    # EVALUATE
    # =====================================================

    all_validation_rows = []

    all_test_rows = []

    all_threshold_rows = []


    selected_thresholds = {}


    for (
        model_name,
        model_info
    ) in models.items():

        print(
            "\nEvaluating:"
        )

        print(
            model_info[
                "display_name"
            ]
        )


        (
            validation_rows,
            test_rows,
            threshold_rows,
            f1_threshold,
            precision_threshold,

        ) = evaluate_model(
            model_name,
            model_info,
            validation,
            test
        )


        all_validation_rows.extend(
            validation_rows
        )


        all_test_rows.extend(
            test_rows
        )


        all_threshold_rows.append(
            threshold_rows
        )


        selected_thresholds[
            model_name
        ] = {

            "f1_threshold":
                f1_threshold,

            "precision_threshold":
                precision_threshold,
        }


    # =====================================================
    # DATAFRAMES
    # =====================================================

    validation_results = pd.DataFrame(
        all_validation_rows
    )


    test_results = pd.DataFrame(
        all_test_rows
    )


    threshold_results = pd.concat(
        all_threshold_rows,
        ignore_index=True
    )


    # =====================================================
    # SAVE RESULTS
    # =====================================================

    VALIDATION_RESULTS_FILE.parent.mkdir(
        parents=True,
        exist_ok=True
    )


    validation_results.to_csv(
        VALIDATION_RESULTS_FILE,
        index=False
    )


    test_results.to_csv(
        TEST_RESULTS_FILE,
        index=False
    )


    threshold_results.to_csv(
        THRESHOLD_CURVES_FILE,
        index=False
    )


    # =====================================================
    # PRINT RESULTS
    # =====================================================

    print_results_table(
        "VALIDATION RESULTS",
        validation_results
    )


    # Only print selected test policies,
    # not every fixed threshold.

    selected_test_results = test_results[
        test_results[
            "operating_policy"
        ].isin(
            [
                "best_validation_f1",
                (
                    f"precision_"
                    f"{int(TARGET_PRECISION * 100)}"
                ),
            ]
        )
    ]


    print_results_table(
        "TEST RESULTS",
        selected_test_results
    )


    # =====================================================
    # SELECT CANDIDATE USING VALIDATION ONLY
    # =====================================================

    (
        winner,
        objective,

    ) = select_candidate(
        validation_results
    )


    winner_model_name = (
        winner[
            "model"
        ]
    )


    winner_policy = (
        winner[
            "operating_policy"
        ]
    )


    winner_threshold = float(
        winner[
            "threshold"
        ]
    )


    model_info = models[
        winner_model_name
    ]


    # =====================================================
    # FIND MATCHING TEST RESULT
    # =====================================================

    matching_test = test_results[
        (
            test_results[
                "model"
            ]
            ==
            winner_model_name
        )
        &
        (
            test_results[
                "operating_policy"
            ]
            ==
            winner_policy
        )
    ]


    if len(
        matching_test
    ) > 0:

        test_row = (
            matching_test.iloc[
                0
            ]
        )

        deployment_test_metrics = {

            "accuracy":
                float(
                    test_row[
                        "accuracy"
                    ]
                ),

            "precision":
                float(
                    test_row[
                        "precision"
                    ]
                ),

            "recall":
                float(
                    test_row[
                        "recall"
                    ]
                ),

            "f1":
                float(
                    test_row[
                        "f1"
                    ]
                ),

            "false_positives":
                int(
                    test_row[
                        "false_positives"
                    ]
                ),

            "false_negatives":
                int(
                    test_row[
                        "false_negatives"
                    ]
                ),
        }

    else:

        deployment_test_metrics = None


    # =====================================================
    # DEPLOYMENT CANDIDATE
    # =====================================================

    candidate_data = {

        "model_name":
            winner_model_name,

        "display_name":
            model_info[
                "display_name"
            ],

        "model_file":
            model_info[
                "model_file"
            ],

        "threshold":
            winner_threshold,

        "operating_policy":
            winner_policy,

        "selection_objective":
            objective,

        "target_precision":
            TARGET_PRECISION,

        "validation_metrics": {

            "accuracy":
                float(
                    winner[
                        "accuracy"
                    ]
                ),

            "precision":
                float(
                    winner[
                        "precision"
                    ]
                ),

            "recall":
                float(
                    winner[
                        "recall"
                    ]
                ),

            "f1":
                float(
                    winner[
                        "f1"
                    ]
                ),

            "roc_auc":
                float(
                    winner[
                        "roc_auc"
                    ]
                ),

            "average_precision":
                float(
                    winner[
                        "average_precision"
                    ]
                ),

            "false_positives":
                int(
                    winner[
                        "false_positives"
                    ]
                ),

            "false_negatives":
                int(
                    winner[
                        "false_negatives"
                    ]
                ),
        },

        "test_metrics":
            deployment_test_metrics,
    }


    DEPLOYMENT_CANDIDATE_FILE.parent.mkdir(
        parents=True,
        exist_ok=True
    )


    with open(
        DEPLOYMENT_CANDIDATE_FILE,
        "w",
        encoding="utf-8"
    ) as file:

        json.dump(
            candidate_data,
            file,
            indent=4
        )


    # =====================================================
    # FINAL DISPLAY
    # =====================================================

    print(
        "\n===================================="
    )

    print(
        " DEPLOYMENT CANDIDATE"
    )

    print(
        "===================================="
    )


    print(
        "\nSelected using:"
    )

    print(
        objective
    )


    print(
        "\nModel:"
    )

    print(
        model_info[
            "display_name"
        ]
    )


    print(
        "\nOperating policy:"
    )

    print(
        winner_policy
    )


    print(
        "\nThreshold:"
    )

    print(
        f"{winner_threshold:.4f}"
    )


    print(
        "\nValidation precision:"
    )

    print(
        f"{winner['precision']:.4f}"
    )


    print(
        "Validation recall:"
    )

    print(
        f"{winner['recall']:.4f}"
    )


    print(
        "Validation F1:"
    )

    print(
        f"{winner['f1']:.4f}"
    )


    if deployment_test_metrics:

        print(
            "\nTest precision:"
        )

        print(
            f"{deployment_test_metrics['precision']:.4f}"
        )


        print(
            "Test recall:"
        )

        print(
            f"{deployment_test_metrics['recall']:.4f}"
        )


        print(
            "Test F1:"
        )

        print(
            f"{deployment_test_metrics['f1']:.4f}"
        )


        print(
            "Test false positives:"
        )

        print(
            deployment_test_metrics[
                "false_positives"
            ]
        )


        print(
            "Test false negatives:"
        )

        print(
            deployment_test_metrics[
                "false_negatives"
            ]
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
        "\nValidation comparison:"
    )

    print(
        VALIDATION_RESULTS_FILE
    )


    print(
        "\nTest comparison:"
    )

    print(
        TEST_RESULTS_FILE
    )


    print(
        "\nThreshold comparison:"
    )

    print(
        THRESHOLD_CURVES_FILE
    )


    print(
        "\nDeployment candidate configuration:"
    )

    print(
        DEPLOYMENT_CANDIDATE_FILE
    )


    print(
        "\nIMPORTANT:"
    )

    print(
        "This is the deployment CANDIDATE, "
        "not yet the final production model."
    )


    print(
        "\nAfter this comparison, the next step "
        "is to build predict.py and test "
        "completely unseen real-world domains."
    )


# =========================================================
# ENTRY POINT
# =========================================================

if __name__ == "__main__":

    main()