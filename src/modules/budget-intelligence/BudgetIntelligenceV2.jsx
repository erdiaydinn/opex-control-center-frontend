import React,{useState}from"react";
import{usePlatformPreferences}from"../../platform/preferences/PlatformPreferencesContext.jsx";
import BudgetControlTower from"./BudgetControlTower.jsx";
import BudgetIntelligence from"./BudgetIntelligence.jsx";

const LABELS={
 tr:{nav:"Budget Intelligence görünümleri",control:"Control Tower",operations:"Operasyon"},
 en:{nav:"Budget Intelligence views",control:"Control Tower",operations:"Operations"},
 de:{nav:"Budget Intelligence Ansichten",control:"Control Tower",operations:"Betrieb"},
 ar:{nav:"طرق عرض Budget Intelligence",control:"مركز التحكم",operations:"العمليات"},
 fr:{nav:"Vues Budget Intelligence",control:"Control Tower",operations:"Opérations"},
 es:{nav:"Vistas de Budget Intelligence",control:"Control Tower",operations:"Operaciones"},
 it:{nav:"Viste Budget Intelligence",control:"Control Tower",operations:"Operazioni"},
 nl:{nav:"Budget Intelligence-weergaven",control:"Control Tower",operations:"Operaties"},
 pl:{nav:"Widoki Budget Intelligence",control:"Control Tower",operations:"Operacje"},
 "pt-BR":{nav:"Visões do Budget Intelligence",control:"Control Tower",operations:"Operações"}
};

export default function BudgetIntelligenceV2(){
  const{locale="tr"}=usePlatformPreferences();
  const copy=LABELS[locale]||LABELS.en;
  const[view,setView]=useState("control");
  return <div>
    <nav aria-label={copy.nav} style={{display:"flex",gap:8,padding:"10px 18px",background:"#07111f",borderBottom:"1px solid #21324a"}}>
      <button type="button" aria-pressed={view==="control"} onClick={()=>setView("control")}>{copy.control}</button>
      <button type="button" aria-pressed={view==="operations"} onClick={()=>setView("operations")}>{copy.operations}</button>
    </nav>
    {view==="control"?<BudgetControlTower/>:<BudgetIntelligence/>}
  </div>
}
