package com.betguard.filter.network

import com.betguard.BuildConfig
import org.json.JSONArray
import org.json.JSONObject
import java.util.concurrent.CopyOnWriteArraySet

object GatewayState {
    val listeners=CopyOnWriteArraySet<() -> Unit>()
    val clients=ClientTracker()
    @Volatile var state="off"; private set
    @Volatile var detail="Network Protection is off."; private set
    @Volatile var endpoint: LanAddress? = null; private set
    @Volatile var port=0; private set
    @Volatile var baseUrl=""; private set
    @Volatile var runtime="not_checked"; private set
    private var startedAt=0L
    private var requests=0L
    private var allowed=0L
    private var blocked=0L
    private var warnings=0L
    private var errors=0L
    private var rejected=0L

    @Synchronized fun prepare(address: String, requestedPort: Int, api: String) {
        require(state in listOf("off","failed","interrupted")) { "Stop Network Protection before changing its setup." }
        val selected=LanInterfaces.discover().find { it.address==address }
            ?: throw IllegalArgumentException("Turn on your hotspot or connect to Wi-Fi, then refresh the gateway addresses.")
        require(requestedPort in 1024..65535) { "Use a proxy port from 1024 to 65535." }
        val value=api.trim().trimEnd('/')
        require(value.matches(Regex("https://[^/?#@\\s]+(?:/[^?#]*)?")) ||
            (BuildConfig.DEBUG && value.matches(Regex("http://(?:127\\.0\\.0\\.1|localhost|10\\.0\\.2\\.2)(?::\\d+)?")))) {
            "Configure the BetGuard API address before starting Network Protection."
        }
        endpoint=selected; port=requestedPort; baseUrl=value
        startedAt=System.currentTimeMillis(); requests=0; allowed=0; blocked=0; warnings=0; errors=0; rejected=0
        clients.clear(); runtime="not_checked"
        setState("starting","Starting the phone's network gateway…")
    }

    @Synchronized fun setState(next: String, message: String) {
        state=next; detail=message
        if (next in listOf("off","failed","interrupted")) { clients.clear(); endpoint=null; port=0 }
        changed()
    }
    @Synchronized fun backend(ready: Boolean) {
        runtime=if (ready) "ready" else "unavailable"
        changed()
    }
    @Synchronized fun healthy() {
        if (state=="degraded") setState("active","Gateway is listening. Configure each client's manual proxy to use this phone.")
    }
    @Synchronized fun degrade(message: String) {
        if (state in listOf("active","degraded")) setState("degraded",message)
    }
    @Synchronized fun outcome(ip: String, outcome: String): Boolean {
        if (state !in listOf("active","degraded")) return false
        if (!clients.request(ip,outcome,System.currentTimeMillis())) return false
        requests++
        when(outcome) {
            "block" -> blocked++
            "warn" -> { allowed++; warnings++ }
            "allow" -> allowed++
            else -> errors++
        }
        changed(); return true
    }
    @Synchronized fun reject() { rejected++; changed() }
    fun changed() { listeners.forEach { it() } }
    @Synchronized fun snapshot(): String {
        val now=System.currentTimeMillis()
        val clientRows=clients.snapshot(now)
        return JSONObject().put("state",state).put("detail",detail)
            .put("address",endpoint?.address ?: JSONObject.NULL).put("port",port)
            .put("interfaceName",endpoint?.interfaceName ?: JSONObject.NULL)
            .put("interfaces",JSONArray().apply { LanInterfaces.discover().forEach { put(it.json()) } })
            .put("runtime",runtime).put("startedAt",startedAt).put("requests",requests)
            .put("allowed",allowed).put("blocked",blocked).put("warnings",warnings).put("errors",errors).put("rejected",rejected)
            .put("clients",JSONArray().apply { clientRows.forEach { client -> put(JSONObject()
                .put("ip",client.ip).put("firstSeen",client.firstSeen).put("lastActivity",client.lastActivity)
                .put("requests",client.requests).put("blocked",client.blocked).put("warnings",client.warnings)
                .put("connections",client.connections)) } }).toString()
    }
}
