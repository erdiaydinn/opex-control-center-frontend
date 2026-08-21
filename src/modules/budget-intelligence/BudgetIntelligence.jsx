import React,{useEffect,useState}from"react";import{apiGet}from"../../api/client.js";import{usePlatformPreferences}from"../../platform/preferences/PlatformPreferencesContext.jsx";import"./budget.css";
const money=v=>"₺"+Number(v||0).toLocaleString("tr-TR");
const CATS=["All","Raf & Ekipman","Soğutucu & Dolap","Elektrik","Tadilat & Zemin","Tente & Cephe","Güvenlik & Yangın","Diğer Saha İşleri"];
const MONTHS=["All","Jan","Feb","Mar","Apr","May","Jun","Jul","Aug","Sep","Oct","Nov","Dec"];
const Q=["All","Q1","Q2","Q3","Q4"];
const EMPTY_DATA={
summary:{
planned_budget:0,
committed_po:0,
invoiced_actual:0,
pending_invoice:0,
remaining_budget:0,
open_conflicts:0,
waiting_tasks:0
},
requests:[],
conflicts:[],
tasks:[],
insights:[]
};
async function api(path){return apiGet(path)}
export default function BudgetIntelligence(){
const{t}=usePlatformPreferences();
const[tab,setTab]=useState("Executive"),[data,setData]=useState(EMPTY_DATA),[filters,setFilters]=useState({month:"All",quarter:"All",category:"All",scope:"Ops Relevant",compare:false}),[drawer,setDrawer]=useState(null),[task,setTask]=useState(null),[ask,setAsk]=useState(false),[ai,setAi]=useState(""),[prompt,setPrompt]=useState(""),[csv,setCsv]=useState([]),[apiError,setApiError]=useState(false),[loading,setLoading]=useState(true),[reloadKey,setReloadKey]=useState(0);
useEffect(()=>{
let active=true;
const q=new URLSearchParams(filters).toString();
setLoading(true);
setApiError(false);
Promise.all([
api("/budget/summary?"+q),
api("/budget/requests?"+q),
api("/budget/conflicts"),
api("/budget/tasks"),
api("/budget/insights")
])
.then(([summary,requests,conflicts,tasks,insights])=>{
if(!active)return;
setData({summary,requests,conflicts,tasks,insights});
setLoading(false);
})
.catch(()=>{
if(!active)return;
setData(EMPTY_DATA);
setApiError(true);
setLoading(false);
});
return()=>{active=false};
},[filters,reloadKey]);
function f(k,v){setFilters(p=>({...p,[k]:v}))}
function askAI(){const p=prompt.toLowerCase();setAi(p.includes("neden")||p.includes("niye")?"Talebin ana nedeni iş tanımı ve PR başlığında görünüyor. Kapanış için fatura, scope ve task kontrolleri tamamlanmalı.":"Öncelik yüksek tutarlı PO'ların fatura girişi ve canceled/denied kayıtların admin scope kararlarıdır.")}
function makeTask(ref,owner="Accounting",q="Aksiyon gerekli"){setTask({ref,assigned_to:owner,question:q,action:"",due_date:""})}
function addTask(x){setData(p=>({...p,tasks:[{id:"TK-"+Date.now(),status:"Waiting Answer",answer:"",asked_by:"Director",...x},...p.tasks]}));setTask(null)}
function csvLoad(e){const file=e.target.files?.[0];if(!file)return;const rd=new FileReader();rd.onload=()=>{const lines=String(rd.result).split(/\r?\n/).filter(Boolean);const head=lines[0].split(/\t|;|,/).map(x=>x.trim());setCsv(lines.slice(1,9).map(l=>{const v=l.split(/\t|;|,/);return Object.fromEntries(head.map((h,i)=>[h,v[i]||""]))}))};rd.readAsText(file,"UTF-8")}
const noData=!loading&&!apiError&&!Object.values(data.summary||{}).some(v=>Number(v||0)!==0)&&!data.requests.length&&!data.conflicts.length&&!data.tasks.length&&!data.insights.length;
return <div className="bi13"><aside><div className="brand"><b/><div><strong>Budget Intelligence</strong><span>Executive Finance OS</span></div></div>{["Executive","Requests","Accounting","Construction","Reconciliation","Task Center","Imports","Admin Scope"].map(x=><button key={x} className={tab===x?"on":""} onClick={()=>setTab(x)}>{x}</button>)}</aside><main><header><div><em>EXECUTIVE CONTROL</em><h1>Budget Intelligence</h1><p>Saha operasyon bütçesi, fatura gerçekleşmesi, scope ayrıştırma ve conflict workflow.</p></div><div className="headBtns"><button onClick={()=>setAsk(true)}>Ask Budget AI</button><button onClick={()=>makeTask("", "Accounting","")}>Task Ata</button></div></header><section className="filters"><Sel l="Ay" v={filters.month} a={MONTHS} on={v=>f("month",v)}/><Sel l="Çeyrek" v={filters.quarter} a={Q} on={v=>f("quarter",v)}/><Sel l="Kategori" v={filters.category} a={CATS} on={v=>f("category",v)}/><Sel l="Scope" v={filters.scope} a={["All","Ops Relevant","Admin Review","Exclude Requested"]} on={v=>f("scope",v)}/><label className="check"><input type="checkbox" checked={filters.compare} onChange={e=>f("compare",e.target.checked)}/> Önceki dönemle kıyasla</label></section>
{loading&&<section className="bi-product-state" data-eay-product-state="loading" role="status" aria-busy="true" aria-live="polite" aria-atomic="true"><strong>{t("loading")}</strong></section>}
{!loading&&apiError&&<section className="bi-product-state" data-eay-product-state="error" role="alert" aria-atomic="true"><strong>{t("errorTitle")}</strong><button type="button" onClick={()=>setReloadKey(v=>v+1)}>{t("retry")}</button></section>}
{noData&&<section className="bi-product-state" data-eay-product-state="empty" role="status" aria-live="polite" aria-atomic="true"><strong>{t("emptyTitle")}</strong></section>}
{!loading&&!apiError&&!noData&&<div data-eay-product-state="ready">
{tab==="Executive"&&<Executive data={data} compare={filters.compare} open={setDrawer} makeTask={makeTask}/>}
{tab==="Requests"&&<Page title="Saha Talepleri"><RequestTable rows={data.requests} open={setDrawer}/></Page>}
{tab==="Accounting"&&<Accounting rows={data.requests} open={setDrawer}/>}
{tab==="Construction"&&<Construction rows={data.requests} open={setDrawer}/>}
{tab==="Reconciliation"&&<Page title="Conflict Center"><Conflict rows={data.conflicts} makeTask={makeTask}/></Page>}
{tab==="Task Center"&&<Page title="Task Center"><TaskList rows={data.tasks}/></Page>}
{tab==="Imports"&&<Page title="SQL / CSV Import"><div className="importBox"><p>Ariba sorgu çıktısını CSV/TSV olarak yükle. Sistem PR title/description üzerinden depo, iş tanımı, kategori ve scope önermeye hazırlanır.</p><input type="file" accept=".csv,.txt,.tsv" onChange={csvLoad}/></div><CsvPreview rows={csv}/></Page>}
{tab==="Admin Scope"&&<AdminScope rows={data.requests} open={setDrawer}/>}
</div>}
</main>{drawer&&<Drawer item={drawer} close={()=>setDrawer(null)} setData={setData}/>} {task&&<TaskModal x={task} set={setTask} add={addTask}/>} {ask&&<AIModal close={()=>setAsk(false)} prompt={prompt} setPrompt={setPrompt} run={askAI} result={ai}/>}</div>}
function Sel({l,v,a,on}){return <label>{l}<select value={v} onChange={e=>on(e.target.value)}>{a.map(x=><option key={x}>{x}</option>)}</select></label>}
function Executive({data,compare,open,makeTask}){const s=data.summary;return <><section className="kpis"><K t="Planlanan Bütçe" v={money(s.planned_budget)}/><K t="PO Commit" v={money(s.committed_po)}/><K t="Faturalanan Actual" v={money(s.invoiced_actual)}/><K t="Bekleyen Fatura" v={money(s.pending_invoice)} warn/><K t="Açık Conflict" v={s.open_conflicts}/></section><section className="execGrid"><Card title="Budget vs Actual Trend" wide><Trend rows={data.requests} compare={compare}/></Card><Card title="OPEX / CAPEX Split"><Donut rows={data.requests}/></Card><Card title="Kategori Harcaması"><Category rows={data.requests}/></Card><Card title="Executive Risk Queue"><Risk rows={data.requests} open={open} makeTask={makeTask}/></Card><Card title="AI Executive Notes" wide><div className="notes">{data.insights.map((i,idx)=><div key={idx}><span>{i.severity}</span><b>{i.title}</b><p>{i.text}</p></div>)}</div></Card></section></>}
function K({t,v,warn}){return <div className={"kpi "+(warn?"warn":"")}><span>{t}</span><h2>{v}</h2></div>}
function Card({title,children,wide}){return <section className={"card "+(wide?"wide":"")}><h3>{title}</h3>{children}</section>}
function Trend({rows,compare}){const months=["Mar","Apr","May","Jun","Jul","Aug"];const val=m=>rows.filter(r=>r.month===m).reduce((s,r)=>s+(r.invoice_amount||0),0);const commit=m=>rows.filter(r=>r.month===m).reduce((s,r)=>s+r.pr_amount,0);const max=Math.max(...months.map(m=>commit(m)),1);return <div className="trend">{months.map(m=><div key={m}><span className="commit" style={{height:`${commit(m)/max*100}%`}}/><span className="actual" style={{height:`${val(m)/max*100}%`}}/>{compare&&<i style={{height:`${Math.max(8,commit(m)*0.55/max*100)}%`}}/>}<em>{m}</em><small>{money(commit(m))}</small></div>)}</div>}
function Donut({rows}){const o=rows.filter(r=>(r.accounting_class||r.construction_class)==="OPEX").reduce((s,r)=>s+(r.invoice_amount||r.pr_amount),0),c=rows.filter(r=>(r.construction_class)==="CAPEX").reduce((s,r)=>s+(r.invoice_amount||r.pr_amount),0),p=Math.round(o/Math.max(o+c,1)*100);return <div className="donut"><div style={{background:`conic-gradient(#22d3ee 0 ${p}%,#df1067 ${p}% 100%)`}}><span>{p}% OPEX</span></div><p>OPEX {money(o)} · CAPEX {money(c)}</p></div>}
function Category({rows}){const map={};rows.forEach(r=>map[r.category]=(map[r.category]||0)+(r.invoice_amount||r.pr_amount));return <div className="cat">{Object.entries(map).sort((a,b)=>b[1]-a[1]).slice(0,6).map(([k,v])=><div key={k}><b>{k}</b><span>{money(v)}</span></div>)}</div>}
function Risk({rows,open,makeTask}){return <div className="risk">{rows.filter(r=>r.status!=="Invoiced").slice(0,6).map(r=><div key={r.id}><b>{r.id}</b><p>{r.store} · {r.category}</p><span>{r.status}</span><button onClick={()=>makeTask(r.id,r.status==="Pending Invoice"?"Accounting":"Admin",r.status+" için aksiyon gerekli")}>Task</button><button onClick={()=>open(r)}>Detay</button></div>)}</div>}
function Page({title,children}){return <section className="page"><h2>{title}</h2>{children}</section>}
function RequestTable({rows,open}){return <div className="table"><table><thead><tr><th>PR</th><th>PO</th><th>Depo</th><th>Kategori</th><th>İş Tanımı</th><th>PO Tutar</th><th>Fatura</th><th>Status</th><th>Scope</th></tr></thead><tbody>{rows.map(r=><tr key={r.id} onClick={()=>open(r)}><td>{r.id}</td><td>{r.po||"-"}</td><td>{r.store}</td><td>{r.category}</td><td>{r.work}</td><td>{money(r.pr_amount)}</td><td>{r.invoice_no}</td><td>{r.status}</td><td>{r.scope}</td></tr>)}</tbody></table></div>}
function Accounting({rows,open}){return <Page title="Muhasebe Alanı"><p className="sub">Muhasebe sadece fatura no, tutar, fatura tarihi, giriş tarihi ve muhasebe sınıfı alanlarını tamamlar. Fatura girilmeden actual oluşmaz.</p><RequestTable rows={rows.filter(r=>r.status==="Pending Invoice"||r.accounting_class==="Bekliyor"||r.status==="Conflict")} open={open}/></Page>}
function Construction({rows,open}){return <Page title="İnşaat Alanı"><p className="sub">İnşaat scope, iş gerekçesi, OPEX/CAPEX ön sınıfı ve “bize ait değil / iptal talebi” işaretlerini yönetir.</p><RequestTable rows={rows} open={open}/></Page>}
function AdminScope({rows,open}){return <Page title="Admin Scope Approval"><RequestTable rows={rows.filter(r=>r.scope!=="Ops Relevant")} open={open}/></Page>}
function Conflict({rows,makeTask}){return <div className="list">{rows.map(c=><div key={c.id}><span>{c.severity}</span><b>{c.type}</b><p>{c.message}</p><button onClick={()=>makeTask(c.ref,c.owner,c.message)}>Task Ata</button></div>)}</div>}
function TaskList({rows}){return <div className="list">{rows.map(t=><div key={t.id}><span>{t.status}</span><b>{t.ref} · {t.assigned_to}</b><p>{t.question}</p><small>Termin: {t.due_date||"-"}</small></div>)}</div>}
function CsvPreview({rows}){return rows.length?<div className="table"><table><tbody>{rows.map((r,i)=><tr key={i}>{Object.values(r).slice(0,8).map((v,j)=><td key={j}>{v}</td>)}</tr>)}</tbody></table></div>:<p className="sub">CSV seçilince ilk satırlar burada görünecek.</p>}
function Drawer({item,close,setData}){const[form,setForm]=useState({invoice_no:item.invoice_no||"",invoice_amount:item.invoice_amount||"",invoice_date:item.invoice_date||"",invoice_entry_date:item.invoice_entry_date||new Date().toISOString().slice(0,10),accounting_class:item.accounting_class||"OPEX",scope:item.scope||"Ops Relevant"});function save(){const up={...item,...form,invoice_amount:Number(form.invoice_amount||0),status:form.invoice_no&&form.invoice_no!=="Bekliyor"?"Invoiced":item.status};setData(p=>({...p,requests:p.requests.map(r=>r.id===item.id?up:r)}));close()}return <div className="drawerBg" onClick={close}><aside className="drawer" onClick={e=>e.stopPropagation()}><button className="x" onClick={close}>×</button><h2>{item.id}</h2><section className="invoice"><h3>Muhasebe Girişi</h3><input placeholder="Fatura No" value={form.invoice_no} onChange={e=>setForm({...form,invoice_no:e.target.value})}/><input type="number" placeholder="Fatura Tutarı" value={form.invoice_amount} onChange={e=>setForm({...form,invoice_amount:e.target.value})}/><input type="date" value={form.invoice_date} onChange={e=>setForm({...form,invoice_date:e.target.value})}/><input type="date" value={form.invoice_entry_date} onChange={e=>setForm({...form,invoice_entry_date:e.target.value})}/><select value={form.accounting_class} onChange={e=>setForm({...form,accounting_class:e.target.value})}><option>OPEX</option><option>CAPEX</option></select><button onClick={save}>Kaydet</button></section><section className="invoice"><h3>Scope Kararı</h3><select value={form.scope} onChange={e=>setForm({...form,scope:e.target.value})}><option>Ops Relevant</option><option>Admin Review</option><option>Exclude Requested</option><option>Not Our Scope</option><option>Canceled By Requester</option></select><button onClick={save}>Scope Kaydet</button></section><div className="detail">{Object.entries(item).map(([k,v])=><div key={k}><span>{k}</span><strong>{String(v)}</strong></div>)}</div></aside></div>}
function TaskModal({x,set,add}){return <div className="drawerBg"><div className="modal"><button className="x" onClick={()=>set(null)}>×</button><h2>Task Ata</h2><input placeholder="Ref" value={x.ref} onChange={e=>set({...x,ref:e.target.value})}/><select value={x.assigned_to} onChange={e=>set({...x,assigned_to:e.target.value})}><option>Accounting</option><option>Construction</option><option>Admin</option></select><textarea placeholder="Soru / sebep" value={x.question} onChange={e=>set({...x,question:e.target.value})}/><textarea placeholder="Beklenen aksiyon" value={x.action} onChange={e=>set({...x,action:e.target.value})}/><input type="date" value={x.due_date} onChange={e=>set({...x,due_date:e.target.value})}/><button onClick={()=>add(x)}>Task Oluştur</button></div></div>}
function AIModal({close,prompt,setPrompt,run,result}){return <div className="drawerBg"><div className="modal aiModal"><button className="x" onClick={close}>×</button><h2>Ask Budget AI</h2><textarea placeholder="Örn: Bu talep niye açıldı? Karlıktepe neden raporda? Fulya soğutucu harcaması neden arttı?" value={prompt} onChange={e=>setPrompt(e.target.value)}/><button onClick={run}>Yanıtla</button>{result&&<div className="aiResult">{result}</div>}</div></div>}
