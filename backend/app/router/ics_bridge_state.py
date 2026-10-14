"""Read-only cross-process status and stop-signal helpers for the ICS DNS bridge.

The helper is started independently with Administrator privileges. The FastAPI
process only reads this status; it does NOT receive elevated permissions.
"""

from __future__ import annotations

import json
import os
import time
from pathlib import Path
from uuid import uuid4

STATUS_STALE_SECONDS = 12.0


def state_directory() -> Path:
    """backend/.local; place inside the existing project's local state folder."""
    return Path(__file__).resolve().parents[2] / ".local"


def status_path() -> Path:
    return state_directory() / "ics_dns_bridge_status.json"


def stop_path() -> Path:
    return state_directory() / "ics_dns_bridge_stop.json"


def write_json_atomic(destination: Path, content: dict) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = destination.with_name(f"{destination.name}.{uuid4().hex}.tmp")
    try:
        with temporary.open("w", encoding="utf-8") as stream:
            json.dump(content, stream, sort_keys=True)
            stream.write("\n")
        os.replace(temporary, destination)
    finally:
        temporary.unlink(missing_ok=True)


def read_json(source: Path) -> dict | None:
    try:
        with source.open("r", encoding="utf-8") as stream:
            data = json.load(stream)
        return data if isinstance(data, dict) else None
    except (OSError, ValueError, TypeError):
        return None


def bridge_status() -> dict:
    """Best-effort observability, NOT proof of network-wide enforcement."""
    data = read_json(status_path())
    if not data:
        return {"state": "not_started", "active": False,
                "detail": "The privileged ICS DNS helper has not reported status."}

    state = str(data.get("state", "unknown"))
    last_seen = data.get("updated_at")
    age = (time.time() - last_seen) if isinstance(last_seen, (int, float)) else float("inf")
    active = state == "running" and -5 <= age <= STATUS_STALE_SECONDS
    if state == "running" and not active:
        state = "stale"

    # No client addresses, credentials, or raw DNS queries in the API response.
    return {
        "state": state,
        "active": active,
        "detail": ("Heartbeat received; DNS behavior still requires client tests."
                   if active else "Bridge is stopped, unavailable, or its heartbeat is stale."),
        "gateway": data.get("gateway"),
        "filter_port": data.get("filter_port"),
        "pid": data.get("pid"),
        "requests": data.get("requests", 0),
        "responses": data.get("responses", 0),
        "unmatched_responses": data.get("unmatched_responses", 0),
        "client_count": data.get("client_count", 0),
        "updated_at": last_seen,
        "stopped_reason": data.get("stopped_reason"),
        "enforcement_verified": False,
    }
