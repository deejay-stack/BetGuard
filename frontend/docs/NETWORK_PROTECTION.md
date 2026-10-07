# Network Protection prototype

Network Protection adds an explicit HTTP/HTTPS proxy on the Android BetGuard phone. Device Protection remains its separate DNS VpnService. Joining the hotspot alone does not enable filtering: each demonstration client must use the displayed manual proxy.

## Architecture and decisions

```text
Client browser -> phone LAN HTTP proxy / HTTPS CONNECT
  -> existing Room user rule match
  -> existing FastAPI /v1/domain/check for unmatched hostnames
  -> existing BetGuardRuntime: verified list, cached model decision
  -> BLOCK: refuse before forwarding
     WARN: allow and show administrator review
     ALLOW: forward
  -> existing Room activity with Network source and client IP
```

The Python model stays on FastAPI, loaded once per server process. No model, thresholds or gambling-list changes are part of this addition. The existing Room rule matcher is reused, including its most-specific exact/subdomain rule precedence. WARN is not proof that a website is gambling. The existing baseline uses warning threshold 0.512117 and automatic block threshold 0.70.

For HTTPS, the gateway evaluates the CONNECT hostname, then relays opaque TLS bytes. It does not decrypt content or require a certificate. HTTP requests are forwarded after hostname evaluation. Shared Block/Always Allow actions use existing persistent rules; a newly matching block also closes open proxy connections to that hostname.

## Exact USB development commands

Run these in separate PowerShell terminals. Keep USB debugging authorized. The examples use the connected Android phone; only one device should be selected when running react-native.

Terminal 1 — FastAPI:

```powershell
Set-Location 'C:\Users\daniel jay bernadas\Desktop\BetGuard\betguard\backend'
.\.venv\Scripts\python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8000 --reload
```

Terminal 2 — Metro:

```powershell
Set-Location 'C:\Users\daniel jay bernadas\Desktop\BetGuard\betguard\frontend'
npm.cmd start
```

Terminal 3 — forwarding and Android app:

```powershell
Set-Location 'C:\Users\daniel jay bernadas\Desktop\BetGuard\betguard\frontend'
$env:JAVA_HOME = 'C:\Program Files\Java\jdk-21'
$env:ANDROID_HOME = "$env:LOCALAPPDATA\Android\Sdk"
& "$env:ANDROID_HOME\platform-tools\adb.exe" devices
& "$env:ANDROID_HOME\platform-tools\adb.exe" reverse tcp:8000 tcp:8000
& "$env:ANDROID_HOME\platform-tools\adb.exe" reverse tcp:8081 tcp:8081
npm.cmd run android -- --no-packager
```

For an already installed debug build, launch without rebuilding:

```powershell
& "$env:LOCALAPPDATA\Android\Sdk\platform-tools\adb.exe" shell am start -n com.betguard.dev/com.betguard.MainActivity
```

USB forwarding continues to reach the laptop backend and Metro when the laptop switches Wi-Fi. JavaScript changes use Metro reload; native changes require a new debug APK. Network clients still require internet through the Android phone.

## Hotspot first, home Wi-Fi second

1. Turn on the Android phone's hotspot and internet connection. Connect the laptop and additional phone.
2. In BetGuard, open Protection -> Network Protection. Refresh addresses, choose the hotspot interface, keep an available port, then Start.
3. Read the actual gateway host/port. Do not assume the hotspot address is 192.168.43.1.
4. Configure each client's manual proxy. On iPhone: Settings -> Wi-Fi -> information button beside the connected network -> Configure Proxy -> Manual; enter Server and Port, Authentication off, Save. On Android: edit the connected Wi-Fi network -> advanced options -> Proxy -> Manual. On Windows: Settings -> Network & internet -> Proxy -> Manual proxy; disable it after testing. A browser-specific proxy or curl `--proxy` avoids changing the whole Windows configuration.
5. Test fresh pages in a proxy-aware browser: wikipedia.org should be allowed, stake.com should be blocked, microsoft.com exercises the current warning path. Confirm actual predictions and IP in Activity; do not interpret Microsoft as a confirmed gambling site.
6. Open Network Review and Block Site for the warning. The next request from any proxy client should fail. Always Allow uses the same rule storage; Dismiss leaves the decision unchanged.
7. View devices to see actual requesting IPs, first/last activity, request/block/warning counts. This lists proxy clients, not every Wi-Fi station.
8. Hold Stop for 2.5 seconds and confirm. Set client proxies to None/Off afterward.
9. After the hotspot demonstration, connect phone and laptop to the same home Wi-Fi, refresh, start with the phone's Wi-Fi interface address, update the clients' proxy address, and repeat the tests. No router settings or credentials are needed.

Gateway address changes interrupt the session. Restart with the new address and update clients. Stopping clears protected clients and releases connections. The last session's counters remain until the next Start resets them; saved rules and history remain.

## Offline and saved APK

The gateway needs a configured decision-service address to start. While running, existing local Block rules can refuse requests even if FastAPI is unavailable. Unmatched requests fail with service unavailable rather than being silently allowed or falsely labeled as AI blocks. Allowed browsing still needs internet. Device Protection's offline rules remain separate.

The current USB debug configuration uses localhost forwarding. A standalone release APK needs a reachable HTTPS `remoteBaseUrl` in `frontend/api.config.json`, supplied by your own deployment, to offer online Smart/Network Protection. No deployment URL has been supplied. The unconfigured saved release disables online start; installing it does not deploy the backend.

To save an updated APK using the existing build script:

```powershell
Set-Location 'C:\Users\daniel jay bernadas\Desktop\BetGuard\betguard\frontend'
$env:JAVA_HOME = 'C:\Program Files\Java\jdk-21'
npm.cmd run apk:save -- -VersionName 1.4.0
```

Use `npm.cmd run apk:install -- -VersionName 1.4.0` to build and install instead. APKs use the existing development signing key and preserve BetGuard Dev data when installed as an update. Every saved APK is a snapshot and must be rebuilt after improvements.

## Prototype limits

- Explicit manual proxy, not enforced routing for all hotspot traffic. Apps that ignore proxies, direct connections, other VPNs, QUIC or alternative networks can bypass it. It does not prevent applications from opening.
- HTTPS blocks normally appear as a browser connection/proxy error; encrypted page replacement is not provided.
- Only public hostname destinations on HTTP port 80 and HTTPS CONNECT port 443. No LAN destinations, IP-literal targets, TLS interception, chunked uploads, WebSocket upgrades or non-web protocols.
- Bounded concurrent workers/tunnels target a small 5–20-device demonstration, not a campus deployment. Connection limits and 60-second idle timeouts can affect long sessions.
- No proxy authentication; listener accepts clients on the selected local subnet. Use only the intended private demo network.
- Protected-device count means a valid proxy request or open connection, retained for two minutes after last activity; counts are requests, not people or website visits.
- Model errors and false positives remain possible. WARN stays allowed until administrator action. Shared user rules apply to both protection services.
- Android may stop the service; it reports interruption when detected and does not restart silently. Port conflicts and disappearing interfaces require explicit restart.
- Some routers/hotspots isolate clients; direct LAN reachability is necessary. Home and hotspot interface addresses can differ.

Android foreground service reference: [connectedDevice service type](https://developer.android.com/develop/background-work/services/fgs/service-types).
