package com.betguard.filter.core

data class DnsDecision(val bytes: ByteArray, val kind: String, val detail: String)

/** Called while holding the same repository lock as rule edits and tunnel writes. */
object DnsDecisions {
    fun finalResponse(packet: DnsPacket, latestRule: DomainRule?, bytes: ByteArray, kind: String, detail: String): DnsDecision {
        if (latestRule?.action == "block") return DnsDecision(packet.errorResponse(3), "dns_blocked",
            "NXDOMAIN written for manual block ${latestRule.domain}. This records a DNS request, not a website visit.")
        require(kind != "dns_blocked") { "A policy response must not survive removal of its block rule." }
        require(kind != "dns_detection_blocked" || latestRule == null) { "A detection block must not override a local Allow." }
        if (latestRule?.action == "allow" && kind == "dns_warning") return DnsDecision(bytes, "dns_forwarded",
            "Local Allow overrides the detection warning. Upstream DNS response returned.")
        return DnsDecision(bytes, kind, detail)
    }
}
