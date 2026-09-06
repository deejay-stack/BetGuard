# BetGuard: verification record

6 September 2026 · Source package version 0.1.0

| Check | Result | Practical limit |
| --- | --- | --- |
| TypeScript `tsc --noEmit` | Passed | Type compatibility, not a native Android build |
| ESLint | Passed after configuring Jest globals | Static JavaScript/TypeScript checks |
| React Native UI test | Passed: all five tabs render; unavailable native protection is not reported as active | React test renderer, not visual/device QA |
| Native policy and DNS packet scenarios | 13 passed, including 5,000 malformed-packet samples | Actual Android-independent Kotlin sources compiled and executed on the JVM |
| React Native Codegen | Android bridge generated, including the module's configured Java package | Generation only; Android app compilation remains pending |
| Metro Android release-mode JS bundle | Successfully generated | JavaScript bundle only, not an APK |
| Manifest and package-lock consistency | Checked | Does not resolve every native build dependency |
| APK build, install, and first launch | Not run: no Android SDK or connected device in this environment | Required on the developer workstation |
| Room persistence, VPN permission, foreground lifecycle, routing and browser blocking | Not tested on Android | Required before closing M1 |
| Wi-Fi/mobile transition, IPv6-only behavior and DNS bypass cases | Not tested on device | No coverage or timing claims made |
| Dataset/model training, backend, PostgreSQL deployment and iOS enforcement | Not implemented in this milestone | Subsequent work |

## Environment used for source checks

- React Native 0.87.1; React 19.2.3; Community CLI 20.2.0.
- Node 24.19.0; npm 11.9.0.
- Java 17.0.20 runtime; standalone Kotlin compiler 2.2.0 for the pure core tests.
- The actual test sources are `tests/native/CoreTests.kt` and the Kotlin files in `android/app/src/main/java/com/betguard/filter/core`.
- No Android SDK, adb, Android emulator, attached phone, or full Android Gradle build was available.

The standalone Kotlin test invocation compiled the production core files with the matching Kotlin compiler and then executed `com.betguard.tests.CoreTestsKt`. The Android Gradle test target includes the same test source through `NativeCoreTest`; running that Gradle target on the workstation is still pending.

Metro reported a dependency warning about a private React Native feature-flag import and completed bundling. Keep native dependency/build compatibility under review during the first Android build. Do not interpret the generated bundle as proof of successful installation or routing.

## Required follow-up

Use `docs/ANDROID_ACCEPTANCE.md` and record actual results. Keep M0 open until the app launches; keep M1 open until the external-browser and lifecycle evidence is collected. The native service source is an implementation candidate for that experiment, not a verified release.
