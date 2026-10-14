# Reconciled algorithm comparison

The table is calculated from saved per-domain predictions and checked against
the actual trusted local model binaries. All rows use the same 846-example
benchmark (507 train / 169 validation / 170 historical test). Values are
percentages except FP/FN. Validation accuracies were recalculated using each
model's saved threshold and the serialized model (the optimized model was
reproduced/exported separately). `evaluation/reconciliation.json` records zero
metric discrepancies, matching predicted labels and matching serialized-model
scores within 1e-6 for all five experiments. These are classifier-only metrics,
not end-to-end blocking accuracy or calibrated-confidence measurements.

## Results

| Algorithm / evaluation point | Validation accuracy | Historical test accuracy | Precision | Recall | F1 | ROC-AUC | FP | FN |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| Baseline Logistic Regression, validation-F1 threshold | 87.57 | 85.88 | 81.44 | 92.94 | 86.81 | 96.12 | 18 | 6 |
| Hybrid Logistic Regression, validation-F1 threshold | 86.39 | 86.47 | 83.70 | 90.59 | 87.01 | 92.48 | 15 | 8 |
| Ordinary LinearSVC | 89.35 | 86.47 | 82.29 | 92.94 | 87.29 | 96.96 | 17 | 6 |
| Random Forest | 86.98 | 87.65 | 87.21 | 88.24 | 87.72 | 95.06 | 11 | 10 |
| Frozen optimized LinearSVC | 93.49 | 92.35 | 88.30 | 97.65 | 92.74 | 97.91 | 11 | 2 |
| Baseline, selected warning classification point | 87.57 | 90.00 | 89.53 | 90.59 | 90.06 | 96.12 | 9 | 8 |
| Baseline, 0.70 automatic-block point (ML only) | 72.78 | 72.94 | 100.00 | 45.88 | 62.90 | 96.12 | 0 | 46 |

The last two rows distinguish selection/automatic enforcement from the
validation-F1 baseline comparison. Actual runtime warnings use the rounded
constant 0.512117; the selection report uses 0.5121174012449518. WARN remains
allowed. AUC summarizes ranking and therefore stays constant across different
thresholds for the same model's scores.

| Algorithm | Features | Training configuration / classification threshold | Strength / limitation |
| --- | --- | --- | --- |
| Baseline LR | Character TF-IDF (3,5), min_df=2, sublinear TF, L2 normalization | balanced weights, max_iter=3000, random_state=42, default C=1; F1 point 0.48498417601354515; selected point 0.5121174012449518 | Simple sparse baseline; substring correlations can block ordinary domains; probability output is not independently calibrated here |
| Hybrid LR | Same TF-IDF plus DomainLexicalTransformer and StandardScaler | balanced, max_iter=3000, random_state=42, default C=1; 0.49930907524659235 | Explicit lexical structure, but this experiment did not improve ranking or recall over baseline |
| Ordinary LinearSVC | Character TF-IDF (3,5), min_df=2, sublinear TF, L2 normalization; no lexical | C=0.5, balanced, random_state=42, max_iter=10000; margin -0.07233326051015576 | Sparse margin model; different features and threshold from optimized SVM |
| Random Forest | Character TF-IDF (3,5), min_df=2 | 500 trees, max_depth=None, min_samples_leaf=1, max_features=log2, balanced; probability threshold 0.444 | Nonlinear ensemble comparator; local binary approximately 13.2 MB versus small linear artifacts; no claim about runtime speed without timing |
| Optimized LinearSVC | Character TF-IDF (2,6), min_df=1 + 25 unscaled lexical features in frozen order | C=0.5, balanced, random_state=42, max_iter=10000; margin -0.05278699316952151 selected for validation accuracy | Best historical recall/F1/AUC here; uncalibrated margin, false positives and domain shift remain |

Optimization compared linear algorithms, n-gram ranges, min_df and C on
train/validation. Historical metrics alone cannot isolate whether the margin
loss, broader vocabulary, lexical features or validation threshold caused the
improvement; that would require controlled ablation experiments. The saved
frozen export fits only the original train split and performs no fresh tuning.

## Corrections to earlier recorded numbers

The supplied baseline test tuple (87.65% accuracy, 87.21% precision, 88.24%
recall, 87.72% F1, 11 FP / 10 FN) does **not** describe
`baseline_test_predictions.csv`. Those values match the local Random Forest
test counts/metrics; the supplied AUC 93.04% instead matches the baseline's
validation AUC (0.930392...). This identifies matching local evidence but does
not establish how the earlier table was assembled. Use the reconciled baseline
row above. Do not rewrite historical reports to hide the discrepancy.

The hybrid and optimized SVM historical test values in the request agree with
local saved predictions. The baseline confusion matrix at the F1 point is
[[67,18],[6,79]]; hybrid [[70,15],[8,77]]; optimized [[74,11],[2,83]]. The baseline
deployment manifest's 90.00% test accuracy belongs to the separate selected
precision operating point, not the F1 point or 0.70 blocking policy.

## Defense discussion

Logistic Regression provides a straightforward regularized linear baseline
for sparse text features and binary labels. Its simplicity makes changes in
features and evaluation policy easier to assess before considering additional
models. This is the design rationale, not a recovered statement from an
unavailable historical author log. [Official logistic-regression documentation](https://scikit-learn.org/stable/modules/linear_model.html#logistic-regression).

Character TF-IDF represents a hostname using overlapping character sequences.
This captures fragments across labels and spelling variants without requiring
natural-language words. TF-IDF weights vary with frequency in the training
corpus; fitting only the training split prevents vocabulary/IDF information
from leaking from evaluation rows. [Official feature-extraction documentation](https://scikit-learn.org/stable/modules/feature_extraction.html).

The optimized lexical vector has 12 base quantities/flags followed by 13
gambling-term flags: capped length, digit/hyphen/dot ratios, unique-character
ratio, entropy, TLD length, longest digit run, 777/888 flags, boundary-aware bet
flag, keyword count, then casino/poker/slot/slots/bingo/jackpot/sportsbook/wager/
gambling/lotto/lottery/roulette/blackjack flags. The fitted matrix has 14,051
TF-IDF columns followed by these 25 values, total 14,076. Lexical cues describe
the domain string; they do not inspect website content or prove wagering.

The optimized SVM's historical improvement is an observed result: versus the
F1 baseline it reduces false negatives from six to two and false positives
from 18 to 11. Versus the selected baseline point it reduces false negatives
from eight to two while increasing false positives from nine to 11. These
different operating points express different tradeoffs. They do not establish
that SVM should automatically block every positive classification.

Recall matters because missed gambling examples remain available if no rule
matches. False positives matter because incorrect blocks disrupt school,
banking, work and ordinary browsing. Precision and intervention policy must
therefore be assessed together; maximized validation accuracy is not an
automatic-blocking safety objective.

LinearSVC is a linear support-vector classifier, not a boosting algorithm.
Its decision function produces signed margins whose orientation is checked
against classes [0,1]. These margins are not probabilities or percentages.
An independently evaluated calibration method would be needed for probability
claims. [Official LinearSVC documentation](https://scikit-learn.org/stable/modules/generated/sklearn.svm.LinearSVC.html).

Validation supports model/threshold selection; historical test reports the
fixed model on different saved rows. Repeated examination of historical test
limits its independence even when no test examples were fitted. Family-based
splitting reduces one leakage mode, but related brands/aliases across distinct
registrable domains and imperfect labels remain. [Official evaluation/splitting documentation](https://scikit-learn.org/stable/modules/cross_validation.html).

## Real-world limitations and additional observations

Exploratory reuse of the previously examined 98-row external holdout yields
optimized SVM accuracy 81.63%, precision 73.17%, recall 81.08%, F1 76.92%,
AUC 90.74%, 11 FP and seven FN. It is not a new independent test. Among 106
unverified Philippine benign candidates, 49 SVM-positive predictions were
observed; without verified labels these are not measured false positives or
accuracy. `evaluation/domain_probes.csv` records margins for BSP/BDO/BPI,
education, government, ordinary domains and lexical false-positive examples.
The baseline also already blocks alphabet.com in the probe; manual exceptions
remain available, and this audit does not hide that pre-existing limitation.

All 85 historical gambling test rows match the maintained runtime blocklist,
so the full existing pipeline blocks them without using ML. All 85 historical
benign rows remain allowed under current enforcement. That fixture result is
strongly dependent on the historical labels/reference collection and must not
be advertised as independent 100% real-world accuracy. The 13 differences in
`historical_shadow_comparison.csv` compare **full baseline enforcement** with
**SVM classification**, not two equivalent automatic-block policies.

A balanced, small, source-selected benchmark cannot estimate the prevalence
or operational precision of traffic from Philippine school networks. Labels,
domain availability, redirects and hosting can change. A fresh, independently
reviewed, family/brand-disjoint dataset and controlled staging/device tests are
needed before changing automatic blocking.
