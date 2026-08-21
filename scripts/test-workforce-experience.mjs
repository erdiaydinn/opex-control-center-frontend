import assert from "node:assert/strict";
import React from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { createServer } from "vite";

const vite = await createServer({
  server: { middlewareMode: true },
  appType: "custom",
  logLevel: "error",
  optimizeDeps: { noDiscovery: true },
});
try {
  const experience = await vite.ssrLoadModule("/src/modules/workforce/WorkforceExperienceCenter.jsx");
  const auth = await vite.ssrLoadModule("/src/auth/AuthContext.jsx");
  const preferences = await vite.ssrLoadModule("/src/platform/preferences/PlatformPreferencesContext.jsx");

  function render(component) {
    return renderToStaticMarkup(
      React.createElement(
        preferences.PlatformPreferencesProvider,
        null,
        React.createElement(auth.AuthProvider, null, component),
      ),
    );
  }

  const mobile = render(React.createElement(experience.WorkforceExperienceCenter, { onBack() {} }));
  const admin = render(React.createElement(experience.WorkforceExperienceAdmin));
  for (const label of ["Bordro ve Belgeler", "Eğitimlerim", "Nabız Anketi", "Zimmetlerim"]) {
    assert.match(mobile, new RegExp(label));
  }
  assert.match(admin, /Privacy-first evidence|Mahremiyet odaklı kanıt/);
  assert.doesNotMatch(`${mobile}${admin}`, /Avans|Harcama|Seyahat|Yan Hak|Budget Intelligence/i);
  console.log("Workforce experience render tests passed.");
} finally {
  await vite.close();
}
