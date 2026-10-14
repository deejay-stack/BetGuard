# Dataset evidence for the capstone

Counts were read from local CSV rows, excluding headers, on 11 October 2026.
`inspection/local_inventory.json` contains per-file SHA-256 hashes, columns,
counts and source/label distributions for all 93 accessible CSV artifacts.
`evaluation/reconciliation.json` independently checks split membership and
lists the key input digests below. No source dataset or human review was edited.

## Historical stages

| Local artifact under ml/ | Rows | Evidence and qualification |
| --- | ---: | --- |
| data/raw/dataset_with_ssl_dns.csv | 1,090 | Original labels: 572 non-gambling, 518 gambling; 1,090 unique domain strings |
| data/processed/dataset_cleaned.csv | 1,090 | Labels: 568 non-gambling, 522 gambling; four labels differ from raw for matching domains |
| data/manual/verified_labels.csv | 13 | Nine marked verified (four label 0, five label 1); four uncertain with empty labels |
| data/processed/verified_training_candidates.csv | 427 | **final_verified_label**: 423 gambling, four non-gambling; original `label` is not the final target |
| data/processed/gambling_domains_verified.csv | 423 | Selected source-supported historical positives |
| data/processed/non_gambling_domains_verified.csv | 423 | 419 UT1-category negatives and four manual negatives |
| data/processed/balanced_domain_dataset.csv | 846 | 423 label 0 and 423 label 1; all domains unique |
| data/processed/splits/baseline_train.csv | 507 | 254 label 0, 253 label 1; 484 registrable families |
| data/processed/splits/baseline_validation.csv | 169 | 84 label 0, 85 label 1; 159 registrable families |
| data/processed/splits/baseline_test.csv | 170 | 85 label 0, 85 label 1; 157 registrable families |
| data/runtime/gambling_blocklist.csv | 359,736 | Unique reference domains for rule lookup; **not** the supervised training set |
| data/processed/external_holdout.csv | 98 | 61 label 0, 37 label 1; 97 families; previously examined, retained separately |

`apply_manual_labels.py` merges manual/external verification by normalized
domain, holds label conflicts and deduplicates final trainable records.
`build_training_dataset.py::load_verified_domains` uses `final_verified_label`,
not the original labels. The builder collects UT1 category negatives, rejects
known gambling conflicts, selects diverse negatives with seed 42 and shuffles
the 846-row balanced result. Its source and audit reports are retained.
“Verified” in historical filenames describes that workflow; it does not mean
every row was independently reviewed by a human for direct real-money wagering.
Historical positive records rely substantially on third-party blocklists.

The baseline split implementation uses a shuffled, seeded five-fold
StratifiedGroupKFold outer split (first fold for test), then a four-fold inner
split (first fold for validation), grouped by offline PSL registrable domain.
Seed is 42. The saved split union equals the balanced dataset's domain-label
map exactly. No exact domain overlaps occur. Recomputed saved families match
the current offline tldextract snapshot and all three pairwise family overlaps
are empty. There are 800 families overall. This protects registrable-family
membership; it does not establish independence between the same gambling
brand on different top-level domains, shared hosting or redirected aliases.

The export fitted TF-IDF vocabulary and classifier exclusively on **507 train
records**. Validation selected the already frozen configuration/threshold;
historical test was transformed/evaluated after reproduction, never fitted.
Neither the 359,736-domain collection, expanded candidates nor newer PAGCOR
records entered this fitted classifier. Historical test was examined during
development and is not an untouched independent test set.

## Reference collection and expanded provenance

`data/runtime/gambling_blocklist_metadata.json` records the 3 October 2026
collection: Block List Project 342,623 entries and UT1 Gambling 38,038 entries.
The CSV reconciles these totals: 321,698 only Block List Project, 17,113 only
UT1 and 20,925 shared; union 359,736. Source URLs are in
`src/update_runtime_blocklist.py::BLOCKLIST_SOURCES`:

- Block List Project: https://raw.githubusercontent.com/blocklistproject/Lists/master/gambling.txt
- UT1 Gambling: https://raw.githubusercontent.com/olbat/ut1-blacklists/master/blacklists/gambling/domains

The runtime builder parses plain domains/hosts/adblock-style records,
normalizes URL hostnames/case/`www.`/trailing dots, merges domains and preserves
source membership. Offline PSL matching operates down to registrable families.
Runtime metadata has collection counts/time but not complete original payload
snapshots or payload digests; the current union checksum does not reconstruct
the exact historical source bytes. Do not imply stronger provenance than saved.

The newer `data/expanded/source_manifest.json` records HaGeZi (208,016 parsed),
ShadowWhisperer (9,653), anti-gambling Indonesia (508) and bet-blocker (2,350),
with URLs and downloaded-payload checksums. Its first pass records 217,652
gambling candidates and failed UT1 benign downloads. The later
`ut1_mirror_manifest.json` records successful GitHub category mirrors, payload
hashes, 216,986 gambling candidates, 105,821 benign candidates, 252 conflicting
families and 5,000 review rows per class. These are separate candidate stages,
not additional training examples and not extensions to the live reference list.
All source manifests, review partitions and verification attempts remain.

## Philippine candidate/review evidence

`data/expanded/pagcor_ph/ph_dataset_manifest.json` explicitly declares
`UNVERIFIED_CANDIDATES`. It records two PAGCOR PDFs dated 8 October 2026,
local/downloaded source snapshots and SHA-256 hashes:

| Snapshot | SHA-256 |
| --- | --- |
| source_snapshots/pagcor_gsa.pdf | 00366a98dbabfb7e59bbbe1c5ef5bd86dff4958327595d7431515d8d455aeeca |
| source_snapshots/pagcor_licensed_casinos.pdf | 73c26be949e0d8de694d9baa71c7d6aab394511455311ef05de52e073d22cc7d |

The saved positive file has 518 candidate hosts / 468 families; benign starters
have 26 hosts / 26 families. Initial/master review queues have 544 hosts / 494
families. Verified-label fields in these accessible files are empty. A later
benign expansion has 106 hosts/families (80 diverse seeds plus 26 existing),
also pending verification. The accessible `manual_review_batch1` template and
completed file each have 117 rows and empty verified-label fields. A filename
containing “completed” does not establish approved labels. Review flags,
reviewer/evidence columns, manifests and all original files are preserved.

The accessible verification-v1 overlap queue has 117 rows / 86 families
flagged for historical overlap; same-name brand aliases also require review.
Exact-family exclusion alone does not settle brand leakage. The newer
`audit_v1/verification_v2` directory denied access, so its rows and review
progress are **unknown**, not zero. Resolve access through the dataset owner
before making claims about that version; this audit did not change ACLs.

PAGCOR registration supports provenance but does not independently demonstrate
current site operation or direct real-money wagering. PDF extraction can pick
up administrative domains; seed candidates require independent benign evidence.
No provisional label was promoted to verified, used to train, or uploaded.

## Key reproducibility checksums

Paths below are relative to `ml/`. Full per-file evidence is machine readable
in the inventory and the shadow artifact manifest.

| Artifact | SHA-256 |
| --- | --- |
| data/raw/dataset_with_ssl_dns.csv | 298a3b67b2c4458e9ea1c5da61d1969401d66f7f4e423c74a3ac0bf6ba59309a |
| data/processed/balanced_domain_dataset.csv | 548b29155657fcb7324245506dba387810c608dd2ba266ec09e11e98c896d16a |
| data/processed/splits/baseline_train.csv | 71b448c2390afd5693f69d38b18e1f4d45a217d4dfaf6f6b2264302ca302c6b3 |
| data/processed/splits/baseline_validation.csv | acffd215c930a5be3600600cd36e91cdbc9707054b6bbd96962a6757ed9de430 |
| data/processed/splits/baseline_test.csv | e093d6dd6b58c2ed087327783752a344eb57774960c689b75189a39db7d797de |
| data/runtime/gambling_blocklist.csv | ed84e678d9a5bb33d9edd59dbf26f5b41d0d1a1f0d6c10711605ba01e7dac754 |
| data/processed/external_holdout.csv | c6ed865e05472d103fd66e2c6ae7c00e5d95f5a159b97f78703f759156636532 |

To reproduce inventory without changing input data, run from `betguard/`:

```powershell
backend/.venv/Scripts/python ml/src/audit_local_evidence.py --output docs/audit/new-inspection
```

Choose a new output directory; the command refuses to overwrite prior evidence.
Do not rerun historical download/build/train scripts just to regenerate counts:
their mutable network sources and output paths could replace saved evidence.
