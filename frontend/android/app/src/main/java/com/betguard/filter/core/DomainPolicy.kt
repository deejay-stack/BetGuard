package com.betguard.filter.core

import java.net.IDN
import java.net.URI
import java.util.Locale

data class DomainRule(val domain: String, val action: String, val includeSubdomains: Boolean)

object DomainPolicy {
    fun normalize(input: String): String {
        val value = input.trim()
        require(value.isNotEmpty() && value.length <= 2048) { "Enter a website link or hostname." }
        require(!value.contains('\\') && value.none { it.isWhitespace() }) { "Remove spaces and backslashes from the link." }
        val uri = try { URI(if (value.contains("://")) value else "https://$value") }
        catch (_: Exception) { throw IllegalArgumentException("Enter a valid website link.") }
        require(uri.scheme?.lowercase(Locale.ROOT) in listOf("http", "https")) { "Only HTTP and HTTPS links are supported." }
        val authority = uri.rawAuthority ?: throw IllegalArgumentException("A hostname is required.")
        require(!authority.contains('@') && !authority.contains('%')) { "Links with credentials or encoded hostnames are not supported." }
        val pieces = authority.split(':')
        require(pieces.size <= 2) { "Use a website hostname, not an IP address." }
        if (pieces.size == 2) require(pieces[1].all { it in '0'..'9' } && pieces[1].toIntOrNull() in 1..65535) { "Use a numeric port from 1 to 65535." }
        val domain = try { IDN.toASCII(pieces[0].removeSuffix("."), IDN.USE_STD3_ASCII_RULES).lowercase(Locale.ROOT) }
        catch (_: Exception) { throw IllegalArgumentException("Enter a valid hostname.") }
        val labels = domain.split('.')
        require(domain.length <= 253 && labels.size >= 2 && labels.all {
            it.length in 1..63 && it.matches(Regex("[a-z0-9](?:[a-z0-9-]*[a-z0-9])?"))
        }) { "Enter a complete hostname, such as example.com." }
        require(!labels.last().all { it.isDigit() }) { "IP addresses are not supported by domain rules." }
        return domain
    }

    fun match(hostname: String, rules: List<DomainRule>): DomainRule? {
        val host = hostname.lowercase(Locale.ROOT).removeSuffix(".")
        return rules.filter {
            host == it.domain || (it.includeSubdomains && host.endsWith(".${it.domain}"))
        }.maxByOrNull { it.domain.length }
    }

    fun explain(host: String, rule: DomainRule?): String =
        if (rule == null) "No matching manual rule. Default: allow. Classification remains unknown."
        else if (rule.domain == host) "Exact hostname rule: ${rule.action} ${rule.domain}."
        else "Parent rule: ${rule.action} ${rule.domain}, including subdomains. The most-specific matching hostname wins."
}
