# EAY Field Design System v1

## Principle

EAY Mobile is task-first. Field workers should not navigate the web module tree to discover work. The primary object is a **Mission**: the next bounded piece of work the verified actor may execute in the current tenant, location, shift and device context.

## Canonical mobile navigation

EAY One targets five stable destinations: **Today · Missions · Scan · Jarvis · Me**.

EAY Terminal is scanner-first and exposes only the mission families allowed for the enrolled device/runtime, such as **Pick · Count · Putaway · Receiving · Transfer**. Manager-only approvals are not surfaced merely because a screen exists.

## Mission contract

Every mission binds:

- mission id;
- tenant;
- assigned actor;
- location;
- operation key;
- runtime profile;
- state and priority;
- creation/due time;
- optional duration estimate.

The queue may rank work for UX, but ranking never grants authority. Launch always composes the mission binding with the current signed policy and Mobile Operation Admission. Wrong actor/location/runtime, terminal state, expired policy or denied operation fails closed.

## Interaction rules

- One primary action per field screen.
- Scanner-first for warehouse flows; keyboard entry is fallback, not default.
- Large touch targets and one-hand reachability.
- Status is never communicated by color alone.
- Scan success/failure uses visual plus haptic/audio feedback where device policy permits.
- Critical confirmations must identify the object and consequence, not use generic “OK”.
- Blind-count screens never reveal expected stock before the governed reconciliation phase.
- Offline state and pending sync count must be visible without exposing payload contents.
- Destructive/approval actions are online-only unless server policy explicitly defines a safer future model.

## Localization contract

Localization belongs to **Platform Core**, not to individual modules or mobile surfaces. EAY One, EAY Terminal and every module consume `config/eay_localization.json` as the shared contract.

Production parity is mandatory for **TR, EN, DE, AR, FR, ES, IT, NL, PL and PT-BR**. A new feature cannot ship to production as an English-first exception. Resource keys must remain in parity, plural forms must satisfy the locale's CLDR cardinal categories and Android lint, and RTL must be locale-driven rather than forced by feature code. Arabic is the current mandatory RTL locale.

Operational terminology must use shared glossary keys so company-specific meanings can be governed centrally instead of being translated independently inside Workforce, Inventory, Planogram, DockOS or other modules.

## Performance budgets

These are engineering targets and must be measured on the physical acceptance matrix before being called achieved:

- warm interaction response: <= 100 ms for local field feedback;
- scan-to-local-feedback: <= 100 ms target;
- no event loss across process death/reboot;
- duplicate committed business mutation: zero tolerated;
- crash-free session target: >= 99.9%;
- actionable offline queue health visible to fleet operations.

## Visual implementation

The design language is implemented as a reusable native Android UI module behind a dedicated compatibility gate. The proven Inventory terminal remains executable during migration; visual modernization may not weaken OIDC, device proof, encrypted offline state, replay protection, pinning or DataWedge behavior.
