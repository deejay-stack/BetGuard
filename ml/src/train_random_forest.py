import json
from pathlib import Path

import joblib
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from sklearn.ensemble import RandomForestClassifier
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics import (
    accuracy_score,
    average_precision_score,
    classification_report,
    confusion_matrix,
    ConfusionMatrixDisplay,
    f1_score,
    precision_recall_curve,
    precision_score,
    recall_score,
    roc_auc_score,
    RocCurveDisplay,
    PrecisionRecallDisplay,
)
from sklearn.pipeline import Pipeline


# =========================================================
# BETGUARD
# RANDOM FOREST DOMAIN CLASSIFIER
# =========================================================
#
# PURPOSE:
#
# Compare Random Forest against the existing:
#
#   1. Logistic Regression
#   2. Linear SVM
#
# using the EXACT SAME saved train / validation / test
# splits.
#
#
# MODEL:
#
#     Domain text
#         ↓
#     Character TF-IDF
#         ↓
#     Random Forest
#
#
# LABELS:
#
#     0 = non-gambling
#     1 = gambling
#
#
# IMPORTANT:
#
# This script DOES NOT create new splits.
#
# =========================================================


RANDOM_STATE = 42


# =========================================================
# PATHS
# =========================================================

TRAIN_SPLIT_FILE = Path(
    "data/processed/splits/baseline_train.csv"
)

VALIDATION_SPLIT_FILE = Path(
    "data/processed/splits/baseline_validation.csv"
)

TEST_SPLIT_FILE = Path(
    "data/processed/splits/baseline_test.csv"
)


MODEL_FILE = Path(
    "models/random_forest_domain_classifier.joblib"
)

THRESHOLD_FILE = Path(
    "models/random_forest_threshold.json"
)

METRICS_FILE = Path(
    "reports/random_forest_metrics.json"
)

VALIDATION_SEARCH_FILE = Path(
    "reports/random_forest_validation_search.csv"
)

CLASSIFICATION_REPORT_FILE = Path(
    "reports/random_forest_classification_report.csv"
)

PREDICTIONS_FILE = Path(
    "reports/random_forest_test_predictions.csv"
)

MISCLASSIFIED_FILE = Path(
    "reports/random_forest_misclassified_domains.csv"
)

CONFUSION_MATRIX_FILE = Path(
    "reports/random_forest_confusion_matrix.png"
)

ROC_CURVE_FILE = Path(
    "reports/random_forest_roc_curve.png"
)

PR_CURVE_FILE = Path(
    "reports/random_forest_precision_recall_curve.png"
)


# =========================================================
# MODEL CONFIGURATIONS
# =========================================================
#
# Small validation-only search.
#
# We deliberately avoid an enormous grid because the
# dataset is relatively small.
#
# =========================================================

RF_CONFIGURATIONS = [
    {
        "n_estimators": 300,
        "max_depth": None,
        "min_samples_leaf": 1,
        "max_features": "sqrt",
        "class_weight": "balanced",
    },
    {
        "n_estimators": 500,
        "max_depth": None,
        "min_samples_leaf": 1,
        "max_features": "sqrt",
        "class_weight": "balanced",
    },
    {
        "n_estimators": 500,
        "max_depth": None,
        "min_samples_leaf": 2,
        "max_features": "sqrt",
        "class_weight": "balanced",
    },
    {
        "n_estimators": 500,
        "max_depth": 20,
        "min_samples_leaf": 1,
        "max_features": "sqrt",
        "class_weight": "balanced",
    },
    {
        "n_estimators": 500,
        "max_depth": 30,
        "min_samples_leaf": 1,
        "max_features": "sqrt",
        "class_weight": "balanced",
    },
    {
        "n_estimators": 500,
        "max_depth": None,
        "min_samples_leaf": 1,
        "max_features": "log2",
        "class_weight": "balanced",
    },
    {
        "n_estimators": 500,
        "max_depth": None,
        "min_samples_leaf": 1,
        "max_features": 0.2,
        "class_weight": "balanced",
    },
    {
        "n_estimators": 500,
        "max_depth": None,
        "min_samples_leaf": 2,
        "max_features": 0.2,
        "class_weight": "balanced",
    },
]


# =========================================================
# NORMALIZE DOMAIN
# =========================================================

def normalize_domain(domain):

    if pd.isna(domain):
        return ""

    domain = str(
        domain
    ).strip().lower()

    if domain.startswith("https://"):
        domain = domain[
            len("https://"):
        ]

    elif domain.startswith("http://"):
        domain = domain[
            len("http://"):
        ]

    domain = domain.split("/")[0]
    domain = domain.split("?")[0]
    domain = domain.split("#")[0]

    if domain.startswith("www."):
        domain = domain[4:]

    domain = domain.rstrip(".")

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
# LOAD SPLIT
# =========================================================

def load_split(path):

    if not path.exists():

        raise FileNotFoundError(
            f"\nSplit file not found:\n"
            f"{path}\n\n"
            "Run train_baseline.py first."
        )

    df = pd.read_csv(
        path
    )

    required_columns = [
        "domain",
        "label",
        "domain_family",
    ]

    missing = [
        column
        for column in required_columns
        if column not in df.columns
    ]

    if missing:

        raise ValueError(
            f"{path} is missing columns: "
            f"{missing}"
        )

    df["domain"] = (
        df["domain"]
        .apply(
            normalize_domain
        )
    )

    df["label"] = pd.to_numeric(
        df["label"],
        errors="raise"
    ).astype(int)

    if (
        ~df["label"].isin(
            [0, 1]
        )
    ).any():

        raise ValueError(
            f"{path} contains invalid labels."
        )

    if (
        df["domain"] == ""
    ).any():

        raise ValueError(
            f"{path} contains empty domains."
        )

    return df


# =========================================================
# LOAD ORIGINAL BASELINE SPLITS
# =========================================================

def load_splits():

    print(
        "\nLoading the existing Logistic Regression splits..."
    )

    train_df = load_split(
        TRAIN_SPLIT_FILE
    )

    validation_df = load_split(
        VALIDATION_SPLIT_FILE
    )

    test_df = load_split(
        TEST_SPLIT_FILE
    )

    return (
        train_df,
        validation_df,
        test_df,
    )


# =========================================================
# LEAKAGE CHECK
# =========================================================

def check_split_leakage(
    train_df,
    validation_df,
    test_df
):

    train_groups = set(
        train_df[
            "domain_family"
        ]
    )

    validation_groups = set(
        validation_df[
            "domain_family"
        ]
    )

    test_groups = set(
        test_df[
            "domain_family"
        ]
    )

    if (
        train_groups & validation_groups
        or
        train_groups & test_groups
        or
        validation_groups & test_groups
    ):

        raise RuntimeError(
            "Domain-family leakage detected."
        )

    print(
        "\nDomain-family leakage check: PASSED"
    )

    print(
        "Train/validation overlap: 0"
    )

    print(
        "Train/test overlap: 0"
    )

    print(
        "Validation/test overlap: 0"
    )


# =========================================================
# PRINT DISTRIBUTION
# =========================================================

def print_split_distribution(
    name,
    df
):

    print(
        f"\n{name}:"
    )

    print(
        f"  Samples: {len(df)}"
    )

    print(
        f"  Domain families: "
        f"{df['domain_family'].nunique()}"
    )

    counts = (
        df[
            "label"
        ]
        .value_counts()
        .sort_index()
    )

    for label, count in counts.items():

        meaning = (
            "non-gambling"
            if label == 0
            else "gambling"
        )

        print(
            f"  {label} ({meaning}): "
            f"{count}"
        )


# =========================================================
# CREATE MODEL
# =========================================================

def create_model(configuration):

    return Pipeline(
        [
            (
                "tfidf",

                TfidfVectorizer(
                    analyzer="char",
                    ngram_range=(
                        3,
                        5
                    ),
                    lowercase=True,
                    min_df=2,
                    sublinear_tf=True,
                    norm="l2",
                ),
            ),

            (
                "classifier",

                RandomForestClassifier(
                    n_estimators=configuration[
                        "n_estimators"
                    ],

                    max_depth=configuration[
                        "max_depth"
                    ],

                    min_samples_leaf=configuration[
                        "min_samples_leaf"
                    ],

                    max_features=configuration[
                        "max_features"
                    ],

                    class_weight=configuration[
                        "class_weight"
                    ],

                    random_state=RANDOM_STATE,

                    n_jobs=-1,
                ),
            ),
        ]
    )


# =========================================================
# FIND BEST VALIDATION THRESHOLD
# =========================================================

def find_best_threshold(
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

    results = []

    best_threshold = 0.5
    best_f1 = -1.0

    for index, threshold in enumerate(
        thresholds
    ):

        precision = precision_values[
            index
        ]

        recall = recall_values[
            index
        ]

        if (
            precision + recall
        ) == 0:

            score = 0.0

        else:

            score = (
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

        results.append(
            {
                "threshold":
                    float(
                        threshold
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
                        score
                    ),
            }
        )

        if score > best_f1:

            best_f1 = score

            best_threshold = float(
                threshold
            )

    return (
        best_threshold,
        best_f1,
        pd.DataFrame(
            results
        ),
    )


# =========================================================
# METRICS
# =========================================================

def calculate_metrics(
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
        predictions
    )

    tn, fp, fn, tp = (
        matrix.ravel()
    )

    metrics = {

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

        "confusion_matrix":
            matrix.tolist(),
    }

    return (
        metrics,
        predictions,
    )


# =========================================================
# VALIDATION SEARCH
# =========================================================

def tune_model(
    train_df,
    validation_df
):

    print(
        "\n===================================="
    )

    print(
        " RANDOM FOREST VALIDATION SEARCH"
    )

    print(
        "===================================="
    )

    y_validation = (
        validation_df[
            "label"
        ].to_numpy()
    )

    results = []

    best_model = None
    best_configuration = None
    best_threshold = None
    best_metrics = None
    best_threshold_table = None

    for index, configuration in enumerate(
        RF_CONFIGURATIONS,
        start=1
    ):

        print(
            f"\nConfiguration "
            f"{index}/"
            f"{len(RF_CONFIGURATIONS)}"
        )

        print(
            configuration
        )

        model = create_model(
            configuration
        )

        model.fit(
            train_df[
                "domain"
            ],
            train_df[
                "label"
            ]
        )

        probabilities = (
            model.predict_proba(
                validation_df[
                    "domain"
                ]
            )[:, 1]
        )

        (
            threshold,
            _,
            threshold_table,

        ) = find_best_threshold(
            y_validation,
            probabilities
        )

        (
            metrics,
            _,

        ) = calculate_metrics(
            y_validation,
            probabilities,
            threshold
        )

        result = {
            "configuration_id":
                index,

            **configuration,

            "threshold":
                float(
                    threshold
                ),

            "accuracy":
                metrics[
                    "accuracy"
                ],

            "precision":
                metrics[
                    "precision"
                ],

            "recall":
                metrics[
                    "recall"
                ],

            "f1":
                metrics[
                    "f1"
                ],

            "roc_auc":
                metrics[
                    "roc_auc"
                ],

            "average_precision":
                metrics[
                    "average_precision"
                ],

            "false_positives":
                metrics[
                    "false_positives"
                ],

            "false_negatives":
                metrics[
                    "false_negatives"
                ],
        }

        results.append(
            result
        )

        print(
            f"  Accuracy:  "
            f"{metrics['accuracy']:.4f}"
        )

        print(
            f"  Precision: "
            f"{metrics['precision']:.4f}"
        )

        print(
            f"  Recall:    "
            f"{metrics['recall']:.4f}"
        )

        print(
            f"  F1:        "
            f"{metrics['f1']:.4f}"
        )

        print(
            f"  ROC-AUC:   "
            f"{metrics['roc_auc']:.4f}"
        )

        print(
            f"  Threshold: "
            f"{threshold:.6f}"
        )

        candidate_key = (
            metrics[
                "f1"
            ],
            metrics[
                "accuracy"
            ],
            metrics[
                "precision"
            ],
        )

        if best_metrics is None:

            choose = True

        else:

            best_key = (
                best_metrics[
                    "f1"
                ],
                best_metrics[
                    "accuracy"
                ],
                best_metrics[
                    "precision"
                ],
            )

            choose = (
                candidate_key
                >
                best_key
            )

        if choose:

            best_model = model

            best_configuration = (
                configuration.copy()
            )

            best_threshold = threshold

            best_metrics = metrics

            best_threshold_table = (
                threshold_table
            )

    validation_results = pd.DataFrame(
        results
    )

    validation_results = (
        validation_results.sort_values(
            [
                "f1",
                "accuracy",
                "precision",
            ],
            ascending=[
                False,
                False,
                False,
            ],
        )
    )

    VALIDATION_SEARCH_FILE.parent.mkdir(
        parents=True,
        exist_ok=True
    )

    validation_results.to_csv(
        VALIDATION_SEARCH_FILE,
        index=False
    )

    print(
        "\n===================================="
    )

    print(
        " SELECTED RANDOM FOREST"
    )

    print(
        "===================================="
    )

    print(
        "\nConfiguration:"
    )

    print(
        best_configuration
    )

    print(
        "\nSelected threshold:"
    )

    print(
        f"{best_threshold:.6f}"
    )

    print(
        "\nValidation accuracy:"
    )

    print(
        f"{best_metrics['accuracy']:.4f}"
    )

    print(
        "\nValidation precision:"
    )

    print(
        f"{best_metrics['precision']:.4f}"
    )

    print(
        "\nValidation recall:"
    )

    print(
        f"{best_metrics['recall']:.4f}"
    )

    print(
        "\nValidation F1:"
    )

    print(
        f"{best_metrics['f1']:.4f}"
    )

    return (
        best_model,
        best_configuration,
        best_threshold,
        best_metrics,
        best_threshold_table,
    )


# =========================================================
# SAVE PLOTS
# =========================================================

def save_confusion_matrix(
    y_true,
    predictions
):

    figure, axis = plt.subplots(
        figsize=(
            6,
            5
        )
    )

    ConfusionMatrixDisplay.from_predictions(
        y_true,
        predictions,
        display_labels=[
            "Non-Gambling",
            "Gambling",
        ],
        ax=axis,
    )

    axis.set_title(
        "BetGuard Random Forest Confusion Matrix"
    )

    figure.tight_layout()

    figure.savefig(
        CONFUSION_MATRIX_FILE,
        dpi=200
    )

    plt.close(
        figure
    )


def save_roc_curve(
    y_true,
    probabilities
):

    figure, axis = plt.subplots(
        figsize=(
            6,
            5
        )
    )

    RocCurveDisplay.from_predictions(
        y_true,
        probabilities,
        ax=axis
    )

    axis.set_title(
        "BetGuard Random Forest ROC Curve"
    )

    figure.tight_layout()

    figure.savefig(
        ROC_CURVE_FILE,
        dpi=200
    )

    plt.close(
        figure
    )


def save_precision_recall_curve(
    y_true,
    probabilities
):

    figure, axis = plt.subplots(
        figsize=(
            6,
            5
        )
    )

    PrecisionRecallDisplay.from_predictions(
        y_true,
        probabilities,
        ax=axis
    )

    axis.set_title(
        "BetGuard Random Forest Precision-Recall Curve"
    )

    figure.tight_layout()

    figure.savefig(
        PR_CURVE_FILE,
        dpi=200
    )

    plt.close(
        figure
    )


# =========================================================
# MAIN
# =========================================================

def main():

    print(
        "\n===================================="
    )

    print(
        " BETGUARD RANDOM FOREST EXPERIMENT"
    )

    print(
        "===================================="
    )

    (
        train_df,
        validation_df,
        test_df,

    ) = load_splits()

    check_split_leakage(
        train_df,
        validation_df,
        test_df
    )

    print_split_distribution(
        "TRAIN",
        train_df
    )

    print_split_distribution(
        "VALIDATION",
        validation_df
    )

    print_split_distribution(
        "TEST",
        test_df
    )

    (
        model,
        selected_configuration,
        selected_threshold,
        validation_metrics,
        threshold_table,

    ) = tune_model(
        train_df,
        validation_df
    )

    # =====================================================
    # FINAL TEST
    # =====================================================

    print(
        "\n===================================="
    )

    print(
        " FINAL RANDOM FOREST TEST"
    )

    print(
        "===================================="
    )

    test_probabilities = (
        model.predict_proba(
            test_df[
                "domain"
            ]
        )[:, 1]
    )

    (
        test_metrics,
        test_predictions,

    ) = calculate_metrics(
        test_df[
            "label"
        ].to_numpy(),
        test_probabilities,
        selected_threshold
    )

    print(
        "\nAccuracy:"
    )

    print(
        f"{test_metrics['accuracy']:.4f}"
    )

    print(
        "\nPrecision (gambling):"
    )

    print(
        f"{test_metrics['precision']:.4f}"
    )

    print(
        "\nRecall (gambling):"
    )

    print(
        f"{test_metrics['recall']:.4f}"
    )

    print(
        "\nF1:"
    )

    print(
        f"{test_metrics['f1']:.4f}"
    )

    print(
        "\nROC-AUC:"
    )

    print(
        f"{test_metrics['roc_auc']:.4f}"
    )

    print(
        "\nAverage Precision / PR-AUC:"
    )

    print(
        f"{test_metrics['average_precision']:.4f}"
    )

    print(
        "\nFalse Positives:"
    )

    print(
        test_metrics[
            "false_positives"
        ]
    )

    print(
        "\nFalse Negatives:"
    )

    print(
        test_metrics[
            "false_negatives"
        ]
    )

    print(
        "\nConfusion Matrix:"
    )

    print(
        np.array(
            test_metrics[
                "confusion_matrix"
            ]
        )
    )

    # =====================================================
    # CLASSIFICATION REPORT
    # =====================================================

    print(
        "\nClassification Report:"
    )

    report_text = classification_report(
        test_df[
            "label"
        ],
        test_predictions,
        target_names=[
            "Non-Gambling",
            "Gambling",
        ],
        digits=4,
        zero_division=0
    )

    print(
        report_text
    )

    report_dict = classification_report(
        test_df[
            "label"
        ],
        test_predictions,
        target_names=[
            "Non-Gambling",
            "Gambling",
        ],
        output_dict=True,
        zero_division=0
    )

    pd.DataFrame(
        report_dict
    ).transpose().to_csv(
        CLASSIFICATION_REPORT_FILE
    )

    # =====================================================
    # PREDICTIONS
    # =====================================================

    prediction_df = (
        test_df.copy()
    )

    prediction_df[
        "gambling_probability"
    ] = test_probabilities

    prediction_df[
        "predicted_label"
    ] = test_predictions

    prediction_df[
        "correct"
    ] = (
        prediction_df[
            "label"
        ]
        ==
        prediction_df[
            "predicted_label"
        ]
    )

    prediction_df.to_csv(
        PREDICTIONS_FILE,
        index=False
    )

    # =====================================================
    # MISCLASSIFICATIONS
    # =====================================================

    misclassified = prediction_df[
        ~prediction_df[
            "correct"
        ]
    ].copy()

    misclassified[
        "distance_from_threshold"
    ] = (
        misclassified[
            "gambling_probability"
        ]
        -
        selected_threshold
    ).abs()

    misclassified = (
        misclassified.sort_values(
            "distance_from_threshold"
        )
    )

    misclassified.to_csv(
        MISCLASSIFIED_FILE,
        index=False
    )

    print(
        "\nMisclassified domains:"
    )

    print(
        len(
            misclassified
        )
    )

    display_columns = [
        column
        for column in [
            "domain",
            "label",
            "predicted_label",
            "gambling_probability",
            "source",
            "category",
        ]
        if column
        in misclassified.columns
    ]

    if len(
        misclassified
    ) > 0:

        print(
            "\nMisclassification examples:"
        )

        print(
            misclassified[
                display_columns
            ]
            .head(20)
            .to_string(
                index=False
            )
        )

    # =====================================================
    # PLOTS
    # =====================================================

    CONFUSION_MATRIX_FILE.parent.mkdir(
        parents=True,
        exist_ok=True
    )

    save_confusion_matrix(
        test_df[
            "label"
        ],
        test_predictions
    )

    save_roc_curve(
        test_df[
            "label"
        ],
        test_probabilities
    )

    save_precision_recall_curve(
        test_df[
            "label"
        ],
        test_probabilities
    )

    # =====================================================
    # SAVE MODEL
    # =====================================================

    MODEL_FILE.parent.mkdir(
        parents=True,
        exist_ok=True
    )

    joblib.dump(
        model,
        MODEL_FILE
    )

    threshold_data = {

        "threshold":
            float(
                selected_threshold
            ),

        "selected_using":
            "validation F1",

        "positive_class":
            1,

        "positive_class_name":
            "gambling",

        "selected_configuration":
            selected_configuration,
    }

    with open(
        THRESHOLD_FILE,
        "w",
        encoding="utf-8"
    ) as file:

        json.dump(
            threshold_data,
            file,
            indent=4
        )

    # =====================================================
    # SAVE METRICS
    # =====================================================

    complete_metrics = {

        "model":
            "Character TF-IDF + Random Forest",

        "tfidf": {
            "analyzer":
                "char",

            "ngram_range":
                [
                    3,
                    5
                ],

            "min_df":
                2,

            "sublinear_tf":
                True,

            "norm":
                "l2",
        },

        "selected_configuration":
            selected_configuration,

        "selected_threshold":
            float(
                selected_threshold
            ),

        "train_size":
            int(
                len(train_df)
            ),

        "validation_size":
            int(
                len(validation_df)
            ),

        "test_size":
            int(
                len(test_df)
            ),

        "validation_metrics":
            validation_metrics,

        "test_metrics":
            test_metrics,
    }

    METRICS_FILE.parent.mkdir(
        parents=True,
        exist_ok=True
    )

    with open(
        METRICS_FILE,
        "w",
        encoding="utf-8"
    ) as file:

        json.dump(
            complete_metrics,
            file,
            indent=4
        )

    threshold_table.to_csv(
        "reports/random_forest_selected_threshold_search.csv",
        index=False
    )

    # =====================================================
    # FINAL OUTPUT
    # =====================================================

    print(
        "\n===================================="
    )

    print(
        " RANDOM FOREST EXPERIMENT COMPLETED"
    )

    print(
        "===================================="
    )

    print(
        "\nSelected configuration:"
    )

    print(
        selected_configuration
    )

    print(
        "\nSelected threshold:"
    )

    print(
        f"{selected_threshold:.6f}"
    )

    print(
        "\nValidation accuracy:"
    )

    print(
        f"{validation_metrics['accuracy']:.4f}"
    )

    print(
        "\nFinal test accuracy:"
    )

    print(
        f"{test_metrics['accuracy']:.4f}"
    )

    print(
        "\nFinal test F1:"
    )

    print(
        f"{test_metrics['f1']:.4f}"
    )

    print(
        "\nModel:"
    )

    print(
        MODEL_FILE
    )

    print(
        "\nMetrics:"
    )

    print(
        METRICS_FILE
    )

    print(
        "\nValidation search:"
    )

    print(
        VALIDATION_SEARCH_FILE
    )

    print(
        "\nIMPORTANT:"
    )

    print(
        "This Random Forest experiment does NOT "
        "replace the deployed Logistic Regression model."
    )


if __name__ == "__main__":

    main()