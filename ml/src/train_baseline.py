import json
from pathlib import Path

import joblib
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import tldextract

from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.linear_model import LogisticRegression
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
from sklearn.model_selection import StratifiedGroupKFold
from sklearn.pipeline import Pipeline


# =========================================================
# BETGUARD
# BASELINE DOMAIN CLASSIFIER
# =========================================================
#
# MODEL:
#
#     Domain text
#         ↓
#     Character TF-IDF
#         ↓
#     Logistic Regression
#
#
# LABELS:
#
#     0 = non-gambling
#     1 = gambling
#
#
# DATA SPLIT:
#
#     ~60% train
#     ~20% validation
#     ~20% test
#
#
# IMPORTANT:
#
# Related subdomains are grouped by their registrable
# parent domain so they cannot leak across splits.
#
# Example:
#
#     casino.example.com
#     sports.example.com
#
# stay in the SAME split.
#
# =========================================================


# =========================================================
# CONFIGURATION
# =========================================================

RANDOM_STATE = 42


# =========================================================
# PATHS
# =========================================================

DATA_FILE = Path(
    "data/processed/balanced_domain_dataset.csv"
)

MODEL_FILE = Path(
    "models/baseline_domain_classifier.joblib"
)

THRESHOLD_FILE = Path(
    "models/baseline_threshold.json"
)

METRICS_FILE = Path(
    "reports/baseline_metrics.json"
)

CLASSIFICATION_REPORT_FILE = Path(
    "reports/baseline_classification_report.csv"
)

PREDICTIONS_FILE = Path(
    "reports/baseline_test_predictions.csv"
)

MISCLASSIFIED_FILE = Path(
    "reports/baseline_misclassified_domains.csv"
)

CONFUSION_MATRIX_FILE = Path(
    "reports/baseline_confusion_matrix.png"
)

ROC_CURVE_FILE = Path(
    "reports/baseline_roc_curve.png"
)

PR_CURVE_FILE = Path(
    "reports/baseline_precision_recall_curve.png"
)

THRESHOLD_RESULTS_FILE = Path(
    "reports/baseline_threshold_search.csv"
)

TRAIN_SPLIT_FILE = Path(
    "data/processed/splits/baseline_train.csv"
)

VALIDATION_SPLIT_FILE = Path(
    "data/processed/splits/baseline_validation.csv"
)

TEST_SPLIT_FILE = Path(
    "data/processed/splits/baseline_test.csv"
)


# =========================================================
# TLD EXTRACTOR
# =========================================================
#
# suffix_list_urls=()
#
# prevents tldextract from trying to download an updated
# Public Suffix List while the script runs.
#
# It uses its packaged suffix snapshot instead.
#
# =========================================================

TLD_EXTRACTOR = tldextract.TLDExtract(
    suffix_list_urls=()
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
# GET DOMAIN FAMILY
# =========================================================
#
# Examples:
#
#     casino.example.com
#         -> example.com
#
#     news.bbc.co.uk
#         -> bbc.co.uk
#
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

    # Fallback for unusual domains.

    return domain


# =========================================================
# LOAD DATASET
# =========================================================

def load_dataset():

    if not DATA_FILE.exists():

        raise FileNotFoundError(
            f"\nDataset not found:\n"
            f"{DATA_FILE}\n\n"
            "Run build_training_dataset.py first."
        )

    df = pd.read_csv(
        DATA_FILE
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
            "Training dataset is missing "
            f"columns: {missing}"
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

    # -----------------------------------------------------
    # Validate labels
    # -----------------------------------------------------

    invalid = df[
        ~df["label"].isin(
            [0, 1]
        )
    ]

    if len(invalid) > 0:

        raise ValueError(
            "Dataset contains labels other "
            "than 0 and 1."
        )

    # -----------------------------------------------------
    # Empty domains
    # -----------------------------------------------------

    empty = df[
        df["domain"] == ""
    ]

    if len(empty) > 0:

        raise ValueError(
            f"Dataset contains "
            f"{len(empty)} empty domains."
        )

    # -----------------------------------------------------
    # Exact duplicates
    # -----------------------------------------------------

    duplicate_domains = df[
        df["domain"].duplicated(
            keep=False
        )
    ]

    if len(duplicate_domains) > 0:

        print(
            "\nDuplicate domains:"
        )

        print(
            duplicate_domains[
                [
                    "domain",
                    "label",
                ]
            ].to_string(
                index=False
            )
        )

        raise ValueError(
            "Remove duplicate domains "
            "before training."
        )

    # -----------------------------------------------------
    # Domain family
    # -----------------------------------------------------

    df[
        "domain_family"
    ] = df[
        "domain"
    ].apply(
        get_domain_family
    )

    return df


# =========================================================
# CREATE TRAIN / VALIDATION / TEST SPLITS
# =========================================================

def create_splits(df):

    print(
        "\nCreating leakage-safe splits..."
    )

    X = df["domain"]

    y = df["label"]

    groups = df[
        "domain_family"
    ]

    # =====================================================
    # FIRST SPLIT
    # =====================================================
    #
    # 5 folds:
    #
    # approximately:
    #
    # 80% temporary train+validation
    # 20% test
    #
    # =====================================================

    outer_splitter = StratifiedGroupKFold(
        n_splits=5,
        shuffle=True,
        random_state=RANDOM_STATE
    )

    outer_splits = list(
        outer_splitter.split(
            X,
            y,
            groups
        )
    )

    train_validation_indices, test_indices = (
        outer_splits[0]
    )

    train_validation_df = (
        df.iloc[
            train_validation_indices
        ]
        .reset_index(
            drop=True
        )
    )

    test_df = (
        df.iloc[
            test_indices
        ]
        .reset_index(
            drop=True
        )
    )

    # =====================================================
    # SECOND SPLIT
    # =====================================================
    #
    # Split the remaining ~80% into:
    #
    # approximately:
    #
    # 75% training
    # 25% validation
    #
    # Result overall:
    #
    # ~60% train
    # ~20% validation
    # ~20% test
    #
    # =====================================================

    inner_splitter = StratifiedGroupKFold(
        n_splits=4,
        shuffle=True,
        random_state=RANDOM_STATE
    )

    inner_splits = list(
        inner_splitter.split(
            train_validation_df[
                "domain"
            ],
            train_validation_df[
                "label"
            ],
            train_validation_df[
                "domain_family"
            ],
        )
    )

    train_indices, validation_indices = (
        inner_splits[0]
    )

    train_df = (
        train_validation_df.iloc[
            train_indices
        ]
        .reset_index(
            drop=True
        )
    )

    validation_df = (
        train_validation_df.iloc[
            validation_indices
        ]
        .reset_index(
            drop=True
        )
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
            "between splits."
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

    print(
        "  Labels:"
    )

    counts = (
        df[
            "label"
        ].value_counts()
        .sort_index()
    )

    for label, count in (
        counts.items()
    ):

        meaning = (
            "non-gambling"
            if label == 0
            else "gambling"
        )

        print(
            f"    {label} "
            f"({meaning}): "
            f"{count}"
        )


# =========================================================
# CREATE MODEL
# =========================================================

def create_model():

    model = Pipeline(
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

                LogisticRegression(
                    max_iter=3000,
                    class_weight="balanced",
                    random_state=RANDOM_STATE,
                ),
            ),
        ]
    )

    return model


# =========================================================
# FIND BEST VALIDATION THRESHOLD
# =========================================================

def find_best_threshold(
    y_true,
    probabilities
):

    precision_values, recall_values, thresholds = (
        precision_recall_curve(
            y_true,
            probabilities
        )
    )

    results = []

    best_threshold = 0.5

    best_f1 = -1.0

    # precision_recall_curve returns one more
    # precision/recall value than thresholds.

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
    probabilities,
    threshold
):

    predictions = (
        probabilities
        >=
        threshold
    ).astype(int)

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
    }

    matrix = confusion_matrix(
        y_true,
        predictions
    )

    metrics[
        "confusion_matrix"
    ] = matrix.tolist()

    return (
        metrics,
        predictions,
    )


# =========================================================
# SAVE SPLITS
# =========================================================

def save_splits(
    train_df,
    validation_df,
    test_df
):

    TRAIN_SPLIT_FILE.parent.mkdir(
        parents=True,
        exist_ok=True
    )

    train_df.to_csv(
        TRAIN_SPLIT_FILE,
        index=False
    )

    validation_df.to_csv(
        VALIDATION_SPLIT_FILE,
        index=False
    )

    test_df.to_csv(
        TEST_SPLIT_FILE,
        index=False
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
        "BetGuard Baseline Confusion Matrix"
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
        "BetGuard Baseline ROC Curve"
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
        "BetGuard Baseline Precision-Recall Curve"
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
        " BETGUARD BASELINE MODEL TRAINING"
    )

    print(
        "===================================="
    )

    # =====================================================
    # LOAD
    # =====================================================

    df = load_dataset()

    print(
        "\nDataset loaded:"
    )

    print(
        len(df),
        "domains"
    )

    print(
        "\nOverall labels:"
    )

    print(
        df[
            "label"
        ].value_counts()
        .sort_index()
    )

    print(
        "\nUnique domain families:"
    )

    print(
        df[
            "domain_family"
        ].nunique()
    )


    # =====================================================
    # SPLIT
    # =====================================================

    (
        train_df,
        validation_df,
        test_df,

    ) = create_splits(
        df
    )

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

    save_splits(
        train_df,
        validation_df,
        test_df
    )


    # =====================================================
    # CREATE MODEL
    # =====================================================

    model = create_model()


    # =====================================================
    # TRAIN
    # =====================================================

    print(
        "\n===================================="
    )

    print(
        " TRAINING"
    )

    print(
        "===================================="
    )

    print(
        "\nTraining TF-IDF + "
        "Logistic Regression..."
    )

    model.fit(
        train_df[
            "domain"
        ],
        train_df[
            "label"
        ]
    )

    print(
        "Training completed."
    )


    # =====================================================
    # VALIDATION
    # =====================================================

    print(
        "\n===================================="
    )

    print(
        " VALIDATION / THRESHOLD SELECTION"
    )

    print(
        "===================================="
    )

    validation_probabilities = (
        model.predict_proba(
            validation_df[
                "domain"
            ]
        )[:, 1]
    )

    (
        best_threshold,
        best_validation_f1,
        threshold_results,

    ) = find_best_threshold(

        validation_df[
            "label"
        ].to_numpy(),

        validation_probabilities
    )

    print(
        "\nSelected threshold:"
    )

    print(
        f"{best_threshold:.4f}"
    )

    print(
        "\nValidation F1 at "
        "selected threshold:"
    )

    print(
        f"{best_validation_f1:.4f}"
    )

    threshold_results.to_csv(
        THRESHOLD_RESULTS_FILE,
        index=False
    )


    # =====================================================
    # TEST
    # =====================================================

    print(
        "\n===================================="
    )

    print(
        " FINAL TEST"
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

        best_threshold
    )


    # =====================================================
    # DISPLAY METRICS
    # =====================================================

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

    report_df = pd.DataFrame(
        report_dict
    ).transpose()

    report_df.to_csv(
        CLASSIFICATION_REPORT_FILE
    )


    # =====================================================
    # SAVE TEST PREDICTIONS
    # =====================================================

    prediction_df = test_df.copy()

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
    # MISCLASSIFIED DOMAINS
    # =====================================================

    misclassified = prediction_df[
        ~prediction_df[
            "correct"
        ]
    ].copy()

    misclassified = (
        misclassified.sort_values(
            "gambling_probability",
            ascending=False
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

    if len(
        misclassified
    ) > 0:

        print(
            "\nMisclassification examples:"
        )

        print(
            misclassified[
                [
                    "domain",
                    "label",
                    "predicted_label",
                    "gambling_probability",
                    "source",
                    "category",
                ]
            ]
            .head(20)
            .to_string(
                index=False
            )
        )


    # =====================================================
    # SAVE PLOTS
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
    # SAVE METRICS
    # =====================================================

    complete_metrics = {

        "model":
            "Character TF-IDF + Logistic Regression",

        "dataset_size":
            int(
                len(df)
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

        "selected_threshold":
            float(
                best_threshold
            ),

        "validation_f1":
            float(
                best_validation_f1
            ),

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
                best_threshold
            ),

        "selected_using":
            "validation F1",

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


    # =====================================================
    # FINAL OUTPUT
    # =====================================================

    print(
        "\n===================================="
    )

    print(
        " TRAINING COMPLETED"
    )

    print(
        "===================================="
    )

    print(
        "\nModel:"
    )

    print(
        MODEL_FILE
    )

    print(
        "\nDecision threshold:"
    )

    print(
        THRESHOLD_FILE
    )

    print(
        "\nMetrics:"
    )

    print(
        METRICS_FILE
    )

    print(
        "\nClassification report:"
    )

    print(
        CLASSIFICATION_REPORT_FILE
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
        "\nNEXT STEP:"
    )

    print(
        "Analyze the baseline results and "
        "misclassified domains before "
        "building the hybrid model."
    )


# =========================================================
# ENTRY POINT
# =========================================================

if __name__ == "__main__":

    main()