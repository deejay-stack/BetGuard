import asyncio
import secrets
import threading
import time

from .base import RouterError, RouterOffline
from .dns import DnsFilter
from .openwrt import OpenWrtAdapter
from .policy import SharedPolicy
from .store import RouterStore


class RouterProtection:
    def __init__(self, settings, runtime, adapter_factory=OpenWrtAdapter):
        self.settings, self.runtime = settings, runtime
        self.store = RouterStore(settings.state_path)
        self.policy = SharedPolicy(runtime, self.store)
        self.dns = DnsFilter(settings, self.policy, self.store, lambda: self.store.get("session", {"state": "off"}))
        self.adapter_factory, self.adapter = adapter_factory, None
        self.lock = threading.RLock()
        self.monitor = None
        prior = self.store.get("session", {})
        if prior.get("state", "off") not in ("off", "preview"):
            self.store.put("session", {**prior, "state": "recovery_required", "detail": "An unfinished router session was found. Authenticate to the same router, verify it, then restore or resume monitoring."})
        elif prior.get("state") == "preview":
            self.store.put("session", {"state": "off", "detail": "Previous preview expired. Connect again; no router changes were applied."})

    async def start(self):
        await self.dns.start()
        self.monitor = asyncio.create_task(self.watch())

    async def watch(self):
        while True:
            await asyncio.sleep(30)
            try:
                await asyncio.to_thread(self.verify)
            except RouterError:
                pass

    def ready(self):
        return bool(self.runtime and self.runtime.get_status().get("gambling_blocklist_domains", 0) and self.dns.running)

    def status(self):
        session = self.store.get("session", {"state": "off", "detail": "Connect an authorized OpenWrt router to review its configuration."})
        plan = session.get("plan", {})
        state = session["state"]
        if state == "active" and (not self.ready() or time.time() - session.get("verifiedAt", 0) > 65):
            state = "degraded"
        totals = self.store.get("totals", dict(requests=0, allowed=0, blocked=0, warnings=0, errors=0))
        detail = "Router health verification is stale or the filtering service is unavailable." if state != session["state"] else session.get("detail", "")
        return dict(state=state, detail=detail, router=plan.get("router"),
                    routerUrl=plan.get("url"), routerType="OpenWrt" if plan else None, version=plan.get("version"),
                    filterHost=self.settings.bind, filterPort=self.settings.port, dnsRunning=self.dns.running,
                    mlReady=self.ready(), blocklistLoaded=bool(self.runtime and self.runtime.get_status().get("gambling_blocklist_domains", 0)),
                    enforcementVerified=state == "active", verifiedAt=session.get("verifiedAt"),
                    preview=session.get("preview") if state == "preview" else None,
                    changes=plan.get("changes", []) if state == "preview" else [],
                    firewallRule=plan.get("redirect") if state == "preview" else None,
                    clients=self.store.clients() if state not in ("off", "preview") else [],
                    history=self.store.history(), **totals)

    def connect(self, url, username, password, authorized):
        if not authorized:
            raise RouterError("Confirm that you own or administer this network.")
        with self.lock:
            prior = self.store.get("session", {"state": "off"})
            adapter = self.adapter_factory(url, self.settings.peers, self.settings.ca_file)
            try:
                adapter.login(username, password)
                if prior["state"] not in ("off", "preview"):
                    if adapter.url != prior["plan"]["url"]:
                        raise RouterError("Restore the unfinished session on its original router before connecting another router.")
                    board = adapter.rpc("system", "board")
                    if board.get("release", {}).get("distribution") != "OpenWrt":
                        raise RouterError("The recovery router did not identify itself as OpenWrt.")
                    if adapter.identity() != prior["plan"]["identity"]:
                        raise RouterError("The router hardware identity differs from the unfinished session. Connect to its original router.")
                    self.store.put("session", {**prior, "state": "recovery_required", "detail": "Router authenticated. Verify the saved session or restore its previous settings."})
                else:
                    if not self.ready():
                        raise RouterError("The BetGuard DNS listener and existing ML runtime must be ready before setup.")
                    inspected = adapter.inspect()
                    plan = adapter.plan(inspected, self.settings.bind, self.settings.port, "bg_dns_" + secrets.token_hex(6))
                    self.store.put("session", dict(state="preview", detail="Review the DNS/DHCP/firewall changes before applying.",
                                                   plan=plan, preview=secrets.token_urlsafe(24), expires=time.time()+300))
            except Exception:
                adapter.close()
                raise
            if self.adapter:
                self.adapter.close()
            self.adapter = adapter
            return self.status()

    def probe(self, plan):
        for domain, action, code in (("wikipedia.org", "ALLOW", 0), ("stake.com", "BLOCK", 3)):
            began = time.monotonic()
            self.adapter.probe(domain)
            observed = self.dns.probes.get((plan["router"], domain))
            if not observed or observed[0] < began or observed[1:] != (action, code):
                raise RouterError("The router's real DNS test did not reach BetGuard with the expected result. Protection is not verified.")

    def apply(self, preview, authorized):
        with self.lock:
            session = self.store.get("session", {})
            if (not authorized or session.get("state") != "preview" or not self.adapter or
                    not secrets.compare_digest(preview, session.get("preview", "")) or time.time() > session.get("expires", 0)):
                raise RouterError("This configuration preview is missing or expired. Connect again and explicitly approve a fresh preview.")
            if not self.ready() or self.store.get("rules") is None:
                raise RouterError("The DNS service, ML runtime and phone's shared rules must be ready.")
            plan = session["plan"]
            # Durable backup precedes the first remote write. A crash here is
            # recoverable even if the caller never receives the response.
            self.store.put("session", dict(state="applying", plan=plan, rollbackDeadline=time.time()+60, detail="Applying and verifying DNS protection…"))
            self.store.reset_session()
            try:
                self.adapter.apply(plan)
                self.adapter.verify(plan)
                self.probe(plan)
                self.adapter.confirm()
                self.store.put("session", dict(state="active", plan=plan, detail="Verified router DNS protection is active.", verifiedAt=time.time()))
            except Exception:
                try:
                    # Best effort cancels rpcd's pending automatic rollback
                    # before idempotent restoration, using the same RPC session.
                    try:
                        self.adapter.rpc("uci", "rollback")
                        for config in ("dhcp", "firewall"):
                            self.adapter.rpc("uci", "revert", dict(config=config))
                    except RouterError:
                        pass
                    self.adapter.restore(plan)
                    self.store.put("session", dict(state="off", detail="Setup verification failed. Previous router settings were restored."))
                except Exception:
                    self.store.put("session", dict(state="recovery_required", plan=plan, detail="Setup failed and restoration is unverified. Reconnect to this router and restore the saved settings; do not assume it is off."))
                raise RouterError(self.store.get("session")["detail"]) from None
            return self.status()

    def verify(self):
        with self.lock:
            session = self.store.get("session", {"state": "off"})
            if session["state"] in ("off", "preview", "applying", "restoring"):
                return self.status()
            if not self.adapter:
                raise RouterError("Reconnect securely to the original router before verification or restoration.")
            if time.time() < session.get("rollbackDeadline", 0):
                raise RouterError("An interrupted apply may still be rolling back. Wait for its 60-second rollback window before verifying recovery.")
            try:
                if not self.ready():
                    raise RouterError("The DNS listener or existing ML runtime is unavailable.")
                self.adapter.verify(session["plan"])
                self.probe(session["plan"])
                self.store.put("session", {**session, "state": "active", "detail": "Verified router DNS protection is active.", "verifiedAt": time.time()})
            except RouterError as error:
                self.store.put("session", {**session, "state": "offline" if isinstance(error, RouterOffline) else "degraded", "detail": str(error), "verifiedAt": None})
                raise
            return self.status()

    def stop(self):
        with self.lock:
            session = self.store.get("session", {"state": "off"})
            if session["state"] in ("off", "preview"):
                self.store.put("session", {"state": "off", "detail": "Router Protection is off; no active configuration remains."})
                return self.status()
            if not self.adapter:
                raise RouterError("Authenticate to the original router to restore its saved settings.")
            self.store.put("session", {**session, "state": "restoring", "detail": "Restoring the saved DNS/DHCP settings and removing BetGuard's firewall rule…"})
            try:
                self.adapter.restore(session["plan"])
            except Exception:
                self.store.put("session", {**session, "state": "recovery_required", "detail": "Restoration is unverified. Keep the DNS filter available, reconnect to the original router and restore its saved settings."})
                raise RouterError(self.store.get("session")["detail"]) from None
            self.store.put("session", {"state": "off", "detail": "Previous router settings were restored and verified."})
            self.adapter.close()
            self.adapter = None
            return self.status()

    async def close(self):
        if self.monitor:
            self.monitor.cancel()
            await asyncio.gather(self.monitor, return_exceptions=True)
        # Shutdown doesn't silently change a router. The journal survives and
        # the next process explicitly exposes recovery_required.
        await self.dns.close()
        # A cancelled asyncio.to_thread call can still be running. Join it
        # through the action lock before closing the durable journal.
        await asyncio.to_thread(self.finish)

    def finish(self):
        with self.lock:
            if self.adapter:
                self.adapter.close()
            self.store.close()
