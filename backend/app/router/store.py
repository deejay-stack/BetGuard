"""Durable restoration journal and bounded router activity; never stores credentials.

Rules are a synchronized replica of Android Room, not independently editable policy.
"""
import json
import sqlite3
import threading
import time


class RouterStore:
    def __init__(self, path):
        path.parent.mkdir(parents=True, exist_ok=True)
        self.lock = threading.RLock()
        self.db = sqlite3.connect(path, check_same_thread=False)
        self.db.row_factory = sqlite3.Row
        with self.db:
            self.db.execute("CREATE TABLE IF NOT EXISTS state (key TEXT PRIMARY KEY, value TEXT NOT NULL)")
            self.db.execute("CREATE TABLE IF NOT EXISTS activity (id INTEGER PRIMARY KEY AUTOINCREMENT, kind TEXT, domain TEXT, clientIp TEXT, decisionSource TEXT, detail TEXT, createdAt INTEGER)")
            self.db.execute("CREATE TABLE IF NOT EXISTS clients (ip TEXT PRIMARY KEY, firstSeen INTEGER, lastActivity INTEGER, requests INTEGER, blocked INTEGER, warnings INTEGER)")

    def get(self, key, default=None):
        with self.lock:
            row = self.db.execute("SELECT value FROM state WHERE key=?", (key,)).fetchone()
            return json.loads(row[0]) if row else default

    def put(self, key, value):
        with self.lock, self.db:
            self.db.execute("INSERT OR REPLACE INTO state VALUES (?,?)", (key, json.dumps(value)))

    def event(self, domain, client, decision, *, error=False, track=True):
        blocked = decision.get("enforcement_action") == "BLOCK" and not error
        warned = decision.get("intervention") == "WARN" and not error
        kind = "router_error" if error else "router_blocked" if blocked else "router_warning" if warned else "router_allowed"
        source = decision.get("decision_source", "unavailable")
        now = int(time.time() * 1000)
        with self.lock, self.db:
            self.db.execute("INSERT INTO activity(kind,domain,clientIp,decisionSource,detail,createdAt) VALUES (?,?,?,?,?,?)",
                            (kind, domain, client, source, "DNS request failed." if error else "DNS decision: " + source, now))
            self.db.execute("DELETE FROM activity WHERE id NOT IN (SELECT id FROM activity ORDER BY id DESC LIMIT 200)")
            if track:
                self.db.execute("INSERT INTO clients VALUES (?,?,?,1,?,?) ON CONFLICT(ip) DO UPDATE SET lastActivity=excluded.lastActivity, requests=requests+1, blocked=blocked+excluded.blocked, warnings=warnings+excluded.warnings",
                                (client, now, now, int(blocked), int(warned)))
                self.db.execute("DELETE FROM clients WHERE ip NOT IN (SELECT ip FROM clients ORDER BY lastActivity DESC LIMIT 128)")
            totals = self.get("totals", dict(requests=0, allowed=0, blocked=0, warnings=0, errors=0))
            totals["requests"] += 1
            totals["errors" if error else "blocked" if blocked else "allowed"] += 1
            totals["warnings"] += int(warned)
            self.put("totals", totals)

    def history(self):
        with self.lock:
            return [{**dict(row), "protection": "router"} for row in self.db.execute("SELECT * FROM activity ORDER BY id DESC LIMIT 200")]

    def reset_session(self):
        with self.lock, self.db:
            self.db.execute("DELETE FROM clients")
            self.put("totals", dict(requests=0, allowed=0, blocked=0, warnings=0, errors=0))

    def clients(self):
        with self.lock:
            return [dict(row) for row in self.db.execute("SELECT * FROM clients WHERE lastActivity>? ORDER BY lastActivity DESC", (int(time.time()*1000)-120000,))]

    def close(self):
        with self.lock:
            self.db.close()
