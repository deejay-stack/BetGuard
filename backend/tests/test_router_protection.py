import asyncio
import copy
import json
import struct
import time
from dataclasses import replace
from unittest.mock import patch

import pytest
from dnslib import A, CNAME, DNSRecord, EDNS0, EDNSOption, QTYPE, RCODE, RR
from fastapi.testclient import TestClient

from app.main import app
from app.router.base import RouterError, RouterOffline
from app.router.config import RouterSettings
from app.router.dns import DnsFilter
from app.router.openwrt import OpenWrtAdapter
from app.router.policy import SharedPolicy
from app.router.service import RouterProtection
from app.router.store import RouterStore


@pytest.fixture
def settings(tmp_path):
    return RouterSettings("127.0.0.1", 0, ("127.0.0.2",), "1.1.1.1", "t"*40, tmp_path / "router.sqlite3")


class Runtime:
    def get_status(self):
        return {"gambling_blocklist_domains": 10}

    def evaluate(self, domain):
        block, warn = domain == "stake.com", domain == "microsoft.com"
        return dict(domain=domain, enforcement_action="BLOCK" if block else "ALLOW",
                    intervention="BLOCK" if block else "WARN" if warn else "NONE",
                    decision_source="verified_gambling_blocklist" if block else "ml_warning" if warn else "ml_low_risk",
                    risk_status="verified_gambling" if block else "suspicious" if warn else "low")


class FakeOpenWrt(OpenWrtAdapter):
    def __init__(self):
        self.url, self.host, self.sid = "https://192.168.10.1/ubus", "192.168.10.1", "f"*32
        self.configs = {
            "dhcp": {"dns": {".type": "dnsmasq", "server": ["9.9.9.9"], "cachesize": "1000", "domain": "lan"},
                     "lan": {".type": "dhcp", "interface": "lan", "dhcp_option": ["6,9.9.9.9", "42,192.168.10.10"], "leasetime": "12h"}},
            "firewall": {"lan": {".type": "zone", "name": "lan", "network": ["lan"], "input": "ACCEPT"}, "keep": {".type": "rule", "name": "Keep unrelated"}}
        }
        self.before = copy.deepcopy(self.configs)
        self.calls = []
        self.confirmed = False

    def rpc(self, obj, method, args=None):
        args = args or {}
        self.calls.append((obj, method, copy.deepcopy(args)))
        if obj == "system":
            return {"release": {"distribution": "OpenWrt", "version": "24.10.0"}}
        if obj == "network.interface.lan":
            return {"up": True, "l3_device": "br-lan", "ipv4-address": [{"address": self.host, "mask": 24}]}
        if obj == "network.device":
            return {"macaddr": "02:00:00:00:10:01"}
        if obj == "uci":
            if method == "changes": return {"changes": {}}
            if method == "get": return {"values": copy.deepcopy(self.configs[args["config"]])}
            if method == "set": self.configs[args["config"]][args["section"]].update(args["values"])
            if method == "add": self.configs[args["config"]][args["name"]] = {".type": args["type"], **args["values"]}
            if method == "delete":
                if "option" in args: self.configs[args["config"]][args["section"]].pop(args["option"], None)
                else: self.configs[args["config"]].pop(args["section"], None)
            if method == "confirm": self.confirmed = True
        return {}

    def execute(self, command, params):
        if command.endswith("dnsmasq"):
            return "--add-subnet --strip-subnet"
        if command.endswith("nft"):
            rules = [{"rule": {"comment": "!fw4: " + rule["name"], "expr": [{"redirect": {"port": 53}}]}}
                     for rule in self.configs["firewall"].values() if rule.get(".type") == "redirect"]
            return json.dumps({"nftables": rules})
        return ""

    def login(self, *_args): pass
    def close(self): pass


def rule(domain, action, subdomains=False):
    return dict(domain=domain, action=action, includeSubdomains=subdomains, updatedAt=1)


def test_uci_minimal_apply_and_exact_restore():
    adapter = FakeOpenWrt()
    plan = adapter.plan(adapter.inspect(), "192.168.10.20", 5353, "bg_dns_test")
    adapter.apply(plan)
    adapter.verify(plan)
    adapter.confirm()
    assert adapter.configs["dhcp"]["dns"]["server"] == ["192.168.10.20#5353"]
    assert adapter.configs["dhcp"]["dns"]["stripsubnet"] == "1"
    assert adapter.configs["dhcp"]["lan"]["dhcp_option"] == ["42,192.168.10.10", "6,192.168.10.1"]
    assert ("uci", "apply", {"rollback": True, "timeout": 60}) in adapter.calls
    adapter.restore(plan)
    assert adapter.configs == adapter.before
    adapter.restore(plan)  # recovery after rpcd already rolled back is idempotent
    assert adapter.configs == adapter.before


def test_restore_conflict_preserves_administrator_edit():
    adapter = FakeOpenWrt()
    plan = adapter.plan(adapter.inspect(), "192.168.10.20", 5353, "bg_dns_test")
    adapter.apply(plan)
    adapter.configs["dhcp"]["dns"]["server"] = ["8.8.8.8"]
    with pytest.raises(RouterError, match="conflicts"):
        adapter.restore(plan)
    assert adapter.configs["dhcp"]["dns"]["server"] == ["8.8.8.8"]


@pytest.mark.parametrize("url", ["http://192.168.1.1", "https://user:password@192.168.1.1", "https://8.8.8.8", "https://192.168.1.1/other", "https://192.168.1.1?secret=x"])
def test_transport_rejects_insecure_or_unapproved_targets(url):
    with pytest.raises(RouterError):
        OpenWrtAdapter(url, ("192.168.1.1",))


def test_untrusted_tls_never_falls_back_to_plaintext():
    adapter = OpenWrtAdapter("https://192.168.1.1", ("192.168.1.1",))
    with patch.object(adapter.opener, "open", side_effect=Exception("password=secret")):
        with pytest.raises(RouterError) as caught:
            adapter.login("root", "secret")
    assert "secret" not in str(caught.value)


def test_shared_rules_most_specific_and_runtime_warn(tmp_path):
    store = RouterStore(tmp_path / "state.sqlite3")
    policy = SharedPolicy(Runtime(), store)
    policy.sync([rule("stake.com", "allow", True), rule("casino.stake.com", "block"), rule("exact.com", "block")])
    assert policy.evaluate("www.stake.com")["enforcement_action"] == "ALLOW"
    assert policy.evaluate("casino.stake.com")["enforcement_action"] == "BLOCK"
    assert policy.evaluate("www.exact.com")["enforcement_action"] == "ALLOW"
    assert policy.evaluate("microsoft.com")["intervention"] == "WARN"
    policy.sync([rule("microsoft.com", "block")])
    assert policy.evaluate("microsoft.com")["enforcement_action"] == "BLOCK"
    policy.sync([rule("microsoft.com", "allow")])
    assert policy.evaluate("microsoft.com")["intervention"] == "NONE"
    store.close()


def test_real_frozen_runtime_router_decisions(tmp_path):
    from betguard_runtime.runtime_service import BetGuardRuntime
    runtime = BetGuardRuntime(verbose=False, use_user_lists=False)
    store = RouterStore(tmp_path / "real.sqlite3")
    policy = SharedPolicy(runtime, store)
    for domain, action, intervention in [("wikipedia.org", "ALLOW", "NONE"), ("stake.com", "BLOCK", "BLOCK"), ("microsoft.com", "ALLOW", "WARN")]:
        result = policy.evaluate(domain)
        assert (result["enforcement_action"], result["intervention"]) == (action, intervention)
    store.close()


def test_dns_udp_tcp_client_identity_privacy_and_rule_propagation(settings):
    async def scenario():
        store = RouterStore(settings.state_path)
        policy = SharedPolicy(Runtime(), store)
        session = {"state": "active", "plan": {"subnets": ["192.168.10.0/24"]}}
        dns = DnsFilter(settings, policy, store, lambda: session)
        async def upstream(query, *, tcp):
            response = query.reply()
            response.add_answer(RR(query.q.qname, QTYPE.A, rdata=A("93.184.216.34"), ttl=300))
            return response
        dns.forward = upstream
        await dns.start()
        udp_port = dns.udp.get_extra_info("sockname")[1]
        tcp_port = dns.tcp.sockets[0].getsockname()[1]
        async def exchange(domain, client, tcp=False):
            query = DNSRecord.question(domain)
            ecs = struct.pack("!HBB", 1, 32, 0) + bytes(map(int, client.split(".")))
            query.add_ar(EDNS0(opts=[EDNSOption(8, ecs)]))
            payload = query.pack()
            if tcp:
                reader, writer = await asyncio.open_connection(settings.bind, tcp_port, local_addr=(settings.peers[0], 0))
                writer.write(struct.pack("!H", len(payload)) + payload)
                size = struct.unpack("!H", await asyncio.wait_for(reader.readexactly(2), 2))[0]
                raw = await asyncio.wait_for(reader.readexactly(size), 2)
                writer.close()
                await writer.wait_closed()
            else:
                import socket
                sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
                sock.bind((settings.peers[0], 0)); sock.setblocking(False)
                loop = asyncio.get_running_loop()
                await loop.sock_sendto(sock, payload, (settings.bind, udp_port))
                raw, _ = await asyncio.wait_for(loop.sock_recvfrom(sock, 4096), 2)
                sock.close()
            return DNSRecord.parse(raw)
        assert (await exchange("wikipedia.org", "192.168.10.42")).header.rcode == RCODE.NOERROR
        assert (await exchange("stake.com", "192.168.10.43", True)).header.rcode == RCODE.NXDOMAIN
        assert (await exchange("microsoft.com", "192.168.10.42")).header.rcode == RCODE.NOERROR
        assert store.history()[0]["kind"] == "router_warning"
        policy.sync([rule("microsoft.com", "block")])
        assert (await exchange("microsoft.com", "192.168.10.43", True)).header.rcode == RCODE.NXDOMAIN
        assert {row["ip"] for row in store.clients()} == {"192.168.10.42", "192.168.10.43"}
        results = await asyncio.gather(*(exchange("stake.com", "192.168.10.42", i%2 == 0) for i in range(20)))
        assert all(r.header.rcode == RCODE.NXDOMAIN for r in results)
        assert await dns.answer(DNSRecord.question("stake.com").pack(), "192.168.99.99", tcp=False) is None
        query = DNSRecord.question("wikipedia.org")
        query.add_ar(EDNS0(opts=[EDNSOption(8, struct.pack("!HBB", 1, 32, 0)+bytes([8,8,8,8]))]))
        assert await dns.answer(query.pack(), settings.peers[0], tcp=False) is None
        await dns.close()
        store.close()
    asyncio.run(scenario())


def test_dns_upstream_failure_and_alias_block(settings):
    async def scenario():
        store = RouterStore(settings.state_path)
        policy = SharedPolicy(Runtime(), store)
        dns = DnsFilter(settings, policy, store, lambda: {"state": "active"})
        async def fail(*args, **kwargs): raise TimeoutError()
        dns.forward = fail
        data = await dns.answer(DNSRecord.question("wikipedia.org").pack(), settings.bind, tcp=False)
        assert DNSRecord.parse(data).header.rcode == RCODE.SERVFAIL
        assert store.history()[0]["kind"] == "router_error"
        async def alias(query, **kwargs):
            response = query.reply()
            response.add_answer(RR(query.q.qname, QTYPE.CNAME, rdata=CNAME("stake.com")))
            return response
        dns.forward = alias
        data = await dns.answer(DNSRecord.question("wikipedia.org").pack(), settings.bind, tcp=True)
        assert DNSRecord.parse(data).header.rcode == RCODE.NXDOMAIN
        store.close()
    asyncio.run(scenario())


def test_private_edns_options_never_leave_filter():
    query = DNSRecord.question("wikipedia.org", "AAAA")
    query.add_ar(EDNS0(flags="do", opts=[EDNSOption(8, struct.pack("!HBB", 1, 32, 0)+bytes([192,168,10,42])), EDNSOption(65001, b"private-mac")]))
    upstream = DnsFilter.outgoing(query)
    assert upstream.q == query.q
    assert all(not rr.rdata for rr in upstream.ar)
    assert upstream.ar[0].ttl & 0x8000
    assert b"private-mac" not in upstream.pack()


def test_live_firewall_and_stale_preview_are_checked():
    adapter = FakeOpenWrt()
    plan = adapter.plan(adapter.inspect(), "192.168.10.20", 5353, "bg_dns_test")
    adapter.configs["dhcp"]["dns"]["server"] = ["8.8.8.8"]
    with pytest.raises(RouterError, match="changed since"):
        adapter.apply(plan)
    assert not any(call[1] == "set" for call in adapter.calls)
    adapter.configs = copy.deepcopy(adapter.before)
    adapter.apply(plan)
    with patch.object(adapter, "execute", return_value='{"nftables": []}'):
        with pytest.raises(RouterError, match="live firewall"):
            adapter.verify(plan)


def test_restore_rejects_a_different_router_at_the_same_address():
    adapter = FakeOpenWrt()
    plan = adapter.plan(adapter.inspect(), "192.168.10.20", 5353, "bg_dns_test")
    adapter.apply(plan)
    calls_before = len(adapter.calls)
    with patch.object(adapter, "identity", return_value="02:00:00:00:99:99"):
        with pytest.raises(RouterError, match="hardware identity"):
            adapter.restore(plan)
    assert not any(method in ("set", "delete", "apply") for _, method, _ in adapter.calls[calls_before:])


def test_router_health_failure_never_reports_active(settings):
    value = RouterProtection(settings, Runtime())
    value.dns.running = True
    adapter = FakeOpenWrt()
    plan = adapter.plan(adapter.inspect(), "192.168.10.20", 5353, "bg_dns_test")
    value.adapter = adapter
    value.store.put("session", dict(state="active", plan=plan, verifiedAt=time.time(), detail="Verified"))
    with patch.object(adapter, "verify", side_effect=RouterOffline("Router unreachable")):
        with pytest.raises(RouterOffline): value.verify()
    assert value.status()["state"] == "offline"
    assert value.status()["enforcementVerified"] is False
    value.store.close()


def test_dns_shutdown_waits_for_inflight_runtime_work(settings):
    from threading import Event
    async def scenario():
        store = RouterStore(settings.state_path)
        policy = SharedPolicy(Runtime(), store)
        dns = DnsFilter(settings, policy, store, lambda: {"state": "active"})
        started, release = Event(), Event()
        original = policy.evaluate
        def delayed(domain):
            started.set()
            release.wait(3)
            return original(domain)
        policy.evaluate = delayed
        task = asyncio.create_task(dns.answer(DNSRecord.question("stake.com").pack(), settings.bind, tcp=False))
        dns.tasks.add(task)
        assert await asyncio.to_thread(started.wait, 2)
        closing = asyncio.create_task(dns.close())
        await asyncio.sleep(0.02)
        assert not closing.done()
        release.set()
        await asyncio.wait_for(closing, 2)
        assert not dns.jobs
        store.close()
    asyncio.run(scenario())


def test_apply_restore_failure_and_restart_recovery(settings):
    settings = replace(settings, bind="192.168.10.20", port=5353)
    value = RouterProtection(settings, Runtime())
    value.dns.running = True
    value.policy.sync([])
    adapter = FakeOpenWrt()
    value.adapter_factory = lambda *_: adapter
    preview = value.connect(adapter.url, "root", "never-persist-password", True)
    assert preview["state"] == "preview"
    with pytest.raises(RouterError): value.apply(preview["preview"], False)
    adapter.probe = lambda domain: value.dns.probes.update({(adapter.host, domain): (time.monotonic(), "BLOCK" if domain == "stake.com" else "ALLOW", 3 if domain == "stake.com" else 0)})
    active = value.apply(preview["preview"], True)
    assert active["state"] == "active" and adapter.confirmed
    assert "never-persist-password" not in settings.state_path.read_bytes().decode("latin1")
    value.store.close()
    recovered = RouterProtection(settings, Runtime())
    assert recovered.status()["state"] == "recovery_required"
    recovered.adapter = adapter
    with patch.object(adapter, "restore", side_effect=RouterError("offline")):
        with pytest.raises(RouterError): recovered.stop()
    assert recovered.status()["state"] == "recovery_required"
    assert recovered.stop()["state"] == "off"
    assert adapter.configs == adapter.before
    recovered.store.close()


def test_setup_never_marks_active_before_probe(settings):
    settings = replace(settings, bind="192.168.10.20", port=5353)
    value = RouterProtection(settings, Runtime())
    value.dns.running = True
    value.policy.sync([])
    adapter = FakeOpenWrt()
    value.adapter_factory = lambda *_: adapter
    preview = value.connect(adapter.url, "root", "secret", True)
    adapter.probe = lambda _: None
    with pytest.raises(RouterError, match="restored"):
        value.apply(preview["preview"], True)
    assert value.status()["state"] == "off"
    assert adapter.configs == adapter.before
    value.store.close()


def test_router_api_requires_token_and_redacts_invalid_password(settings):
    value = RouterProtection(settings, Runtime())
    original = getattr(app.state, "router_protection", None)
    app.state.router_protection = value
    try:
        client = TestClient(app)
        assert client.get("/v1/router/status").status_code == 401
        headers = {"Authorization": "Bearer " + settings.token}
        assert client.get("/v1/router/status", headers=headers).status_code == 200
        response = client.post("/v1/router/connect", headers=headers, json={"password": "private-password", "authorized": False})
        assert response.status_code == 422 and "private-password" not in response.text
        assert client.post("/v1/router/policy", headers=headers, json={"rules": [rule("microsoft.com", "block")]}).status_code == 200
        assert value.policy.evaluate("microsoft.com")["enforcement_action"] == "BLOCK"
    finally:
        app.state.router_protection = original
        value.store.close()
