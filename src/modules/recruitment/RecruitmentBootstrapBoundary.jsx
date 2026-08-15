import React, { useCallback, useEffect, useState } from "react";

import { usePlatformPreferences } from "../../platform/preferences/PlatformPreferencesContext.jsx";
import RecruitmentControl from "./RecruitmentControl.jsx";
import { loadRecruitment, primeRecruitmentBootstrap } from "./recruitmentApi.js";

export default function RecruitmentBootstrapBoundary() {
  const { t } = usePlatformPreferences();
  const [state, setState] = useState("loading");

  const bootstrap = useCallback(async () => {
    setState("loading");
    try {
      const snapshot = await loadRecruitment();
      primeRecruitmentBootstrap(snapshot);
      setState("ready");
    } catch {
      setState("error");
    }
  }, []);

  useEffect(() => {
    bootstrap();
  }, [bootstrap]);

  if (state === "loading") {
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

  if (state === "error") {
    return (
      <section role="alert" aria-atomic="true" data-eay-product-state="error">
        <strong>{t("errorTitle")}</strong>
        <button type="button" onClick={bootstrap}>{t("retry")}</button>
      </section>
    );
  }

  return (
    <section data-eay-product-state="ready">
      <RecruitmentControl />
    </section>
  );
}
