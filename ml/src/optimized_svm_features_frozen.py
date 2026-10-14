import json
import math
import re
from collections import Counter
from pathlib import Path

import numpy as np
import pandas as pd

from scipy.sparse import csr_matrix, hstack

from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import (
    accuracy_score,
    average_precision_score,
    confusion_matrix,
    f1_score,
    precision_score,
    recall_score,
    roc_auc_score,
)
from sklearn.svm import LinearSVC


# =========================================================
# BETGUARD
# LINEAR MODEL OPTIMIZATION
# =========================================================
#
# This experiment:
#
# - reuses the existing TRAIN + VALIDATION splits
# - DOES NOT read baseline_test.csv
# - DOES NOT replace the deployed model
# - compares optimized Logistic Regression vs Linear SVM
# - combines character TF-IDF with lexical domain features
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

SEARCH_RESULTS_FILE = Path(
    "reports/optimized_linear_validation_search.csv"
)

BEST_CANDIDATE_FILE = Path(
    "reports/optimized_linear_best_candidate.json"
)

BEST_PREDICTIONS_FILE = Path(
    "reports/optimized_linear_validation_predictions.csv"
)

BEST_MISCLASSIFIED_FILE = Path(
    "reports/optimized_linear_validation_misclassified.csv"
)


# =========================================================
# SEARCH SPACE
# =========================================================

NGRAM_RANGES = [
    (2, 5),
    (3, 5),
    (2, 6),
    (3, 6),
]

MIN_DF_VALUES = [
    1,
    2,
]

C_VALUES = [
    0.05,
    0.1,
    0.25,
    0.5,
    1.0,
    2.0,
    5.0,
]


# =========================================================
# GENERIC GAMBLING TERMS
# =========================================================
#
# These are general lexical features.
# They were NOT created from the test-set errors.
#
# =========================================================

GAMBLING_TERMS = [
    "casino",
    "poker",
    "slot",
    "slots",
    "bingo",
    "jackpot",
    "sportsbook",
    "wager",
    "gambling",
    "lotto",
    "lottery",
    "roulette",
    "blackjack",
]


# Bet needs slightly more careful matching because
# ordinary words such as "alphabet" contain "bet".

BET_PATTERN = re.compile(
    r"(^|[.\-])bet|bet([0-9]|[.\-]|$)"
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
# LOAD EXISTING SPLIT
# =========================================================

def load_split(path):

    if not path.exists():

        raise FileNotFoundError(
            f"\nMissing split file:\n"
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
# LEAKAGE CHECK
# =========================================================

def check_leakage(
    train_df,
    validation_df
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

    overlap = (
        train_groups
        &
        validation_groups
    )

    if overlap:

        raise RuntimeError(
            "Domain-family leakage detected "
            "between train and validation."
        )

    print(
        "\nDomain-family leakage check: PASSED"
    )

    print(
        "Train/validation overlap: 0"
    )


# =========================================================
# ENTROPY
# =========================================================

def shannon_entropy(text):

    if not text:

        return 0.0

    counts = Counter(
        text
    )

    total = len(
        text
    )

    entropy = 0.0

    for count in counts.values():

        probability = (
            count
            /
            total
        )

        entropy -= (
            probability
            *
            math.log2(
                probability
            )
        )

    return entropy


# =========================================================
# LONGEST DIGIT RUN
# =========================================================

def longest_digit_run(text):

    longest = 0
    current = 0

    for character in text:

        if character.isdigit():

            current += 1

            longest = max(
                longest,
                current
            )

        else:

            current = 0

    return longest


# =========================================================
# LEXICAL DOMAIN FEATURES
# =========================================================

def lexical_feature_vector(domain):

    domain = normalize_domain(
        domain
    )

    length = max(
        len(domain),
        1
    )

    digit_count = sum(
        character.isdigit()
        for character in domain
    )

    hyphen_count = domain.count(
        "-"
    )

    dot_count = domain.count(
        "."
    )

    unique_character_ratio = (
        len(
            set(domain)
        )
        /
        length
    )

    entropy = shannon_entropy(
        domain
    )

    if "." in domain:

        tld = domain.rsplit(
            ".",
            1
        )[-1]

    else:

        tld = ""

    longest_digits = longest_digit_run(
        domain
    )

    generic_term_flags = [
        1.0
        if term in domain
        else 0.0
        for term in GAMBLING_TERMS
    ]

    bet_flag = (
        1.0
        if BET_PATTERN.search(
            domain
        )
        else 0.0
    )

    keyword_count = (
        sum(
            generic_term_flags
        )
        +
        bet_flag
    )

    features = [
        # Domain length
        min(
            length / 63.0,
            1.0
        ),

        # Percentage of numeric characters
        digit_count / length,

        # Percentage of hyphens
        hyphen_count / length,

        # Number of domain levels
        min(
            dot_count / 5.0,
            1.0
        ),

        # Character diversity
        unique_character_ratio,

        # Character entropy
        min(
            entropy / 6.0,
            1.0
        ),

        # TLD length
        min(
            len(tld) / 15.0,
            1.0
        ),

        # Long numeric sequences
        min(
            longest_digits / 10.0,
            1.0
        ),

        # Common numeric gambling patterns
        1.0
        if "777" in domain
        else 0.0,

        1.0
        if "888" in domain
        else 0.0,

        # Carefully matched "bet"
        bet_flag,

        # Total number of gambling indicators
        min(
            keyword_count / 4.0,
            1.0
        ),
    ]

    features.extend(
        generic_term_flags
    )

    return features


# =========================================================
# BUILD LEXICAL MATRIX
# =========================================================

def build_lexical_matrix(domains):

    rows = [
        lexical_feature_vector(
            domain
        )
        for domain in domains
    ]

    return csr_matrix(
        np.asarray(
            rows,
            dtype=np.float64
        )
    )


# =========================================================
# BUILD COMBINED FEATURES
# =========================================================

def build_feature_matrices(
    train_domains,
    validation_domains,
    ngram_range,
    min_df
):

    vectorizer = TfidfVectorizer(
        analyzer="char",
        ngram_range=ngram_range,
        lowercase=True,
        min_df=min_df,
        sublinear_tf=True,
        norm="l2",
    )

    train_tfidf = (
        vectorizer.fit_transform(
            train_domains
        )
    )

    validation_tfidf = (
        vectorizer.transform(
            validation_domains
        )
    )

    train_lexical = (
        build_lexical_matrix(
            train_domains
        )
    )

    validation_lexical = (
        build_lexical_matrix(
            validation_domains
        )
    )

    train_features = hstack(
        [
            train_tfidf,
            train_lexical,
        ],
        format="csr"
    )

    validation_features = hstack(
        [
            validation_tfidf,
            validation_lexical,
        ],
        format="csr"
    )

    return (
        train_features,
        validation_features,
        vectorizer,
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
        predictions,
        labels=[
            0,
            1
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
# FIND BEST VALIDATION THRESHOLDS
# =========================================================

def find_best_thresholds(
    y_true,
    scores
):

    unique_scores = np.unique(
        scores
    )

    if len(unique_scores) == 1:

        thresholds = np.array(
            [
                unique_scores[0]
            ]
        )

    else:

        midpoints = (
            unique_scores[:-1]
            +
            unique_scores[1:]
        ) / 2.0

        thresholds = np.concatenate(
            [
                [
                    unique_scores[0]
                    -
                    1e-12
                ],

                midpoints,

                [
                    unique_scores[-1]
                    +
                    1e-12
                ],
            ]
        )

    best_accuracy = None
    best_f1 = None

    for threshold in thresholds:

        metrics = calculate_metrics(
            y_true,
            scores,
            threshold
        )

        accuracy_key = (
            metrics[
                "accuracy"
            ],
            metrics[
                "precision"
            ],
            metrics[
                "f1"
            ],
            metrics[
                "recall"
            ],
        )

        f1_key = (
            metrics[
                "f1"
            ],
            metrics[
                "accuracy"
            ],
            metrics[
                "precision"
            ],
            metrics[
                "recall"
            ],
        )

        if best_accuracy is None:

            choose_accuracy = True

        else:

            choose_accuracy = (
                accuracy_key
                >
                best_accuracy[
                    "_key"
                ]
            )

        if choose_accuracy:

            best_accuracy = {
                **metrics,
                "_key":
                    accuracy_key,
            }

        if best_f1 is None:

            choose_f1 = True

        else:

            choose_f1 = (
                f1_key
                >
                best_f1[
                    "_key"
                ]
            )

        if choose_f1:

            best_f1 = {
                **metrics,
                "_key":
                    f1_key,
            }

    best_accuracy.pop(
        "_key"
    )

    best_f1.pop(
        "_key"
    )

    return (
        best_accuracy,
        best_f1,
    )


# =========================================================
# TRAIN MODEL
# =========================================================

def train_model(
    model_name,
    c_value,
    train_features,
    train_labels,
    validation_features,
    validation_labels
):

    if model_name == "logistic_regression":

        model = LogisticRegression(
            C=c_value,
            max_iter=5000,
            class_weight="balanced",
            random_state=RANDOM_STATE,
        )

        model.fit(
            train_features,
            train_labels
        )

        scores = (
            model.predict_proba(
                validation_features
            )[:, 1]
        )

    elif model_name == "linear_svm":

        model = LinearSVC(
            C=c_value,
            class_weight="balanced",
            random_state=RANDOM_STATE,
            max_iter=10000,
        )

        model.fit(
            train_features,
            train_labels
        )

        scores = (
            model.decision_function(
                validation_features
            )
        )

    else:

        raise ValueError(
            f"Unknown model: {model_name}"
        )

    (
        best_accuracy,
        best_f1,

    ) = find_best_thresholds(
        validation_labels,
        scores
    )

    ranking_metrics = {

        "roc_auc":
            float(
                roc_auc_score(
                    validation_labels,
                    scores
                )
            ),

        "average_precision":
            float(
                average_precision_score(
                    validation_labels,
                    scores
                )
            ),
    }

    return (
        scores,
        best_accuracy,
        best_f1,
        ranking_metrics,
    )


# =========================================================
# MAIN
# =========================================================

def main():

    print(
        "\n===================================="
    )

    print(
        " BETGUARD LINEAR MODEL OPTIMIZATION"
    )

    print(
        "===================================="
    )

    print(
        "\nThis experiment uses TRAIN + "
        "VALIDATION only."
    )

    print(
        "The existing TEST split is NOT read."
    )

    # -----------------------------------------------------
    # LOAD EXISTING DATA
    # -----------------------------------------------------

    train_df = load_split(
        TRAIN_SPLIT_FILE
    )

    validation_df = load_split(
        VALIDATION_SPLIT_FILE
    )

    check_leakage(
        train_df,
        validation_df
    )

    print(
        f"\nTRAIN samples: "
        f"{len(train_df)}"
    )

    print(
        f"VALIDATION samples: "
        f"{len(validation_df)}"
    )

    train_domains = (
        train_df[
            "domain"
        ]
    )

    validation_domains = (
        validation_df[
            "domain"
        ]
    )

    train_labels = (
        train_df[
            "label"
        ].to_numpy()
    )

    validation_labels = (
        validation_df[
            "label"
        ].to_numpy()
    )

    search_rows = []

    best_candidate = None
    best_candidate_scores = None

    total_feature_configs = (
        len(
            NGRAM_RANGES
        )
        *
        len(
            MIN_DF_VALUES
        )
    )

    feature_number = 0

    # -----------------------------------------------------
    # FEATURE SEARCH
    # -----------------------------------------------------

    for ngram_range in NGRAM_RANGES:

        for min_df in MIN_DF_VALUES:

            feature_number += 1

            print(
                "\n===================================="
            )

            print(
                f" FEATURE CONFIG "
                f"{feature_number}/"
                f"{total_feature_configs}"
            )

            print(
                "===================================="
            )

            print(
                f"\nN-gram range: "
                f"{ngram_range}"
            )

            print(
                f"min_df: "
                f"{min_df}"
            )

            (
                train_features,
                validation_features,
                vectorizer,

            ) = build_feature_matrices(
                train_domains,
                validation_domains,
                ngram_range,
                min_df
            )

            print(
                f"TF-IDF vocabulary: "
                f"{len(vectorizer.vocabulary_)}"
            )

            print(
                f"Combined features: "
                f"{train_features.shape[1]}"
            )

            # -------------------------------------------------
            # MODEL SEARCH
            # -------------------------------------------------

            for model_name in [
                "logistic_regression",
                "linear_svm",
            ]:

                for c_value in C_VALUES:

                    (
                        scores,
                        best_accuracy,
                        best_f1,
                        ranking_metrics,

                    ) = train_model(
                        model_name,
                        c_value,
                        train_features,
                        train_labels,
                        validation_features,
                        validation_labels
                    )

                    row = {

                        "model":
                            model_name,

                        "ngram_min":
                            int(
                                ngram_range[0]
                            ),

                        "ngram_max":
                            int(
                                ngram_range[1]
                            ),

                        "min_df":
                            int(
                                min_df
                            ),

                        "C":
                            float(
                                c_value
                            ),

                        "feature_count":
                            int(
                                train_features.shape[1]
                            ),

                        "best_accuracy_threshold":
                            best_accuracy[
                                "threshold"
                            ],

                        "best_accuracy":
                            best_accuracy[
                                "accuracy"
                            ],

                        "accuracy_precision":
                            best_accuracy[
                                "precision"
                            ],

                        "accuracy_recall":
                            best_accuracy[
                                "recall"
                            ],

                        "accuracy_f1":
                            best_accuracy[
                                "f1"
                            ],

                        "accuracy_false_positives":
                            best_accuracy[
                                "false_positives"
                            ],

                        "accuracy_false_negatives":
                            best_accuracy[
                                "false_negatives"
                            ],

                        "best_f1_threshold":
                            best_f1[
                                "threshold"
                            ],

                        "best_f1":
                            best_f1[
                                "f1"
                            ],

                        "f1_accuracy":
                            best_f1[
                                "accuracy"
                            ],

                        "f1_precision":
                            best_f1[
                                "precision"
                            ],

                        "f1_recall":
                            best_f1[
                                "recall"
                            ],

                        "roc_auc":
                            ranking_metrics[
                                "roc_auc"
                            ],

                        "average_precision":
                            ranking_metrics[
                                "average_precision"
                            ],
                    }

                    search_rows.append(
                        row
                    )

                    print(
                        f"{model_name:20s} "
                        f"C={c_value:<4} "
                        f"Acc="
                        f"{best_accuracy['accuracy']:.4f} "
                        f"Prec="
                        f"{best_accuracy['precision']:.4f} "
                        f"Rec="
                        f"{best_accuracy['recall']:.4f} "
                        f"F1="
                        f"{best_accuracy['f1']:.4f}"
                    )

                    candidate_key = (
                        best_accuracy[
                            "accuracy"
                        ],
                        best_accuracy[
                            "precision"
                        ],
                        best_accuracy[
                            "f1"
                        ],
                        ranking_metrics[
                            "roc_auc"
                        ],
                    )

                    if best_candidate is None:

                        choose = True

                    else:

                        current_key = (
                            best_candidate[
                                "validation_accuracy"
                            ],
                            best_candidate[
                                "validation_precision"
                            ],
                            best_candidate[
                                "validation_f1"
                            ],
                            best_candidate[
                                "roc_auc"
                            ],
                        )

                        choose = (
                            candidate_key
                            >
                            current_key
                        )

                    if choose:

                        best_candidate = {

                            "model":
                                model_name,

                            "ngram_range":
                                [
                                    int(
                                        ngram_range[0]
                                    ),

                                    int(
                                        ngram_range[1]
                                    ),
                                ],

                            "min_df":
                                int(
                                    min_df
                                ),

                            "C":
                                float(
                                    c_value
                                ),

                            "threshold":
                                float(
                                    best_accuracy[
                                        "threshold"
                                    ]
                                ),

                            "threshold_selected_for":
                                "validation accuracy",

                            "validation_accuracy":
                                float(
                                    best_accuracy[
                                        "accuracy"
                                    ]
                                ),

                            "validation_precision":
                                float(
                                    best_accuracy[
                                        "precision"
                                    ]
                                ),

                            "validation_recall":
                                float(
                                    best_accuracy[
                                        "recall"
                                    ]
                                ),

                            "validation_f1":
                                float(
                                    best_accuracy[
                                        "f1"
                                    ]
                                ),

                            "false_positives":
                                int(
                                    best_accuracy[
                                        "false_positives"
                                    ]
                                ),

                            "false_negatives":
                                int(
                                    best_accuracy[
                                        "false_negatives"
                                    ]
                                ),

                            "roc_auc":
                                float(
                                    ranking_metrics[
                                        "roc_auc"
                                    ]
                                ),

                            "average_precision":
                                float(
                                    ranking_metrics[
                                        "average_precision"
                                    ]
                                ),

                            "uses_lexical_features":
                                True,
                        }

                        best_candidate_scores = (
                            scores.copy()
                        )

    # -----------------------------------------------------
    # SAVE SEARCH TABLE
    # -----------------------------------------------------

    search_df = pd.DataFrame(
        search_rows
    )

    search_df = (
        search_df.sort_values(
            [
                "best_accuracy",
                "accuracy_precision",
                "accuracy_f1",
                "roc_auc",
            ],

            ascending=[
                False,
                False,
                False,
                False,
            ],
        )
    )

    SEARCH_RESULTS_FILE.parent.mkdir(
        parents=True,
        exist_ok=True
    )

    search_df.to_csv(
        SEARCH_RESULTS_FILE,
        index=False
    )

    # -----------------------------------------------------
    # SAVE BEST CONFIGURATION
    # -----------------------------------------------------

    with open(
        BEST_CANDIDATE_FILE,
        "w",
        encoding="utf-8"
    ) as file:

        json.dump(
            best_candidate,
            file,
            indent=4
        )

    best_predictions = (
        best_candidate_scores
        >=
        best_candidate[
            "threshold"
        ]
    ).astype(int)

    prediction_df = (
        validation_df.copy()
    )

    prediction_df[
        "optimization_score"
    ] = best_candidate_scores

    prediction_df[
        "predicted_label"
    ] = best_predictions

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
        BEST_PREDICTIONS_FILE,
        index=False
    )

    # -----------------------------------------------------
    # SAVE MISCLASSIFICATIONS
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
            "optimization_score"
        ]
        -
        best_candidate[
            "threshold"
        ]
    ).abs()

    misclassified = (
        misclassified.sort_values(
            "distance_from_threshold"
        )
    )

    misclassified.to_csv(
        BEST_MISCLASSIFIED_FILE,
        index=False
    )

    # -----------------------------------------------------
    # DISPLAY RESULTS
    # -----------------------------------------------------

    print(
        "\n===================================="
    )

    print(
        " TOP VALIDATION CONFIGURATIONS"
    )

    print(
        "===================================="
    )

    columns = [
        "model",
        "ngram_min",
        "ngram_max",
        "min_df",
        "C",
        "best_accuracy",
        "accuracy_precision",
        "accuracy_recall",
        "accuracy_f1",
        "roc_auc",
    ]

    print(
        "\n"
        +
        search_df[
            columns
        ]
        .head(10)
        .to_string(
            index=False
        )
    )

    print(
        "\n===================================="
    )

    print(
        " BEST VALIDATION CANDIDATE"
    )

    print(
        "===================================="
    )

    print(
        f"\nModel: "
        f"{best_candidate['model']}"
    )

    print(
        f"N-gram range: "
        f"{tuple(best_candidate['ngram_range'])}"
    )

    print(
        f"min_df: "
        f"{best_candidate['min_df']}"
    )

    print(
        f"C: "
        f"{best_candidate['C']}"
    )

    print(
        f"Threshold: "
        f"{best_candidate['threshold']:.6f}"
    )

    print(
        f"\nValidation Accuracy: "
        f"{best_candidate['validation_accuracy']:.4f}"
    )

    print(
        f"Validation Precision: "
        f"{best_candidate['validation_precision']:.4f}"
    )

    print(
        f"Validation Recall: "
        f"{best_candidate['validation_recall']:.4f}"
    )

    print(
        f"Validation F1: "
        f"{best_candidate['validation_f1']:.4f}"
    )

    print(
        f"ROC-AUC: "
        f"{best_candidate['roc_auc']:.4f}"
    )

    print(
        f"PR-AUC: "
        f"{best_candidate['average_precision']:.4f}"
    )

    print(
        f"False Positives: "
        f"{best_candidate['false_positives']}"
    )

    print(
        f"False Negatives: "
        f"{best_candidate['false_negatives']}"
    )

    print(
        f"\nValidation errors: "
        f"{len(misclassified)}"
    )

    # -----------------------------------------------------
    # TARGET STATUS
    # -----------------------------------------------------

    if (
        best_candidate[
            "validation_accuracy"
        ]
        >=
        0.90
    ):

        print(
            "\nTARGET STATUS:"
        )

        print(
            ">= 90% VALIDATION ACCURACY REACHED"
        )

        print(
            "\nDo NOT deploy yet."
        )

        print(
            "Freeze this configuration and "
            "perform an independent evaluation."
        )

    else:

        print(
            "\nTARGET STATUS:"
        )

        print(
            "90% VALIDATION ACCURACY "
            "NOT YET REACHED"
        )

        print(
            "\nNext step should be verified "
            "dataset expansion."
        )

    print(
        "\nFiles saved:"
    )

    print(
        SEARCH_RESULTS_FILE
    )

    print(
        BEST_CANDIDATE_FILE
    )

    print(
        BEST_PREDICTIONS_FILE
    )

    print(
        BEST_MISCLASSIFIED_FILE
    )

    print(
        "\nIMPORTANT:"
    )

    print(
        "baseline_test.csv was NOT used."
    )

    print(
        "The deployed BetGuard model "
        "was NOT changed."
    )


if __name__ == "__main__":

    main()