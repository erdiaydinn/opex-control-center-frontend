import React, { useMemo, useState } from "react";
import { apiDownload } from "../../api/client.js";
import { usePlatformPreferences } from "../../platform/preferences/PlatformPreferencesContext.jsx";
import "./budget-control-tower.css";

const COPY = {
  tr:{eyebrow:"EAY · FINANCE",title:"Financial Control Tower",sub:"Bütçe, gerçekleşen, commitment, forecast ve finansal güvence aynı kanıta bağlı görünümde.",budget:"Bütçe",actual:"Gerçekleşen",commitment:"Commitment",forecast:"Forecast",headroom:"Kalan Alan",variance:"Forecast Farkı",util:"Kullanım",risk:"Kontrol Bulguları",cost:"Cost Center Performansı",category:"Kategori Görünümü",supplier:"Supplier Exposure",reports:"Yönetim Raporları",download:"Executive CSV",downloading:"Hazırlanıyor…",evidence:"Kanıt",human:"İnsan incelemesi gerekli",noMutation:"AI finansal kaydı değiştiremez",portfolio:"Finansal Durum",healthy:"Kontrol altında",watch:"Yakın izleme",critical:"Müdahale gerekli",priority:"Öncelikli karar kuyruğu",actualCol:"Actual",forecastCol:"Forecast",varianceCol:"Fark",exposure:"Exposure",empty:"Gösterilecek kayıt yok",budgetCoverage:"Forecast / Bütçe",findingCount:"Açık bulgu",assurance:"Assurance bağlı",rank:"Sıra"},
  en:{eyebrow:"EAY · FINANCE",title:"Financial Control Tower",sub:"Budget, actuals, commitments, forecast and assurance on one evidence-bound surface.",budget:"Budget",actual:"Actual",commitment:"Commitment",forecast:"Forecast",headroom:"Headroom",variance:"Forecast Variance",util:"Utilization",risk:"Control Findings",cost:"Cost Center Performance",category:"Category View",supplier:"Supplier Exposure",reports:"Management Reports",download:"Executive CSV",downloading:"Preparing…",evidence:"Evidence",human:"Human review required",noMutation:"AI cannot mutate financial truth",portfolio:"Financial Position",healthy:"Under control",watch:"Watch closely",critical:"Intervention required",priority:"Priority decision queue",actualCol:"Actual",forecastCol:"Forecast",varianceCol:"Variance",exposure:"Exposure",empty:"No records to display",budgetCoverage:"Forecast / Budget",findingCount:"Open findings",assurance:"Assurance bound",rank:"Rank"},
  de:{eyebrow:"EAY · FINANCE",title:"Financial Control Tower",sub:"Budget, Ist, Verpflichtungen, Forecast und Assurance in einer evidenzgebundenen Sicht.",budget:"Budget",actual:"Ist",commitment:"Verpflichtung",forecast:"Forecast",headroom:"Spielraum",variance:"Forecast-Abweichung",util:"Auslastung",risk:"Kontrollbefunde",cost:"Kostenstellen",category:"Kategorien",supplier:"Lieferantenexposure",reports:"Managementberichte",download:"Executive CSV",downloading:"Wird erstellt…",evidence:"Evidenz",human:"Menschliche Prüfung erforderlich",noMutation:"KI ändert keine Finanzwahrheit",portfolio:"Finanzlage",healthy:"Unter Kontrolle",watch:"Genau beobachten",critical:"Eingriff erforderlich",priority:"Priorisierte Entscheidungen",actualCol:"Ist",forecastCol:"Forecast",varianceCol:"Abweichung",exposure:"Exposure",empty:"Keine Datensätze",budgetCoverage:"Forecast / Budget",findingCount:"Offene Befunde",assurance:"Assurance gebunden",rank:"Rang"},
  ar:{eyebrow:"EAY · المالية",title:"مركز الرقابة المالية",sub:"الميزانية والفعلي والالتزامات والتوقعات والضمان المالي في عرض موثق واحد.",budget:"الميزانية",actual:"الفعلي",commitment:"الالتزام",forecast:"التوقع",headroom:"المتبقي",variance:"فرق التوقع",util:"الاستخدام",risk:"نتائج الرقابة",cost:"مراكز التكلفة",category:"الفئات",supplier:"تعرض الموردين",reports:"تقارير الإدارة",download:"CSV تنفيذي",downloading:"جارٍ التحضير…",evidence:"الدليل",human:"تتطلب مراجعة بشرية",noMutation:"الذكاء الاصطناعي لا يغير الحقيقة المالية",portfolio:"الموقف المالي",healthy:"تحت السيطرة",watch:"مراقبة دقيقة",critical:"يتطلب تدخلاً",priority:"قائمة القرارات ذات الأولوية",actualCol:"الفعلي",forecastCol:"التوقع",varianceCol:"الفرق",exposure:"التعرض",empty:"لا توجد سجلات للعرض",budgetCoverage:"التوقع / الميزانية",findingCount:"النتائج المفتوحة",assurance:"الضمان مرتبط",rank:"الترتيب"},
  fr:{eyebrow:"EAY · FINANCE",title:"Financial Control Tower",sub:"Budget, réel, engagements, prévision et assurance sur une vue liée aux preuves.",budget:"Budget",actual:"Réel",commitment:"Engagement",forecast:"Prévision",headroom:"Marge",variance:"Écart prévision",util:"Utilisation",risk:"Constats de contrôle",cost:"Centres de coûts",category:"Catégories",supplier:"Exposition fournisseurs",reports:"Rapports de gestion",download:"CSV exécutif",downloading:"Préparation…",evidence:"Preuve",human:"Revue humaine requise",noMutation:"L'IA ne modifie pas la vérité financière",portfolio:"Position financière",healthy:"Sous contrôle",watch:"Surveillance étroite",critical:"Intervention requise",priority:"File de décisions prioritaires",actualCol:"Réel",forecastCol:"Prévision",varianceCol:"Écart",exposure:"Exposition",empty:"Aucun enregistrement",budgetCoverage:"Prévision / Budget",findingCount:"Constats ouverts",assurance:"Assurance liée",rank:"Rang"},
  es:{eyebrow:"EAY · FINANCE",title:"Financial Control Tower",sub:"Presupuesto, real, compromisos, forecast y assurance en una vista basada en evidencia.",budget:"Presupuesto",actual:"Real",commitment:"Compromiso",forecast:"Forecast",headroom:"Margen",variance:"Variación forecast",util:"Utilización",risk:"Hallazgos de control",cost:"Centros de coste",category:"Categorías",supplier:"Exposición proveedores",reports:"Informes de gestión",download:"CSV ejecutivo",downloading:"Preparando…",evidence:"Evidencia",human:"Revisión humana requerida",noMutation:"La IA no modifica la verdad financiera",portfolio:"Posición financiera",healthy:"Bajo control",watch:"Vigilar de cerca",critical:"Intervención requerida",priority:"Cola de decisiones prioritarias",actualCol:"Real",forecastCol:"Forecast",varianceCol:"Variación",exposure:"Exposición",empty:"No hay registros",budgetCoverage:"Forecast / Presupuesto",findingCount:"Hallazgos abiertos",assurance:"Assurance vinculada",rank:"Rango"},
  it:{eyebrow:"EAY · FINANCE",title:"Financial Control Tower",sub:"Budget, actual, impegni, forecast e assurance in una vista legata alle evidenze.",budget:"Budget",actual:"Actual",commitment:"Impegno",forecast:"Forecast",headroom:"Margine",variance:"Scostamento forecast",util:"Utilizzo",risk:"Rilievi di controllo",cost:"Centri di costo",category:"Categorie",supplier:"Esposizione fornitori",reports:"Report direzionali",download:"CSV executive",downloading:"Preparazione…",evidence:"Evidenza",human:"Revisione umana richiesta",noMutation:"L'IA non modifica la verità finanziaria",portfolio:"Posizione finanziaria",healthy:"Sotto controllo",watch:"Monitorare da vicino",critical:"Intervento richiesto",priority:"Coda decisioni prioritarie",actualCol:"Actual",forecastCol:"Forecast",varianceCol:"Scostamento",exposure:"Esposizione",empty:"Nessun record",budgetCoverage:"Forecast / Budget",findingCount:"Rilievi aperti",assurance:"Assurance collegata",rank:"Posizione"},
  nl:{eyebrow:"EAY · FINANCE",title:"Financial Control Tower",sub:"Budget, actuals, verplichtingen, forecast en assurance in één evidence-gebonden view.",budget:"Budget",actual:"Actual",commitment:"Verplichting",forecast:"Forecast",headroom:"Ruimte",variance:"Forecastverschil",util:"Benutting",risk:"Controlebevindingen",cost:"Kostenplaatsen",category:"Categorieën",supplier:"Leveranciersblootstelling",reports:"Managementrapporten",download:"Executive CSV",downloading:"Voorbereiden…",evidence:"Bewijs",human:"Menselijke review vereist",noMutation:"AI wijzigt financiële waarheid niet",portfolio:"Financiële positie",healthy:"Onder controle",watch:"Nauw volgen",critical:"Interventie vereist",priority:"Prioritaire besliswachtrij",actualCol:"Actual",forecastCol:"Forecast",varianceCol:"Verschil",exposure:"Blootstelling",empty:"Geen records",budgetCoverage:"Forecast / Budget",findingCount:"Open bevindingen",assurance:"Assurance gekoppeld",rank:"Rang"},
  pl:{eyebrow:"EAY · FINANCE",title:"Financial Control Tower",sub:"Budżet, wykonanie, zobowiązania, prognoza i assurance w jednym widoku opartym na dowodach.",budget:"Budżet",actual:"Wykonanie",commitment:"Zobowiązanie",forecast:"Prognoza",headroom:"Pozostało",variance:"Odchylenie prognozy",util:"Wykorzystanie",risk:"Ustalenia kontrolne",cost:"Centra kosztów",category:"Kategorie",supplier:"Ekspozycja dostawców",reports:"Raporty zarządcze",download:"CSV Executive",downloading:"Przygotowanie…",evidence:"Dowód",human:"Wymagana weryfikacja człowieka",noMutation:"AI nie zmienia prawdy finansowej",portfolio:"Pozycja finansowa",healthy:"Pod kontrolą",watch:"Ścisły monitoring",critical:"Wymagana interwencja",priority:"Priorytetowa kolejka decyzji",actualCol:"Wykonanie",forecastCol:"Prognoza",varianceCol:"Odchylenie",exposure:"Ekspozycja",empty:"Brak rekordów",budgetCoverage:"Prognoza / Budżet",findingCount:"Otwarte ustalenia",assurance:"Assurance powiązane",rank:"Pozycja"},
  "pt-BR":{eyebrow:"EAY · FINANCE",title:"Financial Control Tower",sub:"Orçamento, realizado, compromissos, forecast e assurance em uma visão vinculada a evidências.",budget:"Orçamento",actual:"Realizado",commitment:"Compromisso",forecast:"Forecast",headroom:"Saldo",variance:"Variação forecast",util:"Utilização",risk:"Achados de controle",cost:"Centros de custo",category:"Categorias",supplier:"Exposição fornecedores",reports:"Relatórios gerenciais",download:"CSV executivo",downloading:"Preparando…",evidence:"Evidência",human:"Revisão humana necessária",noMutation:"A IA não altera a verdade financeira",portfolio:"Posição financeira",healthy:"Sob controle",watch:"Monitorar de perto",critical:"Intervenção necessária",priority:"Fila de decisões prioritárias",actualCol:"Realizado",forecastCol:"Forecast",varianceCol:"Variação",exposure:"Exposição",empty:"Nenhum registro",budgetCoverage:"Forecast / Orçamento",findingCount:"Achados abertos",assurance:"Assurance vinculada",rank:"Posição"}
};

const money=(v,locale)=>new Intl.NumberFormat(locale||"tr-TR",{style:"currency",currency:"TRY",maximumFractionDigits:0}).format(Number(v||0));
const pct=(v,locale)=>`${Number(v||0).toLocaleString(locale||undefined,{maximumFractionDigits:1})}%`;
const severityRank={critical:4,high:3,medium:2,low:1};

export default function BudgetControlTower({data}){
  const { locale="tr", localeMeta }=usePlatformPreferences();
  const dir=localeMeta?.dir||"ltr";
  const c=COPY[locale]||COPY.en;
  const [exporting,setExporting]=useState(false);
  const s=data?.summary||{};
  const costCenters=useMemo(()=>[...(data?.cost_centers||[])].sort((a,b)=>Number(b.forecast_variance||0)-Number(a.forecast_variance||0)),[data]);
  const findings=useMemo(()=>[...(data?.findings||[])].sort((a,b)=>(severityRank[String(b.severity||"").toLowerCase()]||0)-(severityRank[String(a.severity||"").toLowerCase()]||0)),[data]);
  const suppliers=useMemo(()=>[...(data?.suppliers||[])].sort((a,b)=>Number(b.exposure||0)-Number(a.exposure||0)),[data]);
  const maxCost=useMemo(()=>Math.max(1,...costCenters.map(x=>Math.max(Number(x.budget||0),Number(x.forecast||0)))),[costCenters]);
  const utilization=Number(s.forecast_utilization_pct||0);
  const headroom=Number(s.remaining_headroom||0);
  const criticalFindings=findings.filter(x=>["critical","high"].includes(String(x.severity||"").toLowerCase())).length;
  const posture=headroom<0||utilization>105||criticalFindings>0?"critical":utilization>=95||findings.length>0?"watch":"healthy";
  const postureLabel=posture==="critical"?c.critical:posture==="watch"?c.watch:c.healthy;

  async function download(){
    if(exporting)return;
    setExporting(true);
    try{
      const blob=await apiDownload("/v1/budget/reports/executive.csv");
      const url=URL.createObjectURL(blob);
      const a=document.createElement("a");
      a.href=url;a.download="eay-budget-executive-pack.csv";a.click();
      URL.revokeObjectURL(url);
    }finally{setExporting(false)}
  }

  return <main className="bct" dir={dir}>
    <header className="bct-head">
      <div><span>{c.eyebrow}</span><h1>{c.title}</h1><p>{c.sub}</p></div>
      <button type="button" onClick={download} disabled={exporting}>{exporting?c.downloading:c.download}</button>
    </header>

    <section className={`bct-posture ${posture}`} aria-label={c.portfolio}>
      <div><span>{c.portfolio}</span><strong>{postureLabel}</strong></div>
      <div><span>{c.budgetCoverage}</span><strong>{pct(utilization,locale)}</strong></div>
      <div><span>{c.findingCount}</span><strong>{findings.length}</strong></div>
      <div><span>{c.assurance}</span><strong>{String(data?.evidence_fingerprint||"").slice(0,12)}…</strong></div>
    </section>

    <section className="bct-kpis">
      <K l={c.budget} v={money(s.budget,locale)}/><K l={c.actual} v={money(s.actual,locale)}/><K l={c.commitment} v={money(s.commitment,locale)}/><K l={c.forecast} v={money(s.forecast,locale)} hot={Number(s.forecast_variance)>0}/><K l={c.headroom} v={money(s.remaining_headroom,locale)} hot={headroom<0}/><K l={c.variance} v={money(s.forecast_variance,locale)} hot={Number(s.forecast_variance)>0}/>
    </section>

    <section className="bct-grid">
      <Card title={c.cost} wide>
        {costCenters.length?<div className="bct-bars">{costCenters.slice(0,12).map((x,index)=><div className="bct-bar" key={x.cost_center}><span className="bct-rank">{index+1}</span><b>{x.cost_center}</b><div><i data-over={Number(x.forecast||0)>Number(x.budget||0)} style={{width:`${Math.min(100,Number(x.forecast||0)/maxCost*100)}%`}}/></div><span>{money(x.forecast,locale)} / {money(x.budget,locale)}</span></div>)}</div>:<Empty text={c.empty}/>} 
      </Card>

      <Card title={c.priority}>
        {findings.length?<div className="bct-findings">{findings.slice(0,10).map(x=><article key={x.finding_id} data-severity={String(x.severity||"").toLowerCase()}><span>{x.severity}</span><b>{x.cost_center} · {x.category}</b><p>{x.reason}</p><p>{money(x.forecast,locale)} / {money(x.budget,locale)}</p><small>{c.evidence}: {String(x.evidence_fingerprint||"").slice(0,16)}… · {c.human}</small></article>)}</div>:<Empty text={c.empty}/>} 
      </Card>

      <Card title={c.category}>
        {(data?.categories||[]).length?<div className="bct-table" role="table"><div className="bct-table-head" role="row"><b>{c.category}</b><span>{c.actualCol}</span><span>{c.forecastCol}</span><span>{c.varianceCol}</span></div>{(data.categories||[]).slice(0,10).map(x=><div key={x.category} role="row"><b>{x.category}</b><span>{money(x.actual,locale)}</span><span>{money(x.forecast,locale)}</span><span className={Number(x.forecast_variance)>0?"negative":"positive"}>{money(x.forecast_variance,locale)}</span></div>)}</div>:<Empty text={c.empty}/>} 
      </Card>

      <Card title={c.supplier}>
        {suppliers.length?<ol className="bct-suppliers">{suppliers.slice(0,10).map((x,index)=><li key={x.supplier}><span><small>{c.rank} {index+1}</small>{x.supplier}</span><b>{money(x.exposure,locale)}</b></li>)}</ol>:<Empty text={c.empty}/>} 
      </Card>

      <Card title={c.reports} wide>
        <div className="bct-reports">{(data?.report_catalog||[]).map(x=><span key={x}>{String(x).replaceAll("_"," ")}</span>)}</div>
        <footer><code>{String(data?.evidence_fingerprint||"").slice(0,24)}…</code><strong>{c.noMutation}</strong></footer>
      </Card>
    </section>
  </main>
}
function K({l,v,hot}){return <div className={hot?"bct-kpi hot":"bct-kpi"}><span>{l}</span><strong>{v}</strong></div>}
function Card({title,children,wide}){return <section className={wide?"bct-card wide":"bct-card"}><h2>{title}</h2>{children}</section>}
function Empty({text}){return <p className="bct-empty">{text}</p>}
