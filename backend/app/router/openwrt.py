"""OpenWrt ubus/UCI adapter. TLS verification is mandatory; no credential persistence."""
import copy
import ipaddress
import json
import re
import ssl
import urllib.request
import urllib.error
from urllib.parse import urlsplit

from .base import RouterError, RouterOffline

DNS_OPTIONS = ("server", "noresolv", "cachesize", "addsubnet", "stripsubnet")


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *args, **kwargs):
        raise RouterError("Router redirects are unsupported. Enter its direct HTTPS ubus address.")


class OpenWrtAdapter:
    def __init__(self, url, peers, ca_file=None):
        parts = urlsplit(url)
        try:
            host = str(ipaddress.ip_address(parts.hostname or ""))
            valid = (parts.scheme == "https" and host in peers and not parts.username and not parts.password
                     and parts.path in ("", "/", "/ubus") and not parts.query and not parts.fragment
                     and parts.port in (None, 443))
        except ValueError:
            valid = False
        if not valid:
            raise RouterError("Use the HTTPS IPv4 address of an operator-configured router peer, on port 443.")
        self.url = f"https://{host}/ubus"
        self.host = host
        self.sid = "0" * 32
        self.opener = urllib.request.build_opener(urllib.request.ProxyHandler({}), NoRedirect(),
                        urllib.request.HTTPSHandler(context=ssl.create_default_context(cafile=ca_file)))

    def rpc(self, obj, method, args=None):
        payload = json.dumps(dict(jsonrpc="2.0", id=1, method="call", params=[self.sid, obj, method, args or {}])).encode()
        request = urllib.request.Request(self.url, data=payload, headers={"Content-Type": "application/json"})
        try:
            with self.opener.open(request, timeout=5) as response:
                raw = response.read(262145)
            if len(raw) > 262144:
                raise ValueError()
            result = json.loads(raw).get("result")
            if not isinstance(result, list) or not result or result[0] != 0:
                raise ValueError()
            return result[1] if len(result) > 1 else {}
        except RouterError:
            raise
        except (urllib.error.URLError, TimeoutError, ConnectionError):
            raise RouterOffline("The router's HTTPS service is unreachable or its certificate is not trusted. Check the connection and reconnect securely.") from None
        except Exception:
            raise RouterError("OpenWrt did not accept the secure request. Check TLS trust, reachability, credentials and ubus permissions.") from None

    def login(self, username, password):
        result = self.rpc("session", "login", dict(username=username, password=password, timeout=300))
        sid = result.get("ubus_rpc_session", "")
        if not re.fullmatch(r"[a-f0-9]{32}", sid):
            raise RouterError("Router authentication failed.")
        self.sid = sid

    def execute(self, command, params):
        result = self.rpc("file", "exec", dict(command=command, params=params))
        if result.get("code") != 0:
            raise RouterError("A required OpenWrt diagnostic or reload failed.")
        return result.get("stdout", "")

    def values(self, config):
        return self.rpc("uci", "get", dict(config=config)).get("values", {})

    def clean(self):
        if any(self.rpc("uci", "changes").get("changes", {}).values()):
            raise RouterError("Finish or discard this administrator session's pending UCI changes before continuing.")

    def identity(self):
        network = self.rpc("network.interface.lan", "status")
        device = network.get("l3_device") or network.get("device")
        if not isinstance(device, str) or not device:
            raise RouterError("The router's LAN device identity is unavailable.")
        address = self.rpc("network.device", "status", {"name": device}).get("macaddr", "").lower()
        if not re.fullmatch(r"(?:[0-9a-f]{2}:){5}[0-9a-f]{2}", address) or address == "00:00:00:00:00:00":
            raise RouterError("The router's LAN hardware identity is unavailable.")
        return address

    def inspect(self):
        self.clean()
        board = self.rpc("system", "board")
        release = board.get("release", {})
        if release.get("distribution") != "OpenWrt":
            raise RouterError("This router did not identify itself as OpenWrt.")
        self.execute("/sbin/fw4", ["check"])
        help_text = self.execute("/usr/sbin/dnsmasq", ["--help"])
        if "--add-subnet" not in help_text or "--strip-subnet" not in help_text:
            raise RouterError("This dnsmasq build lacks the required client attribution options.")
        network = self.rpc("network.interface.lan", "status")
        ipv4 = network.get("ipv4-address", [])
        if not network.get("up") or len(ipv4) != 1:
            raise RouterError("This prototype requires one active OpenWrt LAN IPv4 subnet.")
        router_ip = ipv4[0]["address"]
        if self.host != router_ip:
            raise RouterError("Connect using the router's actual LAN IPv4 address.")
        subnets = [str(ipaddress.ip_network(f"{router_ip}/{ipv4[0]['mask']}", strict=False))]
        for item in network.get("ipv6-address", []):
            subnets.append(str(ipaddress.ip_network(f"{item['address']}/{item['mask']}", strict=False)))
        for item in network.get("ipv6-prefix-assignment", []):
            subnets.append(str(ipaddress.ip_network(f"{item['address']}/{item['mask']}", strict=False)))
        dhcp, firewall = self.values("dhcp"), self.values("firewall")
        dns = [(name, value) for name, value in dhcp.items() if value.get(".type") == "dnsmasq"]
        lan = [(name, value) for name, value in dhcp.items() if value.get(".type") == "dhcp" and value.get("interface") == "lan"]
        zones = [v for v in firewall.values() if v.get(".type") == "zone" and v.get("name") == "lan"]
        if len(dns) != 1 or len(lan) != 1 or len(zones) != 1 or str(dns[0][1].get("port", "53")) != "53" or lan[0][1].get("ignore") == "1":
            raise RouterError("Unsupported DNS/DHCP/firewall layout. Use a single dnsmasq instance and active LAN DHCP zone.")
        def items(value):
            return value.split() if isinstance(value, str) else value or []
        if "lan" not in items(zones[0].get("network")) or zones[0].get("input") != "ACCEPT":
            raise RouterError("This prototype requires an existing LAN zone with LAN membership and DNS input access; it will not change the zone policy.")
        options = dns[0][1]
        if ((options.get("interface") and "lan" not in items(options["interface"])) or
                "lan" in items(options.get("notinterface")) or
                (options.get("listen_address") and router_ip not in items(options["listen_address"]))):
            raise RouterError("The existing dnsmasq listener does not cover the LAN. Review it before configuring BetGuard.")
        for value in firewall.values():
            if value.get(".type") == "redirect" and value.get("src") == "lan" and value.get("enabled", "1") != "0":
                ports = str(value.get("src_dport", ""))
                if not ports or any(p == "53" or ("-" in p and int(p.split("-")[0]) <= 53 <= int(p.split("-")[1])) for p in ports.split()):
                    raise RouterError("An existing LAN DNS redirect needs administrator review before BetGuard can configure this router.")
        return dict(version=release.get("version", "Unknown"), router=router_ip, identity=self.identity(), subnets=subnets,
                    dns_section=dns[0][0], lan_section=lan[0][0], dhcp=dhcp, firewall=firewall)

    def plan(self, inspected, filter_host, port, name):
        if not any(ipaddress.ip_address(filter_host) in ipaddress.ip_network(n) for n in inspected["subnets"]):
            raise RouterError("The DNS filter must have a stable IPv4 address on the router's LAN.")
        if filter_host == inspected["router"] or name in inspected["firewall"]:
            raise RouterError("The filter host or reserved firewall section conflicts with this router.")
        dns = inspected["dhcp"][inspected["dns_section"]]
        lan = inspected["dhcp"][inspected["lan_section"]]
        options = lan.get("dhcp_option", [])
        if isinstance(options, str):
            options = [options]
        after = dict(server=[f"{filter_host}#{port}"], noresolv="1", cachesize="0", addsubnet="32,128", stripsubnet="1")
        dhcp_options = [v for v in options if not v.startswith("6,") and not v.startswith("option:dns-server,")] + [f"6,{inspected['router']}"]
        redirect = dict(name=f"BetGuard DNS {name}", src="lan", src_dport="53", dest_port="53", proto=["tcp", "udp"], target="DNAT", family="any", enabled="1")
        changes = [dict(config="dhcp", section=inspected["dns_section"], option=key, before=copy.deepcopy(dns.get(key)), after=value) for key, value in after.items()]
        changes.append(dict(config="dhcp", section=inspected["lan_section"], option="dhcp_option", before=copy.deepcopy(lan.get("dhcp_option")), after=dhcp_options))
        return dict(router=inspected["router"], identity=inspected["identity"], version=inspected["version"], subnets=inspected["subnets"],
                    url=self.url, filterHost=filter_host, filterPort=port, name=name, changes=changes, redirect=redirect)

    def set_option(self, change, value):
        args = {key: change[key] for key in ("config", "section")}
        if value is None:
            # Don't delete an already absent option: UCI returns NOT_FOUND.
            if change["option"] in self.values(change["config"]).get(change["section"], {}):
                self.rpc("uci", "delete", {**args, "option": change["option"]})
        else:
            self.rpc("uci", "set", {**args, "values": {change["option"]: value}})

    def current(self, plan):
        if self.identity() != plan["identity"]:
            raise RouterError("The router hardware identity differs from the saved session. No restoration or configuration was attempted.")
        return {"dhcp": self.values("dhcp"), "firewall": self.values("firewall")}

    def assert_options(self, plan, which):
        configs = self.current(plan)
        for change in plan["changes"]:
            section = configs[change["config"]].get(change["section"])
            if section is None or section.get(change["option"]) != change[which]:
                raise RouterError("Router settings changed since the preview. Review the configuration instead of overwriting it.")
        return configs

    def apply(self, plan):
        self.clean()
        configs = self.assert_options(plan, "before")
        if plan["name"] in configs["firewall"]:
            raise RouterError("The reserved firewall section already exists.")
        try:
            for change in plan["changes"]:
                self.set_option(change, change["after"])
            self.rpc("uci", "add", dict(config="firewall", type="redirect", name=plan["name"], values=plan["redirect"]))
            # rpcd snapshots the changed configurations and rolls back if not confirmed.
            self.rpc("uci", "apply", dict(rollback=True, timeout=60))
            self.reload()
        except RouterError:
            # Discard only this dedicated RPC session's staged deltas. The
            # persistent journal and rpcd rollback remain available after commit.
            for config in ("dhcp", "firewall"):
                try:
                    self.rpc("uci", "revert", dict(config=config))
                except RouterError:
                    pass
            raise

    def reload(self):
        self.execute("/etc/init.d/dnsmasq", ["restart"])
        self.execute("/etc/init.d/firewall", ["reload"])

    def verify(self, plan):
        configs = self.assert_options(plan, "after")
        rule = configs["firewall"].get(plan["name"], {})
        if any(rule.get(k) != v for k, v in plan["redirect"].items()):
            raise RouterError("The DNS redirect configuration is not applied.")
        text = self.execute("/usr/sbin/nft", ["-j", "list", "chain", "inet", "fw4", "dstnat_lan"])
        try:
            rules = [r.get("rule", {}) for r in json.loads(text)["nftables"]]
            match = [r for r in rules if plan["redirect"]["name"] in r.get("comment", "")]
            if not match or not any(e.get("redirect", {}).get("port") == 53 for r in match for e in r.get("expr", [])):
                raise ValueError()
        except (ValueError, KeyError, TypeError):
            raise RouterError("The live firewall did not show BetGuard's DNS redirect.") from None

    def probe(self, domain):
        if domain not in ("wikipedia.org", "stake.com"):
            raise RouterError("Unsupported diagnostic query.")
        # The response text is not trusted as verification: the DNS service
        # must observe this query from the router during the test window.
        try:
            self.execute("/bin/busybox", ["nslookup", domain, "127.0.0.1"])
        except RouterError:
            if domain != "stake.com":
                raise

    def confirm(self):
        self.rpc("uci", "confirm")

    def restore(self, plan):
        self.clean()
        configs = self.current(plan)
        rule = configs["firewall"].get(plan["name"])
        if rule and any(rule.get(k) != v for k, v in plan["redirect"].items()):
            raise RouterError("The BetGuard firewall entry was edited. Resolve the conflict before restoration.")
        needs_change = bool(rule)
        for change in plan["changes"]:
            section = configs[change["config"]].get(change["section"])
            if section is None or section.get(change["option"]) not in (change["before"], change["after"]):
                raise RouterError("A changed DNS option conflicts with the saved backup. Restoration needs administrator review.")
            needs_change = needs_change or section.get(change["option"]) != change["before"]
        if needs_change:
            for change in plan["changes"]:
                self.set_option(change, change["before"])
            if rule:
                self.rpc("uci", "delete", dict(config="firewall", section=plan["name"]))
            self.rpc("uci", "apply", dict(rollback=True, timeout=60))
        self.reload()
        final = self.assert_options(plan, "before")
        if plan["name"] in final["firewall"]:
            raise RouterError("The BetGuard firewall rule was not removed.")
        live = self.execute("/usr/sbin/nft", ["-j", "list", "chain", "inet", "fw4", "dstnat_lan"])
        if plan["redirect"]["name"] in live:
            raise RouterError("The live BetGuard firewall rule remains after restoration.")
        if needs_change:
            self.confirm()

    def close(self):
        if self.sid != "0" * 32:
            try:
                self.rpc("session", "destroy")
            except RouterError:
                pass
        self.sid = "0" * 32
