import React, { useEffect, useState } from "react";
import { Navigate } from "react-router-dom";

import { apiGet } from "../api/client.js";
import { usePlatformPreferences } from "../platform/preferences/PlatformPreferencesContext.jsx";

export default function ControlPlaneRoute({ children }) {
  const { t } = usePlatformPreferences();
  const [state, setState] = useState("loading");

  useEffect(() => {
    let active = true;

    apiGet("/v1/platform/authority")
      .then(() => {
        if (active) setState("allowed");
      })
      .catch(() => {
        if (active) setState("denied");
      });

    return () => {
      active = false;
    };
  }, []);

  if (state === "loading") {
    return (
      <div
        role="status"
        aria-live="polite"
        aria-busy="true"
        data-eay-product-state="loading"
      >
        {t("loading")}
      </div>
    );
  }

  if (state !== "allowed") {
    return <Navigate to="/" replace />;
  }

  return children;
}
