package com.betguard.filter.network

import java.net.Inet4Address
import java.net.NetworkInterface
import android.content.Context
import android.net.ConnectivityManager
import org.json.JSONObject

data class LanAddress(val address: String, val prefixLength: Int, val interfaceName: String) {
    fun json() = JSONObject().put("address",address).put("prefixLength",prefixLength).put("interfaceName",interfaceName)
}

object LanInterfaces {
    private var connectivity: ConnectivityManager?=null
    fun initialize(context: Context) { connectivity=context.getSystemService(ConnectivityManager::class.java) }
    fun discover(): List<LanAddress> = try {
        val upstreamInterfaces=connectivity?.allNetworks?.mapNotNull {
            connectivity?.getLinkProperties(it)?.interfaceName
        }?.toSet() ?: emptySet()
        NetworkInterface.getNetworkInterfaces().toList().filter {
            it.isUp && !it.isLoopback && it.name.matches(Regex("(?:wlan|swlan|ap|softap|eth|en|br)[a-zA-Z0-9_.-]*"))
        }.flatMap { network -> network.interfaceAddresses.mapNotNull { entry ->
            val ip=entry.address
            if (ip is Inet4Address && ip.isSiteLocalAddress && entry.networkPrefixLength.toInt() in 8..30)
                LanAddress(ip.hostAddress!!,entry.networkPrefixLength.toInt(),network.name) else null
        } }.distinctBy { it.address }.sortedBy { if (it.interfaceName !in upstreamInterfaces) 0 else 1 }
    } catch (_: Exception) { emptyList() }
}
