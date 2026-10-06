# BetGuard frontend

Start with the [plain-language app, architecture and APK guide](docs/APP_GUIDE.md). Home now offers visible On-device rules / Smart protection choices and an expandable quick guide. Use `npm.cmd run apk:save` to save each improvement or `npm.cmd run apk:install` to rebuild and update the connected BetGuard Dev installation while retaining its data.

React Native + TypeScript with Kotlin VPN/DNS filtering and Room storage on Android. Five tabs provide Home, Check link, Rules, Activity and Settings, with persisted System/Light/Dark appearance. The iOS directory is the existing template; iOS filtering is not implemented.

## Main files

| Path | Purpose |
| --- | --- |
| App.tsx, src/screens/ | Navigation and five screens |
| src/components/, src/theme.ts | Shared controls, branding and themes |
| src/state/ | Native state, manual rules and appearance |
| src/api/, api.config.json | FastAPI client and public API base URL |
| specs/ | Native bridge contract |
| android/ | Kotlin VPN, Room, resources and Gradle build |
| ios/ | iOS template and CocoaPods configuration |
| __tests__/, tests/native/ | Mobile and Kotlin core regression tests |
| docs/ANDROID_ACCEPTANCE.md | Physical-device verification checklist |

See [development and stable milestone workflow](docs/DEVELOPMENT_WORKFLOW.md) for the two Android installations, build profiles, signing limits and Git workflow.

See [Android repair and physical-device results](docs/ANDROID_REPAIR_REPORT.md) for the October 2026 bridge repair, VPN shutdown fix, complete change list and tested limitations.

## Run on Windows

Run commands from this frontend directory. Use Node 22.11 or newer and a compatible full JDK (JDK 21 was verified). Android's configured toolchain uses API 36, Build-Tools 36.1.0 and NDK 27.3.13750724. Open this folder's android directory in Android Studio; set ANDROID_HOME to the SDK directory and JAVA_HOME to the JDK directory, without a trailing bin. The Windows Gradle configuration also handles Clang short paths and long CMake object paths.

```powershell
npm.cmd ci
npm.cmd start
```

Keep Metro running. In another frontend terminal:

```powershell
npm.cmd run android
```

For an existing installed debug APK, restart Metro after the folder move with `npm.cmd start -- --reset-cache`. Install a new development APK to obtain the com.betguard.dev identity and BetGuard Dev launcher label. Later JS-only changes use Metro reload. Changes to native code/bridge methods require a rebuilt APK; a release APK bundles JavaScript and requires rebuilding for UI or API-address changes. Do not uninstall merely to refresh development code: that erases local data.

EAS configuration lives here too. Run `npx.cmd eas-cli build --platform android --profile development` from this directory when choosing a cloud build. This app uses a custom native module; Expo Go cannot run its filtering service. On macOS, run CocoaPods in ios before iOS development.

## Backend and USB

In api.config.json, select developmentTarget as device, emulator or remote. Set remoteBaseUrl to a real HTTPS FastAPI endpoint when deployed; preview/production use only that field and report unconfigured when it is empty. Never put database credentials or Supabase keys in the mobile app. See [backend setup](../backend/docs/database/SUPABASE_SETUP.md).

The backend is an API, not the mobile screen. Its root URL may return `{"detail":"Not Found"}` because no `/` route is registered. Open `http://127.0.0.1:8000/docs` for API documentation or `/health/detection` for detector readiness; launch BetGuard Dev on the phone for the UI.

```powershell
adb devices
adb reverse tcp:8000 tcp:8000
adb reverse tcp:8081 tcp:8081
```

Check Link sends an explicitly checked hostname to FastAPI and shows the existing
reviewed-catalog result plus the independent finalized detector's ALLOW/WARN/BLOCK
decision. It never changes a saved rule automatically. Block, Allow and Remove
Override remain local, user-controlled operations.

WARN means the website stays allowed. Go back returns Home; Continue once opens the normalized hostname without saving a rule; Always allow and Block site save existing Room rules. Catalog failure does not hide a successful detector response. Dashboard counters describe actual retained DNS activity, not the number of link checks.

Enable protection offers manual rules only or optional online detection. Online
mode sends unmatched DNS hostnames to the same API. Manual Room rules take
priority; BLOCK uses the existing NXDOMAIN workflow, WARN forwards DNS and records
an uncertain warning in History, and ALLOW forwards normally. In online mode a
503, timeout or invalid detection response returns SERVFAIL and a degraded status;
it never fabricates an ALLOW/BLOCK decision. Manual mode remains independent of
FastAPI. Rules and history are not uploaded. Hostnames in online requests can be
observed by the API operator; URL paths, credentials and queries are never sent.

Native API calls use the existing public API address passed from src/api/config.ts
and bind to a non-VPN network to avoid recursive API-hostname DNS checks. Changes
to the native bridge/VPN require rebuilding the Android APK. Production still
requires the configured HTTPS remoteBaseUrl; USB development uses adb reverse.

## Checks

```powershell
npm.cmd run typecheck
npm.cmd run lint
npm.cmd test -- --runInBand --testTimeout=20000
cd android
.\gradlew.bat :app:testDevelopmentDebugUnitTest :app:assembleDevelopmentDebug
.\gradlew.bat :app:assembleProductionRelease
```

The native target uses tests/native/CoreTests.kt. Unit tests and successful bundling do not establish VPN routing, Room persistence or physical layout. Complete [Android acceptance](docs/ANDROID_ACCEPTANCE.md), including both themes and manual controls with FastAPI stopped.

## Filtering scope

Manual rules use normalized hostnames. The most specific matching rule wins; removing an override exposes the parent rule or default Allow. Room stores rules and the latest 200 history events. Rules persist, but protection must be enabled again after process termination/reboot.

When online detection is enabled, removing the last matching manual override exposes online detection instead of default Allow. The JavaScript/native bridge requires version 2 and checks required methods before enabling native actions; an older installed APK needs a rebuilt APK. Stop explicitly closes the VPN interface before stopping the Android service.

## Save an app on the phone

From android, build a bundled preview with `.\gradlew.bat :app:assembleDevelopmentRelease -PreactNativeArchitectures=arm64-v8a`. The APK is `android/app/build/outputs/apk/development/release/app-development-release.apk`; it installs as BetGuard Dev and runs without Metro. The arm64 target matches the tested RMX3710. Omit the architecture option for other supported architectures.

For each improvement, run `npm.cmd run apk:save` or `npm.cmd run apk:install`. The newest bundled copy is `build/apk/BetGuard-latest.apk`, with a versioned copy and checksum alongside it. The install command also saves the versioned APK in the phone's Download folder. The UI and Android build share `app.version.json`; each packaged build increments its build number. Release builds require remoteBaseUrl to use online checks away from the PC. With its current empty value, the bundled app supports on-device rules and clearly reports smart checks as unconfigured. Configure a deployed HTTPS backend and rebuild to enable independent mobile online checks.

Install updates with `adb install -r <apk-path>` using the same signing key. The older com.betguard installation on the tested phone has a different signing certificate from this project's debug.keystore. It was preserved; BetGuard Dev was installed separately. The preview uses the existing development signing key and is intended for testing. A store release needs your own release signing configuration.

The VPN experiment handles IPv4 UDP DNS directed to 10.77.0.2:53. Blocked questions receive NXDOMAIN; allowed questions use 1.1.1.1 through a protected socket. Encrypted/private DNS, arbitrary external resolvers, TCP DNS, direct IPs, cached answers and existing connections can bypass it. IPv6-only networks and captive portals require further work. This is not universal or tamper-proof protection.
