import React, { useCallback, useEffect, useMemo, useState } from "react";
import { BadgeCheck, Factory, RefreshCw, ShieldCheck, TimerReset, UserRoundCog, WandSparkles } from "lucide-react";

import { useAuth } from "../../auth/AuthContext.jsx";
import { workforceActivityStudioMessage } from "../../platform/i18n/workforceActivityStudioMessages.js";
import { usePlatformPreferences } from "../../platform/preferences/PlatformPreferencesContext.jsx";
import {
  approveWorkforceActivity,
  approveWorkforceLaborStandard,
  loadWorkforceActivityTemplate,
  loadWorkforceCapabilityPeople,
  loadWorkforceFlexibilityAdmin,
  loadWorkforceLaborStandards,
  updateWorkforceEmployeeCapabilities,
  updateWorkforceWorksiteType,
} from "./workforceFlexibilityApi.js";
import "./workforceActivityStudio.css";


const TEMPLATE_KEYS = ["qsr", "supermarket", "manufacturing", "convenience_kiosk", "darkstore"];
const WORKSITE_TYPES = ["restaurant", "store", "factory", "kiosk", "darkstore", "warehouse", "office", "other"];

function todayIstanbul() {
  return new Date().toLocaleDateString("sv-SE", { timeZone: "Europe/Istanbul" });
}

function parseKeys(value) {
  return [...new Set(String(value || "").split(",").map((item) => item.trim()).filter(Boolean))].sort();
}

export default function WorkforceActivityStudio() {
  const { canAction } = useAuth();
  const { locale } = usePlatformPreferences();
  const m = useCallback((key, params) => workforceActivityStudioMessage(locale, key, params), [locale]);
  const allowed = canAction("workforce", "manageSystemConfig");
  const canManageEmployees = canAction("workforce", "manageEmployees");
  const canManageWorksites = canAction("workforce", "manageWarehouses");
  const [templateKey, setTemplateKey] = useState("qsr");
  const [candidates, setCandidates] = useState([]);
  const [activities, setActivities] = useState([]);
  const [standards, setStandards] = useState([]);
  const [locations, setLocations] = useState([]);
  const [employees, setEmployees] = useState([]);
  const [selectedActivity, setSelectedActivity] = useState("");
  const [selectedEmployee, setSelectedEmployee] = useState("");
  const [selectedWorksite, setSelectedWorksite] = useState("");
  const [worksiteType, setWorksiteType] = useState("warehouse");
  const [skillKeys, setSkillKeys] = useState("");
  const [certificationKeys, setCertificationKeys] = useState("");
  const [equipmentKeys, setEquipmentKeys] = useState("");
  const [effectiveFrom, setEffectiveFrom] = useState(todayIstanbul());
  const [sourceRef, setSourceRef] = useState("");
  const [laborSourceRef, setLaborSourceRef] = useState("");
  const [secondsPerUnit, setSecondsPerUnit] = useState("");
  const [people, setPeople] = useState("1");
  const [busy, setBusy] = useState("");
  const [message, setMessage] = useState("");
  const [error, setError] = useState("");

  const reload = useCallback(async () => {
    if (!allowed) return;
    setBusy((value) => value || "load");
    setError("");
    try {
      const [admin, laborRows] = await Promise.all([
        loadWorkforceFlexibilityAdmin(),
        loadWorkforceLaborStandards(),
      ]);
      setActivities(admin.activities || []);
      setLocations(admin.locations || []);
      setStandards(laborRows || []);
      setSelectedActivity((current) => current || admin.activities?.[0]?.activityKey || "");
      setSelectedWorksite((current) => current || admin.locations?.[0]?.id || "");
      if (canManageEmployees) {
        const rows = await loadWorkforceCapabilityPeople().catch(() => []);
        setEmployees(rows);
        setSelectedEmployee((current) => current || rows[0]?.employeeId || rows[0]?.id || "");
      }
    } catch (requestError) {
      setError(requestError.message || m("loadError"));
    } finally {
      setBusy((value) => value === "load" ? "" : value);
    }
  }, [allowed, canManageEmployees, m]);

  const preview = useCallback(async (key = templateKey) => {
    if (!allowed) return;
    setBusy("preview"); setError("");
    try {
      const result = await loadWorkforceActivityTemplate(key);
      setCandidates(result.rows || []);
    } catch (requestError) {
      setError(requestError.message || m("loadError"));
    } finally { setBusy(""); }
  }, [allowed, m, templateKey]);

  useEffect(() => { reload(); }, [reload]);
  useEffect(() => { preview(templateKey); }, [templateKey]);

  const activeKeys = useMemo(() => new Set(activities.map((row) => row.activityKey)), [activities]);
  const standardByKey = useMemo(() => new Map(standards.map((row) => [row.activityKey, row])), [standards]);
  const selected = activities.find((row) => row.activityKey === selectedActivity);
  const employee = employees.find((row) => String(row.employeeId || row.id) === String(selectedEmployee));
  const worksite = locations.find((row) => String(row.id) === String(selectedWorksite));

  useEffect(() => {
    if (!employee) return;
    setSkillKeys((employee.skillKeys || []).join(", "));
    setCertificationKeys((employee.certificationKeys || []).join(", "));
    setEquipmentKeys((employee.equipmentKeys || []).join(", "));
  }, [employee]);
  useEffect(() => {
    if (worksite?.locationType) setWorksiteType(worksite.locationType);
  }, [worksite]);

  async function approveCandidate(candidate) {
    if (!sourceRef.trim()) { setError(m("source")); return; }
    setBusy(`activity-${candidate.activityKey}`); setMessage(""); setError("");
    try {
      await approveWorkforceActivity({ ...candidate, effectiveFrom, sourceRef: sourceRef.trim() });
      setMessage(m("saved"));
      await reload();
    } catch (requestError) {
      setError(requestError.message || m("loadError"));
    } finally { setBusy(""); }
  }

  async function approveLabor(event) {
    event.preventDefault();
    if (!selectedActivity || !laborSourceRef.trim() || !secondsPerUnit) return;
    setBusy("labor"); setMessage(""); setError("");
    try {
      await approveWorkforceLaborStandard({ activityKey: selectedActivity, secondsPerUnit, people, effectiveFrom, sourceRef: laborSourceRef.trim() });
      setMessage(m("saved"));
      setSecondsPerUnit(""); setLaborSourceRef("");
      await reload();
    } catch (requestError) {
      setError(requestError.message || m("loadError"));
    } finally { setBusy(""); }
  }

  async function saveCapabilities(event) {
    event.preventDefault();
    if (!canManageEmployees || !selectedEmployee) return;
    setBusy("capability"); setMessage(""); setError("");
    try {
      await updateWorkforceEmployeeCapabilities(selectedEmployee, {
        skillKeys: parseKeys(skillKeys), certificationKeys: parseKeys(certificationKeys), equipmentKeys: parseKeys(equipmentKeys),
      });
      setMessage(m("saved"));
      await reload();
    } catch (requestError) {
      setError(requestError.message || m("loadError"));
    } finally { setBusy(""); }
  }

  async function saveWorksite(event) {
    event.preventDefault();
    if (!canManageWorksites || !selectedWorksite) return;
    setBusy("worksite"); setMessage(""); setError("");
    try {
      await updateWorkforceWorksiteType(selectedWorksite, worksiteType);
      setMessage(m("saved"));
      await reload();
    } catch (requestError) {
      setError(requestError.message || m("loadError"));
    } finally { setBusy(""); }
  }

  if (!allowed) {
    return <section className="wfx-panel wfx-activity-studio-denied"><ShieldCheck size={19} /><span>{m("permission")}</span></section>;
  }

  return <section className="wfx-panel wfx-activity-studio">
    <header><div><span>{m("eyebrow")}</span><h3>{m("title")}</h3><p>{m("detail")}</p></div><Factory size={26} /></header>
    {error ? <div className="wfx-activity-message error">{error}</div> : null}
    {message ? <div className="wfx-activity-message success"><BadgeCheck size={16} />{message}</div> : null}

    <div className="wfx-activity-template-toolbar">
      <label>{m("template")}<select value={templateKey} onChange={(event) => setTemplateKey(event.target.value)}>{TEMPLATE_KEYS.map((key) => <option key={key} value={key}>{m(key)}</option>)}</select></label>
      <label>{m("effective")}<input type="date" value={effectiveFrom} onChange={(event) => setEffectiveFrom(event.target.value)} /></label>
      <label className="wide">{m("source")}<input value={sourceRef} maxLength={300} onChange={(event) => setSourceRef(event.target.value)} placeholder={m("source")} /></label>
      <button type="button" onClick={() => preview()} disabled={busy === "preview"}><RefreshCw size={16} />{m("preview")}</button>
    </div>
    <p className="wfx-activity-hint"><ShieldCheck size={15} />{m("templateHint")}</p>

    <div className="wfx-activity-candidate-grid">
      {candidates.map((candidate) => {
        const active = activeKeys.has(candidate.activityKey);
        return <article key={`${templateKey}-${candidate.activityKey}`} className={active ? "active" : ""}>
          <div className="wfx-activity-card-head"><span>{active ? m("governed") : m("candidate")}</span><strong>{candidate.displayName}</strong><small>{candidate.category} · {candidate.demandMode} · {candidate.unitKey}</small></div>
          <div className="wfx-activity-meta">
            {candidate.locationTypes?.length ? <span>{m("location")}: {candidate.locationTypes.join(", ")}</span> : null}
            {candidate.requiredSkillKeys?.length ? <span>{m("skills")}: {candidate.requiredSkillKeys.join(", ")}</span> : null}
            {candidate.requiredCertificationKeys?.length ? <span>{m("certifications")}: {candidate.requiredCertificationKeys.join(", ")}</span> : null}
            {candidate.requiredEquipmentKeys?.length ? <span>{m("equipment")}: {candidate.requiredEquipmentKeys.join(", ")}</span> : null}
          </div>
          <button type="button" disabled={active || busy === `activity-${candidate.activityKey}` || !sourceRef.trim()} onClick={() => approveCandidate(candidate)}><WandSparkles size={15} />{active ? m("governed") : busy === `activity-${candidate.activityKey}` ? m("activating") : m("activate")}</button>
        </article>;
      })}
      {!candidates.length ? <div className="wfx-activity-empty">{m("noPreview")}</div> : null}
    </div>

    <section className="wfx-activity-governed">
      <header><div><small>{m("active")}</small><strong>{activities.length}</strong></div><BadgeCheck size={19} /></header>
      {activities.length ? <div>{activities.map((activity) => {
        const standard = standardByKey.get(activity.activityKey);
        return <button type="button" key={`${activity.activityKey}-${activity.version}`} className={selectedActivity === activity.activityKey ? "selected" : ""} onClick={() => setSelectedActivity(activity.activityKey)}><span><strong>{activity.displayName}</strong><small>{activity.category} · {m("version", { version: activity.version })}</small></span><em className={standard ? "ready" : "missing"}>{standard ? m("standardReady") : m("standardMissing")}</em></button>;
      })}</div> : <p>{m("noActive")}</p>}
    </section>

    <form className="wfx-activity-labor" onSubmit={approveLabor}>
      <header><TimerReset size={20} /><div><small>{m("labor")}</small><strong>{selected?.displayName || m("selectActivity")}</strong></div></header>
      <div>
        <label>{m("selectActivity")}<select value={selectedActivity} onChange={(event) => setSelectedActivity(event.target.value)}>{activities.map((activity) => <option key={activity.activityKey} value={activity.activityKey}>{activity.displayName}</option>)}</select></label>
        <label>{m("seconds")}<input type="number" min="0.001" step="0.001" value={secondsPerUnit} onChange={(event) => setSecondsPerUnit(event.target.value)} /></label>
        <label>{m("people")}<input type="number" min="0.001" step="0.001" value={people} onChange={(event) => setPeople(event.target.value)} /></label>
        <label>{m("effective")}<input type="date" value={effectiveFrom} onChange={(event) => setEffectiveFrom(event.target.value)} /></label>
        <label className="wide">{m("laborSource")}<input value={laborSourceRef} maxLength={300} onChange={(event) => setLaborSourceRef(event.target.value)} /></label>
      </div>
      <p><ShieldCheck size={15} />{m("laborHint")}</p>
      <button disabled={!selectedActivity || !secondsPerUnit || !laborSourceRef.trim() || busy === "labor"}><TimerReset size={16} />{busy === "labor" ? m("approvingLabor") : m("approveLabor")}</button>
    </form>

    <div className="wfx-activity-authority-grid">
      <form className="wfx-activity-authority-card" onSubmit={saveCapabilities}>
        <header><UserRoundCog size={20} /><div><strong>{m("capabilityTitle")}</strong><small>{m("capabilityDetail")}</small></div></header>
        {canManageEmployees ? <>
          <label>{m("employee")}<select value={selectedEmployee} onChange={(event) => setSelectedEmployee(event.target.value)}>{employees.map((row) => <option key={row.employeeId || row.id} value={row.employeeId || row.id}>{row.fullName || row.name || row.employeeId || row.id}</option>)}</select></label>
          <label>{m("skills")}<input value={skillKeys} onChange={(event) => setSkillKeys(event.target.value)} placeholder={m("commaHint")} /></label>
          <label>{m("certifications")}<input value={certificationKeys} onChange={(event) => setCertificationKeys(event.target.value)} placeholder={m("commaHint")} /></label>
          <label>{m("equipment")}<input value={equipmentKeys} onChange={(event) => setEquipmentKeys(event.target.value)} placeholder={m("commaHint")} /></label>
          <button disabled={!selectedEmployee || busy === "capability"}><BadgeCheck size={15} />{busy === "capability" ? m("savingCapabilities") : m("saveCapabilities")}</button>
        </> : <p><ShieldCheck size={15} />{m("capabilityPermission")}</p>}
      </form>

      <form className="wfx-activity-authority-card" onSubmit={saveWorksite}>
        <header><Factory size={20} /><div><strong>{m("worksiteTitle")}</strong><small>{m("worksiteDetail")}</small></div></header>
        {canManageWorksites ? <>
          <label>{m("worksite")}<select value={selectedWorksite} onChange={(event) => setSelectedWorksite(event.target.value)}>{locations.map((row) => <option key={row.id} value={row.id}>{row.name}</option>)}</select></label>
          <label>{m("worksiteType")}<select value={worksiteType} onChange={(event) => setWorksiteType(event.target.value)}>{WORKSITE_TYPES.map((key) => <option key={key} value={key}>{key}</option>)}</select></label>
          <button disabled={!selectedWorksite || busy === "worksite"}><BadgeCheck size={15} />{busy === "worksite" ? m("savingWorksite") : m("saveWorksite")}</button>
        </> : <p><ShieldCheck size={15} />{m("worksitePermission")}</p>}
      </form>
    </div>
  </section>;
}
