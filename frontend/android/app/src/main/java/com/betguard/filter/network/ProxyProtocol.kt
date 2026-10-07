package com.betguard.filter.network

import com.betguard.filter.core.DomainPolicy
import java.io.InputStream
import java.net.InetAddress
import java.net.URI

class ProxyRequestError(val status: Int = 400) : Exception()
data class ProxyRequest(val hostname: String, val port: Int, val connect: Boolean,
    val forwardedHeaders: ByteArray, val bodyLength: Long)

/** One HTTP request per connection. HTTPS remains an opaque CONNECT tunnel. */
object ProxyProtocol {
    const val MAX_HEADERS = 16384
    const val MAX_BODY = 32L * 1024 * 1024

    fun read(input: InputStream): ProxyRequest {
        val bytes = ArrayList<Byte>()
        while (bytes.size < MAX_HEADERS) {
            val next = input.read()
            if (next < 0) throw ProxyRequestError()
            bytes.add(next.toByte())
            if (bytes.size >= 4 && bytes.takeLast(4) == listOf(13.toByte(),10.toByte(),13.toByte(),10.toByte())) break
        }
        if (bytes.size >= MAX_HEADERS) throw ProxyRequestError(431)
        return parse(bytes.toByteArray().toString(Charsets.ISO_8859_1))
    }

    fun parse(raw: String): ProxyRequest {
        try {
            if (raw.length >= MAX_HEADERS || !raw.endsWith("\r\n\r\n")) throw ProxyRequestError(431)
            val lines = raw.dropLast(4).split("\r\n")
            val first = lines.first().split(' ')
            if (first.size != 3 || first[2] !in listOf("HTTP/1.0","HTTP/1.1")) throw ProxyRequestError()
            val method = first[0]
            val target = first[1]
            val fields = lines.drop(1).map { line ->
                val split = line.indexOf(':')
                if (split < 1 || !line.substring(0,split).matches(Regex("[!#$%&'*+.^_`|~0-9A-Za-z-]+")) ||
                    line.any { it.code < 32 && it != '\t' || it.code == 127 }) throw ProxyRequestError()
                line.substring(0,split).lowercase() to line.substring(split+1).trim()
            }
            val hostFields = fields.filter { it.first == "host" }
            if (hostFields.size != 1 || fields.any { it.first == "transfer-encoding" || it.first == "upgrade" })
                throw ProxyRequestError(400)
            val lengths = fields.filter { it.first == "content-length" }
            if (lengths.size > 1) throw ProxyRequestError()
            val length = if (lengths.isEmpty()) 0L else lengths[0].second.let {
                if (!it.matches(Regex("[0-9]+"))) throw ProxyRequestError()
                it.toLongOrNull() ?: throw ProxyRequestError(413)
            }
            if (length > MAX_BODY) throw ProxyRequestError(413)
            if (fields.any { it.first == "expect" }) throw ProxyRequestError(417)
            val connect = method == "CONNECT"
            val authority: String
            val path: String
            if (connect) {
                if (!target.matches(Regex("[^/:?#]+:443")) || length != 0L) throw ProxyRequestError()
                authority = target
                path = ""
            } else {
                if (method !in listOf("GET","HEAD","POST","PUT","PATCH","DELETE","OPTIONS")) throw ProxyRequestError(405)
                val uri = URI(target)
                if (uri.scheme != "http" || uri.rawUserInfo != null || uri.rawFragment != null || uri.rawAuthority == null)
                    throw ProxyRequestError()
                if (uri.port !in listOf(-1,80)) throw ProxyRequestError(403)
                authority = uri.rawAuthority
                path = (uri.rawPath.takeUnless { it.isNullOrEmpty() } ?: "/") + (uri.rawQuery?.let { "?$it" } ?: "")
                if (path.any { it.code <= 32 || it.code == 127 }) throw ProxyRequestError()
            }
            val host = DomainPolicy.normalize(authority)
            val hostHeader = DomainPolicy.normalize(hostFields[0].second)
            val port = if (connect) 443 else 80
            val headerUri = URI("http://${hostFields[0].second}")
            if (host != hostHeader || headerUri.port !in listOf(-1,port)) throw ProxyRequestError()
            val connectionNames = fields.filter { it.first == "connection" }.flatMap { it.second.lowercase().split(',').map(String::trim) }.toSet()
            if (connectionNames.any { it in listOf("host","content-length") }) throw ProxyRequestError()
            val removed = connectionNames + setOf("connection","proxy-connection","proxy-authorization","proxy-authenticate","keep-alive","te","trailer")
            val header = if (connect) "" else buildString {
                append("$method $path HTTP/1.1\r\n")
                fields.filter { it.first !in removed }.forEach { append("${it.first}: ${it.second}\r\n") }
                append("Connection: close\r\n\r\n")
            }
            return ProxyRequest(host,port,connect,header.toByteArray(Charsets.ISO_8859_1),length)
        } catch (error: ProxyRequestError) { throw error }
        catch (_: Exception) { throw ProxyRequestError() }
    }

    /** Never turn this domain proxy into a route to localhost, LAN services or IP literals. */
    fun publicDestination(address: InetAddress): Boolean {
        if (address.isAnyLocalAddress || address.isLoopbackAddress || address.isLinkLocalAddress ||
            address.isSiteLocalAddress || address.isMulticastAddress) return false
        val bytes = address.address.map { it.toInt() and 255 }
        if (bytes.size == 4) return bytes[0] !in listOf(0,127) && bytes[0] < 224 &&
            !(bytes[0] == 100 && bytes[1] in 64..127) && !(bytes[0] == 169 && bytes[1] == 254) &&
            !(bytes[0] == 198 && bytes[1] in 18..19)
        // Native global IPv6 unicast only; mapped/transition addresses are not a LAN escape route.
        return bytes.size == 16 && bytes[0] in 0x20..0x3f &&
            !(bytes[0] == 0x20 && bytes[1] == 0x02) &&
            !(bytes.take(4) == listOf(0x20,0x01,0,0))
    }

    fun sameSubnet(address: String, local: String, prefix: Int): Boolean {
        fun ipv4(value: String): Long? {
            val parts=value.split('.').map { it.toIntOrNull() ?: return null }
            if (parts.size!=4 || parts.any { it !in 0..255 }) return null
            return parts.fold(0L) { total, part -> (total shl 8) or part.toLong() }
        }
        if (prefix !in 8..30) return false
        val remote=ipv4(address) ?: return false
        val host=ipv4(local) ?: return false
        val mask=(0xffffffffL shl (32-prefix)) and 0xffffffffL
        return (remote and mask) == (host and mask)
    }
}
