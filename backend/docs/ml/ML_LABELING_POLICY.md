# Hostname labeling policy: hostname-labels-v1

The unit is a **website hostname observed at a recorded time**, not a transaction, user, message, keyword, page paragraph, or isolated URL path. Inspect actual purpose and functionality. A mention of gambling is not a gambling label. Record source/evidence, collection date, reviewer, review date and usage rights. Labels can become stale when ownership or content changes.

| Label | Apply when |
| --- | --- |
| `gambling` | The hostname directly offers or materially facilitates staking money or transferable value on uncertain outcomes for a payout: betting, wagering, real-value casino games, lotteries, or an operator's dedicated wagering portal. Evidence must identify that function, not merely a suggestive name. |
| `non_gambling` | Review finds a clear non-wagering purpose and enough evidence to distinguish it from the positive definition. This is a task label, not a claim that a site is safe, lawful, trustworthy, or suitable for everyone. |
| `unknown` | Evidence is insufficient, inaccessible, contradictory, outdated, or the hostname mixes activities that cannot be classified reliably at hostname granularity. Also use for unresolved borderline mechanics. |

Sports news, scores and journalism are non-gambling when their purpose is informational and they do not facilitate placing wagers. Dedicated betting funnels/affiliate portals that materially facilitate gambling need direct supporting evidence; a general news site with an occasional gambling advertisement must not be automatically labeled gambling. Document mixed cases for review.

Educational discussion, research, prevention, recovery/support and reporting about gambling are non-gambling when informational. Ordinary video games are non-gambling under this policy. Games with real-value wagering/cash-out mechanics require review under the positive definition. Simulated casinos with demonstrably nonredeemable play currency and no transferable-value wagering are non-gambling for this binary task; record the simulated nature in evidence. If redemption, trading, prizes, loot-box or sweepstakes mechanics are unclear, use unknown and obtain a second review.

Mixed-purpose websites need particular care: label a dedicated wagering subdomain independently when evidence supports it; do not infer the parent or all sibling subdomains share its label. If the hostname itself mixes substantial wagering and unrelated services and a domain-level decision would be misleading, use unknown. The DNS input cannot distinguish HTTPS paths.

Workflow:

1. Start collected observations as `pending`; capture the exact source snapshot/list ID and its terms. Blocklist membership and popularity are candidate evidence, never automatic ground truth.
2. A reviewer applies this policy using recorded evidence, supplies `reviewed_by` and a timezone-aware `reviewed_at`, and records limitations. Unresolved cases remain unknown/pending. Conflicts and borderline cases require a second reviewer; record the resolution in evidence before training.
3. Resolve duplicate-host label conflicts explicitly. Same hostname with different historical labels needs a defined observation cutoff, not majority voting. Keep original provenance in private source records.
4. Link aliases/operators only with reliable documented evidence, such as verified ownership or operator disclosures. Matching keywords, shared hosting/CDN/IP, and similar names are insufficient.
5. Mark usage approval only after reviewing the actual snapshot's license/terms. Do not assume public availability grants redistribution/training rights.

Only reviewed `gambling`/`non_gambling` observations with approved usage enter supervised learning. Reviewed unknown remains an explicit catalog hold: the API will not replace it with a model prediction. No predictions, manual Block/Allow choices, DNS events, or unreviewed blocklist rows become training labels automatically.
