import React, { useCallback, useEffect, useState } from "react";

import { useAuth } from "../../auth/AuthContext.jsx";
import { usePlatformPreferences } from "../../platform/preferences/PlatformPreferencesContext.jsx";
import WorkforceCommandCenter from "./WorkforceCommandCenter.jsx";
import WorkforceControl from "./WorkforceControl.jsx";
import { loadAdminWorkforce } from "./workforceApi.js";

export default function WorkforceBootstrapBoundary() {
  const { canAction, isSuperAdmin } = useAuth();
  const { t } = usePlatformPreferences();
  const [status, setStatus] = useState("loading");
  const [attempt, setAttempt] = useState(0);

  const retry = useCallback(() => {
    setStatus("loading");
    setAttempt((current) => current + 1);
  }, []);

  useEffect(() => {
    let active = true;

    async function bootstrap() {
      try {
        await loadAdminWorkforce();
        if (active) setStatus("ready");
      } catch {
        if (active) setStatus("error");
      }
    }

    bootstrap();
    return () => {
      active = false;
    };
  }, [attempt]);

  if (status === "loading") {
    return (
      <section
        role="status"
        aria-live="polite"
        aria-atomic="true"
        aria-busy="true"
        data-eay-product-state="loading"
      >
        {t("loading")}
      </section>
    );
  }

  if (status === "error") {
    return (
      <section role="alert" aria-atomic="true" data-eay-product-state="error">
        <p>{t("errorTitle")}</p>
        <button type="button" onClick={retry}>{t("retry")}</button>
      </section>
    );
  }

  const commandCenterAllowed = isSuperAdmin()
    || canAction("workforce", "workforce.pressure.read")
    || canAction("workforce", "workforce.schedule.read")
    || canAction("workforce", "createShift");

  return <>
    {commandCenterAllowed ? <WorkforceCommandCenter /> : null}
    <WorkforceControl />
  </>;
}
