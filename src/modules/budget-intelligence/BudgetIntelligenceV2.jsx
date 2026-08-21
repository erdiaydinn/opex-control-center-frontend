import React,{useState}from"react";
import BudgetControlTower from"./BudgetControlTower.jsx";
import BudgetIntelligence from"./BudgetIntelligence.jsx";

export default function BudgetIntelligenceV2(){
  const[view,setView]=useState("control");
  return <div>
    <nav aria-label="Budget Intelligence views" style={{display:"flex",gap:8,padding:"10px 18px",background:"#07111f",borderBottom:"1px solid #21324a"}}>
      <button type="button" aria-pressed={view==="control"} onClick={()=>setView("control")}>Control Tower</button>
      <button type="button" aria-pressed={view==="operations"} onClick={()=>setView("operations")}>Operations</button>
    </nav>
    {view==="control"?<BudgetControlTower/>:<BudgetIntelligence/>}
  </div>
}
