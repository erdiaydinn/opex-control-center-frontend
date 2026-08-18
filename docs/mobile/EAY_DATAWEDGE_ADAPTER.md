# EAY Terminal DataWedge Adapter v2

## Purpose

The existing Zebra DataWedge transport is wired into Mobile Core Scanner Ingress rather than remaining a configuration-only shell.

## Session-scoped intent route

Each app process creates a 128-bit random DataWedge action/category pair and reconfigures the managed DataWedge profile to broadcast only to that session route. The receiver is registered dynamically. This removes a permanently predictable scanner action from the normal execution path.

## Secure intent destination

The adapter computes the installed EAY APK signing-certificate SHA-1 identity locally and configures DataWedge `intent_component_info` with both package name and signing signature. For certificate rotation, all Android signing-history entries visible to the running app are supplied. This follows Zebra's secure Intent Output contract and makes package-name impersonation insufficient for DataWedge delivery.

This is still defense in depth, not operation authorization. A scan never grants permission to mutate inventory or attendance.

## DataWedge API control is an MDM gate

The application cannot safely self-assert that it is the only app permitted to reconfigure DataWedge. Production MDM/StageNow/ZDM must place DataWedge configuration APIs in controlled mode and whitelist the EAY package/signature. Until managed-device evidence proves this setting on the supported Zebra fleet, production readiness remains false.

## Accepted Zebra fields

The adapter consumes the documented DataWedge intent fields for:

- `com.symbol.datawedge.source`;
- `com.symbol.datawedge.data_string`;
- `com.symbol.datawedge.label_type`.

Only `source=scanner` enters the barcode path. Known label types are mapped to the Mobile Core symbology enum; unknown types remain UNKNOWN and are rejected by the current terminal Scanner Policy.

## Privacy

The activity never renders or logs the raw barcode in the generic scanner status. It reports only admission result and symbology. Raw values remain operational payload and are forbidden from routine telemetry.

## Production truth

Repository compilation and unit contracts do not prove DataWedge behavior on real hardware. Zebra model/OS/DataWedge-version matrix, secure component delivery, controlled DataWedge API configuration, rapid repeated scans, scanner service restart, app process restart, managed kiosk mode, battery/network stress and unexpected symbologies remain physical acceptance gates.
