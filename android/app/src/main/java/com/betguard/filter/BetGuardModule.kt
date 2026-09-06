package com.betguard.filter

import android.app.Activity
import android.content.Intent
import android.net.VpnService
import com.facebook.react.bridge.*

class BetGuardModule(private val context: ReactApplicationContext) : NativeBetGuardSpec(context), ActivityEventListener {
    private val repo = RuleRepository.get(context)
    private var permissionPromise: Promise? = null
    private val listener: () -> Unit = {
        repo.io.execute {
            if (context.hasActiveReactInstance() && mEventEmitterCallback != null) emitOnSnapshot(repo.snapshot())
        }
    }

    init { context.addActivityEventListener(this); repo.listeners.add(listener) }
    override fun getName() = NAME
    override fun getSnapshot(promise: Promise) = run(promise) { repo.snapshot() }
    override fun saveRule(input: String, action: String, includeSubdomains: Boolean, promise: Promise) =
        run(promise) { repo.save(input, action, includeSubdomains) }
    override fun removeRule(domain: String, promise: Promise) = run(promise) { repo.remove(domain); null }
    override fun checkLink(input: String, promise: Promise) = run(promise) { repo.check(input) }
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
            context.stopService(Intent(context, BetGuardVpnService::class.java))
            repo.setState("off", "Protection is off. Your saved rules stay on this phone.")
            promise.resolve(null)
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
