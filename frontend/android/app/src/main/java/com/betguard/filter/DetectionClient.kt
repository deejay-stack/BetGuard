package com.betguard.filter

import com.betguard.filter.core.DomainPolicy
import android.net.Network
import org.json.JSONObject
import java.net.HttpURLConnection
import java.net.URL
import java.util.concurrent.ConcurrentHashMap

class DetectionUnavailable : RuntimeException()

data class DetectionResult(val enforcementAction: String, val intervention: String, val source: String)

/** Native adapter for the same FastAPI API; the VPN must also work without JS/Metro. */
class DetectionClient {
    private val connections = ConcurrentHashMap.newKeySet<HttpURLConnection>()
    @Volatile private var closed = false

    fun check(baseUrl: String, hostname: String, network: Network): DetectionResult {
        if (closed) throw DetectionUnavailable()
        val host = DomainPolicy.normalize(hostname)
        // Resolve/connect on a non-VPN network. Using the VPN's resolver for
        // the API hostname would recursively classify the API's own DNS lookup.
        val connection = network.openConnection(URL("$baseUrl/v1/domain/check")) as HttpURLConnection
        connections.add(connection)
        try {
            if (closed) throw DetectionUnavailable()
            connection.requestMethod = "POST"
            connection.connectTimeout = 1500
            connection.readTimeout = 1500
            connection.instanceFollowRedirects = false
            connection.doOutput = true
            connection.setRequestProperty("Content-Type", "application/json")
            connection.setRequestProperty("Accept", "application/json")
            val body = JSONObject().put("domain", host).toString().toByteArray(Charsets.UTF_8)
            connection.setFixedLengthStreamingMode(body.size)
            connection.outputStream.use { it.write(body) }
            if (connection.responseCode != 200) throw DetectionUnavailable()
            val buffer = ByteArray(16385)
            var size = 0
            connection.inputStream.use { stream ->
                while (size < buffer.size) {
                    val count = stream.read(buffer, size, buffer.size - size)
                    if (count < 0) break
                    size += count
                }
            }
            if (size > 16384) throw DetectionUnavailable()
            val response = JSONObject(String(buffer, 0, size, Charsets.UTF_8))
            if (response.getBoolean("ok") != true) throw DetectionUnavailable()
            val result = response.getJSONObject("result")
            if (result.getString("domain") != host.removePrefix("www.")) throw DetectionUnavailable()
            val action = result.getString("enforcement_action")
            val intervention = result.getString("intervention")
            val source = result.getString("decision_source")
            val policy = when (source) {
                "verified_gambling_blocklist" -> Triple("BLOCK", "BLOCK", "verified_gambling")
                "ml_high_risk" -> Triple("BLOCK", "BLOCK", "high")
                "ml_warning" -> Triple("ALLOW", "WARN", "suspicious")
                "ml_low_risk" -> Triple("ALLOW", "NONE", "low")
                // User-specific overrides are exclusively in Room on this device.
                else -> throw DetectionUnavailable()
            }
            if (action != policy.first || intervention != policy.second || result.getString("risk_status") != policy.third)
                throw DetectionUnavailable()
            if (source.startsWith("ml_")) {
                val score = result.getDouble("ml_score")
                if (!score.isFinite() || score !in 0.0..1.0) throw DetectionUnavailable()
            }
            return DetectionResult(action, intervention, source)
        } catch (_: Exception) {
            throw DetectionUnavailable()
        } finally { connection.disconnect(); connections.remove(connection) }
    }

    fun close() {
        closed = true
        connections.forEach { it.disconnect() }
    }
}
