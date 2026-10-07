package com.betguard.filter.network

data class GatewayClient(val ip: String, val firstSeen: Long, var lastActivity: Long,
    var requests: Long = 0, var blocked: Long = 0, var warnings: Long = 0,
    var connections: Int = 0)

/** Clients become protected only after a valid hostname request reaches the decision path. */
class ClientTracker {
    private val clients=LinkedHashMap<String,GatewayClient>()
    @Synchronized fun request(ip: String, outcome: String, now: Long): Boolean {
        if (ip !in clients && clients.size >= 64) {
            val expired=clients.values.firstOrNull { it.connections==0 && now-it.lastActivity>120000 } ?: return false
            clients.remove(expired.ip)
        }
        val client=clients.getOrPut(ip) { GatewayClient(ip,now,now) }
        client.lastActivity=now; client.requests++
        if (outcome=="block") client.blocked++
        if (outcome=="warn") client.warnings++
        return true
    }
    @Synchronized fun connection(ip: String, delta: Int, now: Long) {
        clients[ip]?.let { it.connections=(it.connections+delta).coerceAtLeast(0); it.lastActivity=now }
    }
    @Synchronized fun snapshot(now: Long): List<GatewayClient> = clients.values
        .filter { it.connections>0 || now-it.lastActivity<120000 }.map { it.copy() }
    @Synchronized fun clear() { clients.clear() }
}
