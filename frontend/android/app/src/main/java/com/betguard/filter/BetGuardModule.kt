package com.betguard.filter

import android.app.Activity
import android.content.Intent
import android.net.VpnService
import com.facebook.react.bridge.*
import java.util.concurrent.atomic.AtomicBoolean
import com.betguard.filter.network.GatewayState
import com.betguard.filter.network.BetGuardNetworkService
import com.betguard.filter.network.LanInterfaces

class BetGuardModule(private val context: ReactApplicationContext) : NativeBetGuardSpec(context), ActivityEventListener {
    private val repo = RuleRepository.get(context)
    private var permissionPromise: Promise? = null
    private val snapshotQueued = AtomicBoolean(false)
    private val networkQueued = AtomicBoolean(false)
    private val networkListener: () -> Unit = {
        if (networkQueued.compareAndSet(false, true)) repo.io.execute {
            networkQueued.set(false)
            if (context.hasActiveReactInstance() && mEventEmitterCallback != null) emitOnNetworkSnapshot(GatewayState.snapshot())
        }
    }
    private val listener: () -> Unit = {
        if (snapshotQueued.compareAndSet(false, true)) repo.io.execute {
            snapshotQueued.set(false)
            if (context.hasActiveReactInstance() && mEventEmitterCallback != null) emitOnSnapshot(repo.snapshot())
        }
    }

    init { LanInterfaces.initialize(context); context.addActivityEventListener(this); repo.listeners.add(listener); GatewayState.listeners.add(networkListener) }
    override fun getName() = NAME
    override fun getBridgeVersion(): Double = 2.0
    override fun getThemePreference(): String = AppearancePreferences.read(context)
    override fun setThemePreference(mode: String, promise: Promise) =
        run(promise) { AppearancePreferences.save(context, mode); null }
    override fun getSnapshot(promise: Promise) = run(promise) { repo.snapshot() }
    override fun getVisibleApplications(promise: Promise) = run(promise) { ApplicationInventory.read(context) }
    override fun getNetworkSnapshot(promise: Promise) = run(promise) { GatewayState.snapshot() }
    override fun startNetworkProtection(address: String, port: Double, baseUrl: String, promise: Promise) {
        repo.io.execute {
            try {
                require(port.isFinite() && port==port.toInt().toDouble()) { "Use a proxy port from 1024 to 65535." }
                GatewayState.prepare(address,port.toInt(),baseUrl)
                UiThreadUtil.runOnUiThread {
                    try {
                        val intent=Intent(context,BetGuardNetworkService::class.java)
                        if(android.os.Build.VERSION.SDK_INT>=26) context.startForegroundService(intent) else context.startService(intent)
                        promise.resolve(null)
                    } catch (error: Exception) {
                        GatewayState.setState("failed","Network Protection couldn't start. Open BetGuard and try again.")
                        promise.reject("E_NETWORK_START","Network Protection couldn't start. Open BetGuard and try again.")
                    }
                }
            } catch (error: Exception) { promise.reject("E_NETWORK_SETUP",error.message,error) }
        }
    }
    override fun stopNetworkProtection(promise: Promise) {
        UiThreadUtil.runOnUiThread {
            try {
                if (GatewayState.state in listOf("off","failed","interrupted")) { promise.resolve(null); return@runOnUiThread }
                GatewayState.setState("stopping","Closing the network gateway…")
                context.startService(Intent(context,BetGuardNetworkService::class.java).setAction(BetGuardNetworkService.ACTION_STOP))
                promise.resolve(null)
            } catch (_: Exception) { promise.reject("E_NETWORK_STOP","Could not stop the gateway. Reopen BetGuard and try again.") }
        }
    }
    override fun configureDetection(baseUrl: String, promise: Promise) =
        run(promise) { repo.configureDetection(baseUrl); null }
    override fun saveRule(input: String, action: String, includeSubdomains: Boolean, promise: Promise) =
        run(promise) { repo.save(input, action, includeSubdomains) }
    override fun removeRule(domain: String, promise: Promise) = run(promise) { repo.remove(domain); null }
    override fun checkLink(input: String, promise: Promise) = run(promise) { repo.check(input) }
    override fun resolveLink(input: String, promise: Promise) = run(promise) { repo.check(input, false) }
    override fun clearHistory(promise: Promise) = run(promise) { repo.clearHistory(); null }

    override fun startProtection(promise: Promise) {
        UiThreadUtil.runOnUiThread {
            if (permissionPromise != null) { promise.reject("E_PENDING", "Finish the open permission request first."); return@runOnUiThread }
            val activity = context.currentActivity
            if (activity == null) { promise.reject("E_ACTIVITY", "Open BetGuard before enabling protection."); return@runOnUiThread }
            try {
                val permission = VpnService.prepare(activity)
                if (permission != null) {
                    permissionPromise = promise
                    activity.startActivityForResult(permission, PERMISSION_REQUEST)
                } else startService(promise)
            } catch (e: Exception) { permissionPromise = null; promise.reject("E_VPN", e.message, e) }
        }
    }

    private fun startService(promise: Promise) {
        if (repo.state == "stopping") { promise.reject("E_STOPPING", "Wait for protection to stop before enabling it again."); return }
        if (repo.state in listOf("active", "degraded", "starting")) { promise.resolve(null); return }
        try {
            repo.setState("starting", "Starting DNS filtering…")
            val intent = Intent(context, BetGuardVpnService::class.java)
            if (android.os.Build.VERSION.SDK_INT >= 26) context.startForegroundService(intent)
            else context.startService(intent)
            promise.resolve(null)
        } catch (e: Exception) {
            repo.setState("failed", "Could not start protection. Open the app and try again.")
            promise.reject("E_START", e.message, e)
        }
    }

    override fun stopProtection(promise: Promise) {
        UiThreadUtil.runOnUiThread {
            try {
                if (permissionPromise != null) {
                    promise.reject("E_PENDING", "Finish the VPN permission request first.")
                    return@runOnUiThread
                }
                // Android binds an established VPN. stopService alone cannot
                // destroy that bound instance or close its network interface.
                repo.setState("stopping", "Stopping DNS filtering. Waiting for the interface to close.")
                context.startService(Intent(context, BetGuardVpnService::class.java)
                    .setAction(BetGuardVpnService.ACTION_STOP))
                promise.resolve(null)
            } catch (e: Exception) {
                repo.setState("failed", "Could not stop protection. Check Android VPN settings.")
                promise.reject("E_STOP", "Could not stop protection. Check Android VPN settings.", e)
            }
        }
    }

    override fun onActivityResult(activity: Activity, requestCode: Int, resultCode: Int, data: Intent?) {
        if (requestCode != PERMISSION_REQUEST) return
        val promise = permissionPromise ?: return
        permissionPromise = null
        if (resultCode == Activity.RESULT_OK && VpnService.prepare(context) == null) startService(promise)
        else { repo.setState("off", "VPN permission was not granted. Protection is off."); promise.reject("E_PERMISSION", "VPN permission was not granted.") }
    }

    override fun onNewIntent(intent: Intent) = Unit
    override fun invalidate() {
        repo.listeners.remove(listener)
        GatewayState.listeners.remove(networkListener)
        context.removeActivityEventListener(this)
        permissionPromise?.reject("E_CLOSED", "The app closed during the permission request.")
        permissionPromise = null
        super.invalidate()
    }

    private fun run(promise: Promise, action: () -> Any?) {
        repo.io.execute {
            try { promise.resolve(action()) } catch (e: Exception) { promise.reject("E_BETGUARD", e.message, e) }
        }
    }
    companion object { const val NAME = "NativeBetGuard"; const val PERMISSION_REQUEST = 771 }
}
