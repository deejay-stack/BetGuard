# BetGuard frontend

React Native + TypeScript with Kotlin VPN/DNS filtering and Room storage on Android. Screens, themes, branding, navigation and manual controls are preserved. The iOS directory is the existing template; iOS filtering is not implemented.

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

## Run on Windows

Run commands from this frontend directory. Use Node 22.11 or newer and a compatible full JDK. Android's configured toolchain requires API 37, Build-Tools 37.0.0 and NDK 27.1.12297006. Open this folder's android directory in Android Studio; set ANDROID_HOME and JAVA_HOME to your actual installations.

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

```powershell
adb devices
adb reverse tcp:8000 tcp:8000
adb reverse tcp:8081 tcp:8081
```

Check Link sends an explicitly checked hostname to FastAPI and shows the existing
reviewed-catalog result plus the independent finalized detector's ALLOW/WARN/BLOCK
decision. It never changes a saved rule automatically. Block, Allow and Remove
Override remain local, user-controlled operations.

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

The VPN experiment handles IPv4 UDP DNS directed to 10.77.0.2:53. Blocked questions receive NXDOMAIN; allowed questions use 1.1.1.1 through a protected socket. Encrypted/private DNS, arbitrary external resolvers, TCP DNS, direct IPs, cached answers and existing connections can bypass it. IPv6-only networks and captive portals require further work. This is not universal or tamper-proof protection.
