# Available-data audit — 22 September 2026

**No usable website-classification dataset is present in this workspace. No real-data training, model accuracy measurement, or deployable model export has been performed.**

Inspection covered the existing `betguard` source tree and development records, excluding dependencies, Git objects, native build outputs, virtual environments and experiment/deployment output directories. No applicable AGENTS.md was found in the project or checked ancestors. The initial inventory counts are recorded below. Generate a fresh machine-readable inventory with the CLI when data is supplied; paths changed during the frontend/backend reorganization. The `backend/data`, `backend/runs`, and `backend/models` directories were absent at initial inspection. A manuscript screenshot was not present and was not treated as training data.

| Audit item | Observed result |
| --- | --- |
| Dataset candidate files (CSV, TSV, JSONL, Parquet, Excel, ARFF or hostname-row JSON arrays) | 0 |
| Existing trained model artifacts | 0 |
| JSON files in initial inventory | 8 configuration/asset/manifest files; 0 website-label datasets |
| Available real hostname observations | 0 |
| Reviewed gambling / non-gambling / unknown observations | 0 / 0 / 0 |
| Approved source/license records for a dataset | 0 |
| Eligible supervised observations and assigned splits | 0; no real-data split created |
| Class balance, duplicate rate, missing-value rate and conflict rate | Not measurable without observations; no rates inferred from an empty dataset |
| Collection dates, review agreement, operator/alias coverage | Unavailable |

The existing PostgreSQL catalog schema is an implementation, not evidence of populated data. At the initial dataset audit, hosted row counts and readiness were unverified. On 24 September, read-only TLS connectivity, migration status and API readiness were verified under betguard_app. This did not export or audit catalog labels, and no inference about dataset size or quality follows from readiness. Recorded manual-blocking acceptance remains pending; earlier phone startup is not proof of effective DNS filtering.

The pipeline's `audit` command now counts rows, valid/invalid records, missing/null/blank fields, classes, sources, licenses, review states, dates, duplicate normalized hosts and IDs, conflicting labels, related groups, synthetic records and supervised exclusions. It produces real counts from supplied JSONL. Invalid rows/conflicts block training; there is no silent label imputation. Synthetic records exist only in test code and temporary software-test files; their classifications/metrics are not evidence about actual websites.

## Candidate sources, not acquired training data

The following official/project pages were reviewed online. **No source list was downloaded into the dataset, licensed for this project, reviewed row by row, or used to train a model.**

| Candidate | Possible role | Required work |
| --- | --- | --- |
| [Block List Project](https://github.com/blocklistproject/Lists) gambling category | Candidate positive domains | The repository advertises the Unlicense. Record the exact revision, applicable upstream terms and retrieval date; verify each site's current function against BetGuard's policy, resolve false positives and aliases, and preserve evidence. A filtering list is not a reviewed supervised benchmark. |
| [Tranco](https://tranco-list.eu/) reproducible ranking | Candidate sampling frame across website categories | Popularity is not a non-gambling label. Independently review both classes, include difficult negatives and long-tail sites, and record list ID/date. Its source attribution lists different provider terms, including noncommercial and share-alike terms; verify the selected snapshot's usage/redistribution rights before setting `usage_allowed=true`. |
| Human-reviewed, permissioned project collection | Domain-specific positives, hard negatives and ambiguous cases | Supply real hostname observations, source snapshots, collection/review timestamps, reviewer IDs, evidence and usage terms. Include sports reporting, education, recovery, video games, simulated casinos, mixed-purpose sites, non-English/IDN and ordinary services. |

Avoid treating an unrelated financial-fraud, customer-transaction, sentiment, or document dataset as website classification. Do not label every unlisted/popular hostname non-gambling. Sample across sources and record bias; source overlap, domain-family similarity and label drift can inflate apparent performance.

## Data needed next

Supply privately maintained UTF-8 JSONL matching [the generated observation schema](ML_OBSERVATION.schema.json), with one hostname observation per line. Resolve conflicts and establish usage rights and reviewer agreement before creating a versioned snapshot. Use [the labeling policy](ML_LABELING_POLICY.md). The default fixed protocol requires at least 20 examples of each class in every partition and sufficient independent registrable/operator groups; this is a software minimum, **not** evidence of statistical adequacy. A credible low false-positive claim needs a much larger representative negative holdout and analysis of uncertainty and subgroup errors.

Dataset paths, raw evidence and exported split files may contain sensitive review material; they remain local/ignored by default. Do not send browsing history automatically from the phone or populate the real catalog with software fixtures.
