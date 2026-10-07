package com.betguard.filter

import com.betguard.filter.network.ClientTracker
import com.betguard.filter.network.ProxyProtocol
import com.betguard.filter.network.ProxyRequestError
import java.io.ByteArrayInputStream
import java.net.InetAddress
import java.util.concurrent.Executors
import org.junit.Assert.*
import org.junit.Test

class NetworkProxyTest {
    private fun parse(first: String, headers: String="Host: wikipedia.org") =
        ProxyProtocol.parse("$first\r\n$headers\r\n\r\n")
    private fun rejected(first: String, headers: String="Host: wikipedia.org") {
        try { parse(first,headers); fail("Malformed or unsupported request accepted") } catch (_: ProxyRequestError) { }
    }
    @Test fun connectUsesHostnameWithoutReadingEncryptedPayload() {
        val bytes="CONNECT Wikipedia.ORG:443 HTTP/1.1\r\nHost: Wikipedia.ORG:443\r\n\r\nsecret TLS bytes".toByteArray()
        val input=ByteArrayInputStream(bytes)
        val request=ProxyProtocol.read(input)
        assertEquals("wikipedia.org",request.hostname)
        assertTrue(request.connect); assertEquals(443,request.port)
        assertEquals("secret TLS bytes",input.readBytes().toString(Charsets.UTF_8))
    }
    @Test fun httpForwardsOriginFormAndStripsProxyCredentialsAndHopHeaders() {
        val request=parse("POST http://wikipedia.org/path?value=private HTTP/1.1",
            "Host: wikipedia.org\r\nContent-Length: 3\r\nConnection: Foo\r\nFoo: removed\r\nProxy-Authorization: private\r\nX-Test: preserved")
        assertEquals(3L,request.bodyLength)
        val outgoing=request.forwardedHeaders.toString(Charsets.ISO_8859_1)
        assertTrue(outgoing.startsWith("POST /path?value=private HTTP/1.1\r\n"))
        assertFalse(outgoing.contains("Proxy-Authorization",true))
        assertFalse(outgoing.contains("removed"))
        assertTrue(outgoing.contains("x-test: preserved"))
        assertTrue(outgoing.endsWith("Connection: close\r\n\r\n"))
    }
    @Test fun ambiguousSmugglingAndOpenRelayTargetsAreRejected() {
        rejected("CONNECT wikipedia.org:25 HTTP/1.1")
        rejected("CONNECT 127.0.0.1:443 HTTP/1.1","Host: 127.0.0.1:443")
        rejected("GET http://user:secret@wikipedia.org/ HTTP/1.1")
        rejected("GET https://wikipedia.org/ HTTP/1.1")
        rejected("GET http://wikipedia.org:8080/ HTTP/1.1")
        rejected("GET http://stake.com/ HTTP/1.1")
        rejected("GET http://wikipedia.org/ HTTP/1.1","Host: wikipedia.org\r\nHost: stake.com")
        rejected("POST http://wikipedia.org/ HTTP/1.1","Host: wikipedia.org\r\nContent-Length: 3\r\nContent-Length: 3")
        rejected("POST http://wikipedia.org/ HTTP/1.1","Host: wikipedia.org\r\nTransfer-Encoding: chunked\r\nContent-Length: 3")
        rejected("GET http://wikipedia.org/ HTTP/1.1","Host: wikipedia.org\r\n Folded: invalid")
        rejected("GET http://wikipedia.org/ HTTP/1.1","Host: wikipedia.org\r\nConnection: Content-Length")
    }
    @Test fun headerAndUploadLimitsAreEnforced() {
        rejected("POST http://wikipedia.org/ HTTP/1.1","Host: wikipedia.org\r\nContent-Length: 999999999")
        rejected("POST http://wikipedia.org/ HTTP/1.1","Host: wikipedia.org\r\nContent-Length: -1")
        try { ProxyProtocol.read(ByteArrayInputStream(ByteArray(ProxyProtocol.MAX_HEADERS) { 65 })); fail() }
        catch (error: ProxyRequestError) { assertEquals(431,error.status) }
        try { ProxyProtocol.read(ByteArrayInputStream("GET ".toByteArray())); fail() }
        catch (_: ProxyRequestError) { }
    }
    @Test fun destinationsExcludeLanLoopbackAndAlternateAddressForms() {
        for (ip in listOf("127.0.0.1","10.0.0.1","192.168.1.1","172.16.0.1","169.254.1.1","100.64.1.1","224.0.0.1","::1","fc00::1","2002:c0a8:101::1"))
            assertFalse(ip,ProxyProtocol.publicDestination(InetAddress.getByName(ip)))
        assertTrue(ProxyProtocol.publicDestination(InetAddress.getByName("1.1.1.1")))
        assertTrue(ProxyProtocol.publicDestination(InetAddress.getByName("2606:4700:4700::1111")))
        assertTrue(ProxyProtocol.sameSubnet("192.168.43.25","192.168.43.1",24))
        assertFalse(ProxyProtocol.sameSubnet("192.168.1.25","192.168.43.1",24))
        assertFalse(ProxyProtocol.sameSubnet("127.0.0.1","192.168.43.1",24))
        assertFalse(ProxyProtocol.sameSubnet("192.168.43.25","192.168.43.1",0))
    }
    @Test fun clientCountsStayConsistentUnderTwentyConcurrentClients() {
        val tracker=ClientTracker()
        val pool=Executors.newFixedThreadPool(20)
        try {
            val jobs=(1..20).map { client -> pool.submit {
                repeat(20) { index -> assertTrue(tracker.request("192.168.43.$client",if(index%2==0) "block" else "warn",1000)) }
            } }
            jobs.forEach { it.get() }
            val clients=tracker.snapshot(2000)
            assertEquals(20,clients.size)
            assertEquals(400L,clients.sumOf { it.requests })
            assertEquals(200L,clients.sumOf { it.blocked })
            assertEquals(200L,clients.sumOf { it.warnings })
            tracker.connection("192.168.43.1",1,2000)
            assertEquals(1,tracker.snapshot(200000).size)
            tracker.connection("192.168.43.1",-1,200000)
            assertEquals(0,tracker.snapshot(400000).size)
            tracker.clear(); assertTrue(tracker.snapshot(400000).isEmpty())
        } finally { pool.shutdownNow() }
    }
}
