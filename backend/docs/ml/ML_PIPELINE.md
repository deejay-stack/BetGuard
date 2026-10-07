# Hostname ML development and explicit-check integration

This is the historical optional catalog-model development workflow. **Your finalized trained baseline domain model is now integrated** through `betguard_runtime`, FastAPI and Android Smart DNS; see [ML_INTEGRATION](ML_INTEGRATION.md). The [capstone alignment](../../../docs/CAPSTONE_ALIGNMENT.md) distinguishes that live hostname model from the separate [app metadata research workflow](../research/APP_METADATA_RESEARCH.md). Statements below about the earlier model not being integrated describe that earlier milestone, not current Smart protection.

This milestone adds a runnable development workflow and optional model serving to the existing `POST /v1/check`. It does not add a trained classifier, automatic DNS uploads, automatic blocking, another backend, or a Supabase SDK. [The audit](ML_DATA_AUDIT.md) found no suitable dataset. Software tests do not establish real-data performance, Supabase connectivity or phone acceptance; those require separate verification.

## Runtime and offline tools

`app/services/model_service.py` is the optional boundary used by FastAPI. It returns absent without loading science libraries when both model variables are unset. `app/ml/` contains only inference transforms, eligibility/abstention helpers and trusted loading. Offline data auditing, grouped splits, estimator factories, evaluation and export now live in `ml_tools/`, outside the deployable `app` package. Run its commands from the backend directory. Nothing here trains during startup.

The separately trained final model is not integrated yet. Its complete feature/estimator artifact must satisfy the documented serving contract, or a reviewed adapter must be implemented later. Renaming a pickle file is insufficient. This refactor changes compatibility source hashes; no existing reviewed deployment artifact was present. Future releases must be exported/reviewed against the current code.

## Data and labeling

Apply [hostname-labels-v1](ML_LABELING_POLICY.md). One JSONL object represents a dated, reviewed hostname observation. Required fields are:

- `record_id`, `hostname`, `classification` (`gambling`, `non_gambling`, `unknown`), `label_provenance`.
- `review_status` (`pending` or `reviewed`), `reviewed_at` (timezone-aware for reviewed, null for pending), `reviewed_by` (required for reviewed).
- `source_uri` (exact source/snapshot reference), `collected_at` (timezone-aware), `license`, `license_uri`, `usage_allowed` (JSON boolean), `evidence`.
- `policy_version`: `hostname-labels-v1`. `synthetic` defaults false and must be true for any artificial fixture.
- Optional `related_group_id` plus `related_group_evidence` to link reliably established aliases/operators. No grouping by keyword or shared CDN.

The complete JSON Schema is [ML_OBSERVATION.schema.json](ML_OBSERVATION.schema.json). Source metadata describes evidence; it is not a feature. Records with unknown labels, pending review or unapproved usage are excluded from the binary task. Invalid rows, duplicate IDs and conflicting labels on the same normalized host block training. Same-label duplicate hosts are counted and reduced deterministically after all relationship links are collected, preferring an eligible reviewed observation. Different subdomains may have different labels, but they remain in one leakage group.

The ML workflow does not read/write Supabase. Catalog imports remain a separate, validated administrative operation; never import predictions as reviewed labels. No schema change/migration is needed for model inference: a release artifact stays on the backend filesystem, and predictions are not persisted to the domain catalog.

## Install and run

From `betguard/backend` in PowerShell, use the existing virtual environment:

```powershell
.venv\Scripts\python -m pip install -r requirements-ml.lock.txt
.venv\Scripts\python -m pip install --no-deps -e .
.venv\Scripts\python -m ml_tools.cli --help
New-Item -ItemType Directory -Force data, runs, models
```

The ML lock contains the tested backend, test and ML dependencies. The original backend-only lock is retained; ML dependencies are optional (`pip install -e '.[test,ml]'` resolves compatible versions instead of using the lock). A normal API deployment without a configured model does not import scikit-learn. No installer/startup command trains a model.

Place **real, licensed, reviewed** JSONL at your own path, then run explicitly:

```powershell
.venv\Scripts\python -m ml_tools.cli inventory .. --output data/inventory.json
.venv\Scripts\python -m ml_tools.cli schema docs/ml/ML_OBSERVATION.schema.json
.venv\Scripts\python -m ml_tools.cli audit data/reviewed-v1.jsonl --output data/audit-v1.json
.venv\Scripts\python -m ml_tools.cli split data/reviewed-v1.jsonl --output data/split-v1.json
.venv\Scripts\python -m ml_tools.cli train data/reviewed-v1.jsonl --split data/split-v1.json --run runs/experiment-v1
# Review validation results/operational criteria and freeze selection FIRST.
.venv\Scripts\python -m ml_tools.cli evaluate data/reviewed-v1.jsonl --run runs/experiment-v1
# After reviewing held-out results and limitations, explicitly approve export:
.venv\Scripts\python -m ml_tools.cli export --run runs/experiment-v1 --output models/release-v1 --reviewed-by '<REVIEWER_ID>' --review-note '<EVALUATION_SCOPE_AND_LIMITATIONS>'
```

The dataset filenames and reviewer arguments above are placeholders, not supplied data. Missing data prevents training. The public CLI has no synthetic-training bypass. Tests call internal functions with a software-test flag and produce artifacts explicitly rejected for deployment. No expensive run was started automatically.

`split --config path/to/config.json` accepts `TrainingConfig` fields. Defaults: seed 42; row cap 20,000; 8,000 character features; 64 forest trees; at least 20 examples/class/partition; validation minimum 5 decisions per accepted side; maximum FPR 0.02, maximum false-negative rate 0.05, predictive value minimum 0.95; p95 single-host latency limit 100 ms. These are conservative **development gates to review before collecting a holdout**, not validated product guarantees. The command caps rows at 50,000, features at 20,000 and trees at 128. Training is serial, forest `n_jobs=1`, and numerical thread pools are limited to one thread.

## Leakage controls and features

Normalization calls the same Python function as FastAPI, matching the established Android contract for lowercasing, IDNA/punycode, trailing dots, supported HTTP(S) hosts and rejecting credentials, malformed ports and IPs. Paths/query strings never become features. PSL grouping uses maintained [tldextract](https://github.com/john-kurkowski/tldextract) with private suffixes enabled, so `example.co.uk` is one registrable site and separately hosted `tenant.github.io` sites remain distinct. It uses the package's bundled [Public Suffix List](https://publicsuffix.org/list/) snapshot without network/cache writes. The version and snapshot SHA-256 are recorded; update the pinned package deliberately, rerun audit/splits and retrain when needed.

A union of registrable domains and evidenced operator/alias IDs makes related records inseparable. Two fixed stratified group folds yield approximately 60% train, 20% validation and 20% test; grouping can alter counts. Both seeds and every hostname/record/group/label membership are saved. Dataset/split hashes detect changes. Cross-partition overlap and within-partition duplicates are rejected. Membership is rechecked against the fixed seeded protocol. Do not search seeds after viewing test outcomes.

All three estimators use their own fitted copy of the same scikit-learn pipeline: normalization → sparse character 3–5-gram TF-IDF plus sparse lexical features → classifier. Lexical features measure hostname length, digit/hyphen proportions, dot count, longest label, IDN presence and character entropy; they describe spelling/structure, not proof of wagering. Lexical max-absolute scaling is fitted on training only and preserves sparsity. There is no `.toarray()` conversion, page crawler, path text or HTTPS-content feature.

Estimators: balanced Logistic Regression (liblinear), balanced linear SVM (LinearSVC), and depth/leaf-limited balanced Random Forest. TF-IDF vocabulary/IDF, scaling, estimator weights and class weights are fitted on **training only**. Forest sparse support avoids a large dense matrix, but its trees still consume memory; caps are intentional. See [scikit-learn's leakage guidance](https://scikit-learn.org/stable/common_pitfalls.html).

## Evaluation and abstention

Validation alone chooses two score cutoffs: accepted gambling predictions must meet precision/FPR/minimum-count gates; accepted non-gambling predictions must meet negative predictive value/false-negative/minimum-count gates. Scores between the cutoffs return unknown. If no cutoff meets a gate, that side abstains entirely. Selection ranks validation gambling recall under those constraints and the latency budget, then coverage, then a fixed simpler-model preference (Logistic Regression, SVM, Random Forest) for reproducible ties.

Training writes validation results without computing test predictions. `evaluate` compares all three frozen pipelines on exactly the same held-out records. It writes an exclusive start marker before inference and refuses repeated evaluation in that run. An interrupted evaluation requires an explicit audit of partial exposure; do not quietly delete the marker and tune on the same test. Creating another directory cannot prevent deliberate test reuse; preserve the original holdout across experiments and use new external/future data after model changes informed by test results.

Reports contain class counts, split membership, binary confusion matrix `[[TN, FP], [FN, TP]]`, precision, recall, F1, accuracy, FPR, specificity, ROC-AUC and average precision (PR summary). They also include a **separate abstaining** confusion matrix (rows true non-gambling/gambling; columns predicted non-gambling/gambling/unknown), coverage, abstention count, selective accuracy, gambling precision/recall and false-positive/negative rates with abstentions retained in class denominators. Binary metrics use the estimator's ordinary score cutoff (margin 0 or forest score 0.5), not the abstention policy. Read both tables; high selective accuracy with near-zero coverage is not sufficient.

Training duration and warm single-host median/p95 inference latency (up to 100 probes) are recorded. Latency excludes database/network/device time and depends on the machine. Zero measured false positives on a small holdout does not establish a low population error rate; groups may contain correlated hosts. False positives matter because a future filter could block legitimate sites. Examine actual false-positive cases, language/category/source subgroups, sample uncertainty, class prevalence and temporal drift before deployment. Metrics apply only to the audited dataset and split.

No numerical confidence/probability is displayed. LR/SVM decision margins and forest vote proportions are internal ranking scores only; SVM scores are not probabilities, and the other estimators' outputs have not been calibrated. The artifact explicitly records calibration as not evaluated. If probability display is later required, allocate independent calibration data and assess reliability/Brier/log loss before exposing it; see [scikit-learn calibration](https://scikit-learn.org/stable/modules/calibration.html).

Abstention is not a reliable detector for every unfamiliar site. A misleading hostname can yield an extreme score. Known public-suffix format is only an eligibility check, not out-of-distribution detection. Hostname models cannot establish content, ownership, legality, safety or coverage beyond their data.

## Artifact and backend configuration

The `backend/models/` directory containing only `.gitkeep` is reserved for future trusted releases. Put each complete reviewed export in its own versioned subdirectory; do not place a lone pickle file there. No placeholder model or fabricated artifact is included. Artifact files are ignored by Git; only `.gitkeep` is tracked; real artifacts stay ignored.

`export` retains the validation-selected winner; it does not pick a different model using test results or refit on test data. It requires held-out gates and explicit reviewer notes. Each release contains the complete fitted normalization/features/estimator, label mapping, thresholds, model/version metadata, dependency and source-code hashes, PSL identity, dataset/split references, audit, membership, validation/held-out comparison and timing. Keep raw versioned data and the lockfile privately for reproduction. The artifact uses [skops persistence](https://scikit-learn.org/stable/model_persistence.html), never arbitrary pickle/joblib loading.

Only trusted project exports may be served. After a real-data review, set these **backend-only** environment values and restart FastAPI:

```dotenv
MODEL_ARTIFACT_DIR=<ABSOLUTE_PATH_TO_REVIEWED_RELEASE_DIRECTORY>
MODEL_MANIFEST_SHA256=<EXACT_MANIFEST_SHA256_PRINTED_BY_REVIEWED_EXPORT>
```

The expected manifest hash comes from the reviewed export/deployment process, not from blindly trusting a downloaded file's own adjacent checksum. It binds metadata and the payload hash. The loader enforces format, labels, features, exact dependency/Python versions, normalization code and PSL identity; limits compressed/uncompressed sizes; and explicitly allowlists the project's two transformer classes and scikit-learn's tree-state class beyond skops' trusted built-ins. Missing/incompatible/unapproved/software-test artifacts cannot serve definitive predictions. A checksum is integrity/provenance anchoring, not proof of model quality or protection if an attacker controls both the artifact and deployment configuration.

One spawned inference process per FastAPI process loads its artifact once. Numerical threads and accepted in-flight requests are limited to one. Requests get a 1.5-second inference deadline; a timed-out task keeps its capacity slot until it finishes, so there is no growing queue. A stuck worker requires process restart; timeout does not claim to cancel an already executing native computation. Database work and inference run outside FastAPI's event loop. Size the number of web workers for the model memory cost. Startup gives loading up to 30 seconds; a failure leaves the model unsuitable rather than claiming readiness of ML.

Database readiness remains a separate requirement: `GET /health/ready` verifies the schema/read access and also reports model state. A database failure is HTTP 503 even if a model exists, so a stale fallback cannot silently bypass a reviewed catalog hold. Existing encrypted SQLAlchemy connections, private schema/grants, Alembic workflow and import command remain unchanged.

## API and mobile behavior

The existing `POST /v1/check` accepts a hostname/HTTP(S) input, normalizes it, and returns classification, explicit `source`, `reason`, explanation and applicable reviewed/model metadata. Sources are `reviewed_catalog`, `model`, `unavailable`.

- Reviewed catalog entries take precedence, **including reviewed unknown**.
- Missing/pending entries may use a validated model. Absent/unsuitable model returns HTTP 200 unknown with an explanation; it does not fabricate a label.
- Model abstention or unsupported suffix input returns unknown with the model source/version.
- Database/worker failure, saturation or timeout returns HTTP 503 with `source: unavailable`; invalid input remains 422. These failures are distinct from a completed unknown result.

The phone shows normalized hostname, classification, source, model version when applicable, explanation and local manual rule. It says “classified as non-gambling,” not “safe.” Existing timeout, cancellation, retry and stale-response guards remain. Check Link also exposes Remove Override for an exact saved rule; removal resolves the actual parent/default policy rather than saving an Allow rule. Block/Allow preserve existing subdomain scope. Checking never changes rules, and retries do not add another local history event.

Only an explicit user check sends a hostname. Room, Kotlin VPN/DNS logic, themes, branding and navigation are unchanged. No browsing stream is sent to the server. Metro reload suffices for JS changes if the installed debug APK already has the previous `resolveLink` bridge; an older native APK/release bundle still needs rebuilding as documented in [Supabase setup](../database/SUPABASE_SETUP.md).

## Phone verification and next milestone

Follow [Android acceptance](../../../frontend/docs/ANDROID_ACCEPTANCE.md) for manual enforcement. Additionally verify reviewed positive/negative/unknown, pending/missing with no model, a later real validated model prediction/abstention, DB failure, timeout/cancel/retry, rapid input edits and tab switching. Confirm source/version text in both themes, that no confidence is displayed, and that Block/Allow/Remove Override work with FastAPI stopped and preserve parent precedence/history. No such physical-device outcome is claimed here.

The next milestone is **controlled integration of validated classifications into automatic filtering**, after real data/evaluation and existing manual-device acceptance. It must explicitly design caching/expiry, DNS latency and budgets, offline behavior, privacy/consent, catalog/model updates, error/unknown policy, rule precedence and rollback. This milestone intentionally leaves classification advisory in the explicit website checker.
