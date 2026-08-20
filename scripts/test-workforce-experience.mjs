import assert from "node:assert/strict";
import React from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { createServer } from "vite";

const vite = await createServer({ server: { middlewareMode: true }, appType: "custom", logLevel: "error" });
try {
  const module = await vite.ssrLoadModule("/src/modules/workforce/WorkforceExperienceCenter.jsx");
  const preferences = await vite.ssrLoadModule(
    "/src/platform/preferences/PlatformPreferencesContext.jsx",
  );
  const auth = await vite.ssrLoadModule("/src/auth/AuthContext.jsx");
  const renderWithPlatform = (component) => renderToStaticMarkup(
    React.createElement(
      preferences.PlatformPreferencesProvider,
      null,
      React.createElement(auth.AuthProvider, null, component),
    ),
  );
  const mobile = renderWithPlatform(
    React.createElement(module.WorkforceExperienceCenter, { onBack() {} }),
  );
  const admin = renderWithPlatform(React.createElement(module.WorkforceExperienceAdmin));
  for (const label of ["Bordro ve Belgeler", "Eğitimlerim", "Nabız Anketi", "Zimmetlerim"]) assert.match(mobile, new RegExp(label));
  assert.match(admin, /Mahremiyet odaklı kanıt|Privacy-first evidence/);
  assert.doesNotMatch(`${mobile}${admin}`, /Avans|Harcama|Seyahat|Yan Hak|Budget Intelligence/i);
  console.log("Workforce experience render tests passed.");
} finally {
  await vite.close();
}
