"""Shared inference eligibility, artifact integrity and abstention helpers."""
import hashlib
import importlib.metadata
import importlib.resources
import json
from pathlib import Path
import numpy as np
import tldextract
from app.schemas.catalog import normalize_hostname

# Pinned offline PSL snapshot; no startup download or filesystem cache.
EXTRACT = tldextract.TLDExtract(
    suffix_list_urls=(), cache_dir=None, include_psl_private_domains=True,
)


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def json_write(path: Path, data):
    path.write_text(json.dumps(data, indent=2, sort_keys=True, allow_nan=False) + "\n", encoding="utf-8")


def psl_metadata():
    snapshot = importlib.resources.files("tldextract").joinpath(".tld_set_snapshot").read_bytes()
    return {"library": importlib.metadata.version("tldextract"),
            "snapshot_sha256": hashlib.sha256(snapshot).hexdigest(), "private_suffixes": True}


def registrable_domain(value: str) -> str:
    host = normalize_hostname(value)
    result = EXTRACT(host)
    if not result.suffix or not result.domain:
        raise ValueError("Hostname has no registrable domain in the pinned public suffix snapshot.")
    return result.top_domain_under_public_suffix


def decisions(score, thresholds):
    score = np.asarray(score)
    result = np.full(score.shape, -1, dtype=int)
    if thresholds["non_gambling_max"] is not None:
        result[score <= thresholds["non_gambling_max"]] = 0
    if thresholds["gambling_min"] is not None:
        result[score >= thresholds["gambling_min"]] = 1
    return result


