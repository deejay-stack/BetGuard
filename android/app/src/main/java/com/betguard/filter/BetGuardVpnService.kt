package com.betguard.filter

import android.app.*
import android.content.Intent
import android.content.pm.ServiceInfo
import android.net.*
import android.os.*
import android.system.OsConstants
import android.system.Os
import android.system.StructPollfd
import com.betguard.MainActivity
import com.betguard.R
import com.betguard.filter.core.DnsPacket
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
    private val networks = ConcurrentHashMap.newKeySet<Network>()
    @Volatile private var running = false
    private var watchingNetwork = false
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
                if (networks.isEmpty()) repo.setState("degraded", "No supported network is available. Saved rules remain on this phone.")
                else repo.io.execute { repo.record("network", "", "Network changed. In-flight DNS requests may need to retry.") }
            }
        }
    }

    override fun onStartCommand(intent: Intent?, flags: Int, startId: Int): Int {
        if (intent?.action == ACTION_STOP) { stopSelf(); return START_NOT_STICKY }
        if (running) return START_NOT_STICKY
        try {
            require(prepare(this) == null) { "VPN permission is required." }
            showNotification()
            repo.setState("starting", "Preparing the DNS filter…")
            val descriptor = Builder().setSession("BetGuard DNS filter")
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
            repo.setState("active", "DNS filter is running. Only new requests through the supported DNS path are covered.")
            reader = Thread({ readPackets() }, "BetGuard-DNS").apply { isDaemon = true; start() }
        } catch (_: Exception) {
            repo.setState("failed", "Protection could not start. Check VPN permission and try again.")
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
                        repo.setState("degraded", "The DNS filter is busy. Some requests may need to retry.")
                    }
                }
            }
            if (running) fail("The DNS interface closed. Re-enable protection.")
        } catch (_: Exception) { if (running) fail("The DNS interface was interrupted. Re-enable protection.") }
    }

    private fun handle(packet: DnsPacket) {
        if (!running) return
        try {
            synchronized(repo) {
                if (repo.match(packet.hostname)?.action == "block") {
                    respond(packet, packet.errorResponse(3), "dns_blocked", "Matching manual block rule.")
                    return
                }
            }
            val socket = DatagramSocket()
            sockets.add(socket)
            try {
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
                respond(packet, bytes, "dns_forwarded", "Resolver response returned; this is not a gambling classification.")
                if (running && repo.state == "degraded") repo.setState("active", "DNS responses are flowing again. Only the supported DNS path is covered.")
            } finally { socket.close(); sockets.remove(socket) }
        } catch (_: Exception) {
            if (running) {
                respond(packet, packet.errorResponse(2), "dns_error", "Resolver unavailable; DNS request returned SERVFAIL. This is not a policy block.")
                repo.setState("degraded", "The DNS resolver could not be reached. Check your connection or disable protection.")
            }
        }
    }

    private fun respond(packet: DnsPacket, bytes: ByteArray, kind: String, message: String) {
        if (!running) return
        try {
            // The same lock protects rule edits and the final decision: a late response cannot
            // overwrite a newly saved block/allow rule. No URL paths or query tokens are logged.
            synchronized(repo) {
                val blocked = repo.match(packet.hostname)?.action == "block"
                val response = if (blocked) packet.errorResponse(3) else bytes
                synchronized(outputLock) {
                    if (!running) return
                    val stream = output ?: return
                    stream.write(packet.wrap(response))
                }
                repo.io.execute { repo.record(if (blocked) "dns_blocked" else kind, packet.hostname,
                    if (blocked) "NXDOMAIN response written to the DNS interface for a matching manual rule." else message) }
            }
        } catch (_: Exception) { if (running) fail("The DNS response could not be delivered. Re-enable protection.") }
    }

    private fun fail(message: String) {
        repo.setState("failed", message)
        main.post { stopSelf() }
    }

    override fun onRevoke() {
        repo.setState("interrupted", "Android revoked VPN access. Protection is off.")
        stopSelf()
        super.onRevoke()
    }

    override fun onDestroy() {
        running = false
        if (watchingNetwork) connectivity.unregisterNetworkCallback(networkCallback)
        sockets.forEach { it.close() }
        workers.shutdownNow()
        try { tunnel?.close() } catch (_: Exception) { }
        reader?.interrupt()
        tunnel = null
        input = null
        synchronized(outputLock) { output = null }
        if (repo.state !in listOf("failed", "interrupted"))
            repo.setState("off", "Protection is off. Your saved rules stay on this phone.")
        stopForeground(STOP_FOREGROUND_REMOVE)
        super.onDestroy()
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
        val notification = builder.setContentTitle("BetGuard DNS filter")
            .setContentText("Manual rules enabled · Tap to view status")
            .setSmallIcon(R.drawable.ic_shield).setContentIntent(openAppIntent()).setOngoing(true)
            .addAction(Notification.Action.Builder(null, "Stop", stop).build()).build()
        if (Build.VERSION.SDK_INT >= 34) startForeground(771, notification, ServiceInfo.FOREGROUND_SERVICE_TYPE_SYSTEM_EXEMPTED)
        else startForeground(771, notification)
    }

    companion object {
        const val ACTION_STOP = "com.betguard.STOP"
        const val CHANNEL = "betguard_protection"
    }
}
