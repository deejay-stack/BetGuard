package com.betguard.filter.network

import android.app.*
import android.content.Intent
import android.content.pm.ServiceInfo
import android.net.ConnectivityManager
import android.net.Network
import android.net.NetworkCapabilities
import android.os.Build
import android.os.Handler
import android.os.Looper
import android.util.Log
import com.betguard.BuildConfig
import com.betguard.MainActivity
import com.betguard.R
import com.betguard.filter.DetectionClient
import com.betguard.filter.DetectionUnavailable
import com.betguard.filter.DetectionResult
import com.betguard.filter.RuleRepository
import java.io.BufferedInputStream
import java.io.InputStream
import java.io.OutputStream
import java.net.*
import java.util.concurrent.*

/** Explicit LAN HTTP proxy. No tether routing, TLS decryption or classifier duplication. */
class BetGuardNetworkService : Service() {
    private val repo by lazy { RuleRepository.get(this) }
    private val connectivity by lazy { getSystemService(ConnectivityManager::class.java) }
    private val detector=DetectionClient()
    private val main=Handler(Looper.getMainLooper())
    private val sockets=ConcurrentHashMap.newKeySet<Socket>()
    private val tunnels=ConcurrentHashMap<Socket,String>()
    private val workers=ThreadPoolExecutor(4,64,30,TimeUnit.SECONDS,SynchronousQueue<Runnable>())
    private val relays=ThreadPoolExecutor(0,64,30,TimeUnit.SECONDS,SynchronousQueue<Runnable>())
    private val monitor=Executors.newSingleThreadScheduledExecutor()
    @Volatile private var running=false
    private var server: ServerSocket?=null
    private val ruleListener: () -> Unit = {
        // A new Block closes old CONNECT tunnels as well as refusing the next request.
        tunnels.forEach { (socket,domain) -> if (repo.match(domain)?.action=="block") close(socket) }
    }

    override fun onBind(intent: Intent?) = null
    override fun onStartCommand(intent: Intent?, flags: Int, startId: Int): Int {
        if (intent?.action==ACTION_STOP) {
            GatewayState.setState("stopping","Closing the network gateway and its client connections…")
            release("off","Network Protection is off. Set clients' Wi-Fi proxy to None before browsing directly.")
            return START_NOT_STICKY
        }
        if (running) return START_NOT_STICKY
        if (GatewayState.state!="starting") { stopSelf(); return START_NOT_STICKY }
        try {
            notification()
            running=true
            workers.execute { startGateway() }
        } catch (error: Exception) { fail("Network Protection couldn't start. Open BetGuard and try again.",error) }
        return START_NOT_STICKY
    }

    private fun startGateway() {
        try {
            val endpoint=GatewayState.endpoint ?: throw IllegalStateException()
            val socket=ServerSocket()
            server=socket
            socket.reuseAddress=false
            socket.bind(InetSocketAddress(endpoint.address,GatewayState.port),64)
            if (!running) { socket.close(); return }
            synchronized(this) {
                if (!running) { socket.close(); return }
                repo.listeners.add(ruleListener)
                GatewayState.setState("active","Gateway is listening. Only devices using its manual proxy are protected.")
            }
            monitor.scheduleWithFixedDelay({
                if (running) {
                    if (LanInterfaces.discover().none { it==endpoint }) {
                        release("interrupted","The gateway address changed or disappeared. Refresh addresses and restart; update clients' proxy settings.")
                    } else {
                        if (underlying()==null) GatewayState.degrade("No internet connection is available. Check mobile data or Wi-Fi.")
                        GatewayState.changed()
                        main.post { if (running) notification() }
                    }
                }
            },5,5,TimeUnit.SECONDS)
            while (running) {
                val client=socket.accept()
                val ip=client.inetAddress.hostAddress ?: ""
                if (!ProxyProtocol.sameSubnet(ip,endpoint.address,endpoint.prefixLength)) { client.close(); continue }
                client.soTimeout=15000
                sockets.add(client)
                try { workers.execute { handle(client,ip) } }
                catch (_: RejectedExecutionException) { GatewayState.reject(); response(client,503); close(client) }
            }
        } catch (error: Exception) {
            if (running) fail(if (error is BindException) "The proxy port is already in use. Choose another port and try again."
                else "The network gateway stopped. Check your hotspot or Wi-Fi and restart Network Protection.",error)
        }
    }

    private fun underlying(): Network? = connectivity.allNetworks.firstOrNull { network ->
        val capabilities=connectivity.getNetworkCapabilities(network)
        capabilities?.hasCapability(NetworkCapabilities.NET_CAPABILITY_NOT_VPN)==true &&
            capabilities.hasCapability(NetworkCapabilities.NET_CAPABILITY_INTERNET) &&
            capabilities.hasCapability(NetworkCapabilities.NET_CAPABILITY_VALIDATED)
    }

    private fun decision(hostname: String, network: Network): DetectionResult {
        repo.match(hostname)?.let { return local(it.action) }
        val remote=try {
            detector.check(GatewayState.baseUrl,hostname,network).also { GatewayState.backend(true) }
        } catch (error: DetectionUnavailable) {
            repo.match(hostname)?.let { return local(it.action) }
            GatewayState.backend(false); throw error
        }
        return repo.match(hostname)?.let { local(it.action) } ?: remote
    }
    private fun local(action: String) = DetectionResult(if(action=="block") "BLOCK" else "ALLOW",
        if(action=="block") "BLOCK" else "NONE",if(action=="block") "user_blocklist" else "user_allowlist")

    private fun handle(client: Socket, ip: String) {
        var destination: Socket?=null
        var host=""
        var tracked=false
        var accepted=false
        try {
            val input=BufferedInputStream(client.getInputStream())
            val request=ProxyProtocol.read(input)
            host=request.hostname
            val network=underlying()
            // Manual Block works even while the backend/underlying internet is unavailable.
            var result=repo.match(host)?.let { local(it.action) }
                ?: decision(host,network ?: throw DetectionUnavailable())
            synchronized(repo) {
                result=repo.match(host)?.let { local(it.action) } ?: result
                if (result.enforcementAction=="BLOCK") { event(ip,host,"block",result.source); tracked=true; response(client,403); return }
            }
            val route=network ?: throw SocketException()
            val addresses=route.getAllByName(host)
            if (addresses.isEmpty() || addresses.any { !ProxyProtocol.publicDestination(it) }) {
                event(ip,host,"error","destination_restricted"); tracked=true; response(client,403); return
            }
            var lastError: Exception?=null
            for (address in addresses.take(4)) {
                val socket=route.socketFactory.createSocket()
                sockets.add(socket)
                try { socket.connect(InetSocketAddress(address,request.port),4000); destination=socket; break }
                catch (error: Exception) { lastError=error; close(socket) }
            }
            val upstream=destination ?: throw (lastError ?: SocketException())
            upstream.soTimeout=60000
            client.soTimeout=60000
            synchronized(repo) {
                if (!running) return
                result=repo.match(host)?.let { local(it.action) } ?: result
                if (result.enforcementAction=="BLOCK") { event(ip,host,"block",result.source); tracked=true; response(client,403); return }
                tunnels[client]=host
                val outcome=if(result.intervention=="WARN") "warn" else "allow"
                if (!event(ip,host,outcome,result.source)) { response(client,503); return }
                tracked=true
                GatewayState.clients.connection(ip,1,System.currentTimeMillis())
                accepted=true
                if (request.connect) {
                    client.getOutputStream().write("HTTP/1.1 200 Connection Established\r\n\r\n".toByteArray(Charsets.US_ASCII))
                } else upstream.getOutputStream().write(request.forwardedHeaders)
            }
            GatewayState.healthy()
            if (BuildConfig.DEBUG) Log.d("BetGuardNetwork","client=$ip domain=$host decision=${result.enforcementAction} source=${result.source}")
            if (request.connect) tunnel(input,client,upstream)
            else {
                copyBody(input,upstream.getOutputStream(),request.bodyLength)
                copy(upstream.getInputStream(),client.getOutputStream())
            }
        } catch (error: ProxyRequestError) {
            GatewayState.reject(); response(client,error.status)
        } catch (error: DetectionUnavailable) {
            if (!tracked && host.isNotEmpty()) event(ip,host,"error","detection_unavailable")
            GatewayState.degrade("The BetGuard decision service is unavailable. Check the backend connection; unmatched requests are refused.")
            response(client,503)
        } catch (error: Exception) {
            if (running && !accepted) {
                if (!tracked && host.isNotEmpty()) event(ip,host,"error","connection_unavailable")
                response(client,502)
            }
            if (BuildConfig.DEBUG && running) Log.d("BetGuardNetwork","Connection ended: ${error.javaClass.simpleName}")
        } finally {
            if (accepted) GatewayState.clients.connection(ip,-1,System.currentTimeMillis())
            tunnels.remove(client)
            destination?.let { close(it) }
            close(client); GatewayState.changed()
        }
    }

    private fun event(ip: String, hostname: String, outcome: String, source: String): Boolean {
        if (!running) return false
        if (!GatewayState.outcome(ip,outcome)) return false
        if (BuildConfig.DEBUG) Log.d("BetGuardNetwork","client=$ip domain=$hostname outcome=$outcome source=$source")
        val kind=when(outcome) { "block" -> "network_blocked"; "warn" -> "network_warning"; "allow" -> "network_allowed"; else -> "network_error" }
        val message=when(outcome) {
            "block" -> "Proxy connection refused before forwarding."
            "warn" -> "Uncertain model warning; proxy connection allowed. Review the hostname in Network Protection."
            "allow" -> "Proxy connection permitted. This is not a safety guarantee or a website visit count."
            else -> "Proxy request could not be completed. No AI block decision was made."
        }
        repo.io.execute { repo.recordNetwork(kind,hostname,ip,source,"$message Source: $source.") }
        return true
    }

    private fun tunnel(input: InputStream, client: Socket, upstream: Socket) {
        val reverse=relays.submit {
            try { copy(upstream.getInputStream(),client.getOutputStream()); client.shutdownOutput() }
            catch (_: Exception) { close(client); close(upstream) }
        }
        try { copy(input,upstream.getOutputStream()); upstream.shutdownOutput(); reverse.get(65,TimeUnit.SECONDS) }
        finally { reverse.cancel(true) }
    }
    private fun copy(input: InputStream, output: OutputStream) {
        val buffer=ByteArray(16384)
        while (running) { val read=input.read(buffer); if (read<0) break; output.write(buffer,0,read) }
    }
    private fun copyBody(input: InputStream, output: OutputStream, length: Long) {
        var remaining=length
        val buffer=ByteArray(16384)
        while (remaining>0 && running) {
            val read=input.read(buffer,0,minOf(buffer.size.toLong(),remaining).toInt())
            if (read<0) throw ProxyRequestError()
            output.write(buffer,0,read); remaining-=read
        }
    }
    private fun response(socket: Socket, status: Int) {
        try {
            val text=when(status) { 403 -> "Request refused by BetGuard"; 503 -> "BetGuard service unavailable"; else -> "Proxy request could not be completed" }
            val body="$text. Open BetGuard on the gateway phone for details.\n".toByteArray(Charsets.UTF_8)
            socket.getOutputStream().write("HTTP/1.1 $status $text\r\nContent-Type: text/plain; charset=utf-8\r\nContent-Length: ${body.size}\r\nConnection: close\r\n\r\n".toByteArray(Charsets.US_ASCII))
            socket.getOutputStream().write(body)
        } catch (_: Exception) { }
    }
    private fun close(socket: Socket) { try { socket.close() } catch (_: Exception) { }; sockets.remove(socket) }
    private fun fail(message: String, error: Exception) {
        Log.e("BetGuardNetwork","Gateway failure: ${error.javaClass.simpleName}")
        release("failed",message)
    }
    @Synchronized private fun release(next: String, message: String) {
        running=false
        try { server?.close() } catch (_: Exception) { }
        server=null; repo.listeners.remove(ruleListener)
        detector.close(); sockets.forEach { close(it) }; tunnels.clear()
        monitor.shutdownNow(); workers.shutdownNow(); relays.shutdownNow()
        GatewayState.setState(next,message)
        main.post { stopForeground(STOP_FOREGROUND_REMOVE); stopSelf() }
    }
    override fun onDestroy() {
        if (running) release("interrupted","Android stopped the network gateway. Open BetGuard to restart it.")
        super.onDestroy()
    }
    private fun notification() {
        val manager=getSystemService(NotificationManager::class.java)
        if (Build.VERSION.SDK_INT>=26) manager.createNotificationChannel(NotificationChannel(CHANNEL,"Network Protection",NotificationManager.IMPORTANCE_LOW))
        val open=PendingIntent.getActivity(this,773,Intent(this,MainActivity::class.java),PendingIntent.FLAG_IMMUTABLE or PendingIntent.FLAG_UPDATE_CURRENT)
        val stop=PendingIntent.getService(this,774,Intent(this,BetGuardNetworkService::class.java).setAction(ACTION_STOP),PendingIntent.FLAG_IMMUTABLE or PendingIntent.FLAG_UPDATE_CURRENT)
        val builder=if(Build.VERSION.SDK_INT>=26) Notification.Builder(this,CHANNEL) else Notification.Builder(this)
        val content="${GatewayState.clients.snapshot(System.currentTimeMillis()).size} protected clients · open BetGuard for status"
        val notification=builder.setContentTitle("BetGuard Network Protection").setContentText(content)
            .setSmallIcon(R.drawable.ic_shield).setContentIntent(open).setOngoing(true)
            .addAction(Notification.Action.Builder(null,"Stop network",stop).build()).build()
        if(Build.VERSION.SDK_INT>=34) startForeground(773,notification,ServiceInfo.FOREGROUND_SERVICE_TYPE_CONNECTED_DEVICE)
        else startForeground(773,notification)
    }
    companion object { val ACTION_STOP="${BuildConfig.APPLICATION_ID}.NETWORK_STOP"; const val CHANNEL="betguard_network" }
}
