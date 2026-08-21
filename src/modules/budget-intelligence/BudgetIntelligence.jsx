import React, { useEffect, useState } from "react";
import { apiGet } from "../../api/client.js";
import { usePlatformPreferences } from "../../platform/preferences/PlatformPreferencesContext.jsx";
import BudgetControlTower from "./BudgetControlTower.jsx";

const EMPTY_DATA = null;

export default function BudgetIntelligence() {
  const { t } = usePlatformPreferences();
  const [data, setData] = useState(EMPTY_DATA);
  const [loading, setLoading] = useState(true);
  const [apiError, setApiError] = useState(false);
  const [reloadKey, setReloadKey] = useState(0);

  useEffect(() => {
    let active = true;
    setLoading(true);
    setApiError(false);
    apiGet("/v1/budget/control-tower")
      .then((payload) => {
        if (active) setData(payload || EMPTY_DATA);
      })
      .catch(() => {
        if (!active) return;
        setData(EMPTY_DATA);
        setApiError(true);
      })
      .finally(() => {
        if (active) setLoading(false);
      });
    return () => {
      active = false;
    };
  }, [reloadKey]);

  const noData = !loading && !apiError && !data;
  const ready = !loading&&!apiError&&!noData;

  if (loading) {
    return (
      <section data-eay-product-state="loading" role="status" aria-busy="true" aria-live="polite" aria-atomic="true">
        {t("loading")}
      </section>
    );
  }

  if (apiError) {
    return (
      <section data-eay-product-state="error" role="alert">
        <h1>{t("errorTitle")}</h1>
        <button type="button" onClick={() => setReloadKey(v=>v+1)}>{t("retry")}</button>
      </section>
    );
  }

  if (noData) {
    return (
      <section data-eay-product-state="empty" role="status" aria-live="polite" aria-atomic="true">
        {t("emptyTitle")}
      </section>
    );
  }

  return ready ? (
    <section data-eay-product-state="ready">
      <BudgetControlTower data={data} />
    </section>
  ) : null;
}
