# App metadata experiments and capstone evaluation

Your existing trained **domain** classifier remains deployed; no new model is required for Smart DNS. This separate workflow supports the manuscript's metadata task, three-algorithm comparison and research evidence. It never runs at startup.

## Dataset

The contract is [APP_OBSERVATION.schema.json](../ml/APP_OBSERVATION.schema.json). One JSONL observation has public `app_name`, optional `package_name`, `description`, `keywords`, requested `permissions`, `reviews`, and:

- Unique `record_id`; `classification`: gambling / non_gambling / unknown.
- `family_id` / `family_evidence` linking documented operators/rebrands/versions, not generic keywords or shared hosting.
- `source_uri`, `license`, `license_uri`, strict boolean `usage_allowed`.
- `review_status`, reviewer code, `label_evidence`, timezone-aware collection/review dates.
- Boolean `synthetic`, true only for artificial software fixtures.

Collect both legitimate and gambling apps, including sports information, probability lessons, free casino-style games without wagering, payment tools, disguised branding and ambiguous cases. Labels need evidence of wagering rather than a keyword. Unknown/pending labels are excluded. Public review text must omit authors, contact details and other personal information. Store reviewer codes, not student identities.

The casino/game/RTP screenshot is not a validated two-class app metadata dataset. Do not invent descriptions from domain features, fabricate benign examples or deploy test-fixture models. The loader validates provenance/dates, rejects duplicate IDs/conflicting identical content and deduplicates eligible feature text. It joins family/package/text links before splitting; excluded observations can still preserve evidenced alias links. Package identifiers/provenance are not predictive features.

## Compare algorithms

From backend, using the existing environment with scikit-learn/skops:

```powershell
# The dataset below must be real reviewed observations; it is not supplied.
New-Item -ItemType Directory -Force data, runs, models | Out-Null
.\.venv\Scripts\python.exe -m ml_tools.application audit data\reviewed-apps-v1.jsonl
.\.venv\Scripts\python.exe -m ml_tools.application compare data\reviewed-apps-v1.jsonl --run runs\apps-v1
```

One fixed seeded grouped fold reserves approximately 20%; actual proportions depend on family sizes. Identical three-fold grouped CV compares SVM, RF and LR within the remaining 80%. Feature fitting occurs inside development folds; final candidates fit on development only. Selection uses out-of-fold TSS, specificity, precision and a fixed simpler-model preference, locked before any test prediction. Do not rename runs to reuse a holdout after tuning on its results.

Processing lowercases, normalizes Unicode accents, tokenizes and fits sparse word/bigram TF-IDF for names/descriptions/keywords/permissions/reviews. Negations are retained. Balanced LinearSVC, bounded balanced RF and balanced LR train serially with one numerical thread. Names/permissions alone are insufficient for serving. No score is displayed as calibrated confidence.

Reports include audit/hash, actual membership, frozen selection, development fit/out-of-fold/test metrics for all three, training/CV time, warm model-only median/p95 latency and selected artifact/predictions. Accuracy, precision, sensitivity, specificity, TSS, F1 and confusion matrices are reported. Fit/CV/holdout gaps indicate overfitting; independent future/noisy/language/operator cohorts remain needed for robustness. Minimum 20 examples per class in development and test, five independent groups and both classes in CV folds are required. No real data is trained by this project change.

## Reviewed export and serving

After reviewing labels, false positives, subgroup errors, licensing and performance:

```powershell
.\.venv\Scripts\python.exe -m ml_tools.application export --run runs\apps-v1 --output models\app-release-v1 --reviewed-by 'REVIEWER_CODE' --review-note 'Describe held-out results, false-positive review and evaluated scope.'
```

Placeholders are research inputs, not an assertion that an artifact exists. Synthetic artifacts cannot deploy. Minimum release gates: held-out size >=40, precision >=.95, specificity >=.98, sensitivity >=.80. These development gates are not product guarantees. Export does not select another model using test results or fit on the holdout.

After an actual approved export, set backend-only configuration and restart FastAPI:

```dotenv
APP_MODEL_ARTIFACT_DIR=<absolute reviewed release directory>
APP_MODEL_MANIFEST_SHA256=<exact hash printed by reviewed export>
```

Inspect `/health/apps`. Loading checks feature hash, Python/library versions, format, labels, reviewed real-data purpose, model integrity, fitted pipeline and allowlisted skops types. Inference is bounded and loaded once. Absence/incompatibility returns unknown; failures are unavailable. A hostname joblib is incompatible. Existing `.env`, domain artifacts and Supabase configuration were not changed.

The metadata endpoint is advisory. App text cannot reliably identify every network domain a package contacts. Future metadata-driven automatic policies require evidenced app/domain mappings and false-blocking review while honoring overrides. Today known app hostnames can be saved manually; existing Smart automatically classifies supported hostnames.

## Human expert comparison — Statement 5

Ask a qualified independent reviewer to classify the frozen held-out cases without seeing model results. Keep reference ground truth independent from the reviewer under comparison, or disclose circularity. One expert JSONL row: `record_id`, integer `label` (0/1), `reviewed_by` (code), `blinded_to_model: true`. Do not substitute model predictions for expert labels.

```powershell
.\.venv\Scripts\python.exe -m ml_tools.application experts runs\apps-v1\predictions.json data\independent-expert-labels.jsonl --output runs\apps-v1\expert-comparison.json
```

Exactly matching unique IDs and both reference classes are required. The tool reports paired model/expert metrics, agreement, Cohen's kappa and exact McNemar discordant counts/p-value. Report sample size, uncertainty, qualifications, ambiguity policy and family correlation. Paired model performance is not student benefit.

## BISU UAT and exposure pilot — Statement 6

Research consent is separate from app permission. Recruit enrolled consenting BISU Clarin undergraduate smartphone users using the manuscript's stratification by college/department. Faculty approval, consent, recruitment and questionnaire validation must be arranged by the researchers. BetGuard does not recruit or collect research responses automatically.

Use approved simulated tasks, test hostnames/manual rules and comparable baseline/protected windows. Do not ask students to wager or create gambling accounts. Record expected/observed DNS outcomes, native state, latency and network conditions. A check is not a blocked attempt; caching/Private-DNS bypasses are limitations.

UAT tasks: explain Local/Smart and permission; enable and recognize Protected/Off/Attention; add/test a Block rule in Activity; confirm legitimate access and allowed WARN; edit exact/subdomain scope/remove; select an app with local consent and separately consent to sending public metadata; recognize not evaluated; cancel/clear/leave; stop with the hold control and re-enable.

Suggested questionnaire items (1–5, **researcher-made and not yet validated**): I understand modes; I can navigate tabs; I understand permission/data sharing; I recognize protection state; I can manage rules; I understand uncertain results; response time is adequate; the system is acceptable for my study environment. Usability is separate from classifier accuracy.

Descriptive matched pilot JSONL uses only `participant_code` (e.g. `P-001`), `phase` (baseline/protected), `consented: true`, integer `gambling_attempts` and `accessible_gambling_attempts`. Supply one pair per participant. Keep the code/person key outside BetGuard. Use approved simulated exposure and note window/attempt-rate confounders.

```powershell
.\.venv\Scripts\python.exe -m ml_tools.capstone pilot data\consented-pilot.jsonl --output runs\pilot-summary.json
```

Validation enforces consent, pairing and counts. Output contains aggregate accessibility rates and descriptive percentage-point change; zero attempts yield null. It does not establish significance, causation, population benefit, addiction reduction or actual browsing exposure. No participant data/results are bundled into the APK.

## Existing trained domain evidence

```powershell
.\.venv\Scripts\python.exe -m ml_tools.capstone existing-model --output docs\research\EXISTING_DOMAIN_EVIDENCE.json
```

This summarizes saved reports without a new test or weight change. [EXISTING_DOMAIN_EVIDENCE.json](EXISTING_DOMAIN_EVIDENCE.json) distinguishes thresholds/tasks. Keep the original domain 60/20/20 experiment distinct from metadata 80/20. Existing LR hostname artifacts cannot establish SVM/RF app results.
