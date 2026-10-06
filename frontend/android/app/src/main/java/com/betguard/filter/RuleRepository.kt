package com.betguard.filter

import android.content.Context
import com.betguard.BuildConfig
import com.betguard.filter.core.DomainPolicy
import com.betguard.filter.core.DomainRule
import com.betguard.filter.core.ServiceStatus
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
    @Volatile var detectionBaseUrl = ""; private set

    @Synchronized fun configureDetection(baseUrl: String) {
        require(state in listOf("off", "failed", "interrupted")) { "Stop protection before changing detection mode." }
        val value = baseUrl.trim().trimEnd('/')
        require(value.isEmpty() || value.matches(Regex("https://[^/?#@\\s]+(?:/[^?#]*)?")) ||
            (BuildConfig.DEBUG && value.matches(Regex("http://(?:127\\.0\\.0\\.1|localhost|10\\.0\\.2\\.2)(?::\\d+)?")))) {
            "Configure the BetGuard API address before enabling online detection."
        }
        // An empty endpoint deliberately selects the existing offline manual mode.
        detectionBaseUrl = value
    }

    @Synchronized fun match(hostname: String): DomainRule? = DomainPolicy.match(
        hostname, dao.rules().map { DomainRule(it.domain, it.action, it.includeSubdomains) }
    )

    @Synchronized fun save(input: String, action: String, includeSubdomains: Boolean): String {
        require(action in listOf("block", "allow")) { "Choose block or allow." }
        val host = DomainPolicy.normalize(input)
        db.runInTransaction {
            val previous = dao.rules().find { it.domain == host }
            val changedRule = previous != null && (previous.action != action || previous.includeSubdomains != includeSubdomains)
            dao.save(RuleEntity(host, action, includeSubdomains, System.currentTimeMillis()))
            insert(if (changedRule) "rule_changed" else "rule_saved", host, "$action rule ${if (changedRule) "updated" else "saved"}; ${if (includeSubdomains) "includes subdomains" else "exact hostname"}. This is a setting change, not a blocked request.")
        }
        changed()
        return host
    }

    @Synchronized fun remove(input: String) {
        val host = DomainPolicy.normalize(input)
        db.runInTransaction {
            dao.remove(host)
            insert("rule_removed", host, "Override removed. ${DomainPolicy.explain(host, match(host))}")
        }
        changed()
    }

    @Synchronized fun check(input: String, recordHistory: Boolean = true): String {
        val host = DomainPolicy.normalize(input)
        val rule = match(host)
        val reason = DomainPolicy.explain(host, rule)
        if (recordHistory) {
            insert("link_check", host, "Classification not available yet. $reason")
            changed()
        }
        return JSONObject().put("domain", host).put("classification", "unknown")
            .put("action", rule?.action ?: "allow").put("matchedDomain", rule?.domain ?: JSONObject.NULL)
            .put("reason", reason)
            .put("checkedAt", System.currentTimeMillis()).toString()
    }

    @Synchronized fun setState(next: String, message: String) {
        state = next
        detail = message
        io.execute { record("service", "", message) }
    }

    @Synchronized fun updateNetworkState(next: String, message: String) {
        if (ServiceStatus.acceptsNetworkUpdate(state) && state != next) setState(next, message)
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
        return JSONObject().put("state", state).put("detail", detail)
            .put("detectionEnabled", detectionBaseUrl.isNotEmpty())
            .put("rules", rules).put("history", history).toString()
    }

    private fun changed() { listeners.forEach { it() } }

    companion object {
        @Volatile private var instance: RuleRepository? = null
        fun get(context: Context): RuleRepository = instance ?: synchronized(this) {
            instance ?: RuleRepository(context).also { instance = it }
        }
    }
}
