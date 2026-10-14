import json
from pathlib import Path

import joblib
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

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
from sklearn.svm import LinearSVC


# =========================================================
# BETGUARD
# LINEAR SVM DOMAIN CLASSIFIER
# =========================================================
#
# PURPOSE:
#
# Compare Linear SVM against the existing Logistic
# Regression baseline using the EXACT SAME saved
# train / validation / test splits.
#
#
# MODEL:
#
#     Domain text
#         ↓
#     Character TF-IDF
#         ↓
#     Linear SVM
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
# The script DOES NOT create new dataset splits.
#
# It loads:
#
#     baseline_train.csv
#     baseline_validation.csv
#     baseline_test.csv
#
# so the comparison with Logistic Regression remains fair.
#
# =========================================================


# =========================================================
# CONFIGURATION
# =========================================================

RANDOM_STATE = 42

C_VALUES = [
    0.01,
    0.05,
    0.1,
    0.25,
    0.5,
    1.0,
    2.0,
    5.0,
    10.0,
]


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
    "models/svm_domain_classifier.joblib"
)

THRESHOLD_FILE = Path(
    "models/svm_threshold.json"
)

METRICS_FILE = Path(
    "reports/svm_metrics.json"
)

VALIDATION_SEARCH_FILE = Path(
    "reports/svm_validation_search.csv"
)

CLASSIFICATION_REPORT_FILE = Path(
    "reports/svm_classification_report.csv"
)

PREDICTIONS_FILE = Path(
    "reports/svm_test_predictions.csv"
)

MISCLASSIFIED_FILE = Path(
    "reports/svm_misclassified_domains.csv"
)

CONFUSION_MATRIX_FILE = Path(
    "reports/svm_confusion_matrix.png"
)

ROC_CURVE_FILE = Path(
    "reports/svm_roc_curve.png"
)

PR_CURVE_FILE = Path(
    "reports/svm_precision_recall_curve.png"
)


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
# LOAD ONE SPLIT
# =========================================================

def load_split(path):

    if not path.exists():

        raise FileNotFoundError(
            f"\nSplit file not found:\n{path}\n\n"
            "Run train_baseline.py first so the original "
            "leakage-safe splits are available."
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
            f"{path} is missing columns: {missing}"
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

    invalid = df[
        ~df["label"].isin(
            [0, 1]
        )
    ]

    if len(invalid) > 0:

        raise ValueError(
            f"{path} contains invalid labels."
        )

    empty = df[
        df["domain"] == ""
    ]

    if len(empty) > 0:

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
# CHECK SPLIT LEAKAGE
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

    train_validation_overlap = (
        train_groups
        &
        validation_groups
    )

    train_test_overlap = (
        train_groups
        &
        test_groups
    )

    validation_test_overlap = (
        validation_groups
        &
        test_groups
    )

    if (
        train_validation_overlap
        or
        train_test_overlap
        or
        validation_test_overlap
    ):

        raise RuntimeError(
            "Domain-family leakage detected "
            "between the saved splits."
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
# PRINT SPLIT DISTRIBUTION
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
            f"  {label} ({meaning}): {count}"
        )


# =========================================================
# CREATE SVM MODEL
# =========================================================

def create_model(c_value):

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

                LinearSVC(
                    C=c_value,
                    class_weight="balanced",
                    random_state=RANDOM_STATE,
                    max_iter=10000,
                ),
            ),
        ]
    )


# =========================================================
# FIND BEST DECISION THRESHOLD
# =========================================================

def find_best_threshold(
    y_true,
    scores
):

    (
        precision_values,
        recall_values,
        thresholds,

    ) = precision_recall_curve(
        y_true,
        scores
    )

    results = []

    best_threshold = 0.0
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

    threshold_df = pd.DataFrame(
        results
    )

    return (
        best_threshold,
        best_f1,
        threshold_df,
    )


# =========================================================
# CALCULATE METRICS
# =========================================================

def calculate_metrics(
    y_true,
    scores,
    threshold
):

    predictions = (
        scores
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
                    scores
                )
            ),

        "average_precision":
            float(
                average_precision_score(
                    y_true,
                    scores
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
# TUNE C USING VALIDATION ONLY
# =========================================================

def tune_model(
    train_df,
    validation_df
):

    print(
        "\n===================================="
    )

    print(
        " SVM VALIDATION SEARCH"
    )

    print(
        "===================================="
    )

    y_validation = (
        validation_df[
            "label"
        ].to_numpy()
    )

    validation_results = []

    best_model = None
    best_c = None
    best_threshold = None
    best_metrics = None
    best_threshold_table = None

    for c_value in C_VALUES:

        print(
            f"\nTesting C = {c_value}"
        )

        model = create_model(
            c_value
        )

        model.fit(
            train_df[
                "domain"
            ],
            train_df[
                "label"
            ]
        )

        scores = (
            model.decision_function(
                validation_df[
                    "domain"
                ]
            )
        )

        (
            threshold,
            best_f1,
            threshold_table,

        ) = find_best_threshold(
            y_validation,
            scores
        )

        (
            metrics,
            _,

        ) = calculate_metrics(
            y_validation,
            scores,
            threshold
        )

        result = {

            "C":
                float(
                    c_value
                ),

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

        validation_results.append(
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

        # Primary selection:
        # highest validation F1.
        #
        # Tie-breakers:
        # higher accuracy,
        # then higher precision,
        # then lower C for a simpler model.

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
            -float(
                c_value
            ),
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
                -float(
                    best_c
                ),
            )

            choose = (
                candidate_key
                >
                best_key
            )

        if choose:

            best_model = model
            best_c = c_value
            best_threshold = threshold
            best_metrics = metrics
            best_threshold_table = (
                threshold_table
            )

    validation_df_results = (
        pd.DataFrame(
            validation_results
        )
    )

    validation_df_results = (
        validation_df_results.sort_values(
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

    validation_df_results.to_csv(
        VALIDATION_SEARCH_FILE,
        index=False
    )

    print(
        "\n===================================="
    )

    print(
        " SELECTED SVM"
    )

    print(
        "===================================="
    )

    print(
        f"\nSelected C: "
        f"{best_c}"
    )

    print(
        f"Selected threshold: "
        f"{best_threshold:.6f}"
    )

    print(
        f"Validation accuracy: "
        f"{best_metrics['accuracy']:.4f}"
    )

    print(
        f"Validation precision: "
        f"{best_metrics['precision']:.4f}"
    )

    print(
        f"Validation recall: "
        f"{best_metrics['recall']:.4f}"
    )

    print(
        f"Validation F1: "
        f"{best_metrics['f1']:.4f}"
    )

    return (
        best_model,
        best_c,
        best_threshold,
        best_metrics,
        best_threshold_table,
        validation_df_results,
    )


# =========================================================
# SAVE CONFUSION MATRIX
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
        "BetGuard Linear SVM Confusion Matrix"
    )

    figure.tight_layout()

    figure.savefig(
        CONFUSION_MATRIX_FILE,
        dpi=200
    )

    plt.close(
        figure
    )


# =========================================================
# SAVE ROC CURVE
# =========================================================

def save_roc_curve(
    y_true,
    scores
):

    figure, axis = plt.subplots(
        figsize=(
            6,
            5
        )
    )

    RocCurveDisplay.from_predictions(
        y_true,
        scores,
        ax=axis
    )

    axis.set_title(
        "BetGuard Linear SVM ROC Curve"
    )

    figure.tight_layout()

    figure.savefig(
        ROC_CURVE_FILE,
        dpi=200
    )

    plt.close(
        figure
    )


# =========================================================
# SAVE PRECISION-RECALL CURVE
# =========================================================

def save_precision_recall_curve(
    y_true,
    scores
):

    figure, axis = plt.subplots(
        figsize=(
            6,
            5
        )
    )

    PrecisionRecallDisplay.from_predictions(
        y_true,
        scores,
        ax=axis
    )

    axis.set_title(
        "BetGuard Linear SVM Precision-Recall Curve"
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
        " BETGUARD LINEAR SVM EXPERIMENT"
    )

    print(
        "===================================="
    )

    # -----------------------------------------------------
    # LOAD EXACT BASELINE SPLITS
    # -----------------------------------------------------

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

    # -----------------------------------------------------
    # VALIDATION-ONLY MODEL SELECTION
    # -----------------------------------------------------

    (
        model,
        selected_c,
        selected_threshold,
        validation_metrics,
        threshold_table,
        validation_results,

    ) = tune_model(
        train_df,
        validation_df
    )

    # -----------------------------------------------------
    # IMPORTANT:
    #
    # Test data has not been used above.
    #
    # It is touched only now, after C and the decision
    # threshold have already been selected.
    # -----------------------------------------------------

    print(
        "\n===================================="
    )

    print(
        " FINAL SVM TEST"
    )

    print(
        "===================================="
    )

    test_scores = (
        model.decision_function(
            test_df[
                "domain"
            ]
        )
    )

    (
        test_metrics,
        test_predictions,

    ) = calculate_metrics(
        test_df[
            "label"
        ].to_numpy(),
        test_scores,
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

    # -----------------------------------------------------
    # CLASSIFICATION REPORT
    # -----------------------------------------------------

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

    report_df = pd.DataFrame(
        report_dict
    ).transpose()

    CLASSIFICATION_REPORT_FILE.parent.mkdir(
        parents=True,
        exist_ok=True
    )

    report_df.to_csv(
        CLASSIFICATION_REPORT_FILE
    )

    # -----------------------------------------------------
    # TEST PREDICTIONS
    # -----------------------------------------------------

    prediction_df = (
        test_df.copy()
    )

    prediction_df[
        "svm_decision_score"
    ] = test_scores

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

    # -----------------------------------------------------
    # MISCLASSIFIED DOMAINS
    # -----------------------------------------------------

    misclassified = prediction_df[
        ~prediction_df[
            "correct"
        ]
    ].copy()

    misclassified[
        "distance_from_threshold"
    ] = (
        misclassified[
            "svm_decision_score"
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
            "svm_decision_score",
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

    # -----------------------------------------------------
    # SAVE PLOTS
    # -----------------------------------------------------

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
        test_scores
    )

    save_precision_recall_curve(
        test_df[
            "label"
        ],
        test_scores
    )

    # -----------------------------------------------------
    # SAVE MODEL + THRESHOLD
    # -----------------------------------------------------

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

        "threshold_type":
            "LinearSVC decision_function score",

        "selected_using":
            "validation F1",

        "selected_C":
            float(
                selected_c
            ),

        "positive_class":
            1,

        "positive_class_name":
            "gambling",
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

    # -----------------------------------------------------
    # SAVE COMPLETE METRICS
    # -----------------------------------------------------

    complete_metrics = {

        "model":
            "Character TF-IDF + Linear SVM",

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

        "selected_C":
            float(
                selected_c
            ),

        "selected_threshold":
            float(
                selected_threshold
            ),

        "train_size":
            int(
                len(
                    train_df
                )
            ),

        "validation_size":
            int(
                len(
                    validation_df
                )
            ),

        "test_size":
            int(
                len(
                    test_df
                )
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

    # -----------------------------------------------------
    # SAVE BEST THRESHOLD SEARCH
    # -----------------------------------------------------

    threshold_search_file = Path(
        "reports/svm_selected_threshold_search.csv"
    )

    threshold_table.to_csv(
        threshold_search_file,
        index=False
    )

    # -----------------------------------------------------
    # FINAL OUTPUT
    # -----------------------------------------------------

    print(
        "\n===================================="
    )

    print(
        " SVM EXPERIMENT COMPLETED"
    )

    print(
        "===================================="
    )

    print(
        "\nSelected C:"
    )

    print(
        selected_c
    )

    print(
        "\nSelected decision threshold:"
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
        "\nTest predictions:"
    )

    print(
        PREDICTIONS_FILE
    )

    print(
        "\nMisclassified domains:"
    )

    print(
        MISCLASSIFIED_FILE
    )

    print(
        "\nConfusion matrix:"
    )

    print(
        CONFUSION_MATRIX_FILE
    )

    print(
        "\nROC curve:"
    )

    print(
        ROC_CURVE_FILE
    )

    print(
        "\nPrecision-recall curve:"
    )

    print(
        PR_CURVE_FILE
    )

    print(
        "\nIMPORTANT:"
    )

    print(
        "This SVM experiment does NOT replace the "
        "currently deployed Logistic Regression model."
    )


# =========================================================
# ENTRY POINT
# =========================================================

if __name__ == "__main__":

    main()