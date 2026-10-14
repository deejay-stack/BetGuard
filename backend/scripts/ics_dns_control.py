r"""Manually control a separate, privileged Windows ICS DNS bridge.

From backend/ in Windows Administrator PowerShell:
  .\.venv-dns-bridge\Scripts\python.exe .\scripts\ics_dns_control.py start
  .\.venv-dns-bridge\Scripts\python.exe .\scripts\ics_dns_control.py status
  .\.venv-dns-bridge\Scripts\python.exe .\scripts\ics_dns_control.py stop

The FastAPI process is NOT started or elevated by this script.
"""

import argparse
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.router.ics_bridge_state import bridge_status
from app.router.ics_redirector import IcsDnsBridge, request_stop


def main():
    parser = argparse.ArgumentParser(description="BetGuard Windows ICS DNS bridge")
    subparsers = parser.add_subparsers(dest="command", required=True)
    start = subparsers.add_parser("start", help="Run the bounded elevated helper")
    start.add_argument("--max-seconds", type=int, default=900,
                       help="Duration; default 900, 0 for continuous (only after further tests)")
    subparsers.add_parser("status", help="Read non-privileged bridge status")
    subparsers.add_parser("stop", help="Request safe shutdown (Administrator)")
    args = parser.parse_args()

    if args.command == "status":
        print(json.dumps(bridge_status(), indent=2))
        return 0
    if args.command == "stop":
        if not request_stop():
            print("No active bridge reported. Nothing to stop.")
            return 0
        print("Stop requested. Waiting for the bridge to release WinDivert...")
        for _ in range(15):
            time.sleep(1)
            if not bridge_status()["active"]:
                print("Bridge stopped. Windows ICS DNS should be available again.")
                return 0
        print("Timed out waiting for status. Check the bridge terminal.")
        return 1

    if args.max_seconds < 0:
        parser.error("--max-seconds cannot be negative")
    print("BetGuard DNS must already be running on 192.168.137.1:5300.")
    print("This helper is IPv4 UDP-only and fail-open when it stops.")
    print(f"Duration: {args.max_seconds or 'CONTINUOUS'} seconds")
    try:
        IcsDnsBridge(max_seconds=args.max_seconds).run()
    except (OSError, RuntimeError, PermissionError) as error:
        print(f"Bridge could not start or stopped with an error: {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
