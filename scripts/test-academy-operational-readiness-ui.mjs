import fs from "node:fs";
import process from "node:process";

import { academyOperationalReadinessMessageCoverage } from "../src/platform/i18n/academyOperationalReadinessMessages.js";

const UI_LOCALES = ["tr", "en", "de", "ar", "fr", "es", "it", "nl", "pl", "pt-BR"];
const skillGapPath = "src/modules/academy/AcademySkillGap.jsx";
const messagesPath = "src/platform/i18n/academyOperationalReadinessMessages.js";
const skillGap = fs.readFileSync(skillGapPath, "utf8");
const messages = fs.readFileSync(messagesPath, "utf8");

const requirements = [
  ['apiGet("/v1/academy/operational-readiness/me")', "canonical self-scoped operational readiness authority"],
  ['apiGet("/v1/academy/credentials/me/skill-gaps")', "canonical role skill-gap authority"],
  ['Promise.allSettled', "independent closed-loop and skill-gap loading"],
  ['data-eay-operational-readiness="self-scoped"', "self-scoped learner surface marker"],
  ['item.source_domain', "operational source domain provenance"],
  ['item.signal_type', "operational signal provenance"],
  ['item.source_ref', "source reference provenance"],
  ['item.source_version', "source version provenance"],
  ['item.source_fingerprint', "source fingerprint provenance"],
  ['item.recommended_path_title_i18n', "mapping-derived remediation path"],
  ['item.enrollment_id', "server-resolved enrollment identity"],
  ['item.latest_observation_id', "post-training operational observation"],
  ['item.baseline_value', "observed baseline"],
  ['item.observed_value', "observed post-training value"],
  ['item.observed_delta', "observed delta"],
  ['data-eay-causal-attribution="false"', "non-causal impact boundary"],
  ['ox("associationOnly")', "localized non-causal impact disclosure"],
  ['readiness?.policy || "operational_gap_v1"', "server policy with safe display fallback"],
  ['openRecommendedPath(item)', "governed remediation navigation"],
];

for (const [needle, label] of requirements) {
  if (!skillGap.includes(needle)) {
    console.error(`${skillGapPath}: missing ${label}: ${needle}`);
    process.exit(1);
  }
}

if (/operational-readiness\/me[^"'\n]*[?&](subject|required_level|current_level)=/i.test(skillGap)) {
  console.error(`${skillGapPath}: operational readiness request must not carry browser-supplied subject/proficiency authority.`);
  process.exit(1);
}

if (/localStorage|sessionStorage/.test(skillGap)) {
  console.error(`${skillGapPath}: learner operational readiness authority must not come from browser storage.`);
  process.exit(1);
}

if (!messages.includes('associationOnly')) {
  console.error(`${messagesPath}: causal-boundary disclosure is required.`);
  process.exit(1);
}

const coverage = academyOperationalReadinessMessageCoverage(UI_LOCALES);
for (const locale of UI_LOCALES) {
  const missing = coverage.missing[locale] || [];
  const extra = coverage.extra[locale] || [];
  if (missing.length || extra.length) {
    console.error(
      `Academy operational readiness i18n mismatch for ${locale}: ${JSON.stringify({ missing, extra })}`,
    );
    process.exit(1);
  }
}

console.log(
  "Academy operational readiness self-scope, provenance, remediation, non-causal observation and ten-locale contract: PASS",
);
