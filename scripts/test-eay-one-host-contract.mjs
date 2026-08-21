import fs from "node:fs";

function requireCondition(condition, message) {
  if (!condition) throw new Error(message);
}

function stringKeys(source) {
  return new Set([...source.matchAll(/<string\s+name="([^"]+)"/g)].map((match) => match[1]));
}

const settings = fs.readFileSync("android-inventory/settings.gradle.kts", "utf8");
const build = fs.readFileSync("android-inventory/eay-one-app/build.gradle.kts", "utf8");
const manifest = fs.readFileSync("android-inventory/eay-one-app/src/main/AndroidManifest.xml", "utf8");
const activity = fs.readFileSync("android-inventory/eay-one-app/src/main/java/com/eay/one/MainActivity.kt", "utf8");
const workflow = fs.readFileSync(".github/workflows/eay-brand-one-host.yml", "utf8");
const foundation = fs.readFileSync(".github/workflows/eay-mobile-foundation.yml", "utf8");
const baseStrings = fs.readFileSync("android-inventory/eay-one-app/src/main/res/values/strings.xml", "utf8");

requireCondition(settings.includes('include(":eay-one-app")'), "EAY One must ship as a separate Android application module");
requireCondition(build.includes('applicationId = "com.eay.one"'), "EAY One application identity drifted");
requireCondition(build.includes('implementation(project(":field-ui-runtime"))'), "EAY One must reuse the canonical shared field runtime");
for (const forbidden of ["appauth", "okhttp", "retrofit", "room", "sqlcipher"]) {
  requireCondition(!build.toLowerCase().includes(forbidden), `EAY One host must not create a second authority/transport stack: ${forbidden}`);
}
requireCondition(!manifest.includes("android.permission.INTERNET"), "EAY One foundation must stay network-denied until corporate session composition is reviewed");
requireCondition(activity.includes("FieldRuntimeSurface.EAY_ONE"), "EAY One host must render the EAY_ONE runtime surface");
requireCondition(activity.includes("missions = emptyList()"), "EAY One foundation must not manufacture synthetic mission truth");
requireCondition(activity.includes("EayTerminalRuntimeView"), "EAY One host must reuse the canonical runtime view bridge");
requireCondition(activity.includes("FieldSessionRecoveryBannerModel"), "EAY One must expose canonical session recovery presentation");
requireCondition(activity.includes("FieldRecoveryVisualSeverity.SECURITY"), "Missing EAY One SECURITY session recovery severity");
requireCondition(activity.includes("FieldRecoveryActionKind.SIGN_IN_AGAIN"), "Missing EAY One SIGN_IN_AGAIN presentation intent");
requireCondition(activity.includes("handleSessionRecoveryAction"), "EAY One session recovery action handler missing");
for (const forbiddenAuthLaunch of ["Intent.ACTION_VIEW", "Uri.parse", "startActivity(", "AuthorizationService", "AuthState"]) {
  requireCondition(!activity.includes(forbiddenAuthLaunch), `EAY One fail-closed host must not launch a second auth stack: ${forbiddenAuthLaunch}`);
}

const requiredTranslatedKeys = new Set([...stringKeys(baseStrings)].filter((key) => key !== "eay_one_app_name"));
const localeDirs = ["values-tr", "values-de", "values-ar", "values-fr", "values-es", "values-it", "values-nl", "values-pl", "values-pt-rBR"];
for (const dir of localeDirs) {
  const path = `android-inventory/eay-one-app/src/main/res/${dir}/strings.xml`;
  requireCondition(fs.existsSync(path), `Missing EAY One locale resources: ${dir}`);
  const localeKeys = stringKeys(fs.readFileSync(path, "utf8"));
  for (const key of requiredTranslatedKeys) {
    requireCondition(localeKeys.has(key), `Missing EAY One locale key ${key} in ${dir}`);
  }
}

requireCondition(workflow.includes("permissions:\n  contents: read"), "EAY One workflow must remain read-only");
requireCondition(workflow.includes("EAY_EXACT_HEAD: ${{ github.event.pull_request.head.sha || github.sha }}"), "EAY One workflow lost exact-head binding");
requireCondition(workflow.includes('ref: ${{ env.EAY_EXACT_HEAD }}'), "EAY One workflow checkout must bind to exact head");
requireCondition(workflow.includes("cancel-in-progress: true"), "EAY One workflow must cancel superseded runs");
requireCondition(workflow.includes("github.event.pull_request.number || github.ref"), "EAY One concurrency must use stable PR/ref identity");
requireCondition(!workflow.split("jobs:", 1)[0].includes("contents: write"), "EAY One workflow must not gain write permissions");
requireCondition(workflow.includes(":eay-one-app:assembleDebug :eay-one-app:lintDebug"), "Dedicated EAY One workflow must compile and lint the host");
requireCondition(foundation.includes(":eay-one-app:lintDebug"), "Mobile Foundation must lint EAY One");
requireCondition(foundation.includes(":eay-one-app:assembleDebug"), "Mobile Foundation must assemble EAY One");
requireCondition(foundation.includes("node scripts/test-eay-one-host-contract.mjs"), "Mobile security gate must enforce EAY One authority contract");

console.log("EAY One separate-host + explicit fail-closed session recovery + CI admission contract: PASS");
