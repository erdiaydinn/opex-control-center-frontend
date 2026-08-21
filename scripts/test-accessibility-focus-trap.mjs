import fs from "node:fs";

const source = fs.readFileSync("src/platform/preferences/AccessibilityControl.jsx", "utf8");

function requireCondition(condition, message) {
  if (!condition) throw new Error(message);
}

requireCondition(source.includes('const FOCUSABLE_SELECTOR = ['), "accessibility dialog focusable selector contract is missing");
requireCondition(source.includes('event.key !== "Tab"'), "accessibility dialog must handle Tab navigation");
requireCondition(source.includes('event.shiftKey'), "accessibility dialog must handle reverse Tab navigation");
requireCondition(source.includes('dialogRef.current?.contains(active)'), "accessibility dialog must detect escaped focus");
requireCondition(source.includes('lastFocusable.focus()'), "Shift+Tab must wrap to the final dialog control");
requireCondition(source.includes('firstFocusable.focus()'), "Tab must wrap to the first dialog control");
requireCondition(source.includes('aria-modal="true"'), "accessibility dialog modal semantics must be preserved");
requireCondition(source.includes('tabIndex="-1"'), "accessibility dialog needs a fail-closed focus fallback target");
requireCondition(source.includes('(previous || triggerRef.current)?.focus?.()'), "closing the accessibility dialog must restore prior focus");

console.log("EAY accessibility modal focus containment: PASS");
