# Reusable network detection interface

This audit implemented no router configuration or network changes. Existing
user work already includes `backend/app/router/`, router API/screens and
frontend LAN/VPN services. These files were retained and included in tests.
They must not be described as a router milestone implemented by this audit.

The domain service is already independent of React screens:
`app.services.domain_service.evaluate(runtime, domains)` accepts normalized
hostnames and returns validated `DomainDecision` objects. Mobile clients use
POST `/v1/domain/check` or `/v1/domain/check-batch` (maximum 100), while existing
router `SharedPolicy` wraps the same service after its replicated manual rules.
No retraining or network downloads belong in the DNS request path.

| Interface | Existing capability / minimum requirement |
| --- | --- |
| Normalize/query | Reuse strict `normalize_hostname`; canonical ASCII host, IDNA handling, hostname only. Reject invalid requests, credentials and IP literals consistently |
| Manual exceptions | Scoped exact/subdomain rules, most-specific match, explicit allow or block, atomic revisioned snapshots. Room is device authority; router replica must not become all users' shared defaults |
| Reference list | Load maintained source-supported domains once, suffix-boundary match to registrable family, audited provenance/update version and cache invalidation |
| ML inference | Existing baseline loaded once; classification and enforcement remain distinct. Shadow adapter outputs `decision_score`, `score_type=svm_margin`, threshold and predicted label; it supplies no automatic-block authorization |
| DNS decision | BLOCK -> NXDOMAIN; ALLOW/NONE and ALLOW/WARN -> validated upstream response; unavailable/malformed -> SERVFAIL/error. Log policy blocks separately from resolver failures |
| Cache | Current locked bounded 10,000-entry domain decision cache; include model/list/policy revisions and user scope if adding another policy cache. Never reuse an allow/block after a rule edit |
| DNS forwarding | Existing router module supports bounded UDP/TCP, response/question validation, CNAME/DNAME checks, trusted-peer restrictions and TTL caps; review and test that user's module independently before deploying |
| Clients | Stable client identity and trusted attribution, per-network authorization, bounded connection/request tracking. Existing SQLite stores sessions/events; Room rules are not implicitly global |
| Monitoring | Live/detection/router health, latency, model version, list revision, cache hits, DNS counts/errors, degraded/unavailable states. Hostname-only logs with retention/access controls |
| Administration | Existing router bearer-token checks and explicit authorization fields; configuration preview, durable backup, restoration/verification. Do not invoke these operations during a source audit |

Two policies must stay distinct: the standalone engine checks its text allowlist
before its blocklist; native/router replicated manual rules intentionally pick
the longest matching domain. A network service must retain the intended scope
and specificity rather than silently changing exceptions. Explicit manual
allows must also protect against secondary alias/ML blocks.

The existing optional router settings can describe OpenWrt peers or stock
DHCP client networks, but source presence is not deployment proof. The service
has no demonstrated administrator access to a particular user's router here.
Inspect supported DHCP/DNS settings and topology only with authorization.
Encrypted DNS, cached/established connections, direct IP traffic and unsupported
resolver paths can bypass DNS filtering. TLS content inspection and universal
traffic blocking are not implied by a DNS decision interface.

For eventual SVM integration, first define and validate a margin-compatible
response contract or independently validated calibration. The current backend,
JS and Kotlin [0,1] score contract cannot carry raw margins. Then set separate
classification/warning/automatic-block criteria from new reviewed data, retain
baseline config selection, and test service failure plus manual rule precedence
on controlled staging devices. No new `BETGUARD_ML_MODEL` setting was invented;
the existing deployment manifest/resource-root convention remains the source
of selection.
