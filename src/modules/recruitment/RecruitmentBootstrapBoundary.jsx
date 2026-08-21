import React, { useCallback, useEffect, useState } from "react";

import { usePlatformPreferences } from "../../platform/preferences/PlatformPreferencesContext.jsx";
import RecruitmentCandidateDocumentCenter from "./RecruitmentCandidateDocumentCenter.jsx";
import RecruitmentControl from "./RecruitmentControl.jsx";
import RecruitmentInterviewCenter from "./RecruitmentInterviewCenter.jsx";
import RecruitmentLifecycleCenter from "./RecruitmentLifecycleCenter.jsx";
import RecruitmentOrchestrationCenter from "./RecruitmentOrchestrationCenter.jsx";
import { loadRecruitment, primeRecruitmentBootstrap } from "./recruitmentApi.js";

export default function RecruitmentBootstrapBoundary() {
  const { t } = usePlatformPreferences();
  const [state, setState] = useState("loading");
  const [revision, setRevision] = useState(0);

  const bootstrap = useCallback(async () => {
    setState("loading");
    try {
      const snapshot = await loadRecruitment();
      primeRecruitmentBootstrap(snapshot);
      setRevision((value) => value + 1);
      setState("ready");
    } catch {
      setState("error");
    }
  }, []);

  useEffect(() => {
    bootstrap();
  }, [bootstrap]);

  useEffect(() => {
    const reload = () => bootstrap();
    window.addEventListener("eay:recruitment:external-change", reload);
    return () => window.removeEventListener("eay:recruitment:external-change", reload);
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
      <RecruitmentControl key={revision} />
      <RecruitmentCandidateDocumentCenter />
      <RecruitmentOrchestrationCenter />
      <RecruitmentInterviewCenter />
      <RecruitmentLifecycleCenter />
    </section>
  );
}