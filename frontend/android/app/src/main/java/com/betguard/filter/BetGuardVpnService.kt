package com.betguard.filter

import android.app.*
import android.content.Intent
import android.content.pm.ServiceInfo
import android.net.*
import android.os.*
import android.system.OsConstants
import android.system.Os
import android.system.StructPollfd
import android.util.Log
import com.betguard.BuildConfig
import com.betguard.MainActivity
import com.betguard.R
import com.betguard.filter.core.DnsPacket
import com.betguard.filter.core.DnsDecisions
import com.betguard.filter.core.ServiceStatus
import java.io.FileInputStream
import java.io.FileOutputStream
import java.net.DatagramPacket
import java.net.DatagramSocket
import java.net.InetAddress
import java.util.concurrent.*

/** Feasibility filter: routes only the virtual IPv4 DNS resolver, never all IP traffic. */
class BetGuardVpnService : VpnService() {
    private val repo by lazy { RuleRepository.get(this) }
    private var tunnel: ParcelFileDescriptor? = null
    private var reader: Thread? = null
    private var input: FileInputStream? = null
    private var output: FileOutputStream? = null
    private val outputLock = Any()
    private val main = Handler(Looper.getMainLooper())
    private val sockets = ConcurrentHashMap.newKeySet<DatagramSocket>()
    private val detection = DetectionClient()
    private val networks = ConcurrentHashMap.newKeySet<Network>()
    @Volatile private var running = false
    private var watchingNetwork = false
    private var released = false
    private val workers = ThreadPoolExecutor(4, 4, 0L, TimeUnit.MILLISECONDS, ArrayBlockingQueue(64))
    private val connectivity by lazy { getSystemService(ConnectivityManager::class.java) }
    private val networkCallback = object : ConnectivityManager.NetworkCallback() {
        override fun onAvailable(network: Network) {
            networks.add(network)
            if (running) repo.io.execute { repo.record("network", "", "A network is available. DNS requests will use the current underlying connection.") }
        }
        override fun onLost(network: Network) {
            networks.remove(network)
            if (running) {
                sockets.forEach { it.close() }
                if (networks.isEmpty()) repo.updateNetworkState("degraded", "No supported network is available. Saved rules remain on this phone.")
                else repo.io.execute { repo.record("network", "", "Network changed. In-flight DNS requests may need to retry.") }
            }
        }
    }

    override fun onStartCommand(intent: Intent?, flags: Int, startId: Int): Int {
        if (intent?.action == ACTION_STOP) {
            repo.setState("stopping", "Stopping DNS filtering. Waiting for the interface to close.")
            releaseTunnel()
            stopSelf(); return START_NOT_STICKY
        }
        if (running) return START_NOT_STICKY
        try {
            require(prepare(this) == null) { "VPN permission is required." }
            showNotification()
            repo.setState("starting", "Preparing the DNS filter…")
            val descriptor = Builder().setSession("${getString(R.string.app_name)} DNS filter")
                .setMtu(1500).addAddress("10.77.0.1", 32)
                .addDnsServer("10.77.0.2").addRoute("10.77.0.2", 32)
                .allowFamily(OsConstants.AF_INET6).setBlocking(false)
                .setConfigureIntent(openAppIntent())
                .establish() ?: throw IllegalStateException("Android did not establish the DNS interface.")
            tunnel = descriptor
            input = FileInputStream(descriptor.fileDescriptor)
            output = FileOutputStream(descriptor.fileDescriptor)
            running = true
            connectivity.registerNetworkCallback(NetworkRequest.Builder()
                .addCapability(NetworkCapabilities.NET_CAPABILITY_INTERNET)
                .addCapability(NetworkCapabilities.NET_CAPABILITY_NOT_VPN).build(), networkCallback)
            watchingNetwork = true
            repo.setState("active", "DNS filter is running (${if (repo.detectionBaseUrl.isEmpty()) "manual rules" else "online detection"}). Only new requests through the supported DNS path are covered.")
            reader = Thread({ readPackets() }, "BetGuard-DNS").apply { isDaemon = true; start() }
        } catch (error: Exception) {
            Log.e("BetGuardVPN", "Start failed: ${error.javaClass.simpleName}")
            running = false
            repo.setState("failed", "Protection could not start. Check VPN permission and try again.")
            releaseTunnel()
            stopSelf()
        }
        // A killed/rebooted app must be reopened and explicitly enabled; never show stale ACTIVE.
        return START_NOT_STICKY
    }

    private fun readPackets() {
        val buffer = ByteArray(65535)
        try {
            val descriptor = tunnel?.fileDescriptor ?: return
            val pending = StructPollfd().apply { fd = descriptor; events = OsConstants.POLLIN.toShort() }
            while (running) {
                // Bounded polling lets Stop release the reader even when DNS is idle.
                if (Os.poll(arrayOf(pending), 500) == 0) continue
                if (!running) break
                check(pending.revents.toInt() and OsConstants.POLLIN != 0) { "DNS interface unavailable." }
                val size = input?.read(buffer) ?: break
                if (size < 0) break
                val packet = DnsPacket.parse(buffer, size) ?: continue
                try { workers.execute { handle(packet) } }
                catch (_: RejectedExecutionException) {
                    if (running) {
                        respond(packet, packet.errorResponse(2), "dns_error", "DNS filter busy; request returned SERVFAIL.")
                        repo.updateNetworkState("degraded", "The DNS filter is busy. Some requests may need to retry.")
                    }
                }
            }
            if (running) fail("The DNS interface closed. Re-enable protection.")
        } catch (error: Exception) {
            if (running) {
                Log.e("BetGuardVPN", "Reader failed: ${error.javaClass.simpleName}")
                fail("The DNS interface was interrupted. Re-enable protection.")
            }
        }
    }

    private fun handle(packet: DnsPacket) {
        if (!running) return
        try {
            val localRule = repo.match(packet.hostname)
            synchronized(repo) {
                if (repo.match(packet.hostname)?.action == "block") {
                    respond(packet, packet.errorResponse(3), "dns_blocked", "Matching manual block rule.")
                    return
                }
            }
            val result = if (localRule == null && repo.detectionBaseUrl.isNotEmpty()) {
                try {
                    val network = connectivity.allNetworks.firstOrNull { candidate ->
                        val capabilities = connectivity.getNetworkCapabilities(candidate)
                        capabilities?.hasCapability(NetworkCapabilities.NET_CAPABILITY_NOT_VPN) == true &&
                            capabilities.hasCapability(NetworkCapabilities.NET_CAPABILITY_INTERNET)
                    } ?: throw DetectionUnavailable()
                    detection.check(repo.detectionBaseUrl, packet.hostname, network)
                } catch (error: DetectionUnavailable) {
                    // An override saved while HTTP was pending remains usable
                    // even when online detection subsequently fails.
                    if (repo.match(packet.hostname) == null) throw error
                    null
                }
            } else null
            // Apply automatic BLOCK only while holding the edit/write lock. A
            // newly saved local Allow must override the remote response.
            synchronized(repo) {
                if (result?.enforcementAction == "BLOCK" && repo.match(packet.hostname) == null) {
                    respond(packet, packet.errorResponse(3), "dns_detection_blocked",
                        "BetGuard blocked access to this gambling-risk domain (${result.source}). This records a DNS request, not a website visit.")
                    return
                }
            }
            val socket = DatagramSocket()
            sockets.add(socket)
            try {
                if (!running) return
                // Prevent the resolver's own packets from re-entering the VPN.
                check(protect(socket)) { "Could not protect the DNS socket." }
                socket.soTimeout = 2000
                socket.connect(InetAddress.getByName("1.1.1.1"), 53)
                socket.send(DatagramPacket(packet.message, packet.message.size))
                val responseBuffer = ByteArray(65507)
                val response = DatagramPacket(responseBuffer, responseBuffer.size)
                socket.receive(response)
                val bytes = responseBuffer.copyOf(response.length)
                check(packet.accepts(bytes)) { "Invalid resolver response." }
                val rcode = bytes[3].toInt() and 15
                val resolverFailed = rcode == 2 || rcode == 5
                val warning = !resolverFailed && result?.intervention == "WARN"
                respond(packet, bytes, if (resolverFailed) "dns_error" else if (warning) "dns_warning" else "dns_forwarded",
                    if (warning) "BetGuard detected characteristics associated with gambling websites. This is uncertain; network access remains allowed (${result?.source})."
                    else "Upstream DNS response (RCODE $rcode) returned. ${if (resolverFailed) "Resolver failure/refusal; not a manual block." else "Not a website visit or a safety classification."}")
                if (running) repo.updateNetworkState(if (resolverFailed) "degraded" else "active",
                    if (resolverFailed) "The DNS resolver returned an error. Some requests may fail."
                    else "DNS responses are flowing. Only the supported DNS path is covered.")
            } finally { socket.close(); sockets.remove(socket) }
        } catch (_: DetectionUnavailable) {
            if (running) {
                respond(packet, packet.errorResponse(2), "dns_error", "BetGuard detection unavailable; DNS request returned SERVFAIL. No ALLOW/BLOCK decision was made.")
                repo.updateNetworkState("degraded", "Online detection is unavailable. Switch to manual rules only for offline protection.")
            }
        } catch (_: Exception) {
            if (running) {
                respond(packet, packet.errorResponse(2), "dns_error", "Resolver unavailable; DNS request returned SERVFAIL. This is not a policy block.")
                repo.updateNetworkState("degraded", "The DNS resolver could not be reached. Check your connection or disable protection.")
            }
        }
    }

    private fun respond(packet: DnsPacket, bytes: ByteArray, kind: String, message: String) {
        if (!running) return
        try {
            // The same lock protects rule edits and the final decision: a late response cannot
            // overwrite a newly saved block/allow rule. No URL paths or query tokens are logged.
            synchronized(repo) {
                if (!ServiceStatus.acceptsNetworkUpdate(repo.state)) return
                val decision = DnsDecisions.finalResponse(packet, repo.match(packet.hostname), bytes, kind, message)
                synchronized(outputLock) {
                    if (!running) return
                    val stream = output ?: return
                    stream.write(packet.wrap(decision.bytes))
                }
                repo.io.execute { repo.record(decision.kind, packet.hostname, decision.detail) }
            }
        } catch (_: Exception) { if (running) fail("The DNS response could not be delivered. Re-enable protection.") }
    }

    private fun fail(message: String) {
        synchronized(repo) {
            if (!running || !ServiceStatus.acceptsNetworkUpdate(repo.state)) return
            synchronized(outputLock) { running = false }
            repo.setState("failed", message)
        }
        main.post { releaseTunnel(); stopSelf() }
    }

    override fun onRevoke() {
        synchronized(outputLock) { running = false }
        repo.setState("interrupted", "Android revoked VPN access. Protection is off.")
        releaseTunnel()
        stopSelf()
        super.onRevoke()
    }

    override fun onDestroy() {
        releaseTunnel()
        super.onDestroy()
    }

    /** Close the TUN before stopSelf: an Android VPN binding can outlive startService. */
    private fun releaseTunnel() {
        if (released) return
        released = true
        synchronized(outputLock) { running = false }
        if (watchingNetwork) try { connectivity.unregisterNetworkCallback(networkCallback) } catch (_: IllegalArgumentException) { }
        watchingNetwork = false
        try { tunnel?.close() } catch (error: Exception) {
            Log.e("BetGuardVPN", "Interface close failed: ${error.javaClass.simpleName}")
            repo.setState("failed", "Could not close the DNS interface. Check Android VPN settings.")
        }
        tunnel = null
        sockets.forEach { it.close() }
        detection.close()
        workers.shutdownNow()
        reader?.interrupt()
        input = null
        synchronized(outputLock) { output = null }
        if (repo.state !in listOf("failed", "interrupted"))
            repo.setState("off", "Protection is off. Your saved rules stay on this phone.")
        stopForeground(STOP_FOREGROUND_REMOVE)
    }

    private fun openAppIntent(): PendingIntent = PendingIntent.getActivity(this, 0,
        Intent(this, MainActivity::class.java), PendingIntent.FLAG_IMMUTABLE or PendingIntent.FLAG_UPDATE_CURRENT)

    private fun showNotification() {
        val manager = getSystemService(NotificationManager::class.java)
        if (Build.VERSION.SDK_INT >= 26) manager.createNotificationChannel(NotificationChannel(
            CHANNEL, "DNS protection", NotificationManager.IMPORTANCE_LOW))
        val stop = PendingIntent.getService(this, 1, Intent(this, BetGuardVpnService::class.java).setAction(ACTION_STOP),
            PendingIntent.FLAG_IMMUTABLE or PendingIntent.FLAG_UPDATE_CURRENT)
        val builder = if (Build.VERSION.SDK_INT >= 26) Notification.Builder(this, CHANNEL) else Notification.Builder(this)
        val notification = builder.setContentTitle("${getString(R.string.app_name)} DNS filter")
            .setContentText("Open app for current protection status")
            .setSmallIcon(R.drawable.ic_shield).setContentIntent(openAppIntent()).setOngoing(true)
            .addAction(Notification.Action.Builder(null, "Stop", stop).build()).build()
        if (Build.VERSION.SDK_INT >= 34) startForeground(771, notification, ServiceInfo.FOREGROUND_SERVICE_TYPE_SYSTEM_EXEMPTED)
        else startForeground(771, notification)
    }

    companion object {
        val ACTION_STOP = "${BuildConfig.APPLICATION_ID}.STOP"
        const val CHANNEL = "betguard_protection"
    }
}
