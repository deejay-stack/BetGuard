# BetGuard

A mobile capstone for detecting and blocking gambling websites, with user-controlled rules.

**Current delivery: first Android feasibility source package.** Five React Native screens connect to Kotlin rule storage and a DNS filtering service. Manual rules are implemented in source. Gambling classification remains explicitly unknown until a real model is trained and connected. There is no trained model, FastAPI server, PostgreSQL deployment, or verified APK in this package.

## Start on Windows

1. Extract the package and open the `betguard` folder in VS Code.
2. Install Node.js satisfying `package.json` (22.11 or newer) and a full JDK 17 compatible with the Android build tooling. Confirm `node --version` and `javac -version` in the terminal. The source checks here used Node 24.19.0 and Java 17.
3. Install Android Studio and use SDK Manager to install the SDK Platform **37**, Build-Tools **37.0.0**, Platform-Tools, Command-line Tools, and NDK **27.1.12297006**, matching `android/build.gradle`. Set `ANDROID_HOME` to the actual SDK directory and add its `platform-tools` directory to PATH. Set `JAVA_HOME` to your installed JDK. Restart VS Code after changing environment variables. Open `android` in Android Studio to resolve any additional native build components the template requests.
4. On a physical Android phone, enable Developer options and USB debugging. Connect it by USB and accept its debugging prompt. `adb devices` should list it as `device`. An emulator can support initial launch testing. The minimum configured Android API is 24; physical Wi-Fi/mobile switching needs a real phone.
5. In the project root, install the locked dependencies and start Metro:

```powershell
npm ci
npm start
```

6. Keep that terminal running. In a second terminal in the same project root:

```powershell
npm run android
```

On a USB-connected phone, if Metro is not reachable, run `adb reverse tcp:8081 tcp:8081` and reload. If Gradle cannot find the SDK, check `ANDROID_HOME` or let Android Studio create your machine-specific `android/local.properties`; do not commit that file.

This project uses a custom native module, so run its Android build. Expo Go cannot execute this native service. The generated iOS project does not implement filtering.

## First app walkthrough

- **Home:** see native status, enable DNS protection with Android consent, or stop it.
- **Sites:** add `example.com` as a harmless manual test block. Choose exact-host or subdomain scope; allow it again or return to automatic policy.
- **Check link:** validate a hostname and inspect the effective manual rule. The classification stays unknown.
- **History:** inspect saved-rule events separately from DNS responses, policy blocks, resolver failures, and service state changes.
- **Settings:** review coverage, resolver disclosure, and clear local history while preserving rules.

Follow [the Android acceptance checklist](docs/ANDROID_ACCEPTANCE.md) before claiming that blocking works. Test in an external browser, with a fresh supported DNS request, and compare a blocked domain against a reachable control.

## Coverage of this experiment

The local VPN routes only IPv4 UDP DNS packets to `10.77.0.2:53`. Matching blocked questions receive NXDOMAIN; allowed questions go to `1.1.1.1` through a protected socket. Upstream failures return SERVFAIL and produce a degraded status. No website content is intercepted or decrypted.

Encrypted DNS, arbitrary external DNS servers, TCP DNS fallback, IP-only connections, browser caches and existing connections are outside this prototype. IPv6-only networks, captive portals, and networks that block the resolver need further work. Other devices sharing Wi-Fi are unaffected. Rules persist, but protection requires enabling again after process termination/reboot. Never describe this build as universal or tamper-proof protection.

## Project map

| Path | Purpose |
| --- | --- |
| `App.tsx`, `src/screens` | Five tabs and screen components |
| `src/components`, `src/theme.ts` | Shared controls and visual styling |
| `src/state` | Native snapshot subscription and UI commands |
| `specs/NativeBetGuard.ts` | Turbo Native Module contract |
| `android/app/src/main/java/com/betguard/filter` | Room database, repository, module, VPN service |
| `android/app/src/main/java/com/betguard/filter/core` | Android-independent hostname policy and DNS packet code |
| `tests/native` | Native policy/packet regression scenarios |
| `docs` | Decisions, device acceptance, verification record |

## Verification commands

```powershell
npm run typecheck
npm run lint
npm test -- --runInBand
```

With the Android SDK and full JDK available:

```powershell
cd android
.\gradlew.bat testDebugUnitTest
.\gradlew.bat assembleDebug
```

The native test target calls the same Kotlin policy and DNS code used by the service. Its scenarios include hostname normalization, manual precedence, malformed packet rejection, resolver-response correlation, and response checksums. It does not replace device tests for Room, permissions, lifecycle, routing, browser behavior, or network transitions.

See [verification status](docs/VERIFICATION.md) for what actually ran in the source-development environment.

## Next SDLC gate

First build and launch on an Android device. Then prove blocked/control/unblocked requests, persistence, permission revocation, and network switching. Record gaps before integrating the gambling classifier. PostgreSQL remains the selected backend database for the subsequent FastAPI/model milestone.

The React Native template includes a standard debug signing key for development; this is not a production signing identity. Source is private by default. Agree ownership and third-party license obligations before release; dependency licenses remain with their authors.
