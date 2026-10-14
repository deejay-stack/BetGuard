"""Pure-Python regression tests; does not open WinDivert or change networking."""

import os
import struct
import sys
import time
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.router.ics_redirector import (
    BridgeOptions, IcsDnsBridge, build_filter, dns_probe_payload,
    dns_transaction_id,
)


class FakePacket:
    def __init__(self, inbound, client, port, ident, is_response=False):
        self.is_outbound = not inbound
        self.src_addr = "192.168.137.1" if is_response else client
        self.dst_addr = client if is_response else "192.168.137.1"
        self.src_port = 5300 if is_response else port
        self.dst_port = port if is_response else 53
        flags = 0x8180 if is_response else 0x0100
        self.payload = struct.pack("!HHHHHH", ident, flags, 1, 0, 0, 0)


class FakeDivert:
    def __init__(self):
        self.sent = []

    def send(self, packet):
        self.sent.append((packet.src_addr, packet.src_port,
                          packet.dst_addr, packet.dst_port))


class BridgeTests(unittest.TestCase):
    def test_filter_matches_tested_network(self):
        rules = build_filter(BridgeOptions())
        for content in ("192.168.137.3", "192.168.137.254", "udp.DstPort == 53",
                        "udp.SrcPort == 5300", "192.168.137.1"):
            self.assertIn(content, rules)

    def test_probe_wire_format_and_question_validation(self):
        packet = dns_probe_payload("stake.com", 1234)
        self.assertEqual(dns_transaction_id(packet, False), 1234)
        self.assertIsNone(dns_transaction_id(packet, True))
        self.assertIsNone(dns_transaction_id(b"x", False))
        reply = bytearray(packet)
        reply[2:4] = struct.pack("!H", 0x8183)
        self.assertEqual(dns_transaction_id(bytes(reply), True), 1234)

    def test_matching_reply_gets_port_53(self):
        bridge = IcsDnsBridge(max_seconds=10)
        fake = FakeDivert()
        bridge._process(fake, FakePacket(True, "192.168.137.216", 52000, 123))
        self.assertEqual(fake.sent[-1][-1], 5300)
        bridge._process(fake, FakePacket(False, "192.168.137.216", 52000, 123, True))
        self.assertEqual(fake.sent[-1][1], 53)
        self.assertEqual(bridge.stats["requests"], 1)
        self.assertEqual(bridge.stats["responses"], 1)
        self.assertEqual(bridge.stats["client_count"], 1)
        self.assertEqual(len(bridge.pending), 0)

    def test_unmatched_reply_keeps_original_port(self):
        bridge = IcsDnsBridge()
        fake = FakeDivert()
        bridge._process(fake, FakePacket(False, "192.168.137.216", 52000, 777, True))
        self.assertEqual(fake.sent[-1][1], 5300)
        self.assertEqual(bridge.stats["unmatched_responses"], 1)

    def test_client_ports_do_not_cross_match(self):
        bridge = IcsDnsBridge()
        fake = FakeDivert()
        bridge._process(fake, FakePacket(True, "192.168.137.216", 52000, 42))
        bridge._process(fake, FakePacket(True, "192.168.137.239", 53000, 42))
        bridge._process(fake, FakePacket(False, "192.168.137.239", 53000, 42, True))
        self.assertEqual(bridge.stats["responses"], 1)
        self.assertEqual(len(bridge.pending), 1)
        self.assertIn(("192.168.137.216", 52000, 42), bridge.pending)

    def test_expired_pending_entries_removed(self):
        bridge = IcsDnsBridge()
        bridge.pending[("192.168.137.216", 53000, 5)] = time.monotonic() - 30
        bridge._prune_pending(time.monotonic())
        self.assertFalse(bridge.pending)


if __name__ == "__main__":
    unittest.main()
