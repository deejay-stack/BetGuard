"""Windows ICS IPv4 UDP DNS redirector, running as a separate elevated process.

The FastAPI application MUST NOT be elevated to use this. A single Windows
WinDivert helper translates LAN DNS requests :53 to an existing BetGuard DNS
listener :5300, and translates only matching BetGuard replies back to :53.

Limitations: IPv4 UDP DNS only; does not intercept DoH, DoT, VPN, TCP DNS,
IPv6, or clients that use a different DNS destination. Stopping the helper
restores Windows ICS DNS (unfiltered): this is fail-open, not fail-closed.
"""

from __future__ import annotations

import ctypes
import os
import secrets
import signal
import socket
import struct
import threading
import time
from dataclasses import dataclass
from uuid import uuid4

from .ics_bridge_state import (
    bridge_status, read_json, status_path, stop_path, write_json_atomic,
)


@dataclass(frozen=True)
class BridgeOptions:
    gateway: str = "192.168.137.1"
    client_first: str = "192.168.137.3"
    client_last: str = "192.168.137.254"
    incoming_port: int = 53
    betguard_port: int = 5300
    outstanding_ttl: float = 20.0
    outstanding_limit: int = 8192
    health_interval: float = 6.0
    health_failures_before_stop: int = 3


def build_filter(options: BridgeOptions) -> str:
    return (
        f"((inbound and ip and udp and "
        f"ip.SrcAddr >= {options.client_first} and "
        f"ip.SrcAddr <= {options.client_last} and "
        f"ip.DstAddr == {options.gateway} and "
        f"udp.DstPort == {options.incoming_port}) "
        f"or (outbound and ip and udp and "
        f"ip.SrcAddr == {options.gateway} and "
        f"ip.DstAddr >= {options.client_first} and "
        f"ip.DstAddr <= {options.client_last} and "
        f"udp.SrcPort == {options.betguard_port}))"
    )


def dns_transaction_id(payload: bytes, is_response: bool) -> int | None:
    """Return the DNS transaction ID only for a plausible query/response."""
    if len(payload) < 12:
        return None
    txn_id, flags, questions = struct.unpack_from("!HHH", payload)
    if bool(flags & 0x8000) != is_response or not questions:
        return None
    return txn_id


def dns_probe_payload(domain: str, transaction_id: int) -> bytes:
    qname = b"".join(bytes([len(label)]) + label.encode("ascii")
                     for label in domain.split(".")) + b"\x00"
    return (struct.pack("!HHHHHH", transaction_id, 0x0100, 1, 0, 0, 0)
            + qname + struct.pack("!HH", 1, 1))


def test_betguard_dns(options: BridgeOptions) -> bool:
    """Fail-open prerequisite: both allow and block cases must work directly."""
    for domain, required_rcode in (("wikipedia.org", 0), ("stake.com", 3)):
        transaction_id = secrets.randbelow(65536)
        payload = dns_probe_payload(domain, transaction_id)
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
                sock.settimeout(1.5)
                sock.bind((options.gateway, 0))
                sock.sendto(payload, (options.gateway, options.betguard_port))
                result, _address = sock.recvfrom(4096)
        except OSError:
            return False
        if len(result) < 12 or int.from_bytes(result[:2], "big") != transaction_id:
            return False
        flags = int.from_bytes(result[2:4], "big")
        if not flags & 0x8000 or flags & 0xF != required_rcode:
            return False
    return True


def is_administrator() -> bool:
    if os.name != "nt":
        return False
    try:
        return bool(ctypes.windll.shell32.IsUserAnAdmin())
    except (OSError, AttributeError):
        return False


class ExclusiveWindowsMutex:
    """Prevent simultaneous elevated helpers modifying the same packets."""

    def __init__(self):
        self.handle = None
        self.kernel32 = None

    def __enter__(self):
        if os.name != "nt":
            raise RuntimeError("The ICS DNS bridge is supported only on Windows.")
        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        kernel32.CreateMutexW.argtypes = [ctypes.c_void_p, ctypes.c_int, ctypes.c_wchar_p]
        kernel32.CreateMutexW.restype = ctypes.c_void_p
        handle = kernel32.CreateMutexW(None, True, "Local\\BetGuardIcsDnsBridge")
        if not handle:
            raise OSError("Could not create the bridge's single-instance mutex.")
        if ctypes.get_last_error() == 183:  # ERROR_ALREADY_EXISTS
            kernel32.CloseHandle(ctypes.c_void_p(handle))
            raise RuntimeError("An ICS DNS bridge is already running.")
        self.handle, self.kernel32 = handle, kernel32
        return self

    def __exit__(self, *_exc):
        if self.handle:
            self.kernel32.ReleaseMutex(ctypes.c_void_p(self.handle))
            self.kernel32.CloseHandle(ctypes.c_void_p(self.handle))
            self.handle = None


class IcsDnsBridge:
    def __init__(self, options: BridgeOptions | None = None, max_seconds: int = 900):
        self.options = options or BridgeOptions()
        if max_seconds < 0:
            raise ValueError("max_seconds must be zero or positive")
        self.max_seconds = max_seconds  # 0 is explicit opt-in for continuous mode
        self.run_id = uuid4().hex
        self.request_stop = threading.Event()
        self.divert = None
        self.stats_lock = threading.Lock()
        self.stats = {"requests": 0, "responses": 0,
                      "unmatched_responses": 0, "client_count": 0}
        self.clients: set[str] = set()
        self.pending: dict[tuple[str, int, int], float] = {}
        self.stop_reason = ""

    def _report(self, state: str, reason: str | None = None):
        with self.stats_lock:
            stats = dict(self.stats)
        write_json_atomic(status_path(), {
            "run_id": self.run_id,
            "state": state,
            "pid": os.getpid(),
            "gateway": self.options.gateway,
            "filter_port": self.options.betguard_port,
            "updated_at": time.time(),
            "stopped_reason": reason,
            **stats,
        })

    def _request_shutdown(self, reason: str):
        if not self.request_stop.is_set():
            self.stop_reason = reason
        self.request_stop.set()
        try:
            if self.divert is not None and self.divert.is_open:
                self.divert.close()  # Unblocks recv(); ICS resumes serving port 53.
        except (OSError, RuntimeError):
            pass

    def _watchdog(self, started: float):
        failures = 0
        last_check = time.monotonic()
        while not self.request_stop.wait(1.0):
            if self.max_seconds and time.monotonic() - started >= self.max_seconds:
                self._request_shutdown("Time-limited run completed")
                return
            command = read_json(stop_path())
            if command and command.get("run_id") == self.run_id:
                self._request_shutdown("Stop requested by local administrator")
                return
            if time.monotonic() - last_check >= self.options.health_interval:
                last_check = time.monotonic()
                if test_betguard_dns(self.options):
                    failures = 0
                else:
                    failures += 1
                    if failures >= self.options.health_failures_before_stop:
                        self._request_shutdown("BetGuard DNS health checks failed; reverted to ICS DNS")
                        return
            try:
                self._report("running")
            except OSError as error:
                self._request_shutdown(f"Cannot update status heartbeat: {error}")
                return

    def _prune_pending(self, current: float):
        ttl = self.options.outstanding_ttl
        expired = [key for key, timestamp in self.pending.items()
                   if current - timestamp > ttl]
        for key in expired:
            self.pending.pop(key, None)

    def _process(self, divert, packet):
        payload = bytes(packet.payload)
        if packet.is_outbound:
            txn = dns_transaction_id(payload, is_response=True)
            key = (packet.dst_addr, packet.dst_port, txn)
            if txn is not None and key in self.pending:
                self.pending.pop(key, None)
                packet.src_port = self.options.incoming_port
                divert.send(packet)
                with self.stats_lock:
                    self.stats["responses"] += 1
            else:
                # Don't claim or rewrite a response we didn't initiate.
                divert.send(packet)
                with self.stats_lock:
                    self.stats["unmatched_responses"] += 1
            return

        txn = dns_transaction_id(payload, is_response=False)
        if txn is None or len(self.pending) >= self.options.outstanding_limit:
            # Malformed or overloaded traffic is handed back to ordinary ICS.
            divert.send(packet)
            return
        client = packet.src_addr
        key = (client, packet.src_port, txn)
        self.pending[key] = time.monotonic()
        packet.dst_port = self.options.betguard_port
        divert.send(packet)
        with self.stats_lock:
            self.stats["requests"] += 1
            self.clients.add(client)
            self.stats["client_count"] = len(self.clients)
            if self.stats["requests"] % 64 == 0:
                self._prune_pending(time.monotonic())

    def run(self):
        if not is_administrator():
            raise PermissionError("Start this helper in Windows PowerShell as Administrator.")
        # Avoid storing a misleading 'running' state when the backend is down.
        if not test_betguard_dns(self.options):
            raise RuntimeError(
                "BetGuard DNS did not pass allow/block probes at "
                f"{self.options.gateway}:{self.options.betguard_port}. "
                "Keep the backend on port 5300 and confirm both queries first."
            )

        try:
            import pydivert
        except ImportError as error:
            raise RuntimeError("Install pydivert in .venv-dns-bridge first.") from error

        with ExclusiveWindowsMutex():
            self._report("starting")
            divert = pydivert.WinDivert(build_filter(self.options))
            self.divert = divert
            watcher = None
            old_sigint = None
            try:
                divert.open()
                started = time.monotonic()
                # Close the handle from a watcher because recv() is blocking
                # and Windows can delay Ctrl+C while inside native recv().
                old_sigint = signal.getsignal(signal.SIGINT)
                signal.signal(signal.SIGINT,
                              lambda *_args: self._request_shutdown("Keyboard interrupt"))
                self._report("running")
                watcher = threading.Thread(target=self._watchdog, args=(started,), daemon=True)
                watcher.start()
                print("BetGuard ICS DNS bridge active (IPv4 UDP only).", flush=True)
                print("Stop from another Administrator PowerShell window using:", flush=True)
                print("  .\\.venv-dns-bridge\\Scripts\\python.exe .\\scripts\\ics_dns_control.py stop", flush=True)
                print("WARNING: if the bridge exits, ICS DNS becomes unfiltered.", flush=True)
                while not self.request_stop.is_set():
                    try:
                        packet = divert.recv()
                        self._process(divert, packet)
                    except Exception:
                        if self.request_stop.is_set():
                            break
                        raise
            except KeyboardInterrupt:
                self._request_shutdown("Keyboard interrupt")
            except Exception as error:
                self.stop_reason = f"Redirector error: {error}"
                raise
            finally:
                self._request_shutdown(self.stop_reason or "Service stopped")
                if watcher:
                    watcher.join(timeout=5)
                try:
                    if divert.is_open:
                        divert.close()
                except (OSError, RuntimeError):
                    pass
                if old_sigint is not None:
                    signal.signal(signal.SIGINT, old_sigint)
                self._report("stopped", reason=self.stop_reason)
                print(f"Bridge stopped. {self.stats}", flush=True)


def request_stop() -> bool:
    if not is_administrator():
        raise PermissionError("Stop the bridge from Windows PowerShell as Administrator.")
    status = read_json(status_path())
    if not status or bridge_status().get("state") != "running":
        return False
    run_id = status.get("run_id")
    if not run_id:
        return False
    write_json_atomic(stop_path(), {"run_id": run_id, "requested_at": time.time()})
    return True
