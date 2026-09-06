# BetGuard: development started

6 September 2026 · First Android feasibility source package

## Delivered in source

- Official React Native 0.87.1 TypeScript project with locked JavaScript dependencies.
- Home, Check Link, Sites, History, and Settings screens with shared styling and navigation.
- Kotlin Turbo Native Module for user commands and native status events.
- Room/SQLite schema and repository for manual allow/block rules and bounded local history.
- IPv4 UDP DNS filtering service source with VPN permission handling, foreground notification/Stop, network-change observation, and explicit failure states.
- Hostname validation and most-specific manual-rule precedence.
- Unknown classification until a trained model is integrated; no fabricated predictions or seeded gambling labels.
- Kotlin regression scenarios, Windows setup instructions, implementation decisions, and an Android acceptance checklist.

## What was verified

TypeScript, JavaScript lint, and a React UI rendering/unsupported-state test passed. Thirteen native core scenarios passed, including 5,000 malformed-packet samples. React Native generated the native bridge and Metro produced an Android JavaScript bundle.

These checks do **not** establish that the APK builds or that a browser request is blocked. This environment has no Android SDK or connected phone. Room, VPN lifecycle, real routing, visual layout, network transitions, and native dependency compatibility still need a workstation/device run.

## First action on the workstation

Extract `BetGuard_Milestone_1_Source.zip`, open its `betguard` folder in VS Code, and follow `README.md`. With the Android SDK/JDK installed and a phone/emulator available, run `npm ci`, start Metro with `npm start`, then run `npm run android` in a second terminal.

The acceptance demonstration is: reach a harmless test domain and a control domain; enable filtering; block the test hostname; make a fresh covered DNS request in an external browser; confirm the control remains reachable; allow the test hostname and verify restored access. Record actual outcomes and DNS/browser configuration.

## Remaining milestones

1. Complete the Android build/launch and filtering feasibility gates.
2. Audit the actual labeled website dataset.
3. Compare Logistic Regression, SVM, and Random Forest with grouped held-out evaluation.
4. Implement FastAPI and PostgreSQL, then integrate the selected classifier while preserving manual rules.
5. Complete device/network testing, UAT, deployment, and handover evidence.

PostgreSQL remains the final server database choice. Room/SQLite is the permanent phone database. No server deployment, trained model, or iOS filtering implementation has been created in this first milestone.
