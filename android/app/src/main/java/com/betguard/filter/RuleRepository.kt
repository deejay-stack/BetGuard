package com.betguard.filter

import android.content.Context
import com.betguard.filter.core.DomainPolicy
import com.betguard.filter.core.DomainRule
import org.json.JSONArray
import org.json.JSONObject
import java.util.concurrent.CopyOnWriteArraySet
import java.util.concurrent.Executors

class RuleRepository private constructor(context: Context) {
    private val db = BetGuardDatabase.create(context)
    private val dao = db.dao()
    val listeners = CopyOnWriteArraySet<() -> Unit>()
    val io = Executors.newSingleThreadExecutor()
    @Volatile var state = "off"; private set
    @Volatile var detail = "Protection is off. Your saved rules stay on this phone."; private set

    @Synchronized fun match(hostname: String): DomainRule? = DomainPolicy.match(
        hostname, dao.rules().map { DomainRule(it.domain, it.action, it.includeSubdomains) }
    )

    @Synchronized fun save(input: String, action: String, includeSubdomains: Boolean): String {
        require(action in listOf("block", "allow")) { "Choose block or allow." }
        val host = DomainPolicy.normalize(input)
        db.runInTransaction {
            dao.save(RuleEntity(host, action, includeSubdomains, System.currentTimeMillis()))
            insert("rule_saved", host, "$action rule saved; ${if (includeSubdomains) "includes subdomains" else "exact hostname"}. Evaluated on new covered DNS requests.")
        }
        changed()
        return host
    }

    @Synchronized fun remove(input: String) {
        val host = DomainPolicy.normalize(input)
        db.runInTransaction {
            dao.remove(host)
            insert("rule_removed", host, "Override removed. Other matching rules still apply; otherwise access is allowed with classification unknown.")
        }
        changed()
    }

    @Synchronized fun check(input: String): String {
        val host = DomainPolicy.normalize(input)
        val rule = match(host)
        insert("link_check", host, "Classification unknown: model not connected. Effective rule: ${rule?.action ?: "no manual rule"}.")
        changed()
        return JSONObject().put("domain", host).put("classification", "unknown")
            .put("action", rule?.action ?: "allow").put("matchedDomain", rule?.domain ?: JSONObject.NULL)
            .put("reason", "Gambling classification is not connected in this prototype.")
            .put("checkedAt", System.currentTimeMillis()).toString()
    }

    fun setState(next: String, message: String) {
        state = next
        detail = message
        io.execute { record("service", "", message) }
    }

    @Synchronized fun record(kind: String, domain: String, message: String) {
        insert(kind, domain, message)
        changed()
    }

    private fun insert(kind: String, domain: String, message: String) {
        dao.insert(HistoryEntity(kind = kind, domain = domain, detail = message, createdAt = System.currentTimeMillis()))
        dao.prune()
    }

    @Synchronized fun clearHistory() { dao.clearHistory(); changed() }

    @Synchronized fun snapshot(): String {
        val rules = JSONArray()
        dao.rules().forEach { rule -> rules.put(JSONObject().put("domain", rule.domain)
            .put("action", rule.action).put("includeSubdomains", rule.includeSubdomains).put("updatedAt", rule.updatedAt)) }
        val history = JSONArray()
        dao.history().forEach { event -> history.put(JSONObject().put("id", event.id).put("kind", event.kind)
            .put("domain", event.domain).put("detail", event.detail).put("createdAt", event.createdAt)) }
        return JSONObject().put("state", state).put("detail", detail).put("rules", rules).put("history", history).toString()
    }

    private fun changed() { listeners.forEach { it() } }

    companion object {
        @Volatile private var instance: RuleRepository? = null
        fun get(context: Context): RuleRepository = instance ?: synchronized(this) {
            instance ?: RuleRepository(context).also { instance = it }
        }
    }
}
