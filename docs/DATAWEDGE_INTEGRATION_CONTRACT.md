# OPEX Inventory V21 — DataWedge Integration Contract

V21 keeps keyboard-wedge scanning for browsers and adds a stable native bridge
contract for Zebra DataWedge or an Android shell.

## DataWedge profile

- Profile: `OPEX_INVENTORY`
- Intent action: `com.opex.inventory.SCAN`
- Category: `android.intent.category.DEFAULT`
- Delivery: Broadcast
- Enabled decoders: EAN-8, EAN-13, Code 128, GS1 DataBar, QR, UPC-A, UPC-E
- Minimum validated DataWedge baseline: 8.1

## Android-to-web bridge

The Android receiver forwards each DataWedge intent to the active WebView:

```javascript
window.opexInventoryScan(dataString, labelType)
```

The web application converts that call into one normalized scan event, records
the symbology, moves focus to the correct step and emits sound/vibration
feedback. The API remains idempotent through `client_event_id`.

## Acceptance rule

The browser self-test is a readiness diagnostic, not a device certification.
Production approval requires the device matrix in
`docs/INVENTORY_V21_DEVICE_ACCEPTANCE.md` to pass on each deployed model.
