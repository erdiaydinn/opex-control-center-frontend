import fs from "node:fs";
import process from "node:process";

const interactionPath = "src/modules/academy/AcademyInteractionTimelineStudio.jsx";
const cssPath = "src/modules/academy/academy-expansion.css";
const interaction = fs.readFileSync(interactionPath, "utf8");
const css = fs.readFileSync(cssPath, "utf8");

const requirements = [
  ['apiPost("/v1/academy/admin/interaction-sets"', "canonical interaction-set authority"],
  ['crypto.subtle.digest("SHA-256"', "source fingerprint"],
  ['const selectedVersion = useMemo(', "selected immutable content-version binding"],
  ['const timelineDurationMs = useMemo(() => {', "duration-aware timeline scale"],
  ['Number(selectedVersion?.duration_ms)', "governed content duration"],
  ['const timelineRef = useRef(null)', "timeline geometry reference"],
  ['event.currentTarget.setPointerCapture(event.pointerId)', "pointer capture"],
  ['function timeFromClientX(clientX)', "pointer-to-time conversion"],
  ['updateNodeByKey(drag.nodeKey, { at_ms: timeFromClientX(event.clientX) })', "drag updates canonical at_ms draft"],
  ["['ArrowLeft', 'ArrowRight'].includes(event.key)", "keyboard timeline movement"],
  ['event.shiftKey ? 5000 : 1000', "coarse and fine keyboard movement"],
  ['clamp(current + direction * step, 0, timelineDurationMs)', "bounded keyboard time movement"],
  ['const orderedNodes = useMemo(', "deterministic visual ordering"],
  ['className={`eay-academy-timeline-marker ${selectedNodeKey === node.node_key ? "is-selected" : ""}`}', "selected marker state"],
  ['style={{ left: `${percent}%` }}', "time-positioned visual marker"],
  ['onFocus={() => setSelectedNodeKey(node.node_key)}', "keyboard/form selection synchronization"],
  ['max="1000"', "backend-aligned score weight ceiling"],
];

for (const [needle, label] of requirements) {
  if (!interaction.includes(needle)) {
    console.error(`${interactionPath}: missing ${label}: ${needle}`);
    process.exit(1);
  }
}

for (const selector of [
  ".eay-academy-timeline-ruler",
  ".eay-academy-timeline-track",
  ".eay-academy-timeline-marker",
  ".eay-academy-timeline-marker.is-selected",
]) {
  if (!css.includes(selector)) {
    console.error(`${cssPath}: missing governed interaction timeline selector: ${selector}`);
    process.exit(1);
  }
}

if (/localStorage|sessionStorage/.test(interaction)) {
  console.error(`${interactionPath}: interaction timing authority must not be persisted or inferred from browser storage.`);
  process.exit(1);
}

if (interaction.includes('"multi_choice"')) {
  console.error(`${interactionPath}: deprecated multi_choice alias must not diverge from backend multiple_choice authority.`);
  process.exit(1);
}

console.log("Academy governed visual interaction timeline authoring contract: PASS");
