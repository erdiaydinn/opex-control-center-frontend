import React, { useMemo, useState } from "react";
import {
  Activity,
  AlertTriangle,
  ArrowRight,
  BadgeCheck,
  BarChart3,
  BookOpen,
  Boxes,
  BrainCircuit,
  Building2,
  Check,
  CheckCircle2,
  ChevronRight,
  CircleDot,
  Clock3,
  FileText,
  GraduationCap,
  Layers3,
  LayoutDashboard,
  ListChecks,
  LockKeyhole,
  MessageSquareText,
  Network,
  PackageCheck,
  Play,
  Radio,
  Search,
  ShieldCheck,
  Sparkles,
  Target,
  Users,
  Video,
  WandSparkles,
  Workflow,
  X,
} from "lucide-react";

import "./eayExperience.css";

const TENANTS = {
  atlas: {
    id: "atlas",
    name: "Atlas Retail",
    label: "Demo şirket A",
    initials: "AR",
    location: "Türkiye",
    accent: "#df1067",
  },
  northstar: {
    id: "northstar",
    name: "Northstar Commerce",
    label: "Demo şirket B",
    initials: "NC",
    location: "Europe",
    accent: "#19a7a5",
  },
};

const MODULES = [
  { id: "academy", name: "Academy", status: "Preview", meta: "Learning OS · Jarvis Teacher", icon: GraduationCap, view: "academy" },
  { id: "jarvis", name: "Jarvis", status: "Preview", meta: "Insight · Security · Actions", icon: BrainCircuit, view: "jarvis" },
  { id: "workforce", name: "Workforce", status: "Integrated", meta: "Employee · Shift · Attendance", icon: Users },
  { id: "inventory", name: "Inventory", status: "Integrated", meta: "Count · Variance · Terminal", icon: Boxes },
  { id: "dockos", name: "DockOS", status: "Integrated", meta: "PO · Slot · Dock", icon: PackageCheck },
  { id: "budget", name: "Budget", status: "Integrated", meta: "Budget · Approval · Actual", icon: BarChart3 },
  { id: "planogram", name: "Planogram", status: "Data gated", meta: "ABC · Affinity · Physical truth", icon: Layers3 },
  { id: "insight", name: "Insight", status: "Live-data gated", meta: "KPI · Signal · Decision", icon: Activity },
];

const LEARNING_ITEMS = [
  {
    id: "food-safety",
    title: "Gıda Güvenliği · Temizlik Renk Standardı",
    format: "Interactive video",
    duration: "8 dk",
    progress: 42,
    mastery: 68,
    due: "Bugün",
    state: "continue",
  },
  {
    id: "cold-chain",
    title: "Soğuk Zincir · Kritik Kontrol Noktaları",
    format: "Scenario + field task",
    duration: "12 dk",
    progress: 100,
    mastery: 91,
    due: "30 gün sonra tekrar",
    state: "retention",
  },
  {
    id: "picking-quality",
    title: "Picking Quality · Hata Önleme",
    format: "Adaptive path",
    duration: "6–15 dk",
    progress: 0,
    mastery: null,
    due: "Rol bazlı öneri",
    state: "next",
  },
];

const STUDIO_BLOCKS = [
  { time: "00:00", type: "Video", label: "Açılış ve amaç", icon: Play },
  { time: "01:48", type: "Checkpoint", label: "Mavi bez hangi alanda?", icon: CircleDot },
  { time: "03:42", type: "Hotspot", label: "Renk standardı görseli", icon: Target },
  { time: "05:10", type: "Branch", label: "Yanlış uygulama senaryosu", icon: Workflow },
  { time: "07:25", type: "Field task", label: "Vardiyada doğrula", icon: ListChecks },
];

const SECURITY_STEPS = ["Tespit", "Etki analizi", "Onay", "Patch", "Regression", "Doğrulama"];

function DemoBadge({ compact = false }) {
  return (
    <span className={`eay-demo-badge${compact ? " eay-demo-badge--compact" : ""}`}>
      <Radio size={13} aria-hidden="true" /> DEMO · synthetic data
    </span>
  );
}

function Metric({ label, value, detail, trend }) {
  return (
    <article className="eay-metric">
      <div className="eay-metric__label">{label}</div>
      <div className="eay-metric__value">{value}</div>
      <div className="eay-metric__detail">
        {trend ? <span className="eay-positive">{trend}</span> : null}
        {detail}
      </div>
    </article>
  );
}

function Overview({ onNavigate, tenant }) {
  const featured = MODULES.slice(0, 2);
  return (
    <div className="eay-view-stack">
      <section className="eay-hero-grid">
        <div className="eay-hero-copy">
          <div className="eay-kicker">EAY PLATFORM · EXPERIENCE BUILD</div>
          <h1>İşletmenin tamamını tek, güvenli ve öğrenen bir sistemde yönetin.</h1>
          <p>
            Bu build, production verisine dokunmadan EAY ürün deneyimini görmeniz için hazırlanmıştır.
            Gerçek modül mimarisi korunur; Academy ve Jarvis’in yeni ürün yüzeyi sentetik verilerle çalışır.
          </p>
          <div className="eay-hero-actions">
            <button className="eay-button eay-button--primary" onClick={() => onNavigate("academy")}>
              Academy’yi dene <ArrowRight size={17} />
            </button>
            <button className="eay-button eay-button--quiet" onClick={() => onNavigate("jarvis")}>
              Jarvis’i dene <BrainCircuit size={17} />
            </button>
          </div>
        </div>
        <aside className="eay-trust-panel" aria-label="Preview güvenlik sınırları">
          <div className="eay-trust-panel__title">
            <ShieldCheck size={19} /> Preview güvenlik sınırı
          </div>
          <ul>
            <li><Check size={16} /> Production auth/RLS değiştirilmez.</li>
            <li><Check size={16} /> Ham şirket verisi bu build’e gömülmez.</li>
            <li><Check size={16} /> Tenant değişiminde demo state sıfırlanır.</li>
            <li><Check size={16} /> Jarvis aksiyonları gerçek mutation yapmaz.</li>
          </ul>
          <div className="eay-tenant-proof">
            <LockKeyhole size={17} />
            <div>
              <strong>{tenant.name}</strong>
              <span>Aktif demo tenant · diğer tenant verisi görünmez</span>
            </div>
          </div>
        </aside>
      </section>

      <section>
        <div className="eay-section-heading">
          <div>
            <span>Ürün yüzeyi</span>
            <h2>Bir platform, uzmanlaşmış modüller.</h2>
          </div>
          <DemoBadge compact />
        </div>
        <div className="eay-module-grid">
          {MODULES.map((module) => {
            const Icon = module.icon;
            const actionable = Boolean(module.view);
            return (
              <button
                key={module.id}
                className={`eay-module-card${actionable ? " eay-module-card--actionable" : ""}`}
                type="button"
                onClick={() => actionable && onNavigate(module.view)}
                disabled={!actionable}
              >
                <span className="eay-module-card__icon"><Icon size={20} /></span>
                <span className="eay-module-card__body">
                  <span className="eay-module-card__head">
                    <strong>{module.name}</strong>
                    <span>{module.status}</span>
                  </span>
                  <small>{module.meta}</small>
                </span>
                {actionable ? <ChevronRight size={18} /> : <LockKeyhole size={15} />}
              </button>
            );
          })}
        </div>
      </section>

      <section className="eay-overview-bottom">
        <div className="eay-panel eay-panel--architecture">
          <div className="eay-panel-heading">
            <div><span>Platform principle</span><h3>Tenant boundary is infrastructure, not a filter.</h3></div>
            <Network size={21} />
          </div>
          <div className="eay-architecture-flow" aria-label="Tenant isolation layers">
            {["Identity", "Policy", "RLS", "Retrieval", "Tools", "Audit"].map((item, index) => (
              <React.Fragment key={item}>
                <span>{item}</span>
                {index < 5 ? <ChevronRight size={15} /> : null}
              </React.Fragment>
            ))}
          </div>
          <p>Demo tenant switch yalnız deneyim state’ini değiştirir; production tenant güvenliğinin kanıtı değildir.</p>
        </div>
        <div className="eay-panel eay-panel--signal">
          <div className="eay-signal-icon"><Sparkles size={21} /></div>
          <div>
            <span>Jarvis advantage</span>
            <h3>Know the company. Know the learner. Know the operation.</h3>
            <p>Kaynaklı bilgi, yetki bağlamı, geçmiş öğrenme ve operasyon sinyalleri tek karar yüzeyinde.</p>
          </div>
        </div>
      </section>
    </div>
  );
}

function Academy({ tenant }) {
  const [mode, setMode] = useState("learner");
  const [teacherQuestion, setTeacherQuestion] = useState("Mavi bez ile kırmızı bez arasındaki fark nedir?");
  const [teacherAnswer, setTeacherAnswer] = useState(null);
  const [assigned, setAssigned] = useState(false);
  const [selectedBlock, setSelectedBlock] = useState("03:42");
  const [audiences, setAudiences] = useState(["Picker", "Store Manager"]);

  const askTeacher = () => {
    setTeacherAnswer({
      title: "Temizlik renk standardı",
      body: "Mavi ve kırmızı bez farklı temizlik bölgelerini ayırmak için kullanılır. Bu demo, gerçek şirket prosedürü değildir; production’da Jarvis yalnız tenant’ın onaylı ve versiyonlu kaynağından cevap verir.",
      source: "Gıda Güvenliği · Temizlik Renk Standardı · v3.2",
      timestamp: "03:42–04:31",
      completion: "Bu eğitimin %42’sini tamamladın. İlgili bölümü henüz doğrulamadın.",
    });
    setAssigned(false);
  };

  const toggleAudience = (audience) => {
    setAudiences((current) => current.includes(audience)
      ? current.filter((item) => item !== audience)
      : [...current, audience]);
  };

  return (
    <div className="eay-view-stack">
      <section className="eay-view-header">
        <div>
          <div className="eay-kicker">ACADEMY · LEARNING OPERATING SYSTEM</div>
          <h1>İzleneni değil, öğrenileni yönetin.</h1>
          <p>Adaptive learning, interactive content, retention ve Jarvis Teacher aynı ürün yüzeyinde.</p>
        </div>
        <div className="eay-segmented" role="tablist" aria-label="Academy görünümü">
          <button className={mode === "learner" ? "active" : ""} onClick={() => setMode("learner")}>Learner</button>
          <button className={mode === "studio" ? "active" : ""} onClick={() => setMode("studio")}>Content Studio</button>
        </div>
      </section>

      {mode === "learner" ? (
        <>
          <div className="eay-metric-grid">
            <Metric label="Mastery" value="84" detail=" / 100" trend="+6 " />
            <Metric label="Retention" value="91%" detail="30 günlük recall" />
            <Metric label="Bugün" value="14 dk" detail="next-best learning" />
            <Metric label="Field proof" value="3 / 4" detail="yönetici doğrulamalı" />
          </div>

          <section className="eay-academy-grid">
            <div className="eay-panel eay-learning-queue">
              <div className="eay-panel-heading">
                <div><span>Senin için sıradaki</span><h3>Learning queue</h3></div>
                <WandSparkles size={20} />
              </div>
              {LEARNING_ITEMS.map((item) => (
                <article className="eay-learning-item" key={item.id}>
                  <div className="eay-learning-item__icon"><BookOpen size={18} /></div>
                  <div className="eay-learning-item__content">
                    <div className="eay-learning-item__top">
                      <strong>{item.title}</strong>
                      <span>{item.duration}</span>
                    </div>
                    <small>{item.format} · {item.due}</small>
                    <div className="eay-progress" aria-label={`${item.progress}% tamamlandı`}>
                      <span style={{ width: `${item.progress}%` }} />
                    </div>
                  </div>
                  <div className="eay-learning-item__mastery">
                    <span>Mastery</span>
                    <strong>{item.mastery ?? "—"}</strong>
                  </div>
                </article>
              ))}
            </div>

            <div className="eay-panel eay-teacher">
              <div className="eay-teacher__head">
                <div className="eay-jarvis-orb"><BrainCircuit size={21} /></div>
                <div><span>Jarvis Teacher</span><strong>{tenant.name} bilgi alanı</strong></div>
                <DemoBadge compact />
              </div>
              <label className="eay-prompt-box">
                <span>Bir eğitim sorusu sor</span>
                <textarea value={teacherQuestion} onChange={(event) => setTeacherQuestion(event.target.value)} rows={3} />
                <button className="eay-button eay-button--primary" type="button" onClick={askTeacher}>
                  Açıkla <ArrowRight size={16} />
                </button>
              </label>
              {teacherAnswer ? (
                <div className="eay-answer-card">
                  <div className="eay-answer-card__status"><BadgeCheck size={16} /> Kaynaklı demo cevap</div>
                  <h4>{teacherAnswer.title}</h4>
                  <p>{teacherAnswer.body}</p>
                  <div className="eay-source-card">
                    <FileText size={17} />
                    <div><strong>{teacherAnswer.source}</strong><span>{teacherAnswer.timestamp}</span></div>
                  </div>
                  <div className="eay-learning-state"><Clock3 size={16} /> {teacherAnswer.completion}</div>
                  <div className="eay-inline-actions">
                    <button className="eay-button eay-button--quiet" type="button">03:42’ye git</button>
                    <button className="eay-button eay-button--primary" type="button" onClick={() => setAssigned(true)} disabled={assigned}>
                      {assigned ? <><Check size={16} /> Görev atandı</> : "2 soruluk görev ata"}
                    </button>
                  </div>
                </div>
              ) : (
                <div className="eay-empty-state"><MessageSquareText size={22} /><span>Soruyu gönder; Jarvis kaynak + öğrenme geçmişi + sonraki aksiyonu birlikte göstersin.</span></div>
              )}
            </div>
          </section>
        </>
      ) : (
        <section className="eay-studio-grid">
          <div className="eay-panel eay-studio-canvas">
            <div className="eay-panel-heading">
              <div><span>Interactive video editor</span><h3>Gıda Güvenliği · v3.2</h3></div>
              <div className="eay-studio-status"><CircleDot size={13} /> Taslak</div>
            </div>
            <div className="eay-video-stage">
              <div className="eay-video-stage__chrome">
                <span><Video size={17} /> 1080p · TR</span><span>03:42 / 08:04</span>
              </div>
              <div className="eay-video-stage__focus">
                <Target size={33} />
                <strong>Hotspot preview</strong>
                <span>Kullanıcı doğru temizlik ekipmanını seçer.</span>
              </div>
            </div>
            <div className="eay-timeline" aria-label="Etkileşim zaman çizgisi">
              {STUDIO_BLOCKS.map((block) => {
                const BlockIcon = block.icon;
                return (
                  <button key={block.time} type="button" className={selectedBlock === block.time ? "active" : ""} onClick={() => setSelectedBlock(block.time)}>
                    <span>{block.time}</span><BlockIcon size={15} /><strong>{block.type}</strong><small>{block.label}</small>
                  </button>
                );
              })}
            </div>
          </div>

          <aside className="eay-panel eay-studio-inspector">
            <div className="eay-panel-heading"><div><span>Publish controls</span><h3>Kime, ne şartla?</h3></div><ShieldCheck size={20} /></div>
            <div className="eay-inspector-group">
              <label>Hedef kullanıcı grubu</label>
              <div className="eay-chip-row">
                {["Picker", "Store Manager", "Inbound", "New hire"].map((audience) => (
                  <button type="button" key={audience} className={audiences.includes(audience) ? "selected" : ""} onClick={() => toggleAudience(audience)}>
                    {audiences.includes(audience) ? <Check size={13} /> : null}{audience}
                  </button>
                ))}
              </div>
            </div>
            <div className="eay-rule-list">
              <div><CheckCircle2 size={16} /><span><strong>Completion</strong> Video + 2 checkpoint + field task</span></div>
              <div><CheckCircle2 size={16} /><span><strong>Pass rule</strong> Mastery ≥ 80</span></div>
              <div><CheckCircle2 size={16} /><span><strong>Retention</strong> 7 / 30 / 90 gün recall</span></div>
              <div><CheckCircle2 size={16} /><span><strong>Prerequisite</strong> Gıda Güvenliği Temelleri</span></div>
            </div>
            <button className="eay-button eay-button--primary eay-button--full" type="button">Önizlemeyi yayınla</button>
            <p className="eay-fineprint">Demo butonu gerçek içerik yayınlamaz. Production’da versioned approval + tenant entitlement gerekir.</p>
          </aside>
        </section>
      )}
    </div>
  );
}

function Jarvis({ tenant }) {
  const [mode, setMode] = useState("operations");
  const [query, setQuery] = useState("Son iki haftada operasyon açısından en kritik sinyal nedir?");
  const [result, setResult] = useState(null);
  const [securityStep, setSecurityStep] = useState(1);
  const [approved, setApproved] = useState(false);

  const runQuery = () => {
    setResult({
      headline: "Tek bir KPI yerine birlikte hareket eden üç sinyal önceliklendirildi.",
      findings: [
        "Sipariş baskısı artarken picking süresi aynı oranda toparlanmıyor.",
        "Kalite sinyali network geneline yayılmadığı için lokal süreç/kadro hipotezi daha güçlü.",
        "Tarihsel baseline benzer dönemlerde hacim artışını gösteriyor; mevcut sapmanın tamamını sezonsallık açıklamıyor.",
      ],
      confidence: "Orta–yüksek",
      source: "Synthetic KPI fixture · Historical-memory contract preview",
    });
  };

  const advanceSecurity = () => {
    if (!approved) {
      setApproved(true);
      setSecurityStep(2);
      return;
    }
    setSecurityStep((current) => Math.min(current + 1, SECURITY_STEPS.length - 1));
  };

  return (
    <div className="eay-view-stack">
      <section className="eay-view-header">
        <div>
          <div className="eay-kicker">JARVIS · GOVERNED INTELLIGENCE</div>
          <h1>Bilgiyi değil, güvenilir kararı hızlandır.</h1>
          <p>Kaynak, tenant, yetki, risk ve aksiyon kanıtı aynı konuşmanın içinde.</p>
        </div>
        <div className="eay-segmented" role="tablist" aria-label="Jarvis görünümü">
          <button className={mode === "operations" ? "active" : ""} onClick={() => setMode("operations")}>Operations</button>
          <button className={mode === "security" ? "active" : ""} onClick={() => setMode("security")}>Security Guardian</button>
        </div>
      </section>

      {mode === "operations" ? (
        <section className="eay-jarvis-grid">
          <div className="eay-panel eay-jarvis-console">
            <div className="eay-console-header">
              <div className="eay-jarvis-orb"><BrainCircuit size={22} /></div>
              <div><strong>Jarvis</strong><span>{tenant.name} · authorized context preview</span></div>
              <DemoBadge compact />
            </div>
            <div className="eay-conversation">
              <div className="eay-message eay-message--user"><span>Sen</span><p>{query}</p></div>
              {result ? (
                <div className="eay-message eay-message--jarvis">
                  <span>Jarvis</span>
                  <h4>{result.headline}</h4>
                  <ol>{result.findings.map((finding) => <li key={finding}>{finding}</li>)}</ol>
                  <div className="eay-evidence-row">
                    <span><BadgeCheck size={15} /> Güven: {result.confidence}</span>
                    <span><FileText size={15} /> {result.source}</span>
                  </div>
                  <div className="eay-action-proposal">
                    <div><Target size={17} /><span><strong>Next best action</strong> Workforce + picking + quality cohort kırılımını karşılaştır.</span></div>
                    <button className="eay-button eay-button--quiet" type="button">Analiz planını göster</button>
                  </div>
                </div>
              ) : (
                <div className="eay-message eay-message--jarvis eay-message--placeholder">
                  <span>Jarvis</span><p>Canlı üretim verisi bu preview’a bağlı değil. Soru gönderdiğinde kaynaklı karar formatını sentetik fixture ile göstereceğim.</p>
                </div>
              )}
            </div>
            <div className="eay-command-input">
              <textarea rows={2} value={query} onChange={(event) => setQuery(event.target.value)} />
              <button className="eay-button eay-button--primary" type="button" onClick={runQuery}>Analiz et <ArrowRight size={16} /></button>
            </div>
          </div>

          <aside className="eay-panel eay-context-rail">
            <div className="eay-panel-heading"><div><span>Decision context</span><h3>Jarvis neye güveniyor?</h3></div><LockKeyhole size={20} /></div>
            <div className="eay-context-item"><Building2 size={17} /><div><strong>Tenant</strong><span>{tenant.name}</span></div></div>
            <div className="eay-context-item"><BadgeCheck size={17} /><div><strong>KPI semantics</strong><span>Canonical contract</span></div></div>
            <div className="eay-context-item"><Clock3 size={17} /><div><strong>Historical memory</strong><span>Versioned + dated</span></div></div>
            <div className="eay-context-item"><ShieldCheck size={17} /><div><strong>Tool authority</strong><span>Fail-closed</span></div></div>
            <div className="eay-context-item"><FileText size={17} /><div><strong>Evidence</strong><span>Source + provenance</span></div></div>
            <div className="eay-context-note"><AlertTriangle size={16} /> Production BigQuery truth bu demo’da aktif değildir.</div>
          </aside>
        </section>
      ) : (
        <section className="eay-security-grid">
          <div className="eay-panel eay-security-finding">
            <div className="eay-security-heading">
              <span className="eay-severity">P0 · DEMO</span>
              <DemoBadge compact />
            </div>
            <h2>Kritik dependency açığı production image’ını etkileyebilir.</h2>
            <p>Bu bulgu tamamen sentetiktir. Gerçek Security Guardian; advisory → exact package/version → reachable code → deployment etkisini doğrulamadan alarm üretmez.</p>
            <div className="eay-finding-grid">
              <div><span>Exploit status</span><strong>Actively exploited · demo</strong></div>
              <div><span>Reachability</span><strong>Auth gateway path · demo</strong></div>
              <div><span>Tenant risk</span><strong>High · boundary adjacent</strong></div>
              <div><span>Remediation</span><strong>Patch + regression</strong></div>
            </div>
            <div className="eay-patch-plan">
              <div className="eay-patch-plan__icon"><ShieldCheck size={20} /></div>
              <div><span>Jarvis proposal</span><strong>Güvenli sürüme yükseltme + auth/RLS regression + SBOM refresh</strong><small>Production mutation için explicit approval gerekir.</small></div>
            </div>
          </div>

          <div className="eay-panel eay-security-runbook">
            <div className="eay-panel-heading"><div><span>Approval-bound remediation</span><h3>Kanıt zinciri</h3></div><Workflow size={20} /></div>
            <div className="eay-security-steps">
              {SECURITY_STEPS.map((step, index) => {
                const done = index < securityStep;
                const active = index === securityStep;
                return (
                  <div key={step} className={`${done ? "done" : ""} ${active ? "active" : ""}`}>
                    <span>{done ? <Check size={14} /> : index + 1}</span><strong>{step}</strong>
                  </div>
                );
              })}
            </div>
            <div className="eay-approval-card">
              {securityStep < 2 ? (
                <>
                  <LockKeyhole size={22} />
                  <div><strong>Onay bekleniyor</strong><span>Bu demo’da bile mutation otomatik başlamaz.</span></div>
                </>
              ) : securityStep < SECURITY_STEPS.length - 1 ? (
                <>
                  <Activity size={22} />
                  <div><strong>Kontrollü remediation simülasyonu</strong><span>Branch → patch → regression → evidence.</span></div>
                </>
              ) : (
                <>
                  <CheckCircle2 size={22} />
                  <div><strong>Doğrulama tamamlandı · demo</strong><span>Gerçek sistemde exact SHA + test evidence + rollback ref tutulur.</span></div>
                </>
              )}
            </div>
            <button className="eay-button eay-button--primary eay-button--full" type="button" onClick={advanceSecurity} disabled={securityStep === SECURITY_STEPS.length - 1}>
              {!approved ? "Demo remediation için onay ver" : securityStep === SECURITY_STEPS.length - 1 ? "Demo tamamlandı" : "Sonraki kanıt adımını çalıştır"}
            </button>
            <p className="eay-fineprint">Bu buton GitHub, production, dependency veya infrastructure üzerinde değişiklik yapmaz.</p>
          </div>
        </section>
      )}
    </div>
  );
}

export default function EayExperience() {
  const [view, setView] = useState("overview");
  const [tenantId, setTenantId] = useState("atlas");
  const tenant = TENANTS[tenantId];

  const navigation = useMemo(() => [
    { id: "overview", label: "Platform", icon: LayoutDashboard },
    { id: "academy", label: "Academy", icon: GraduationCap },
    { id: "jarvis", label: "Jarvis", icon: BrainCircuit },
  ], []);

  const changeTenant = (nextTenant) => {
    setTenantId(nextTenant);
    setView("overview");
  };

  return (
    <div className="eay-experience-shell">
      <header className="eay-experience-topbar">
        <div className="eay-wordmark" onClick={() => setView("overview")} role="button" tabIndex={0}>
          <span className="eay-wordmark__mark">E</span>
          <div><strong>EAY</strong><small>Enterprise Intelligence Platform</small></div>
        </div>
        <nav className="eay-primary-nav" aria-label="Experience navigation">
          {navigation.map((item) => {
            const Icon = item.icon;
            return (
              <button key={item.id} type="button" className={view === item.id ? "active" : ""} onClick={() => setView(item.id)}>
                <Icon size={16} /> {item.label}
              </button>
            );
          })}
        </nav>
        <div className="eay-topbar-actions">
          <DemoBadge compact />
          <label className="eay-tenant-switcher">
            <Building2 size={16} />
            <select value={tenantId} onChange={(event) => changeTenant(event.target.value)} aria-label="Demo tenant seç">
              {Object.values(TENANTS).map((item) => <option value={item.id} key={item.id}>{item.name}</option>)}
            </select>
          </label>
          <div className="eay-user-chip"><span>{tenant.initials}</span><div><strong>Preview Admin</strong><small>{tenant.label}</small></div></div>
        </div>
      </header>

      <main className="eay-experience-main">
        {view === "overview" ? <Overview onNavigate={setView} tenant={tenant} /> : null}
        {view === "academy" ? <Academy key={`academy-${tenantId}`} tenant={tenant} /> : null}
        {view === "jarvis" ? <Jarvis key={`jarvis-${tenantId}`} tenant={tenant} /> : null}
      </main>

      <footer className="eay-experience-footer">
        <span><LockKeyhole size={14} /> Experience Mode · production credentials disabled</span>
        <span>RC0 child preview · not production-ready</span>
      </footer>
    </div>
  );
}
