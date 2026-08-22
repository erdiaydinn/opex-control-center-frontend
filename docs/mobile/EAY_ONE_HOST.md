# EAY One Android Host

EAY One is the employee/manager personal-work-phone surface of EAY Mobile. It is a **separate Android application binary** from the rugged EAY Terminal.

## Repository implementation

- Gradle application module: `android-inventory/eay-one-app`
- Application ID: `com.eay.one` (`.debug` suffix in debug builds)
- Shared UI/runtime: `:field-ui-runtime` + `mobile-presentation-contracts`
- Runtime surface: `FieldRuntimeSurface.EAY_ONE`
- Navigation: Today, Missions, Scan, Jarvis, Me through the canonical shared `EayOneShell`
- Locales at host boundary: default English plus TR, DE, AR, FR, ES, IT, NL, PL and PT-BR
- RTL: application declares `supportsRtl=true`; Arabic strings are provided by the host and shared field UI.

## Authority boundary

The host is intentionally fail-closed until the reviewed corporate identity/session composition is connected. It does **not** create a second identity, token, tenant, permission, mission or inventory authority.

Foundation host invariants:

- no `android.permission.INTERNET`;
- no AppAuth/OkHttp/Retrofit dependency;
- no Room/SQLCipher authority store;
- no synthetic mission cards;
- no locally invented tenant/location/session identity;
- presentation callbacks are intents only, not execution truth;
- server-authoritative mission/execution adapters remain the only future path to synchronized mutations.

Any future commit that adds transport or authentication to `eay-one-app` requires the dedicated brand/host contract and mobile security gates to be re-proven on that exact SHA.

## Repository acceptance

`.github/workflows/eay-brand-one-host.yml` compiles and lints the separate EAY One application, runs the cross-platform brand/login/localization contracts, builds the production web shell and retains a debug APK as repository evidence.

This is repository evidence only. It does not prove corporate OIDC, managed signing, MDM, Play Integrity/App Attest, physical-device behavior, operator UAT or production activation.

`production_activation_permitted=false`

`main_merge_permitted=false`
