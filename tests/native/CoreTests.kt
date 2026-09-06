package com.betguard.tests

import com.betguard.filter.core.DomainPolicy
import com.betguard.filter.core.DomainRule
import com.betguard.filter.core.DnsPacket
import kotlin.random.Random

private var checks = 0
private fun verify(name: String, action: () -> Unit) {
    action(); checks++; println("PASS $name")
}
private fun rejected(input: String) = check(runCatching { DomainPolicy.normalize(input) }.isFailure) { "Accepted invalid rule: $input" }
private fun put16(b: ByteArray, i: Int, n: Int) {b[i]=(n ushr 8).toByte(); b[i+1]=n.toByte()}
private fun u16(b: ByteArray, i: Int) = ((b[i].toInt() and 255) shl 8) or (b[i+1].toInt() and 255)
private fun query(host: String = "example.com", type: Int = 1): ByteArray {
    val dns = mutableListOf<Byte>(0x12,0x34,1,0,0,1,0,0,0,0,0,0)
    host.split('.').forEach {dns.add(it.length.toByte()); dns.addAll(it.toByteArray().toList())}
    dns.addAll(listOf(0,0,type.toByte(),0,1))
    val packet = ByteArray(28+dns.size)
    packet[0]=0x45; put16(packet,2,packet.size); packet[8]=64; packet[9]=17
    byteArrayOf(10,77,0,1).copyInto(packet,12)
    byteArrayOf(10,77,0,2).copyInto(packet,16)
    put16(packet,20,49152); put16(packet,22,53); put16(packet,24,dns.size+8)
    dns.toByteArray().copyInto(packet,28)
    return packet
}

fun main() {
    verify("URL normalization removes sensitive path and query") {check(DomainPolicy.normalize(" HTTPS://Example.COM:443/a?token=secret#x ")=="example.com")}
    verify("hostname, trailing dot, Unicode IDN") {
        check(DomainPolicy.normalize("WWW.Example.com.")=="www.example.com")
        check(DomainPolicy.normalize("https://bücher.example/path")=="xn--bcher-kva.example")
    }
    verify("unsupported schemes, credentials and IP rules rejected") {
        listOf("", "javascript:alert(1)", "ftp://example.com", "https://u:p@example.com", "https://127.0.0.1", "[::1]", "localhost", "com", "*.example.com", "example.com:70000", "https://example.com\\@evil.com", "ex ample.com", "example..com", "example.com%2f.evil.com").forEach(::rejected)
    }
    verify("exact rule does not include children or lookalike suffixes") {
        val rules=listOf(DomainRule("example.com","block",false))
        check(DomainPolicy.match("example.com",rules)?.action=="block")
        check(DomainPolicy.match("www.example.com",rules)==null)
        check(DomainPolicy.match("notexample.com",rules)==null)
        check(DomainPolicy.match("example.com.evil.test",rules)==null)
    }
    verify("more specific allow overrides ancestor block in either order") {
        val rules=listOf(DomainRule("example.com","block",true), DomainRule("help.example.com","allow",true))
        for (order in listOf(rules,rules.reversed())) {
            check(DomainPolicy.match("a.help.example.com",order)?.action=="allow")
            check(DomainPolicy.match("www.example.com",order)?.action=="block")
        }
    }
    verify("removing override exposes parent rule") {
        check(DomainPolicy.match("help.example.com",listOf(DomainRule("example.com","block",true)))?.action=="block")
        check(DomainPolicy.match("help.example.com",emptyList())==null)
    }
    val original=query()
    val parsed=DnsPacket.parse(original) ?: error("Valid query rejected")
    verify("IPv4 UDP question parsing and source port") {check(parsed.hostname=="example.com"); check(parsed.sourcePort==49152)}
    verify("AAAA lookup travels through the same IPv4 DNS path") {check(DnsPacket.parse(query(type=28))?.hostname=="example.com")}
    verify("NXDOMAIN has one question, zero answers and no DNSSEC claims") {
        val dns=parsed.errorResponse(3)
        check(u16(dns,0)==0x1234 && u16(dns,2)==0x8183)
        check(u16(dns,4)==1 && (6..11).all {dns[it].toInt()==0})
        check(dns.copyOfRange(12,dns.size).contentEquals(parsed.message.copyOfRange(12,parsed.questionEnd)))
    }
    verify("response reverses addresses and ports with valid IPv4 checksum") {
        val response=parsed.wrap(parsed.errorResponse(3))
        check(response.copyOfRange(12,16).contentEquals(byteArrayOf(10,77,0,2)))
        check(response.copyOfRange(16,20).contentEquals(byteArrayOf(10,77,0,1)))
        check(u16(response,20)==53 && u16(response,22)==49152)
        check(u16(response,2)==response.size && u16(response,24)==response.size-20)
        var sum=(0 until 20 step 2).sumOf {u16(response,it)}
        while(sum shr 16 != 0) sum=(sum and 65535)+(sum shr 16)
        check(sum==65535)
    }
    verify("resolver response must match ID, question, type and QR") {
        val response=parsed.errorResponse(0); check(parsed.accepts(response))
        check(!parsed.accepts(response.copyOf().apply {this[0]=0}))
        check(!parsed.accepts(response.copyOf().apply {this[lastIndex-2]=28}))
        check(!parsed.accepts(response.copyOf().apply {this[13]='z'.code.toByte()}))
        check(!parsed.accepts(parsed.message))
    }
    verify("uncovered transport, wrong destination and fragmentation rejected") {
        check(DnsPacket.parse(original.copyOf().apply {this[0]=0x65})==null)
        check(DnsPacket.parse(original.copyOf().apply {this[9]=6})==null)
        check(DnsPacket.parse(original.copyOf().apply {this[19]=3})==null)
        check(DnsPacket.parse(original.copyOf().apply {this[6]=0x20})==null)
    }
    verify("truncation and malformed DNS never escape the parser") {
        for (length in 0 until original.size) check(DnsPacket.parse(original,length)==null)
        check(DnsPacket.parse(original.copyOf().apply {this[40]=0xC0.toByte()})==null)
        check(DnsPacket.parse(original.copyOf().apply {this[33]=2})==null)
        check(DnsPacket.parse(original.copyOf().apply {put16(this,24,65535)})==null)
        val random=Random(771)
        repeat(5000) {val bytes=random.nextBytes(random.nextInt(0,300)); DnsPacket.parse(bytes)}
    }
    println("$checks native core scenarios passed (including 5,000 malformed-packet samples).")
}
