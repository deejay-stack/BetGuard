import json
from pathlib import Path

import joblib
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from sklearn.compose import (
    ColumnTransformer,
)

from sklearn.feature_extraction.text import (
    TfidfVectorizer,
)

from sklearn.linear_model import (
    LogisticRegression,
)

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
    PrecisionRecallDisplay,
    RocCurveDisplay,
)

from sklearn.pipeline import (
    Pipeline,
)

from sklearn.preprocessing import (
    StandardScaler,
)

from domain_features import (
    DomainLexicalTransformer,
)


# =========================================================
# BETGUARD
# HYBRID DOMAIN CLASSIFIER
# =========================================================
#
# MODEL:
#
#                 DOMAIN
#                   │
#          ┌────────┴────────┐
#          │                 │
#          ▼                 ▼
# Character TF-IDF     Lexical features
#          │                 │
#          └────────┬────────┘
#                   ▼
#          Logistic Regression
#
#
# IMPORTANT:
#
# We reuse EXACTLY the same train / validation / test
# split from the baseline.
#
# This gives us a fair model-to-model comparison.
#
# =========================================================


# =========================================================
# CONFIG
# =========================================================

RANDOM_STATE = 42

TARGET_PRECISION = 0.90


# =========================================================
# INPUT SPLITS
# =========================================================

TRAIN_FILE = Path(
    "data/processed/splits/baseline_train.csv"
)

VALIDATION_FILE = Path(
    "data/processed/splits/baseline_validation.csv"
)

TEST_FILE = Path(
    "data/processed/splits/baseline_test.csv"
)


# =========================================================
# BASELINE RESULT
# =========================================================

BASELINE_METRICS_FILE = Path(
    "reports/baseline_metrics.json"
)


# =========================================================
# OUTPUT MODEL
# =========================================================

MODEL_FILE = Path(
    "models/hybrid_evaluation_model.joblib"
)

THRESHOLD_FILE = Path(
    "models/hybrid_thresholds.json"
)


# =========================================================
# REPORTS
# =========================================================

METRICS_FILE = Path(
    "reports/hybrid_metrics.json"
)

COMPARISON_FILE = Path(
    "reports/baseline_vs_hybrid.csv"
)

PREDICTIONS_FILE = Path(
    "reports/hybrid_test_predictions.csv"
)

MISCLASSIFIED_FILE = Path(
    "reports/hybrid_misclassified_domains.csv"
)

FALSE_POSITIVES_FILE = Path(
    "reports/hybrid_false_positives.csv"
)

FALSE_NEGATIVES_FILE = Path(
    "reports/hybrid_false_negatives.csv"
)

THRESHOLD_SEARCH_FILE = Path(
    "reports/hybrid_threshold_search.csv"
)

CLASSIFICATION_REPORT_FILE = Path(
    "reports/hybrid_classification_report.csv"
)

CONFUSION_MATRIX_FILE = Path(
    "reports/hybrid_confusion_matrix.png"
)

ROC_CURVE_FILE = Path(
    "reports/hybrid_roc_curve.png"
)

PR_CURVE_FILE = Path(
    "reports/hybrid_precision_recall_curve.png"
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
            f"{path}\n\n"
            "Run train_baseline.py first."
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
# LOAD ALL SPLITS
# =========================================================

def load_splits():

    train = load_split(
        TRAIN_FILE,
        "training"
    )

    validation = load_split(
        VALIDATION_FILE,
        "validation"
    )

    test = load_split(
        TEST_FILE,
        "test"
    )

    return (
        train,
        validation,
        test,
    )


# =========================================================
# VERIFY NO DOMAIN OVERLAP
# =========================================================

def verify_split_integrity(
    train,
    validation,
    test
):

    train_domains = set(
        train[
            "domain"
        ]
    )

    validation_domains = set(
        validation[
            "domain"
        ]
    )

    test_domains = set(
        test[
            "domain"
        ]
    )

    if (
        train_domains
        &
        validation_domains
    ):

        raise RuntimeError(
            "Train/validation domain overlap."
        )

    if (
        train_domains
        &
        test_domains
    ):

        raise RuntimeError(
            "Train/test domain overlap."
        )

    if (
        validation_domains
        &
        test_domains
    ):

        raise RuntimeError(
            "Validation/test domain overlap."
        )

    # Domain-family leakage was already checked by the
    # baseline splitter.

    print(
        "\nSplit integrity: PASSED"
    )


# =========================================================
# CREATE MODEL
# =========================================================

def create_model():

    lexical_pipeline = Pipeline(
        [
            (
                "lexical_features",
                DomainLexicalTransformer()
            ),

            (
                "scale",
                StandardScaler()
            ),
        ]
    )

    features = ColumnTransformer(
        transformers=[
            (
                "character_tfidf",

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

                "domain",
            ),

            (
                "lexical",

                lexical_pipeline,

                "domain",
            ),
        ],

        remainder="drop",

        sparse_threshold=0.3,
    )

    model = Pipeline(
        [
            (
                "features",
                features
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
# THRESHOLD SEARCH
# =========================================================

def find_thresholds(
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

    best_f1 = -1.0

    best_f1_threshold = 0.5


    # =====================================================
    # FIND BEST F1
    # =====================================================

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

        if f1 > best_f1:

            best_f1 = f1

            best_f1_threshold = float(
                threshold
            )


    results = pd.DataFrame(
        rows
    )


    # =====================================================
    # PRECISION-ORIENTED THRESHOLD
    # =====================================================
    #
    # For blocking software, false positives are expensive.
    #
    # Find the threshold with:
    #
    # precision >= TARGET_PRECISION
    #
    # and the highest available recall.
    #
    # =====================================================

    precision_candidates = results[
        results[
            "precision"
        ]
        >=
        TARGET_PRECISION
    ].copy()


    precision_threshold = None

    precision_threshold_stats = None


    if len(
        precision_candidates
    ) > 0:

        precision_candidates = (
            precision_candidates.sort_values(
                by=[
                    "recall",
                    "f1",
                ],
                ascending=[
                    False,
                    False,
                ]
            )
        )

        best_row = (
            precision_candidates.iloc[
                0
            ]
        )

        precision_threshold = float(
            best_row[
                "threshold"
            ]
        )

        precision_threshold_stats = {

            "precision":
                float(
                    best_row[
                        "precision"
                    ]
                ),

            "recall":
                float(
                    best_row[
                        "recall"
                    ]
                ),

            "f1":
                float(
                    best_row[
                        "f1"
                    ]
                ),
        }


    return {
        "f1_threshold":
            best_f1_threshold,

        "f1_validation_score":
            float(
                best_f1
            ),

        "precision_threshold":
            precision_threshold,

        "precision_threshold_validation":
            precision_threshold_stats,

        "search_results":
            results,
    }


# =========================================================
# EVALUATE
# =========================================================

def evaluate(
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
        predictions
    )


# =========================================================
# PRINT METRICS
# =========================================================

def print_metrics(
    title,
    metrics
):

    print(
        f"\n{title}"
    )

    print(
        "-" * len(
            title
        )
    )

    print(
        "Threshold:",
        f"{metrics['threshold']:.4f}"
    )

    print(
        "Accuracy:",
        f"{metrics['accuracy']:.4f}"
    )

    print(
        "Precision:",
        f"{metrics['precision']:.4f}"
    )

    print(
        "Recall:",
        f"{metrics['recall']:.4f}"
    )

    print(
        "F1:",
        f"{metrics['f1']:.4f}"
    )

    print(
        "ROC-AUC:",
        f"{metrics['roc_auc']:.4f}"
    )

    print(
        "PR-AUC:",
        f"{metrics['average_precision']:.4f}"
    )

    print(
        "False positives:",
        metrics[
            "false_positives"
        ]
    )

    print(
        "False negatives:",
        metrics[
            "false_negatives"
        ]
    )


# =========================================================
# SAVE PLOTS
# =========================================================

def save_plots(
    y_true,
    probabilities,
    predictions
):

    CONFUSION_MATRIX_FILE.parent.mkdir(
        parents=True,
        exist_ok=True
    )

    # -----------------------------------------------------
    # Confusion matrix
    # -----------------------------------------------------

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
        "BetGuard Hybrid Confusion Matrix"
    )

    figure.tight_layout()

    figure.savefig(
        CONFUSION_MATRIX_FILE,
        dpi=200
    )

    plt.close(
        figure
    )


    # -----------------------------------------------------
    # ROC
    # -----------------------------------------------------

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
        "BetGuard Hybrid ROC Curve"
    )

    figure.tight_layout()

    figure.savefig(
        ROC_CURVE_FILE,
        dpi=200
    )

    plt.close(
        figure
    )


    # -----------------------------------------------------
    # PR
    # -----------------------------------------------------

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
        "BetGuard Hybrid Precision-Recall Curve"
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
# BASELINE COMPARISON
# =========================================================

def create_comparison(
    hybrid_metrics
):

    rows = []


    if BASELINE_METRICS_FILE.exists():

        with open(
            BASELINE_METRICS_FILE,
            "r",
            encoding="utf-8"
        ) as file:

            baseline_data = json.load(
                file
            )

        baseline = baseline_data[
            "test_metrics"
        ]

        rows.append(
            {
                "model":
                    "TF-IDF baseline",

                "accuracy":
                    baseline[
                        "accuracy"
                    ],

                "precision":
                    baseline[
                        "precision"
                    ],

                "recall":
                    baseline[
                        "recall"
                    ],

                "f1":
                    baseline[
                        "f1"
                    ],

                "roc_auc":
                    baseline[
                        "roc_auc"
                    ],

                "average_precision":
                    baseline[
                        "average_precision"
                    ],

                "false_positives":
                    baseline[
                        "confusion_matrix"
                    ][0][1],

                "false_negatives":
                    baseline[
                        "confusion_matrix"
                    ][1][0],
            }
        )


    rows.append(
        {
            "model":
                "TF-IDF + lexical hybrid",

            "accuracy":
                hybrid_metrics[
                    "accuracy"
                ],

            "precision":
                hybrid_metrics[
                    "precision"
                ],

            "recall":
                hybrid_metrics[
                    "recall"
                ],

            "f1":
                hybrid_metrics[
                    "f1"
                ],

            "roc_auc":
                hybrid_metrics[
                    "roc_auc"
                ],

            "average_precision":
                hybrid_metrics[
                    "average_precision"
                ],

            "false_positives":
                hybrid_metrics[
                    "false_positives"
                ],

            "false_negatives":
                hybrid_metrics[
                    "false_negatives"
                ],
        }
    )


    comparison = pd.DataFrame(
        rows
    )

    comparison.to_csv(
        COMPARISON_FILE,
        index=False
    )

    return comparison


# =========================================================
# MAIN
# =========================================================

def main():

    print(
        "\n===================================="
    )

    print(
        " BETGUARD HYBRID MODEL TRAINING"
    )

    print(
        "===================================="
    )


    # =====================================================
    # LOAD SAME SPLITS
    # =====================================================

    (
        train,
        validation,
        test,

    ) = load_splits()


    print(
        "\nTRAIN:",
        len(train)
    )

    print(
        "VALIDATION:",
        len(validation)
    )

    print(
        "TEST:",
        len(test)
    )


    verify_split_integrity(
        train,
        validation,
        test
    )


    # =====================================================
    # MODEL
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
        "\nTraining character TF-IDF + "
        "lexical features..."
    )


    model.fit(
        train,
        train[
            "label"
        ]
    )


    print(
        "Training completed."
    )


    # =====================================================
    # VALIDATION
    # =====================================================

    validation_probabilities = (
        model.predict_proba(
            validation
        )[:, 1]
    )


    threshold_data = find_thresholds(
        validation[
            "label"
        ].to_numpy(),

        validation_probabilities
    )


    threshold_data[
        "search_results"
    ].to_csv(
        THRESHOLD_SEARCH_FILE,
        index=False
    )


    f1_threshold = (
        threshold_data[
            "f1_threshold"
        ]
    )


    print(
        "\n===================================="
    )

    print(
        " THRESHOLD SELECTION"
    )

    print(
        "===================================="
    )


    print(
        "\nBest validation F1 threshold:"
    )

    print(
        f"{f1_threshold:.4f}"
    )


    print(
        "\nValidation F1:"
    )

    print(
        f"{threshold_data['f1_validation_score']:.4f}"
    )


    if (
        threshold_data[
            "precision_threshold"
        ]
        is not None
    ):

        print(
            "\n90% precision-oriented threshold:"
        )

        print(
            f"{threshold_data['precision_threshold']:.4f}"
        )

        stats = threshold_data[
            "precision_threshold_validation"
        ]

        print(
            "Validation precision:",
            f"{stats['precision']:.4f}"
        )

        print(
            "Validation recall:",
            f"{stats['recall']:.4f}"
        )


    # =====================================================
    # TEST
    # =====================================================

    test_probabilities = (
        model.predict_proba(
            test
        )[:, 1]
    )


    (
        f1_metrics,
        f1_predictions,

    ) = evaluate(

        test[
            "label"
        ].to_numpy(),

        test_probabilities,

        f1_threshold
    )


    print(
        "\n===================================="
    )

    print(
        " TEST RESULTS"
    )

    print(
        "===================================="
    )


    print_metrics(
        "F1-optimized threshold",
        f1_metrics
    )


    precision_metrics = None


    if (
        threshold_data[
            "precision_threshold"
        ]
        is not None
    ):

        (
            precision_metrics,
            precision_predictions,

        ) = evaluate(

            test[
                "label"
            ].to_numpy(),

            test_probabilities,

            threshold_data[
                "precision_threshold"
            ]
        )


        print_metrics(
            "Precision-oriented threshold",
            precision_metrics
        )


    # =====================================================
    # CLASSIFICATION REPORT
    # =====================================================

    report_text = classification_report(
        test[
            "label"
        ],
        f1_predictions,
        target_names=[
            "Non-Gambling",
            "Gambling",
        ],
        digits=4,
        zero_division=0
    )


    print(
        "\nClassification Report "
        "(F1 threshold):"
    )

    print(
        report_text
    )


    report_dict = classification_report(
        test[
            "label"
        ],
        f1_predictions,
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

    predictions = test.copy()


    predictions[
        "gambling_probability"
    ] = test_probabilities


    predictions[
        "predicted_label"
    ] = f1_predictions


    predictions[
        "correct"
    ] = (
        predictions[
            "label"
        ]
        ==
        predictions[
            "predicted_label"
        ]
    )


    predictions[
        "error_type"
    ] = ""


    predictions.loc[
        (
            predictions[
                "label"
            ] == 0
        )
        &
        (
            predictions[
                "predicted_label"
            ] == 1
        ),
        "error_type"
    ] = "false_positive"


    predictions.loc[
        (
            predictions[
                "label"
            ] == 1
        )
        &
        (
            predictions[
                "predicted_label"
            ] == 0
        ),
        "error_type"
    ] = "false_negative"


    predictions.to_csv(
        PREDICTIONS_FILE,
        index=False
    )


    # =====================================================
    # ERRORS
    # =====================================================

    misclassified = predictions[
        ~predictions[
            "correct"
        ]
    ].copy()


    misclassified.to_csv(
        MISCLASSIFIED_FILE,
        index=False
    )


    false_positives = predictions[
        predictions[
            "error_type"
        ]
        ==
        "false_positive"
    ].copy()


    false_positives = (
        false_positives.sort_values(
            "gambling_probability",
            ascending=False
        )
    )


    false_positives.to_csv(
        FALSE_POSITIVES_FILE,
        index=False
    )


    false_negatives = predictions[
        predictions[
            "error_type"
        ]
        ==
        "false_negative"
    ].copy()


    false_negatives = (
        false_negatives.sort_values(
            "gambling_probability",
            ascending=True
        )
    )


    false_negatives.to_csv(
        FALSE_NEGATIVES_FILE,
        index=False
    )


    print(
        "\nFalse positives:"
    )

    print(
        len(
            false_positives
        )
    )


    print(
        "\nFalse negatives:"
    )

    print(
        len(
            false_negatives
        )
    )


    if len(
        false_positives
    ) > 0:

        print(
            "\nTop false positives:"
        )

        print(
            false_positives[
                [
                    "domain",
                    "gambling_probability",
                    "category",
                ]
            ]
            .head(10)
            .to_string(
                index=False
            )
        )


    if len(
        false_negatives
    ) > 0:

        print(
            "\nTop false negatives:"
        )

        print(
            false_negatives[
                [
                    "domain",
                    "gambling_probability",
                ]
            ]
            .head(10)
            .to_string(
                index=False
            )
        )


    # =====================================================
    # SAVE PLOTS
    # =====================================================

    save_plots(
        test[
            "label"
        ],
        test_probabilities,
        f1_predictions
    )


    # =====================================================
    # MODEL COMPARISON
    # =====================================================

    comparison = create_comparison(
        f1_metrics
    )


    print(
        "\n===================================="
    )

    print(
        " BASELINE VS HYBRID"
    )

    print(
        "===================================="
    )


    print(
        comparison.to_string(
            index=False
        )
    )


    # =====================================================
    # SAVE METRICS
    # =====================================================

    saved_threshold_data = {

        "f1_threshold":
            float(
                threshold_data[
                    "f1_threshold"
                ]
            ),

        "f1_validation_score":
            float(
                threshold_data[
                    "f1_validation_score"
                ]
            ),

        "precision_target":
            TARGET_PRECISION,

        "precision_threshold":
            (
                float(
                    threshold_data[
                        "precision_threshold"
                    ]
                )

                if threshold_data[
                    "precision_threshold"
                ]
                is not None

                else None
            ),

        "precision_threshold_validation":
            threshold_data[
                "precision_threshold_validation"
            ],
    }


    with open(
        THRESHOLD_FILE,
        "w",
        encoding="utf-8"
    ) as file:

        json.dump(
            saved_threshold_data,
            file,
            indent=4
        )


    complete_metrics = {

        "model":
            (
                "Character TF-IDF + "
                "lexical domain features + "
                "Logistic Regression"
            ),

        "train_size":
            int(
                len(train)
            ),

        "validation_size":
            int(
                len(validation)
            ),

        "test_size":
            int(
                len(test)
            ),

        "f1_threshold_test_metrics":
            f1_metrics,

        "precision_threshold_test_metrics":
            precision_metrics,
    }


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
    # SAVE EVALUATION MODEL
    # =====================================================

    MODEL_FILE.parent.mkdir(
        parents=True,
        exist_ok=True
    )


    joblib.dump(
        model,
        MODEL_FILE
    )


    # =====================================================
    # FINISHED
    # =====================================================

    print(
        "\n===================================="
    )

    print(
        " HYBRID TRAINING COMPLETED"
    )

    print(
        "===================================="
    )


    print(
        "\nEvaluation model:"
    )

    print(
        MODEL_FILE
    )


    print(
        "\nThresholds:"
    )

    print(
        THRESHOLD_FILE
    )


    print(
        "\nModel comparison:"
    )

    print(
        COMPARISON_FILE
    )


    print(
        "\nFalse positives:"
    )

    print(
        FALSE_POSITIVES_FILE
    )


    print(
        "\nFalse negatives:"
    )

    print(
        FALSE_NEGATIVES_FILE
    )


    print(
        "\nNEXT STEP:"
    )

    print(
        "Compare the baseline and hybrid "
        "models before creating the final "
        "deployment model."
    )


# =========================================================
# ENTRY POINT
# =========================================================

if __name__ == "__main__":

    main()