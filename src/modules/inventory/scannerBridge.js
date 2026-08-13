const EVENT_NAME = "opex:datawedge-scan";
const PROFILE_KEY = "opex_inventory_scanner_profile";

export const DEFAULT_SCANNER_PROFILE = {
  profileName: "OPEX_INVENTORY",
  packageName: "com.opex.inventory",
  intentAction: "com.opex.inventory.SCAN",
  intentCategory: "android.intent.category.DEFAULT",
  delivery: "BROADCAST",
  minimumDataWedgeVersion: "8.1",
  decoders: ["EAN_8", "EAN_13", "CODE_128", "GS1_DATABAR", "QR_CODE", "UPCA", "UPCE"],
};

export function scannerProfile() {
  try {
    return { ...DEFAULT_SCANNER_PROFILE, ...JSON.parse(localStorage.getItem(PROFILE_KEY) || "{}") };
  } catch {
    return DEFAULT_SCANNER_PROFILE;
  }
}

export function scannerCapabilities() {
  const native = window.OpexScanner || window.AndroidScanner;
  const userAgent = navigator.userAgent || "";
  const zebra = /Zebra|Symbol|TC\d+|MC\d+/i.test(userAgent);
  const sunmi = /Sunmi/i.test(userAgent);
  return {
    mode: native ? "NATIVE_BRIDGE" : "KEYBOARD_WEDGE",
    nativeBridge: Boolean(native),
    dataWedge: Boolean(native?.dataWedge || zebra),
    zebra,
    sunmi,
    camera: Boolean(navigator.mediaDevices?.getUserMedia),
    vibration: "vibrate" in navigator,
    audio: typeof AudioContext !== "undefined" || typeof webkitAudioContext !== "undefined",
    userAgent,
  };
}

export function configureNativeScanner() {
  const native = window.OpexScanner || window.AndroidScanner;
  const profile = scannerProfile();
  if (!native?.configure) return { configured: false, profile, reason: "NATIVE_BRIDGE_NOT_AVAILABLE" };
  native.configure(JSON.stringify(profile));
  return { configured: true, profile };
}

export function subscribeScanner(onScan) {
  const listener = (event) => {
    const detail = event.detail || {};
    const value = String(detail.data || detail.barcode || "").trim();
    if (!value) return;
    onScan({
      value,
      symbology: String(detail.labelType || detail.symbology || "UNKNOWN").replace(/^LABEL-TYPE-/i, ""),
      source: detail.source || "DATAWEDGE",
      scannedAt: detail.scannedAt || new Date().toISOString(),
    });
  };
  window.addEventListener(EVENT_NAME, listener);
  window.opexInventoryScan = (data, labelType = "UNKNOWN") =>
    window.dispatchEvent(new CustomEvent(EVENT_NAME, { detail: { data, labelType, source: "NATIVE_BRIDGE" } }));
  return () => {
    window.removeEventListener(EVENT_NAME, listener);
    delete window.opexInventoryScan;
  };
}

export function scannerFeedback(type = "success") {
  if ("vibrate" in navigator) navigator.vibrate(type === "success" ? 45 : [90, 50, 90]);
  try {
    const Context = window.AudioContext || window.webkitAudioContext;
    if (!Context) return;
    const context = new Context();
    const oscillator = context.createOscillator();
    const gain = context.createGain();
    oscillator.frequency.value = type === "success" ? 880 : 220;
    gain.gain.value = 0.045;
    oscillator.connect(gain);
    gain.connect(context.destination);
    oscillator.start();
    oscillator.stop(context.currentTime + (type === "success" ? 0.07 : 0.18));
  } catch {
    // Sound feedback is optional when the browser blocks autoplay.
  }
}

export function runScannerSelfTest() {
  const capabilities = scannerCapabilities();
  const checks = [
    { key: "scanner_input", ok: capabilities.nativeBridge || "onkeydown" in window, label: capabilities.nativeBridge ? "DataWedge native bridge" : "Keyboard wedge input" },
    { key: "offline_queue", ok: "localStorage" in window, label: "Offline event queue" },
    { key: "feedback", ok: capabilities.vibration || capabilities.audio, label: "Sound / vibration feedback" },
    { key: "camera", ok: capabilities.camera, label: "Camera fallback" },
    { key: "secure_context", ok: window.isSecureContext || location.hostname === "localhost", label: "Secure terminal context" },
  ];
  return { capabilities, checks, passed: checks.filter((item) => item.ok).length, total: checks.length };
}
