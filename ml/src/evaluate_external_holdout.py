import json
from pathlib import Path

import pandas as pd

from sklearn.metrics import (
    accuracy_score,
    confusion_matrix,
    f1_score,
    precision_score,
    recall_score,
)

from decision_engine import (
    AUTO_BLOCK_THRESHOLD,
    WARNING_THRESHOLD,
    USER_ALLOWLIST_FILE,
    USER_BLOCKLIST_FILE,
    decide_domain,
    load_gambling_blocklist,
    load_model,
    load_text_list,
    predict_ml_score,
)


# =========================================================
# BETGUARD
# EXTERNAL HOLDOUT EVALUATION V2
# =========================================================
#
# We evaluate TWO different concepts:
#
# HARD BLOCKING
#
#     Did BetGuard automatically block it?
#
#
# INTERVENTION
#
#     Did BetGuard either:
#
#         BLOCK
#
#     or
#
#         WARN
#
#
# This distinction is important because warnings allow
# BetGuard to intervene without falsely hard-blocking
# uncertain legitimate websites.
#
# =========================================================


HOLDOUT_FILE = Path(
    "data/processed/external_holdout.csv"
)

PREDICTIONS_FILE = Path(
    "reports/external_holdout_predictions_v2.csv"
)

METRICS_FILE = Path(
    "reports/external_holdout_metrics_v2.json"
)


# =========================================================
# METRICS
# =========================================================

def binary_metrics(
    y_true,
    y_pred
):

    matrix = confusion_matrix(
        y_true,
        y_pred,
        labels=[
            0,
            1,
        ]
    )


    tn, fp, fn, tp = (
        matrix.ravel()
    )


    return {
        "accuracy":
            float(
                accuracy_score(
                    y_true,
                    y_pred
                )
            ),

        "precision":
            float(
                precision_score(
                    y_true,
                    y_pred,
                    zero_division=0
                )
            ),

        "recall":
            float(
                recall_score(
                    y_true,
                    y_pred,
                    zero_division=0
                )
            ),

        "f1":
            float(
                f1_score(
                    y_true,
                    y_pred,
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

        "confusion_matrix":
            matrix.tolist(),
    }


# =========================================================
# MAIN
# =========================================================

def main():

    print(
        "\n===================================="
    )

    print(
        " BETGUARD EXTERNAL HOLDOUT V2"
    )

    print(
        "===================================="
    )


    if not HOLDOUT_FILE.exists():

        raise FileNotFoundError(
            f"\nMissing:\n"
            f"{HOLDOUT_FILE}"
        )


    holdout = pd.read_csv(
        HOLDOUT_FILE
    )


    print(
        "\nHoldout domains:",
        len(
            holdout
        )
    )


    print(
        "\nClass distribution:"
    )

    print(
        holdout[
            "label"
        ].value_counts()
        .sort_index()
    )


    # =====================================================
    # LOAD ENGINE
    # =====================================================

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


    # =====================================================
    # EVALUATE
    # =====================================================

    rows = []


    for _, row in holdout.iterrows():

        domain = row[
            "domain"
        ]


        true_label = int(
            row[
                "label"
            ]
        )


        decision = decide_domain(
            domain,
            model,
            config,
            gambling_lookup,
            allowlist,
            user_blocklist
        )


        # Raw ML score is measured separately.

        ml_score = predict_ml_score(
            domain,
            model,
            config
        )


        hard_block_prediction = int(
            decision[
                "enforcement_action"
            ]
            ==
            "BLOCK"
        )


        intervention_prediction = int(
            decision[
                "intervention"
            ]
            in
            [
                "BLOCK",
                "WARN",
            ]
        )


        rows.append(
            {
                "domain":
                    domain,

                "true_label":
                    true_label,

                "meaning":
                    row[
                        "meaning"
                    ],

                "label_source":
                    row[
                        "source"
                    ],

                "enforcement_action":
                    decision[
                        "enforcement_action"
                    ],

                "intervention":
                    decision[
                        "intervention"
                    ],

                "risk_status":
                    decision[
                        "risk_status"
                    ],

                "decision_source":
                    decision[
                        "decision_source"
                    ],

                "blocklist_match":
                    decision.get(
                        "matched_domain"
                    ),

                "ml_score":
                    float(
                        ml_score
                    ),

                "hard_block_prediction":
                    hard_block_prediction,

                "intervention_prediction":
                    intervention_prediction,

                "ml_candidate_prediction":
                    int(
                        ml_score
                        >=
                        float(
                            config[
                                "threshold"
                            ]
                        )
                    ),

                "ml_warning_prediction":
                    int(
                        ml_score
                        >=
                        WARNING_THRESHOLD
                    ),

                "ml_autoblock_prediction":
                    int(
                        ml_score
                        >=
                        AUTO_BLOCK_THRESHOLD
                    ),
            }
        )


    results = pd.DataFrame(
        rows
    )


    PREDICTIONS_FILE.parent.mkdir(
        parents=True,
        exist_ok=True
    )


    results.to_csv(
        PREDICTIONS_FILE,
        index=False
    )


    y_true = results[
        "true_label"
    ].to_numpy()


    # =====================================================
    # HARD BLOCK METRICS
    # =====================================================

    hard_block_metrics = (
        binary_metrics(
            y_true,
            results[
                "hard_block_prediction"
            ].to_numpy()
        )
    )


    # =====================================================
    # INTERVENTION METRICS
    # =====================================================

    intervention_metrics = (
        binary_metrics(
            y_true,
            results[
                "intervention_prediction"
            ].to_numpy()
        )
    )


    # =====================================================
    # RAW ML METRICS
    # =====================================================

    ml_candidate_metrics = (
        binary_metrics(
            y_true,
            results[
                "ml_candidate_prediction"
            ].to_numpy()
        )
    )


    ml_warning_metrics = (
        binary_metrics(
            y_true,
            results[
                "ml_warning_prediction"
            ].to_numpy()
        )
    )


    ml_autoblock_metrics = (
        binary_metrics(
            y_true,
            results[
                "ml_autoblock_prediction"
            ].to_numpy()
        )
    )


    # =====================================================
    # COUNTS
    # =====================================================

    gambling = results[
        results[
            "true_label"
        ]
        ==
        1
    ]


    benign = results[
        results[
            "true_label"
        ]
        ==
        0
    ]


    gambling_blocklist = int(
        (
            gambling[
                "decision_source"
            ]
            ==
            "verified_gambling_blocklist"
        ).sum()
    )


    gambling_ml_blocked = int(
        (
            gambling[
                "decision_source"
            ]
            ==
            "ml_high_risk"
        ).sum()
    )


    gambling_warned = int(
        (
            gambling[
                "intervention"
            ]
            ==
            "WARN"
        ).sum()
    )


    gambling_no_intervention = int(
        (
            gambling[
                "intervention"
            ]
            ==
            "NONE"
        ).sum()
    )


    benign_blocked = int(
        (
            benign[
                "intervention"
            ]
            ==
            "BLOCK"
        ).sum()
    )


    benign_warned = int(
        (
            benign[
                "intervention"
            ]
            ==
            "WARN"
        ).sum()
    )


    benign_clean_allow = int(
        (
            benign[
                "intervention"
            ]
            ==
            "NONE"
        ).sum()
    )


    # =====================================================
    # SAVE
    # =====================================================

    metrics = {
        "holdout_size":
            int(
                len(
                    results
                )
            ),

        "warning_threshold":
            WARNING_THRESHOLD,

        "automatic_block_threshold":
            AUTO_BLOCK_THRESHOLD,

        "hard_block_metrics":
            hard_block_metrics,

        "intervention_metrics":
            intervention_metrics,

        "ml_only_candidate_threshold":
            ml_candidate_metrics,

        "ml_only_warning_threshold":
            ml_warning_metrics,

        "ml_only_autoblock_threshold":
            ml_autoblock_metrics,

        "pipeline": {
            "gambling_blocklist_blocked":
                gambling_blocklist,

            "gambling_ml_blocked":
                gambling_ml_blocked,

            "gambling_warned":
                gambling_warned,

            "gambling_no_intervention":
                gambling_no_intervention,

            "benign_blocked":
                benign_blocked,

            "benign_warned":
                benign_warned,

            "benign_clean_allow":
                benign_clean_allow,
        },
    }


    with open(
        METRICS_FILE,
        "w",
        encoding="utf-8"
    ) as file:

        json.dump(
            metrics,
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
        " HARD BLOCK PERFORMANCE"
    )

    print(
        "===================================="
    )


    print(
        "\nPrecision:",
        f"{hard_block_metrics['precision']:.4f}"
    )

    print(
        "Recall:",
        f"{hard_block_metrics['recall']:.4f}"
    )

    print(
        "F1:",
        f"{hard_block_metrics['f1']:.4f}"
    )

    print(
        "False positives:",
        hard_block_metrics[
            "false_positives"
        ]
    )

    print(
        "False negatives:",
        hard_block_metrics[
            "false_negatives"
        ]
    )


    print(
        "\n===================================="
    )

    print(
        " INTERVENTION PERFORMANCE"
    )

    print(
        "===================================="
    )


    print(
        "\nPrecision:",
        f"{intervention_metrics['precision']:.4f}"
    )

    print(
        "Recall:",
        f"{intervention_metrics['recall']:.4f}"
    )

    print(
        "F1:",
        f"{intervention_metrics['f1']:.4f}"
    )

    print(
        "Benign interventions:",
        intervention_metrics[
            "false_positives"
        ]
    )

    print(
        "Gambling with no intervention:",
        intervention_metrics[
            "false_negatives"
        ]
    )


    print(
        "\n===================================="
    )

    print(
        " PIPELINE BREAKDOWN"
    )

    print(
        "===================================="
    )


    print(
        "\nGambling blocked by blocklist:",
        gambling_blocklist
    )

    print(
        "Gambling blocked by ML:",
        gambling_ml_blocked
    )

    print(
        "Gambling warned:",
        gambling_warned
    )

    print(
        "Gambling with no intervention:",
        gambling_no_intervention
    )


    print(
        "\nBenign hard-blocked:",
        benign_blocked
    )

    print(
        "Benign warned:",
        benign_warned
    )

    print(
        "Benign cleanly allowed:",
        benign_clean_allow
    )


    # =====================================================
    # MISSED GAMBLING
    # =====================================================

    missed = gambling[
        gambling[
            "intervention"
        ]
        ==
        "NONE"
    ]


    if len(
        missed
    ) > 0:

        print(
            "\nGambling domains with "
            "NO intervention:"
        )

        print(
            missed[
                [
                    "domain",
                    "ml_score",
                    "label_source",
                ]
            ]
            .sort_values(
                "ml_score",
                ascending=False
            )
            .to_string(
                index=False
            )
        )


    # =====================================================
    # BENIGN WARNINGS
    # =====================================================

    warned_benign = benign[
        benign[
            "intervention"
        ]
        ==
        "WARN"
    ]


    if len(
        warned_benign
    ) > 0:

        print(
            "\nBenign domains receiving warnings:"
        )

        print(
            warned_benign[
                [
                    "domain",
                    "ml_score",
                ]
            ]
            .sort_values(
                "ml_score",
                ascending=False
            )
            .to_string(
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
        "\nPredictions:"
    )

    print(
        PREDICTIONS_FILE
    )


    print(
        "\nMetrics:"
    )

    print(
        METRICS_FILE
    )


if __name__ == "__main__":

    main()