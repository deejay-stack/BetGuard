# BetGuard: implementation decisions

5 September 2026 · Milestone 0/1 source implementation

1. **Name:** BetGuard is the selected product name. Earlier Anti_Gamble planning references describe this same project.
2. **Android first:** React Native 0.87.1 and TypeScript supply shared screens. Kotlin owns Android enforcement and Room data. The generated iOS project is retained, but no iOS protection implementation is included.
3. **Manual enforcement before ML:** The first prototype implements manual rules and returns unknown for gambling classification. No keyword detector, random confidence, fabricated training result, or seeded gambling verdict is substituted for the planned model.
4. **Narrow network experiment:** A local VpnService receives only packets for a virtual DNS resolver. This avoids requiring an unimplemented full-IP forwarding engine. It still requires physical-device evidence and does not fulfill universal domain blocking.
5. **DNS provider:** This feasibility build uses Cloudflare's `1.1.1.1` over ordinary UDP DNS. The enabling dialog and Settings disclose that unblocked DNS questions leave the phone for that resolver. Resolver selection, encrypted upstream DNS, IPv6-only support, and TCP fallback are later design work.
6. **Manual precedence:** One current allow/block rule per normalized hostname. A more specific matching hostname wins over an ancestor's subdomain rule. Removing an override exposes the next applicable rule. Rule changes and the final response decision share a repository lock.
7. **Honest status:** Native service state drives the UI through a TurboModule event. A saved rule is not itself an enforcement event. NXDOMAIN is logged only after the corresponding response is written to the tunnel. That is evidence of a DNS action, not a browser-page result.
8. **Persistence:** Room stores rules and the latest 200 local history entries. No cloud backup of this data is enabled. Rules persist across process restarts; protection does not automatically restart. Android can revoke or stop the VPN.
9. **Backend decision retained:** PostgreSQL + SQLAlchemy remains the final backend choice, with FastAPI and scikit-learn. No backend is required to prove manual DNS filtering, so it is not scaffolded into this milestone. This avoids an unused temporary server database. Backend implementation follows the filtering and dataset gates.
10. **Next model work:** Audit actual website/domain data, license, labels, duplication and split groups; compare Logistic Regression, SVM and Random Forest. Deploy one evaluated pipeline and integrate the agreed unknown/timeout policy without changing manual precedence.

## Source references

- [React Native Community CLI setup](https://reactnative.dev/docs/getting-started-without-a-framework)
- [Turbo Native Module specification and Codegen](https://reactnative.dev/docs/turbo-native-modules-introduction)
- [React Navigation Android configuration](https://reactnavigation.org/docs/getting-started/)
- [Android VpnService development](https://developer.android.com/develop/connectivity/vpn)
- [Foreground-service types and VPN eligibility](https://developer.android.com/develop/background-work/services/fgs/service-types)
- [Room 2.8.4](https://developer.android.com/jetpack/androidx/releases/room)

Exact JavaScript dependency versions are recorded in `package-lock.json`. Android SDK/NDK/Kotlin and Gradle wrapper versions come from the generated React Native template; additional Room and KSP versions are pinned in Gradle. Source checks do not prove that every native dependency combination builds; the Android build gate remains required.
