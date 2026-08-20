import React, { useEffect, useState } from "react";
import { ClipboardCheck } from "lucide-react";
import { useNavigate } from "react-router-dom";

import { usePlatformPreferences } from "../../platform/preferences/PlatformPreferencesContext.jsx";
import { loadMyRecruitmentOnboardingTasks } from "./recruitmentApi.js";

const LABEL = { tr: "Görevlerim", en: "My tasks", de: "Meine Aufgaben", ar: "مهامي" };

export default function OnboardingTaskLauncher() {
  const navigate = useNavigate();
  const { locale } = usePlatformPreferences();
  const [count, setCount] = useState(null);

  useEffect(() => {
    let active = true;
    loadMyRecruitmentOnboardingTasks(false)
      .then((rows) => { if (active) setCount(Array.isArray(rows) ? rows.length : 0); })
      .catch(() => { if (active) setCount(null); });
    return () => { active = false; };
  }, []);

  return <button
    type="button"
    onClick={() => navigate("/onboarding/tasks")}
    aria-label={LABEL[locale] || LABEL.en}
    style={{position:"fixed",right:20,bottom:20,zIndex:40,border:"1px solid rgba(255,255,255,.14)",background:"#171824",color:"#fff",borderRadius:16,padding:"12px 15px",boxShadow:"0 16px 42px rgba(14,16,26,.24)",display:"flex",alignItems:"center",gap:9,fontWeight:800,cursor:"pointer"}}
  >
    <ClipboardCheck size={17}/>
    {LABEL[locale] || LABEL.en}
    {Number.isInteger(count) && count > 0 ? <span style={{minWidth:22,height:22,borderRadius:999,background:"#df1067",display:"inline-grid",placeItems:"center",fontSize:11}}>{count > 99 ? "99+" : count}</span> : null}
  </button>;
}
