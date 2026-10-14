"""Unprivileged, read-only ICS DNS bridge status endpoint.

The bridge is controlled only from an Administrator PowerShell process.
Never expose start/stop of WinDivert as an unauthenticated HTTP action.
"""

from fastapi import APIRouter

from app.router.ics_bridge_state import bridge_status

router = APIRouter(prefix="/v1/ics-dns", tags=["ICS DNS"])


@router.get("/status")
def get_status():
    return bridge_status()
