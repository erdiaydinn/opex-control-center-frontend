# EAY Terminal DataWedge Adapter v1

## Purpose

The existing Zebra DataWedge transport is now wired into Mobile Core Scanner Ingress rather than being a configuration-only shell.

## Session-scoped intent route

Each app process creates a 128-bit random DataWedge action/category pair and reconfigures the managed DataWedge profile to broadcast only to that session route. The receiver is registered dynamically. This reduces the attack surface of a permanently predictable exported scanner action.

This is defense in depth, not cryptographic sender authentication. Managed-device application allowlisting and physical Zebra acceptance remain required. A scan never grants authorization by itself; all resulting mission operations still pass device, policy, tenant, actor, location and server authorization gates.

## Accepted Zebra fields

The adapter consumes the documented DataWedge intent fields for:

- source;
- decoded data string;
- label/symbology type.

Only `source=scanner` enters the barcode path. Known label types are mapped to the Mobile Core symbology enum; unknown types remain UNKNOWN and are rejected by the current terminal Scanner Policy.

## Privacy

The activity never renders or logs the raw barcode in the generic scanner status. It reports only admission result and symbology. Raw values remain operational payload and are forbidden from routine telemetry.

## Production truth

Repository compilation and unit contracts do not prove DataWedge behavior on real hardware. Zebra model/OS/DataWedge-version matrix, rapid repeated scans, scanner service restart, app process restart, managed kiosk mode, battery/network stress and unexpected symbologies remain physical acceptance gates.
