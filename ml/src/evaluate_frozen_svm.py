import json
from pathlib import Path

import numpy as np
import pandas as pd

from scipy.sparse import hstack
from sklearn.svm import LinearSVC
from sklearn.metrics import (
    accuracy_score,
    precision_score,
    recall_score,
    f1_score,
    roc_auc_score,
    average_precision_score,
    confusion_matrix,
)

from optimized_svm_features_frozen import (
    load_split,
    build_feature_matrices,
    build_lexical_matrix,
)


# =========================================================
# BETGUARD - FROZEN OPTIMIZED SVM EVALUATION
# =========================================================
#
# No hyperparameter tuning.
# No threshold optimization.
# No changes to the deployed model.
#
# Uses the saved winning validation configuration.
# Evaluates the original historical test benchmark.
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

CONFIG_FILE = Path(
    "reports/optimized_svm_frozen_candidate.json"
)

METRICS_FILE = Path(
    "reports/optimized_svm_historical_test_metrics.json"
)

PREDICTIONS_FILE = Path(
    "reports/optimized_svm_historical_test_predictions.csv"
)


def evaluate(y_true, scores, threshold):

    predicted = (scores >= threshold).astype(int)

    tn, fp, fn, tp = confusion_matrix(
        y_true,
        predicted,
        labels=[0, 1],
    ).ravel()

    metrics = {
        "accuracy": float(
            accuracy_score(y_true, predicted)
        ),
        "precision": float(
            precision_score(
                y_true, predicted, zero_division=0
            )
        ),
        "recall": float(
            recall_score(
                y_true, predicted, zero_division=0
            )
        ),
        "f1": float(
            f1_score(
                y_true, predicted, zero_division=0
            )
        ),
        "roc_auc": float(
            roc_auc_score(y_true, scores)
        ),
        "average_precision": float(
            average_precision_score(y_true, scores)
        ),
        "true_negatives": int(tn),
        "false_positives": int(fp),
        "false_negatives": int(fn),
        "true_positives": int(tp),
        "correct": int(tn + tp),
        "total": int(len(y_true)),
    }

    return metrics, predicted


def main():

    print("\nBETGUARD - FROZEN SVM EVALUATION")

    if not CONFIG_FILE.exists():
        raise FileNotFoundError(CONFIG_FILE)

    config = json.loads(
        CONFIG_FILE.read_text(encoding="utf-8")
    )

    # Confirm the selected configuration is unchanged.

    if (
        config["model"] != "linear_svm"
        or config["ngram_range"] != [2, 6]
        or config["min_df"] != 1
        or config["C"] != 0.5
    ):
        raise RuntimeError(
            "Frozen configuration differs from "
            "the selected optimization result."
        )

    train = load_split(TRAIN_FILE)
    validation = load_split(VALIDATION_FILE)
    test = load_split(TEST_FILE)

    if (
        len(train), len(validation), len(test)
    ) != (507, 169, 170):
        raise RuntimeError(
            "Dataset split sizes have changed."
        )

    # Verify zero family overlap.

    groups = [
        set(df["domain_family"])
        for df in (train, validation, test)
    ]

    if (
        groups[0] & groups[1]
        or groups[0] & groups[2]
        or groups[1] & groups[2]
    ):
        raise RuntimeError(
            "Domain-family leakage detected."
        )

    print("\nLeakage check: PASSED")
    print("Training:", len(train))
    print("Validation:", len(validation))
    print("Test:", len(test))

    # Fit features ONLY on original training domains.

    x_train, x_validation, vectorizer = (
        build_feature_matrices(
            train["domain"],
            validation["domain"],
            tuple(config["ngram_range"]),
            config["min_df"],
        )
    )

    model = LinearSVC(
        C=config["C"],
        class_weight="balanced",
        random_state=42,
        max_iter=10000,
    )

    model.fit(
        x_train,
        train["label"],
    )

    threshold = config["threshold"]

    # Reproduce validation accuracy before testing.

    validation_scores = model.decision_function(
        x_validation
    )

    validation_metrics, _ = evaluate(
        validation["label"].to_numpy(),
        validation_scores,
        threshold,
    )

    print("\nVALIDATION REPRODUCTION")
    print(
        "Accuracy:",
        f"{validation_metrics['accuracy']:.4%}"
    )

    expected = config["validation_accuracy"]

    if not np.isclose(
        validation_metrics["accuracy"],
        expected,
        atol=1e-8,
    ):
        raise RuntimeError(
            "Validation result does not match "
            "the frozen experiment. Test aborted."
        )

    print("Frozen result verified.")

    # The original test set is evaluated only after
    # reproducing the frozen validation result.

    test_tfidf = vectorizer.transform(
        test["domain"]
    )

    test_lexical = build_lexical_matrix(
        test["domain"]
    )

    x_test = hstack(
        [test_tfidf, test_lexical],
        format="csr",
    )

    test_scores = model.decision_function(
        x_test
    )

    test_metrics, predictions = evaluate(
        test["label"].to_numpy(),
        test_scores,
        threshold,
    )

    print("\nHISTORICAL TEST BENCHMARK")
    print("=========================")

    for key in [
        "accuracy",
        "precision",
        "recall",
        "f1",
        "roc_auc",
        "average_precision",
    ]:
        print(
            f"{key}: {test_metrics[key]:.4%}"
        )

    print(
        "False positives:",
        test_metrics["false_positives"],
    )

    print(
        "False negatives:",
        test_metrics["false_negatives"],
    )

    print(
        "Correct:",
        test_metrics["correct"],
        "/",
        test_metrics["total"],
    )

    print("\nConfusion Matrix:")

    print(
        confusion_matrix(
            test["label"],
            predictions,
            labels=[0, 1],
        )
    )

    # Save separate reports without modifying baseline.

    METRICS_FILE.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    report = {
        "evaluation_type": "historical_test_benchmark",
        "independent_new_holdout": False,
        "configuration": config,
        "validation_reproduction": validation_metrics,
        "test_metrics": test_metrics,
    }

    METRICS_FILE.write_text(
        json.dumps(report, indent=4),
        encoding="utf-8",
    )

    output = test.copy()

    output["svm_decision_score"] = test_scores
    output["predicted_label"] = predictions
    output["correct"] = (
        output["label"]
        == output["predicted_label"]
    )

    output.to_csv(
        PREDICTIONS_FILE,
        index=False,
    )

    print("\nEvaluation completed.")
    print("Metrics:", METRICS_FILE)
    print("Predictions:", PREDICTIONS_FILE)
    print("\nDeployed model unchanged.")


if __name__ == "__main__":
    main()