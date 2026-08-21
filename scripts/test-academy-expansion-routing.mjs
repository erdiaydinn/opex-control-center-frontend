import fs from "node:fs";
import process from "node:process";

const appPath = "src/App.jsx";
const hubPath = "src/modules/academy/AcademyExpansionHub.jsx";
const achievementsPath = "src/modules/academy/AcademyAchievements.jsx";
const app = fs.readFileSync(appPath, "utf8");
const hub = fs.readFileSync(hubPath, "utf8");
const achievements = fs.readFileSync(achievementsPath, "utf8");

const appRequirements = [
  ['lazy(() => import("./modules/academy/AcademyExpansionHub.jsx"))', "lazy Academy expansion boundary"],
  ['path="/academy/experience"', "Academy expansion route"],
  ['moduleKey="academy"><AcademyExpansionHub', "Academy module permission boundary"],
];

for (const [needle, label] of appRequirements) {
  if (!app.includes(needle)) {
    console.error(`${appPath}: missing ${label}: ${needle}`);
    process.exit(1);
  }
}

const hubRequirements = [
  ['canFeature("academy", "contentStudio")', "content-studio feature authority"],
  ['useState(canStudio ? "scenario" : "achievements")', "learner-safe default surface"],
  ['data-eay-product-state="loading"', "loading product-state marker"],
  ['data-eay-product-state="ready"', "ready product-state marker"],
  ['role="alert"', "error announcement semantics"],
  ['navigate("/academy")', "back-to-Academy composition"],
  ['<AcademyScenarioStudio', "scenario Studio composition"],
  ['<AcademyLocalizationGovernance', "localization governance composition"],
  ['<AcademyAchievements', "achievement composition"],
];

for (const [needle, label] of hubRequirements) {
  if (!hub.includes(needle)) {
    console.error(`${hubPath}: missing ${label}: ${needle}`);
    process.exit(1);
  }
}

if (!achievements.includes('/v1/academy/credentials/me')) {
  console.error(`${achievementsPath}: learner achievements must use canonical self-scoped credential authority.`);
  process.exit(1);
}

if (/localStorage|sessionStorage/.test(hub)) {
  console.error(`${hubPath}: Academy expansion authority must not be inferred from browser storage.`);
  process.exit(1);
}

console.log("Academy expansion routing and authority contract: PASS");
