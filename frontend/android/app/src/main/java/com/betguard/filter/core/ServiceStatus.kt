package com.betguard.filter.core

/** Late DNS/network work must never revive a stopped or terminal service. */
object ServiceStatus {
    fun acceptsNetworkUpdate(state: String) = state == "active" || state == "degraded"
}
