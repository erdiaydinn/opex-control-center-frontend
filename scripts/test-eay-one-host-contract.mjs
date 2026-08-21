import fs from "node:fs";

function requireCondition(condition, message) {
  if (!condition) throw new Error(message);
}

const settings = fs.readFileSync("android-inventory/settings.gradle.kts", "utf8");
const build = fs.readFileSync("android-inventory/eay-one-app/build.gradle.kts", "utf8");
const manifest = fs.readFileSync("android-inventory/eay-one-app/src/main/AndroidManifest.xml", "utf8");
const activity = fs.readFileSync("android-inventory/eay-one-app/src/main/java/com/eay/one/MainActivity.kt", "utf8");

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

const localeDirs = ["values-tr", "values-de", "values-ar", "values-fr", "values-es", "values-it", "values-nl", "values-pl", "values-pt-rBR"];
for (const dir of localeDirs) {
  requireCondition(fs.existsSync(`android-inventory/eay-one-app/src/main/res/${dir}/strings.xml`), `Missing EAY One locale resources: ${dir}`);
}

console.log("EAY One separate-host + fail-closed authority contract: PASS");
