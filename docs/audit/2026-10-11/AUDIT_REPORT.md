# BetGuard architecture, cleanup and SVM production-readiness audit

**Decision: CONDITIONALLY READY for offline shadow/staging only. The optimized
SVM was not activated for production blocking.** The existing baseline model,
runtime thresholds, APIs, frontend, database schema and router behavior remain.

Completed on 11 October 2026 (Asia/Manila), using local source and real saved
artifacts. Findings, changes and test limitations below distinguish historical
ML classification from operational network enforcement.

## Deliverable index

- [Architecture before changes](ARCHITECTURE_BEFORE.md): real entry points,
  dependencies, databases, decision precedence and original folder tree.
- [Dataset evidence](DATASET_EVIDENCE.md): counts, provenance, splits, leakage,
  label limitations, SHA-256 hashes and preserved Philippine candidate work.
- [Algorithm comparison](ALGORITHM_COMPARISON.md): reconciled metrics, settings,
  corrections to earlier numbers and capstone discussion.
- [Network interface](NETWORK_INTERFACE.md): reusable detection/DNS interfaces
  and limitations; no router operations were performed.
- [Initial cleanup inventory](inspection/cleanup_inventory.csv) and
  [source/dependency inventory](inspection/local_inventory.json): per-file
  classifications, hashes, CSV counts and Python import/definition maps.
- [Post-cleanup inventory](final_inventory/local_inventory.json): another
  accessible-project snapshot taken before writing this final report.
- [Metric reconciliation](evaluation/reconciliation.json),
  [comparison CSV](evaluation/algorithm_comparison.csv),
  [historical shadow comparison](evaluation/historical_shadow_comparison.csv),
  [domain probes](evaluation/domain_probes.csv) and
  [historical false-positive fixtures](evaluation/optimized_svm_false_positive_fixtures.csv).
- [Preservation checks](preservation.json): 412 original hashed non-cache files
  unchanged, existing tracked user diff preserved exactly (apart from the new
  README link), 64 validated caches removed.

## Architecture findings and changes

The workspace's actual application is the nested `betguard` repository, branch
`main`, original HEAD `983b244`. The outer `master` repository has no commits and
stages a gitlink. No Git state was reset, committed or staged. Existing modified
frontend/backend configuration and untracked router/ML/review work are preserved.

Mobile is React Native/TypeScript with Android Kotlin native services and Room.
`index.js -> App.tsx -> contexts/screens -> src/api` connects to FastAPI
`app.main:app`. FastAPI loads `betguard_runtime` once through
`app/services/domain_service.py`. `/v1/domain/check` and batch invoke
`runtime_service -> decision_engine -> maintained list -> baseline TF-IDF LR`.
Validated decisions go back to the manual-check UI or native DNS blocking.
Explicit local rules win before online detection; WARN allows traffic. A rule
block writes NXDOMAIN. Online service failure produces unavailable/503 and
native DNS SERVFAIL/degraded, not a fabricated allow/block decision.

Standalone text rules use allow-first precedence; Android/router manual
snapshots deliberately choose the most-specific exact/parent rule. Backend
runtime has shared text user lists disabled. These differences are intentional
and were retained. There is a distinct PostgreSQL reviewed-catalog path
(`/v1/check`) and optional skops worker; public app metadata classification is
also separate. Neither should be conflated with the finalized domain runtime.

Existing module boundaries already separate routes, services, inference,
offline tooling, schemas and native enforcement. Moving shared `ml/src` files
would affect both editable package imports and historical CWD-based scripts.
No moves/renames were justified by this audit. Instead, new functions live in
small explicit offline modules, with no startup imports or training side effects:

```text
betguard/
  README.md                         added audit link
  backend/
    app/                            existing production services, unchanged
    ml_tools/, migrations/          existing audited offline protocol/DB, retained
    tests/test_optimized_svm_shadow.py  new artifact and adapter regressions
  frontend/                         existing mobile/native source, unchanged
  ml/
    src/
      runtime_service.py, decision_engine.py  current production, unchanged
      optimized_svm_features_frozen.py        historical feature source, unchanged
      optimized_svm_shadow.py         new fixed export and offline load/inference
      reconcile_model_evidence.py     new saved metric/model comparison command
      audit_local_evidence.py         new read-only recursive inventory command
      ...                            all historical/PH workflows retained
    models/
      deployment_candidate.json      baseline remains selected
      baseline_domain_classifier.joblib  original production binary retained
      optimized_svm_shadow_2026-10-11/
        manifest.json, model.joblib   new isolated shadow artifact
    data/, reports/                  original evidence unchanged
  docs/audit/2026-10-11/              audit, dataset/algorithm/network evidence
  verification/architecture-audit-2026-10-11/
    checkpoint/                      exact tracked-work/baseline rollback copies
    cache-removal.json                exact deletion ledger
    frontend-jest.json, *pytest.xml   verification results (Git-ignored local outputs)
```

Existing ignored artifact/dependency boundaries already suit caches/secrets;
`.gitignore` was inspected and left unchanged, preserving the user's local edit.
The different backend/ML dependency manifests serve distinct packages and must
not be merged merely to reduce file count. No CI workflow/container deployment
was found; documented uvicorn, Metro and APK/Gradle commands are the real entry
mechanisms. Retired `api_service.py`, empty legacy `train.py`, prototype and
versioned evidence files were retained as historical/contextual artifacts.

## Cleanup and rollback checkpoint

Removed **64 generated cache files, 643,267 bytes** (about 628 KiB), specifically
the initial inventory's `REMOVE_CACHE` entries: Python `__pycache__/*.pyc` with
recognizable bytecode headers and corresponding source, and standard pytest
cache tag/readme/ignore/nodeids/lastfailed files. Each target was verified inside
the resolved project root, untracked, and outside reparse-point paths.
`cleanup_caches.ps1` validates the exact inventory and uses `Remove-Item
-LiteralPath` for individual files. No recursive folder deletion occurred.
It leaves directory containers; later Python runs may regenerate bytecode.
The exact path/size/hash ledger is the ignored local
`verification/architecture-audit-2026-10-11/cache-removal.json`.

PowerShell initially refused script execution under its default execution
policy; the cleanup subsequently ran with a process-local `-ExecutionPolicy
Bypass`, without changing system policy. Its first inventory parser attempt
also failed before deletion because Windows PowerShell cannot represent empty
JSON property names; the reviewed script now imports the flat CSV inventory.
Only the successful run removed files. There were no partial deletions in the
failed attempts.

Files moved: **none**. Datasets, historical splits/reports, all models, manifests,
PDF snapshots, user review files, environments, package installations, native
builds, databases, private settings and verification captures were retained.
Two inaccessible directories were left untouched:
`ml/data/expanded/pagcor_ph/audit_v1/verification_v2` and
`backend/verification/pytest-temp/run`. Their access errors are audit limits.

The following uncertain files require owner review **before any future deletion**;
no approval was needed because this audit retained them:

| File | Finding / retention reason |
| --- | --- |
| backend/app/router/config.py.backup | Non-imported extension, but may preserve an earlier user router configuration implementation |
| backend/app/router/dns.py.backup | Non-imported extension, but may preserve user DNS changes needed for comparison/rollback |
| ml/train_baseline_current.txt | Console output/log can be capstone evidence; not safe to call disposable from its name |

Before the only existing tracked-file edit (README), exact README/.gitignore
copies, original short status and a binary diff of all tracked user changes
were saved under `verification/architecture-audit-2026-10-11/checkpoint`.
An additional baseline rollback snapshot preserves original deployment JSON,
baseline joblib and both runtime modules, with digests in `baseline-rollback.json`.
The full current `.gitignore` and user changes are not discarded. A Git commit
alone would not preserve all untracked/ignored work, so no reset-based rollback
is proposed. The initial inventory plus final checks confirm evidence retention.

## ML readiness assessment

Original active model: `ml/models/baseline_domain_classifier.joblib`, selected
by `ml/models/deployment_candidate.json`. Its char-(3,5) TF-IDF Logistic
Regression scores drive current warning 0.512117 / automatic-block 0.70 policy.

The original optimized experiment had configuration/evaluation JSON and CSV,
but **no matching serialized artifact**. Existing `svm_domain_classifier.joblib`
is an ordinary char-(3,5), min_df=2 SVM without 25 lexical features, at a
different threshold. It was not repurposed or overwritten.

New shadow artifact: `ml/models/optimized_svm_shadow_2026-10-11/model.joblib`,
374,357 bytes, paired with `manifest.json`. It stores fitted TF-IDF vectorizer
and LinearSVC. The loader verifies an externally supplied manifest hash, payload
hash, environment, feature/adapter code hashes, frozen config, class orientation,
estimator settings, matrix dimensions and shadow-only purpose before serving
offline predictions. It rejects incompatible/missing/corrupted files explicitly.
Joblib remains a trusted local pickle format: integrity hashes are not a
signature or permission to deserialize downloaded/untrusted objects.

| Gate | Actual evidence / status |
| --- | --- |
| Frozen fit/export | PASS: exact C=0.5, balanced, seed 42, max_iter=10000; original 507 train rows only; no tuning or test/holdout fitting |
| Features | PASS: reused frozen functions; 14,051 fitted char-(2,6) TF-IDF columns followed by 25 lexical columns, 14,076 total; class order [0,1] |
| Dependency compatibility | PASS for current local environment: Python 3.14, sklearn 1.9.1, NumPy 2.5.3, SciPy 1.18.1, pandas 3.0.6, joblib 1.6.0, tldextract 5.3.2; recorded in manifest |
| Historical fidelity | PASS: 158/169 validation and 157/170 test correct; full recorded metrics/labels match; max historical margin difference 2.220446049250313e-16 |
| Frozen threshold | PASS for classification: score >= -0.05278699316952151 means label 1; signed margin never presented as probability |
| Saved/loaded round trip | PASS: identical scores after serialization; load once, repeated deterministic predictions |
| Malformed/unusual input | PASS at existing API boundary; shadow accepts canonical ASCII hostnames including punycode, rejects URLs/credentials/IPs/malformed values; empty batches return no decisions |
| Integrity/failure regression | PASS: missing/corrupt artifacts, wrong manifest/code/env/hash, class order/dimension/threshold drift and nonfinite margins fail explicitly |
| Overrides/current API | PASS for existing baseline flow/tests; standalone allow-first and mobile/router specificity retained; current client/score contracts unchanged |
| SVM active API compatibility | **NOT SATISFIED**: backend/JS/Kotlin require [0,1] ml_score; raw margins can be negative or >1. No active adapter is connected |
| SVM automatic-block threshold | **NOT SATISFIED**: frozen threshold maximizes validation accuracy, not blocking reliability. No validated separate warning/hard-block policy or calibration |
| Fresh independent PH validation | **NOT SATISFIED**: accessible PH candidate labels remain unverified; one verification directory inaccessible; historical/test/old holdout already examined |
| False-positive risk | **NOT SATISFIED** for active deployment: 11 historical FP, 11 benign errors on reused holdout; positive margins on financial/ordinary-domain probes; 49 positive predictions among 106 unlabeled PH benign candidates |
| Live operational evidence | **NOT SATISFIED**: no new APK/device/router staging test, live traffic test, calibration evidence or production latency/load gate |

This supports **CONDITIONALLY READY** for isolated offline shadow/staging.
It does not support automatic blocking activation. Original historical
environment digests were not recorded; reproducing saved scores now proves
current compatibility, not a newly reconstructed historical chain of custody.

To reach READY, review the candidate-label evidence/access, acquire a new
independently labeled domain-family/brand-disjoint sample, set explicit allowed
false-positive/false-negative criteria, validate an automatic-block margin
policy separately from classification, implement a compatible score response
(or independently evaluated calibration), and test both models plus overrides,
failure behavior and controlled device/network enforcement in staging. Do not
retune against the already examined historical test or exploratory holdout.

## Integration preparation and rollback

Only offline preparation occurred. `optimized_svm_shadow.py` reuses the frozen
training feature functions and stores both trained objects; it exposes
`decision_score`, `score_type=svm_margin`, `predicted_label`, classification
threshold and `automatic_blocking_approved=False`. It never returns a production
`DomainDecision` and is not imported by startup. `reconcile_model_evidence.py`
loads the live baseline and compares it to the new artifact without changing
selection, lists, responses or enforcement. There is no silent fallback on
artifact failure. No SVM API response or frontend probability display was added.

Reproduce a new immutable artifact, from `betguard/`:

```powershell
backend/.venv/Scripts/python ml/src/optimized_svm_shadow.py export --output ml/models/optimized_svm_shadow_next
```

The command refuses an existing output directory and first checks train/family
membership, validation, saved test metrics/margins and serialization fidelity.
It does not invoke the optimization executable in the frozen feature file.

Use this artifact offline (canonical hostnames only):

```powershell
backend/.venv/Scripts/python ml/src/optimized_svm_shadow.py predict --artifact ml/models/optimized_svm_shadow_2026-10-11 --manifest-sha256 76d4bc7779b386c7d2c4be36ff59ee14f5093c533617ce42b6e046ae331574a1 wikipedia.org bsp.gov.ph
```

Reproduce comparison in a **new** output directory:

```powershell
backend/.venv/Scripts/python ml/src/reconcile_model_evidence.py --artifact ml/models/optimized_svm_shadow_2026-10-11 --manifest-sha256 76d4bc7779b386c7d2c4be36ff59ee14f5093c533617ce42b6e046ae331574a1 --output docs/audit/new-evaluation
```

Artifact payload SHA-256:
`81d61e71ba422aad3277887d3e6315866e7015d72d2c1ab68e996626d747a416`.
Manifest external anchor:
`76d4bc7779b386c7d2c4be36ff59ee14f5093c533617ce42b6e046ae331574a1`.
The existing `*.joblib` Git ignore still applies. Preserve/package the trusted
binary alongside its manifest and code; no force-add or dependency installation
was performed. Editable resource loading is not a self-contained wheel release.

Immediate operational rollback is already satisfied: production never left the
baseline. A future approved selector must use the existing deployment manifest
and resource-root convention (`BETGUARD_ML_ROOT`), with a separate validated
adapter; no unsupported `BETGUARD_ML_MODEL` variable was introduced. If a future
activation fails, restore the checkpointed baseline deployment JSON, binary and
matching runtime implementation to the actually configured resource root,
verify `baseline-rollback.json` hashes, restart the FastAPI process to clear
loaded resources/cache, and verify `/health/detection` reports `baseline` plus
fixture checks. Preserve any subsequent user edits before restoring source.
Never run `git reset --hard` or overwrite Room/router rules as model rollback.

## Verification actually executed

| Check | Result |
| --- | --- |
| Original backend suite: pytest -q -p no:cacheprovider with isolated basetemp | **144 passed, 1 skipped**, 215.76 s; includes original router tests |
| New frozen artifact/adapter suite | **30 passed**, 12.14 s; JUnit in ignored verification directory |
| Domain + new artifact focused regression run | **54 passed**, 63.61 s; JUnit saved; this run started while cleanup preparation was underway |
| Explicit post-cleanup FastAPI startup/real-decision/batch/unavailable smoke | **6 passed, 18 deselected**, 40.41 s; real model/list and TestClient lifespan, isolated DB configuration |
| Initial Jest run, default 5-second timeout | **148 passed, 1 failed**; ManualFlow native-failed-state test exceeded timeout |
| Full Jest rerun, --runInBand --testTimeout=30000 | **149 passed across 14 suites**, 67.976 s; JSON saved; no frontend code/test changes |
| npm run typecheck | **PASS**, exit 0 |
| npm run lint | **PASS**, exit 0 |
| Frozen export / saved metrics and serialized-score reconciliation | **PASS**, all five historical experiments, all labels and reports agree |
| Split membership and recomputed-family leakage checks | **PASS**, zero pairwise domain/family overlap |
| Preservation check | **PASS**, 412 original hashed files unchanged; original tracked user diff preserved exactly outside README |

Backend warnings report deprecated Starlette/httpx TestClient usage and an anyio
BlockingPortal alias; no dependency upgrades were made. The skipped PostgreSQL
test requires a dedicated `TEST_DATABASE_URL` and explicit
`BETGUARD_TEST_DATABASE_CONFIRMED=yes`; it did not connect to or migrate the
user's production database. Standard unit/integration fixtures isolate DB
startup. Optional router mode was not activated or configured by this audit.

No native APK build, new physical-device/VPN/router enforcement acceptance,
hosted database acceptance or live wagering transaction was performed. Passing
HTTP/Jest/fixture DNS tests demonstrates source/software contracts, not
network-wide bypass prevention. Existing device reports remain historical
evidence, with their stated conditions. No test was marked passed without
execution; the initial frontend timeout is retained as a verification limit.
