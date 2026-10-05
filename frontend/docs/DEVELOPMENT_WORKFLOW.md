# BetGuard development and stable milestones

Run mobile commands from `betguard/frontend`; Python commands from `betguard/backend`. The checked-in project is bare React Native with custom native Android code and EAS configuration. Do not run Expo prebuild or replace native directories.

## Two Android installations

| Build profile | Android task | Installed name / ID | JavaScript |
| --- | --- | --- | --- |
| development | `:app:assembleDevelopmentDebug` | BetGuard Dev / `com.betguard.dev` | Metro; existing React Native debug client |
| preview | `:app:assembleProductionRelease` | BetGuard / `com.betguard` | Bundled in an installable APK |
| production | `:app:bundleProductionRelease` | BetGuard / `com.betguard` | Bundled in a store-oriented AAB |

The existing stable ID, Kotlin namespace and React component name remain intact. Only the development flavor has the `.dev` application ID and launcher-name override. Preview and production intentionally update the same stable application; they are not a third separate installation. Each application ID has separate Room data, settings and permissions. Existing stable data is not copied to Dev.

The development profile selects a Gradle debug task directly. It does not enable EAS's `developmentClient` flag: that flag expects installed/configured `expo-dev-client`, which this bare project does not contain. Metro, Fast Refresh and the native React Native developer menu remain the active coding workflow. Adding Expo's launcher would be a separate native dependency migration, not a prerequisite for these two installations. See [EAS profile reference](https://docs.expo.dev/eas/json/) and [existing React Native variants](https://docs.expo.dev/build-reference/variants/).

The VPN service, notifications and explicit PendingIntents remain inside each app. Stop actions use the current application ID. There are no shared providers, authorities, deep links or shared UID declarations to collide. Both apps can be installed, but [Android permits only one active VPN per user/profile](https://developer.android.com/develop/connectivity/vpn). Enabling one can revoke the other's VPN; verify the native status in each app. Never treat two installed apps as two simultaneous filters.

## Active USB development

1. Use a debug APK built from the **development** profile. `npm.cmd run android` now builds/launches `developmentDebug` with `--appId com.betguard.dev`; it does not target the stable package.
2. Start FastAPI from `backend`, preserving the existing private `.env`:

```powershell
.venv\Scripts\python -m uvicorn app.main:app --host 127.0.0.1 --port 8000 --reload --no-access-log
```

3. In `frontend/api.config.json`, keep `developmentTarget` as `device`. Start Metro from `frontend`:

```powershell
npm.cmd start
```

4. With USB debugging authorized, use another terminal:

```powershell
adb devices
adb reverse tcp:8000 tcp:8000
adb reverse tcp:8081 tcp:8081
```

5. Open BetGuard Dev. Check process/database health, reviewed catalog behavior and manual rules with FastAPI stopped. Reapply **adb reverse after disconnecting/reconnecting**; port mappings are temporary.

For an emulator, set `developmentTarget` to `emulator` and reload Metro. It selects `http://10.0.2.2:8000`. Device selects `http://127.0.0.1:8000`. Select `remote` only when `remoteBaseUrl` is configured with an actual HTTPS endpoint.

## Save a stable milestone

Use `main` for accepted stable states, `develop` for active integration, and `feature/*` for isolated work. Review/merge a tested feature into develop, then main using your normal Git process. No branches, commits, tags or pushes were created automatically by this refactor.

From the **repository root**, after checks and review:

```powershell
git status --short
git diff --stat
git add .
git diff --cached --stat
# Review staged content for secrets and unintended files before committing.
git commit -m "Stable BetGuard database integration"
git tag v0.2-database
```

The message/tag are examples for the applicable milestone; choose a new tag for each accepted state and do not move an existing tag. Never stage `.env`, certificates, credentials, datasets, model checkpoints, virtual environments or caches. `.gitignore` is a guard, not a replacement for staged-content review. Run npm in frontend, not the repository root; FastAPI does not need the Supabase JavaScript SDK.

From **frontend**, after choosing your existing EAS account/project and signing credentials:

```powershell
npx.cmd eas-cli build --platform android --profile development
npx.cmd eas-cli build --platform android --profile preview
npx.cmd eas-cli build --platform android --profile production
```

These are alternatives for the artifact you need, not instructions to submit all three every time. EAS runs remotely and may require account access/build quota. The existing project ID, remote app-version setting and production autoIncrement are preserved. No cloud build or signing-credential generation was performed here. See [EAS APK builds](https://docs.expo.dev/build-reference/apk/).

Download your preview APK and retain a copy named for its Git tag. Replace these example filenames with the downloaded APK paths:

```powershell
adb install -r .\BetGuard-preview.apk
adb install -r .\BetGuard-dev.apk
adb shell pm list packages com.betguard
```

Preview should be `com.betguard`; Dev should be `com.betguard.dev`. Verify labels, local data independence and both launches. Reinstalling Dev must leave stable rules/history intact. Only after that acceptance should you rely on the saved milestone.

**Signing:** existing Gradle signing configuration and keystore bytes were preserved. The current local release configuration still references the existing debug signing config. The production profile produces an AAB, but store release/signing readiness has not been established. Reuse the approved existing stable signing identity through your EAS/release process; do not generate a replacement or uninstall the stable app to bypass a signature mismatch. An update requires a compatible signing identity and version code. Changing signing credentials is outside this refactor.

## Disconnect and resume

A preview APK bundles JavaScript and does not require Metro or USB. Manual blocking, Room rules, local history and settings remain available without FastAPI. Protection still requires Android VPN consent and enabling it; existing DNS coverage/bypass limitations remain.

Preview/production use only `remoteBaseUrl` from `api.config.json`, and accept HTTPS. They never fall back to the development PC or emulator. If no remote FastAPI deployment exists, leave it empty: Check Link clearly reports unconfigured and local actions still work. A local PC URL does not become remotely reachable merely by building a preview APK.

Later reconnect USB, restart FastAPI/Metro, repeat adb reverse, and open **BetGuard Dev**. The saved stable package remains separate. JavaScript changes can use Metro reload in Dev; native flavor/bridge/resource changes require a new Dev APK. Any preview/production JavaScript or API-address change needs a new bundled artifact. Backend environment changes require a backend restart only.

## Verification and prerequisites

```powershell
# In frontend
npm.cmd run typecheck
npm.cmd run lint
npm.cmd test -- --runInBand --testTimeout=20000
cd android
.\gradlew.bat :app:testDevelopmentDebugUnitTest :app:assembleDevelopmentDebug
.\gradlew.bat :app:assembleProductionRelease
```

Install the project's pinned Android API 37, Build-Tools 37.0.0 and NDK 27.1.12297006 plus a compatible JDK before local APK builds. This workstation lacks those components; the build currently stops at NDK configuration (AGP additionally reports preferred NDK 28.2.13676358). Resolve the actual SDK/NDK setup rather than changing project versions to hide the failure.

On-device coexistence, fresh Dev/preview launches, USB disconnection, native VPN consent, actual browser block/allow/remove-override and stable-data preservation remain acceptance steps in [Android acceptance](ANDROID_ACCEPTANCE.md). Software tests and declared IDs do not prove those physical-device outcomes. See [the exact refactor verification record](../../backend/docs/REFACTOR_REPORT.md).
