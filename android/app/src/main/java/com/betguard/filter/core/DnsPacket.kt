package com.betguard.filter.core

/** Only unfragmented IPv4 UDP DNS to the virtual resolver is covered in M1. */
data class DnsPacket(
    val sourceAddress: ByteArray,
    val destinationAddress: ByteArray,
    val sourcePort: Int,
    val message: ByteArray,
    val hostname: String,
    val questionEnd: Int,
) {
    fun errorResponse(rcode: Int): ByteArray {
        val result = message.copyOfRange(0, questionEnd)
        // QR + original RD; RA; no AD, AA, or copied EDNS/DNSSEC claims.
        result[2] = (0x80 or (message[2].toInt() and 1)).toByte()
        result[3] = (0x80 or (rcode and 15)).toByte()
        for (i in 6..11) result[i] = 0
        return result
    }

    fun accepts(response: ByteArray): Boolean {
        if (response.size < 12 || u16(response, 0) != u16(message, 0)) return false
        if ((response[2].toInt() and 0xF8) != 0x80 || u16(response, 4) != 1) return false
        val question = readQuestion(response) ?: return false
        return question.first == hostname &&
            response.copyOfRange(question.second - 4, question.second)
                .contentEquals(message.copyOfRange(questionEnd - 4, questionEnd))
    }

    fun wrap(response: ByteArray): ByteArray {
        require(response.size <= 65507)
        val packet = ByteArray(28 + response.size)
        packet[0] = 0x45
        put16(packet, 2, packet.size)
        packet[8] = 64
        packet[9] = 17
        destinationAddress.copyInto(packet, 12)
        sourceAddress.copyInto(packet, 16)
        put16(packet, 20, 53)
        put16(packet, 22, sourcePort)
        put16(packet, 24, 8 + response.size)
        // UDP checksum zero is permitted for IPv4. IPv6 is not parsed here.
        response.copyInto(packet, 28)
        var sum = 0
        for (i in 0 until 20 step 2) sum += u16(packet, i)
        while (sum shr 16 != 0) sum = (sum and 65535) + (sum shr 16)
        put16(packet, 10, sum.inv() and 65535)
        return packet
    }

    companion object {
        val resolverAddress = byteArrayOf(10, 77, 0, 2)

        fun parse(bytes: ByteArray, size: Int = bytes.size): DnsPacket? {
            if (size < 40 || size > bytes.size || (bytes[0].toInt() ushr 4 and 15) != 4) return null
            val ihl = (bytes[0].toInt() and 15) * 4
            val total = u16(bytes, 2)
            if (ihl < 20 || total > size || total < ihl + 20) return null
            if (bytes[9].toInt() != 17 || (u16(bytes, 6) and 0x3FFF) != 0) return null
            if (!bytes.copyOfRange(16, 20).contentEquals(resolverAddress)) return null
            if (u16(bytes, ihl + 2) != 53) return null
            val udpSize = u16(bytes, ihl + 4)
            if (udpSize < 20 || ihl + udpSize != total) return null
            val dns = bytes.copyOfRange(ihl + 8, total)
            if ((dns[2].toInt() and 0xF8) != 0 || u16(dns, 4) != 1) return null
            val (hostname, end) = readQuestion(dns) ?: return null
            return DnsPacket(bytes.copyOfRange(12, 16), resolverAddress.copyOf(), u16(bytes, ihl), dns, hostname, end)
        }

        private fun readQuestion(dns: ByteArray): Pair<String, Int>? {
            var cursor = 12
            val labels = mutableListOf<String>()
            while (cursor < dns.size) {
                val count = dns[cursor++].toInt() and 255
                if (count == 0) {
                    if (cursor + 4 > dns.size || labels.isEmpty()) return null
                    val name = labels.joinToString(".").lowercase(java.util.Locale.ROOT)
                    if (name.length > 253) return null
                    return name to cursor + 4
                }
                // Reject compressed/extended question labels and truncated payloads.
                if (count > 63 || cursor + count > dns.size) return null
                val label = dns.copyOfRange(cursor, cursor + count)
                if (label.any { (it.toInt() and 255) !in 33..126 || it.toInt() == 46 }) return null
                labels.add(String(label, Charsets.US_ASCII))
                cursor += count
            }
            return null
        }

        private fun u16(b: ByteArray, at: Int) = ((b[at].toInt() and 255) shl 8) or (b[at + 1].toInt() and 255)
        private fun put16(b: ByteArray, at: Int, value: Int) {
            b[at] = (value ushr 8).toByte()
            b[at + 1] = value.toByte()
        }
    }
}
