# Test Smart protection on a USB-connected Android phone

Smart protection already applies the server's `BLOCK` result automatically to new supported DNS requests. You do not need to add every gambling domain manually. The decision order is: matching local Block/Allow rule, verified gambling blocklist, then the trained hostname model. A local Allow overrides automatic detection. `WARN` remains allowed; you can save a Block rule if you want to restrict that hostname too.

The current policy blocks an unmatched domain when its ML score is at least `0.70`; scores from `0.512117` up to `0.70` produce a warning. These are policy thresholds, not a guarantee of accuracy. A hostname score is not proof about webpage content, and this model does not classify app descriptions.

## Terminal 1: backend

```powershell
Set-Location 'C:\Users\daniel jay bernadas\Desktop\BetGuard\betguard\backend'
.\.venv\Scripts\python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8000 --reload --no-access-log
```

Keep this terminal running. The server loads the existing trained model and blocklist; no separate ML server or retraining is required.

## Terminal 2: Metro

```powershell
Set-Location 'C:\Users\daniel jay bernadas\Desktop\BetGuard\betguard\frontend'
npm.cmd start
```

## Terminal 3: phone connection and development app

Unlock the phone and accept USB debugging if prompted. `adb devices` must report `device`, not `unauthorized` or `offline`.

```powershell
Set-Location 'C:\Users\daniel jay bernadas\Desktop\BetGuard\betguard\frontend'
$env:JAVA_HOME = 'C:\Program Files\Java\jdk-21'
$env:ANDROID_HOME = Join-Path $env:LOCALAPPDATA 'Android\Sdk'
$env:PATH = "$env:ANDROID_HOME\platform-tools;$env:JAVA_HOME\bin;$env:PATH"
adb devices
adb reverse tcp:8000 tcp:8000
adb reverse tcp:8081 tcp:8081
npm.cmd run android -- --no-packager
```

Use **BetGuard Dev**. The current development configuration connects through USB to `http://127.0.0.1:8000`. Reapply the two reverse commands after reconnecting USB. A saved release APK does not use Metro or automatically connect to this PC; Smart mode in that APK needs a configured reachable HTTPS backend.

## Terminal 4: test the running server

```powershell
Set-Location 'C:\Users\daniel jay bernadas\Desktop\BetGuard\betguard\frontend'
powershell -NoProfile -ExecutionPolicy Bypass -File scripts/test-smart-protection.ps1
```

The script calls `/health/detection` and `/v1/domain/check-batch`, checks the current frozen model's expected decisions, and prints a table. It does not open gambling websites, alter saved rules, or train a model. A deliberate model/blocklist change can require reviewed changes to these expected regression cases.

| Hostname | Expected decision | Expected source | Current score |
| --- | --- | --- | --- |
| `stake.com` | BLOCK | `verified_gambling_blocklist` | Not used |
| `casino.fanatics.com` | BLOCK | `ml_high_risk` | 0.833413 |
| `wikipedia.org` | ALLOW | `ml_low_risk` | 0.203321 |
| `microsoft.com` | ALLOW + WARN | `ml_warning` | 0.583148 |

`microsoft.com` is a useful example of an uncertain model warning, not a claim that Microsoft is gambling. `stake.com` demonstrates list enforcement; `casino.fanatics.com` demonstrates the ML path because it has no matching blocklist entry in the current deployed list. A manual rule for either hostname would prevent this from being a clean automatic-detection test.

To inspect one full result:

```powershell
$body = @{ domain = 'casino.fanatics.com' } | ConvertTo-Json
Invoke-RestMethod 'http://127.0.0.1:8000/v1/domain/check' -Method Post -ContentType 'application/json' -Body $body | ConvertTo-Json -Depth 5
```

## Test actual protection on the phone

1. In **Protection**, check whether a rule matches your test hostname or its parent. A matching local Block proves manual enforcement; a matching Allow intentionally bypasses automatic detection. Use a hostname without an override to test Smart mode.
2. On **Home**, pause the current filter, select **Smart protection**, and tap **Enable protection**. Approve Android's VPN request if needed. Confirm **Protected**, **SMART MODE**, and the text mentioning smart detection. Keep the backend and USB connection available.
3. In **Check a link**, check `casino.fanatics.com`. Open **Show technical details** and confirm `ml_high_risk` and the ML score. This checks classification; it does not prove traffic was blocked.
4. Run the following in Terminal 4. It restarts Chrome and supplies a fresh URL so Chrome does not simply restore the previously loaded page:

```powershell
$adbPath = Join-Path $env:LOCALAPPDATA 'Android\Sdk\platform-tools\adb.exe'
$testId = [DateTimeOffset]::UtcNow.ToUnixTimeMilliseconds()
& $adbPath shell am force-stop com.android.chrome
& $adbPath shell am start -a android.intent.action.VIEW -d "https://casino.fanatics.com/?betguard_test=$testId" -p com.android.chrome
```

5. Expect a browser DNS error. In BetGuard **Activity**, find a **new** Blocked event for `casino.fanatics.com`. Its detail must mention `ml_high_risk`; a manual rule event or an online-service error is not proof of automatic ML blocking.
6. Repeat with `stake.com`, replacing the hostname in the browser command. Expect a new automatic Blocked event mentioning `verified_gambling_blocklist`.
7. Open `https://wikipedia.org` in a fresh browser request and confirm allowed requests in Activity. Website redirects can generate additional hostname decisions; inspect the exact hostname in each event. For the WARN case, use Check a link on `microsoft.com`; WARN must keep `enforcement_action=ALLOW`. A network request handled for that exact hostname should appear as a warning, provided the upstream resolver succeeds.

If a site still appears, distinguish a restored/cached page from a fresh network request. This filter only handles new IPv4 UDP DNS through its virtual resolver; encrypted/custom DNS, cached addresses, direct IP traffic and existing connections can bypass it. Browser errors alone can also indicate ordinary connection problems. Use the matching timestamp, hostname and decision source in Activity as evidence.

## Verify service failure separately

In a controlled test, stop only the backend with Ctrl+C in Terminal 1 while leaving Smart mode on. Make a new unmatched hostname request. Expected: an online-detection error/SERVFAIL and attention status, not an AI Block decision. A matching local rule still takes priority. Restart Terminal 1 to recover; if you want filtering without the backend, pause protection and choose On-device rules. Server request counters can help show requests arrived, but background apps and link checks also increment them, so counts do not identify a specific website visit.

## What was verified on the connected phone

On October 7, 2026, the live backend returned all four expected results above. With Smart mode enabled and no local rules for the four test hostnames, direct DNS requests returned NXDOMAIN for `stake.com` and `casino.fanatics.com`, normal DNS answers for `wikipedia.org` and `microsoft.com`, and matching Activity records for automatic list Block, automatic ML Block, Allow, and WARN. Chrome's fresh `casino.fanatics.com` request displayed `DNS_PROBE_FINISHED_NXDOMAIN`. Existing saved rules were preserved.

This verifies these enforcement cases through the running app and server. It does not establish perfect gambling detection or universal browser coverage. Measure model quality separately using the frozen held-out results and reviewed real examples, as described in the [capstone alignment report](../../docs/CAPSTONE_ALIGNMENT.md).
