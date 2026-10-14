from app.schemas.catalog import normalize_hostname
from app.services.domain_service import evaluate


class SharedPolicy:
    def __init__(self, runtime, store):
        self.runtime, self.store = runtime, store

    def sync(self, rules):
        # Only the complete canonical Room snapshot can replace the replica.
        if len({r["domain"] for r in rules}) != len(rules):
            raise ValueError("Duplicate rules")
        self.store.put("rules", rules)

    def evaluate(self, value):
        domain = normalize_hostname(value)
        matches = [rule for rule in self.store.get("rules", []) if domain == rule["domain"] or
                   (rule["includeSubdomains"] and domain.endswith("." + rule["domain"]))]
        if matches:
            rule = max(matches, key=lambda r: len(r["domain"]))
            block = rule["action"] == "block"
            return dict(domain=domain, enforcement_action="BLOCK" if block else "ALLOW",
                        intervention="BLOCK" if block else "NONE",
                        decision_source="user_blocklist" if block else "user_allowlist", matched_domain=rule["domain"])
        if self.runtime is None:
            raise RuntimeError("Detection unavailable")
        return evaluate(self.runtime, [domain])[0].model_dump()
