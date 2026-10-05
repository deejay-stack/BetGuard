"""Offline observation validation, provenance audit and leakage grouping."""
import json
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from pydantic import Field, StrictBool, ValidationError, field_validator, model_validator
from app.schemas.catalog import CatalogEntry, normalize_hostname
from app.ml import POLICY_VERSION
from app.ml.runtime import digest, json_write, psl_metadata, registrable_domain


class Observation(CatalogEntry):
    record_id: str = Field(min_length=1, max_length=120)
    source_uri: str = Field(min_length=1, max_length=1000)
    collected_at: datetime
    license: str = Field(min_length=1, max_length=200)
    license_uri: str = Field(min_length=1, max_length=1000)
    usage_allowed: StrictBool
    reviewed_by: str | None = Field(default=None, max_length=200)
    evidence: str = Field(min_length=1, max_length=2000)
    policy_version: str
    related_group_id: str | None = Field(default=None, max_length=200)
    related_group_evidence: str | None = Field(default=None, max_length=2000)
    synthetic: StrictBool = False

    @field_validator("record_id", "source_uri", "license", "license_uri", "evidence")
    @classmethod
    def not_blank(cls, value):
        if not value.strip():
            raise ValueError("Provenance fields cannot be blank.")
        return value.strip()

    @model_validator(mode="after")
    def metadata_valid(self):
        if self.collected_at.tzinfo is None or self.collected_at > datetime.now(timezone.utc):
            raise ValueError("Collection date needs a timezone and cannot be in the future.")
        if self.review_status == "reviewed" and not (self.reviewed_by or "").strip():
            raise ValueError("Reviewed observations need a reviewer identifier.")
        if self.policy_version != POLICY_VERSION:
            raise ValueError("Resolve labels using the current labeling policy.")
        if self.related_group_id is not None and (
            not self.related_group_id.strip() or not (self.related_group_evidence or "").strip()
        ):
            raise ValueError("Related operators/aliases require reliable documented evidence.")
        return self


def group_records(records: list[Observation]) -> dict[str, str]:
    parent = {}

    def find(key):
        parent.setdefault(key, key)
        while parent[key] != key:
            parent[key] = parent[parent[key]]
            key = parent[key]
        return key

    def union(left, right):
        a, b = find(left), find(right)
        parent[max(a, b)] = min(a, b)

    for row in records:
        site = "domain:" + registrable_domain(row.hostname)
        union("host:" + row.hostname, site)
        if row.related_group_id:
            union(site, "operator:" + row.related_group_id)
    return {row.record_id: find("host:" + row.hostname) for row in records}


def audit(path: Path):
    if path.stat().st_size > 50_000_000:
        raise ValueError("Dataset exceeds the 50 MB audit limit. Use a reviewed smaller dataset.")
    records, invalid, missing, empty_values = [], [], Counter(), Counter()
    total = 0
    for line_number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        if not line.strip():
            continue
        total += 1
        try:
            raw = json.loads(line)
            if isinstance(raw, dict):
                for field, definition in Observation.model_fields.items():
                    if definition.is_required() and (raw.get(field) is None or (isinstance(raw.get(field), str) and not raw[field].strip())):
                        empty_values[field] += 1
            row = Observation.model_validate(raw)
            registrable_domain(row.hostname)
            records.append(row)
        except ValidationError as error:
            for issue in error.errors():
                if issue["type"] == "missing":
                    missing[str(issue["loc"][0])] += 1
            invalid.append({"line": line_number, "reason": "invalid_schema_or_review"})
        except (ValueError, TypeError):
            invalid.append({"line": line_number, "reason": "invalid_json_or_public_suffix"})
    by_host = defaultdict(list)
    for row in records:
        by_host[row.hostname].append(row)
    conflicts = sorted(host for host, rows in by_host.items() if len({r.classification for r in rows}) > 1)
    groups = group_records(records)
    group_labels = defaultdict(set)
    for row in records:
        group_labels[groups[row.record_id]].add(row.classification)
    ids = Counter(row.record_id for row in records)
    unique = [sorted(rows, key=lambda r: (not (r.review_status == "reviewed" and r.usage_allowed), r.record_id))[0]
              for host, rows in sorted(by_host.items()) if host not in conflicts]
    eligible = [r for r in unique if r.review_status == "reviewed" and r.classification != "unknown" and r.usage_allowed]
    report = {
        "dataset_sha256": digest(path), "policy_version": POLICY_VERSION, "psl": psl_metadata(),
        "rows": total, "valid_rows": len(records), "invalid_rows": len(invalid), "invalid": invalid,
        "missing_fields": dict(missing), "missing_null_or_blank_required_values": dict(empty_values),
        "class_counts_valid_rows": dict(Counter(r.classification for r in records)),
        "review_counts": dict(Counter(r.review_status for r in records)),
        "sources": dict(Counter(r.source_uri for r in records)), "licenses": dict(Counter(r.license for r in records)),
        "collected_at_range": [min((r.collected_at.isoformat() for r in records), default=None), max((r.collected_at.isoformat() for r in records), default=None)],
        "unique_hostnames": len(by_host), "duplicate_rows": len(records) - len(by_host),
        "duplicate_record_ids": sorted(key for key, count in ids.items() if count > 1),
        "conflicting_hostnames": conflicts, "related_groups": len(set(groups.values())),
        "mixed_label_groups": sum(len(labels) > 1 for labels in group_labels.values()),
        "synthetic_rows": sum(r.synthetic for r in records),
        "excluded_unreviewed_unknown_or_unlicensed": len(unique) - len(eligible),
        "supervised_unique_rows": len(eligible),
        "supervised_class_counts": dict(Counter(r.classification for r in eligible)),
        "status": "needs_review" if invalid or conflicts or any(n > 1 for n in ids.values()) else "validated_schema",
    }
    return report, eligible, groups


def usable_data(path: Path, *, software_test=False):
    report, records, groups = audit(path)
    if report["status"] != "validated_schema":
        raise ValueError("Dataset has invalid rows, conflicting hosts or duplicate record IDs. Resolve the audit first.")
    if report["synthetic_rows"] and not software_test:
        raise ValueError("Synthetic data is permitted only in software tests, never development training/export.")
    if not records:
        raise ValueError("No reviewed, licensed binary observations are available.")
    return report, records, groups
