import React, { useCallback, useEffect, useMemo, useState } from "react";
import { ArrowLeft, Boxes, CheckCircle2, LockKeyhole, RefreshCw, Ruler, ShieldCheck, TriangleAlert } from "lucide-react";
import { useNavigate } from "react-router-dom";

import { apiGet } from "../../api/client.js";
import { translatePlanogram } from "../../platform/i18n/planogramMessages.js";
import { usePlatformPreferences } from "../../platform/preferences/PlatformPreferencesContext.jsx";
import "./planogram-native.css";

const PLANOGRAM_FEATURES = ["layoutView", "layoutEdit", "fixtureEdit", "ruleEdit", "productAssign", "aiRecommend"];
const PLANOGRAM_ACTIONS = ["view", "create", "edit", "approve", "export", "delete"];

// Phase 1 Security Quarantine remains the canonical boundary: no legacy iframe/token bridge.
export const PLANOGRAM_SECURITY_CONTRACT = Object.freeze({
  features: PLANOGRAM_FEATURES,
  actions: PLANOGRAM_ACTIONS,
  legacyBridgeAllowed: false,
});

export default function PlanogramStudio(){
  const navigate=useNavigate();
  const {locale}=usePlatformPreferences();
  const t=useMemo(()=>key=>translatePlanogram(locale,key),[locale]);
  const [data,setData]=useState(null);
  const [loading,setLoading]=useState(true);
  const [error,setError]=useState("");
  const load=useCallback(async()=>{
    setLoading(true);
    setError("");
    try{
      setData(await apiGet("/v1/planogram/readiness"));
    }catch{
      setData(null);
      setError(t("loadError"));
    }finally{
      setLoading(false);
    }
  },[t]);
  useEffect(()=>{load();},[load]);
  const productState=loading?"loading":error?"error":data?"ready":"empty";

  return <main className="eay-planogram-native" aria-busy={loading?"true":"false"} data-eay-product-state={productState}>
    <header className="eay-planogram-head">
      <button type="button" onClick={()=>navigate("/")} aria-label={t("back")}><ArrowLeft size={18} aria-hidden="true"/>{t("back")}</button>
      <div><span>{t("coreAuthority")}</span><h1>{t("title")}</h1><p>{t("subtitle")}</p></div>
      <span className="eay-planogram-gate"><ShieldCheck size={17} aria-hidden="true"/>{t("securityBoundary")}</span>
    </header>
    {loading?<section className="eay-planogram-state" data-eay-product-state="loading" role="status" aria-live="polite" aria-atomic="true"><RefreshCw className="spin" size={20} aria-hidden="true"/>{t("loading")}</section>:null}
    {!loading&&error?<section className="eay-planogram-state" data-eay-product-state="error" role="alert" aria-atomic="true"><span>{error}</span><button type="button" onClick={load}>{t("retry")}</button></section>:null}
    {!loading&&!error&&!data?<section className="eay-planogram-state" data-eay-product-state="empty" role="status" aria-live="polite" aria-atomic="true"><span>{t("loadError")}</span><button type="button" onClick={load}>{t("retry")}</button></section>:null}
    {data&&!loading&&!error?<div data-eay-product-state="ready">
      <section className="eay-planogram-summary">
        <article><Boxes size={21} aria-hidden="true"/><span>{t("engine")}</span><strong>{data.engine?.contract}</strong><small>{t("libraryMode")}</small></article>
        <article><LockKeyhole size={21} aria-hidden="true"/><span>{t("productionBlocked")}</span><strong>{data.production_ready?"READY":"BLOCKED"}</strong><small>{t("solverBlocked")}</small></article>
        <article><CheckCircle2 size={21} aria-hidden="true"/><span>{t("securityBoundary")}</span><strong>{data.engine?.legacy_bridge_enabled?"LEGACY":"CORE"}</strong><small>{t("legacyOff")}</small></article>
      </section>
      <section className="eay-planogram-evidence">
        <header><div><Ruler size={22} aria-hidden="true"/><span>{t("physicalTruth")}</span></div><strong>{t("externalRequired")}</strong></header>
        <div className="eay-planogram-evidence-grid">{(data.physical_truth?.required_evidence||[]).map(item=><article key={item}><TriangleAlert size={18} aria-hidden="true"/><span>{t(item)}</span></article>)}</div>
      </section>
      <section className="eay-planogram-generation"><LockKeyhole size={24} aria-hidden="true"/><div><strong>{t("generationBlocked")}</strong><p>{t("requiredEvidence")}</p></div><button type="button" disabled>{t("solverBlocked")}</button></section>
    </div>:null}
  </main>;
}
