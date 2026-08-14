import React, { useCallback, useEffect, useMemo, useState } from "react";
import { ArrowLeft, Boxes, CheckCircle2, LockKeyhole, RefreshCw, Ruler, ShieldCheck, TriangleAlert } from "lucide-react";
import { useNavigate } from "react-router-dom";

import { apiGet } from "../../api/client.js";
import { translatePlanogram } from "../../platform/i18n/planogramMessages.js";
import { usePlatformPreferences } from "../../platform/preferences/PlatformPreferencesContext.jsx";
import "./planogram-native.css";

// Frontend contract mirrors are CI-checked against the server permission catalog only.
// They are never used as browser-side authorization authority.
const PLANOGRAM_FEATURES = [
  "layoutView",
  "layoutEdit",
  "fixtureEdit",
  "ruleEdit",
  "productAssign",
  "aiRecommend",
];
const PLANOGRAM_ACTIONS = [
  "view",
  "create",
  "edit",
  "approve",
  "export",
  "delete",
];

// Phase 1 Security Quarantine removed the legacy cross-origin iframe/token bridge.
// Native Planogram keeps that quarantine boundary while using EAY Core authority.
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
  const load=useCallback(async()=>{setLoading(true);setError("");try{setData(await apiGet("/v1/planogram/readiness"));}catch{setError(t("loadError"));}finally{setLoading(false);}},[t]);
  useEffect(()=>{load();},[load]);
  return <main className="eay-planogram-native">
    <header className="eay-planogram-head">
      <button type="button" onClick={()=>navigate("/")} aria-label={t("back")}><ArrowLeft size={18}/>{t("back")}</button>
      <div><span>{t("coreAuthority")}</span><h1>{t("title")}</h1><p>{t("subtitle")}</p></div>
      <span className="eay-planogram-gate"><ShieldCheck size={17}/>{t("securityBoundary")}</span>
    </header>
    {loading?<section className="eay-planogram-state" role="status"><RefreshCw className="spin" size={20}/>{t("loading")}</section>:null}
    {error?<section className="eay-planogram-state" role="alert"><span>{error}</span><button type="button" onClick={load}>{t("retry")}</button></section>:null}
    {data&&!loading?<>
      <section className="eay-planogram-summary">
        <article><Boxes size={21}/><span>{t("engine")}</span><strong>{data.engine?.contract}</strong><small>{t("libraryMode")}</small></article>
        <article><LockKeyhole size={21}/><span>{t("productionBlocked")}</span><strong>{data.production_ready?"READY":"BLOCKED"}</strong><small>{t("solverBlocked")}</small></article>
        <article><CheckCircle2 size={21}/><span>{t("securityBoundary")}</span><strong>{data.engine?.legacy_bridge_enabled?"LEGACY":"CORE"}</strong><small>{t("legacyOff")}</small></article>
      </section>
      <section className="eay-planogram-evidence">
        <header><div><Ruler size={22}/><span>{t("physicalTruth")}</span></div><strong>{t("externalRequired")}</strong></header>
        <div className="eay-planogram-evidence-grid">{(data.physical_truth?.required_evidence||[]).map(item=><article key={item}><TriangleAlert size={18}/><span>{t(item)}</span></article>)}</div>
      </section>
      <section className="eay-planogram-generation"><LockKeyhole size={24}/><div><strong>{t("generationBlocked")}</strong><p>{t("requiredEvidence")}</p></div><button type="button" disabled>{t("solverBlocked")}</button></section>
    </>:null}
  </main>;
}
