# Inventory V21 Device Acceptance

Run these tests on every Zebra, Honeywell or Sunmi model before production:

1. DataWedge/profile creation and minimum-version check.
2. EAN-8, EAN-13, Code 128, GS1, QR, UPC-A and UPC-E samples.
3. Location scan → product scan → quantity → save.
4. Fifty rapid scans without focus loss or duplicate events.
5. Scanner double-Enter and long-press trigger.
6. Network loss for 30 minutes, queued events, reconnect and idempotent sync.
7. Application background/foreground and device reboot recovery.
8. Wrong location, unknown barcode and expired location lock.
9. Sound, vibration, success/error color and accessibility contrast.
10. Eight-hour shift battery, memory and thermal test.

Record device model, Android version, DataWedge/scanner-service version, build
number, tester, date and evidence. A failed row blocks production for that
device model.
