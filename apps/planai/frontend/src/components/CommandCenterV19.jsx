import React, { useEffect, useState } from "react";
import { scorePlanogramV19 } from "../services/plonagramV19Api";
import { t19 } from "../i18n/plonagramV19Dictionary";
import "../styles/plonagram-v19.css";

function ScoreRing({ label, value, tone = "pink" }) {
  const safe = Number.isFinite(Number(value)) ? Number(value) : 0;
  return (
    <div className={`v19-score-ring v19-ring-${tone}`} style={{ "--score": `${safe}%` }}>
      <div><b>{safe}</b><span>/100</span></div>
      <p>{label}</p>
    </div>
  );
}

function StatusLine({ label, value, tone = "ok" }) {
  return <div className="v19-status-line"><span>{label}</span><b className={`v19-status-${tone}`}>{value}</b></div>;
}

export default function CommandCenterV19({ lang = "tr", planogram, catalogStats = {}, abcStatus = {}, storeDnaStatus = {} }) {
  const [score, setScore] = useState(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  async function refreshScore() {
    if (!planogram) return;
    setLoading(true);
    setError("");
    try {
      const data = await scorePlanogramV19(planogram);
      setScore(data);
    } catch (err) {
      setError(err.message || String(err));
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    refreshScore();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [planogram]);

  const risk = score?.risk_summary || {};
  const breakdown = score?.score_breakdown || {};

  return (
    <section className="v19-page" dir={lang === "ar" ? "rtl" : "ltr"}>
      <div className="v19-page-head">
        <div>
          <div className="v19-eyebrow">PLONAGRAM OS</div>
          <h1>{t19(lang, "commandCenter")}</h1>
          <p>Engine, kural motoru, catalog, ABC, Store DNA ve AI güveni aynı merkezde.</p>
        </div>
        <button className="v19-primary" onClick={refreshScore} disabled={loading}>{loading ? "Hesaplanıyor..." : "Skoru Yenile"}</button>
      </div>

      {error && <div className="v19-alert v19-alert-danger">{error}</div>}

      <div className="v19-command-grid">
        <div className="v19-card v19-score-card">
          <ScoreRing label={t19(lang, "planogramScore")} value={score?.planogram_score || 0} tone="pink" />
          <ScoreRing label={t19(lang, "aiConfidence")} value={score?.ai_confidence_score || 0} tone="cyan" />
          <div className="v19-council-box">
            <span>{t19(lang, "councilDecision")}</span>
            <b>{score?.council_decision || "HESAPLANMADI"}</b>
          </div>
        </div>

        <div className="v19-card">
          <div className="v19-card-head"><h3>{t19(lang, "ruleEngine")}</h3><span className="v19-pill">Hard Rules</span></div>
          <StatusLine label="storage_raw priority" value="AKTİF" />
          <StatusLine label="Raf → SHELF" value="AKTİF" />
          <StatusLine label="Dolap → +4 FRIDGE" value="AKTİF" />
          <StatusLine label="Donuk → -18 FREEZER" value="AKTİF" />
          <StatusLine label="case_pack_qty rounding" value="AKTİF" />
          <StatusLine label="Güven skoruna göre öneri" value="AKTİF" />
          <p className="v19-note">{t19(lang, "storageRule")}</p>
        </div>

        <div className="v19-card">
          <div className="v19-card-head"><h3>{t19(lang, "catalogStatus")}</h3><span className="v19-pill">Backend</span></div>
          <StatusLine label="Toplam SKU" value={catalogStats.total ?? "-"} />
          <StatusLine label="case_pack_qty eksik" value={risk.case_pack_missing ?? catalogStats.casePackMissing ?? "-"} tone={(risk.case_pack_missing || 0) > 0 ? "warn" : "ok"} />
          <StatusLine label="Koli yuvarlama uygulanan" value={risk.case_pack_rounding_applied ?? "-"} />
          <StatusLine label="Storage ihlali" value={risk.storage_violations ?? "-"} tone={(risk.storage_violations || 0) > 0 ? "bad" : "ok"} />
        </div>

        <div className="v19-card">
          <div className="v19-card-head"><h3>{t19(lang, "abcStatus")}</h3><span className="v19-pill">Sales Logic</span></div>
          <StatusLine label="ABC dosyası" value={abcStatus.loaded ? "YÜKLÜ" : "EKSİK"} tone={abcStatus.loaded ? "ok" : "warn"} />
          <StatusLine label="A class SKU" value={abcStatus.aCount ?? "-"} />
          <StatusLine label="Satış verisi" value={abcStatus.salesLoaded ? "YÜKLÜ" : "KISMİ/EKSİK"} tone={abcStatus.salesLoaded ? "ok" : "warn"} />
          <p className="v19-note">ABC yoksa sistem bunu saklamaz; AI güven skoru düşer.</p>
        </div>

        <div className="v19-card">
          <div className="v19-card-head"><h3>{t19(lang, "storeDnaStatus")}</h3><span className="v19-pill">Spatial Core</span></div>
          <StatusLine label="Koridor/Yüz/Modül/Raf" value={storeDnaStatus.v2 ? "V2 HAZIR" : "LEGACY/KISMİ"} tone={storeDnaStatus.v2 ? "ok" : "warn"} />
          <StatusLine label="Farklı raf sayısı" value={storeDnaStatus.variableShelves ? "DESTEKLİ" : "EKSİK"} tone={storeDnaStatus.variableShelves ? "ok" : "warn"} />
          <StatusLine label="2D/3D tek schema" value={storeDnaStatus.singleSchema ? "AKTİF" : "GEREKLİ"} tone={storeDnaStatus.singleSchema ? "ok" : "bad"} />
        </div>

        <div className="v19-card">
          <div className="v19-card-head"><h3>Score Breakdown</h3><span className="v19-pill">Deterministic</span></div>
          <StatusLine label="Storage compliance" value={breakdown.storage_compliance ?? "-"} />
          <StatusLine label="Fixture fit" value={breakdown.fixture_fit ?? "-"} />
          <StatusLine label="Capacity fit" value={breakdown.capacity_fit ?? "-"} />
          <StatusLine label="Category isolation" value={breakdown.category_isolation ?? "-"} />
          <StatusLine label="Case pack compliance" value={breakdown.case_pack_compliance ?? "-"} />
        </div>
      </div>
    </section>
  );
}
