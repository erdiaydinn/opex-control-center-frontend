import React, { useMemo, useState } from "react";
import { compareShelfChangeV19, fetchProductLibrary } from "../services/plonagramV19Api";
import { t19 } from "../i18n/plonagramV19Dictionary";
import "../styles/plonagram-v19.css";

function normalizeProduct(row = {}) {
  return {
    ...row,
    sku: row.sku || row.SKU || row.barcode || "",
    product_name: row.product_name || row.product_name_local || row.name || "İsimsiz ürün",
    brand: row.brand || row.brand_name || "-",
    category_l1: row.category_l1 || row.frontend_category_local || row.category || "-",
    category_l2: row.category_l2 || row.frontend_subcategory_local || row.subcategory || "-",
    storage_type: row.storage_type || row.storage || "-",
    image_url: row.image_url || row.catalog_image_url || row.pim_image_url || "",
  };
}

function ProductMini({ title, product, confidence, refill }) {
  if (!product && !confidence) {
    return <div className="v19-impact-product"><span className="v19-muted">Boş</span></div>;
  }
  const p = product || confidence || {};
  const name = p.product_name || p.name || confidence?.product_name || "-";
  const sku = p.sku || confidence?.sku || "-";
  const brand = p.brand || confidence?.brand || "-";
  const conf = confidence?.placement_confidence ?? p.placement_confidence;
  return (
    <div className="v19-impact-product">
      <div className="v19-impact-title">{title}</div>
      <b>{name}</b>
      <small>{sku} • {brand}</small>
      <div className="v19-impact-badges">
        {conf != null && <span className="v19-badge v19-confidence">Güven {conf}</span>}
        {refill?.level && <span className={`v19-badge v19-risk-${String(refill.level).toLowerCase()}`}>Refill {refill.level}</span>}
      </div>
    </div>
  );
}

function ImpactMetric({ label, value, suffix = "", goodWhenPositive = true }) {
  const n = Number(value || 0);
  const tone = n === 0 ? "neutral" : (goodWhenPositive ? (n > 0 ? "good" : "bad") : (n < 0 ? "good" : "bad"));
  return <div className={`v19-impact-metric v19-impact-${tone}`}><span>{label}</span><b>{n > 0 ? "+" : ""}{n}{suffix}</b></div>;
}

export default function ShelfImpactStudioV19({ lang = "tr", shelf, aisle, module, currentProduct, onApply }) {
  const [query, setQuery] = useState("");
  const [results, setResults] = useState([]);
  const [candidate, setCandidate] = useState(null);
  const [comparison, setComparison] = useState(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  const shelfProducts = useMemo(() => shelf?.products || [], [shelf]);

  async function search() {
    setLoading(true);
    setError("");
    try {
      const data = await fetchProductLibrary({ q: query, limit: 80 });
      setResults((data.products || []).map(normalizeProduct));
    } catch (err) {
      setError(err.message || String(err));
    } finally {
      setLoading(false);
    }
  }

  async function compare(product) {
    setCandidate(product);
    setLoading(true);
    setError("");
    try {
      const data = await compareShelfChangeV19({
        shelf: shelf || { products: [] },
        current_product: currentProduct || null,
        candidate_product: product,
        aisle,
        module,
      });
      setComparison(data);
    } catch (err) {
      setError(err.message || String(err));
    } finally {
      setLoading(false);
    }
  }

  function onKeyDown(event) {
    if (event.key === "Enter") search();
  }

  const recommendation = comparison?.recommendation;

  return (
    <section className="v19-page" dir={lang === "ar" ? "rtl" : "ltr"}>
      <div className="v19-page-head">
        <div>
          <div className="v19-eyebrow">PLACEMENT INTELLIGENCE</div>
          <h1>{t19(lang, "shelfImpact")}</h1>
          <p>Raf boşsa veya ürün değişecekse etkiyi hızlı gösterir: güven, satış, refill, koli ve kapasite.</p>
        </div>
      </div>

      <div className="v19-card v19-impact-arena">
        <div className="v19-card-head"><h3>FIFA tarzı ürün değişim kıyası</h3><span className="v19-pill">Ekranda görünür, yazıcıda görünmez</span></div>
        <div className="v19-impact-grid">
          <ProductMini title={currentProduct ? t19(lang, "currentProduct") : t19(lang, "emptySlot")} product={currentProduct} confidence={comparison?.current} refill={comparison?.current_refill} />
          <div className="v19-impact-versus">VS</div>
          <ProductMini title={t19(lang, "candidateProduct")} product={candidate} confidence={comparison?.candidate} refill={comparison?.candidate_refill} />
        </div>

        {comparison && (
          <>
            <div className="v19-impact-metrics">
              <ImpactMetric label={t19(lang, "salesEffect")} value={comparison.impact?.sales_delta} />
              <ImpactMetric label="Güven etkisi" value={comparison.impact?.confidence_delta} />
              <ImpactMetric label={t19(lang, "capacityEffect")} value={comparison.impact?.capacity_units_delta} suffix=" adet" />
              <ImpactMetric label={t19(lang, "casePackEffect")} value={comparison.impact?.case_pack_extra_units} suffix=" ekstra" goodWhenPositive={false} />
            </div>
            <div className={`v19-recommendation v19-rec-${String(recommendation).toLowerCase()}`}>
              <span>Öneri</span>
              <b>{recommendation === "APPLY" ? t19(lang, "apply") : recommendation === "DO_NOT_APPLY" ? t19(lang, "doNotApply") : t19(lang, "review")}</b>
              {comparison.risk_flags?.length > 0 && <small>Risk: {comparison.risk_flags.join(", ")}</small>}
            </div>
            <details className="v19-details">
              <summary>{t19(lang, "confidenceDetails")}</summary>
              <ul>
                {(comparison.candidate?.confidence_reasons || []).map((x, i) => <li key={`r-${i}`}>{x}</li>)}
                {(comparison.candidate?.confidence_warnings || []).map((x, i) => <li key={`w-${i}`} className="v19-warn-text">{x}</li>)}
              </ul>
            </details>
            <button className="v19-primary" disabled={recommendation === "DO_NOT_APPLY"} onClick={() => onApply?.({ candidate, comparison })}>Bu değişimi uygula</button>
          </>
        )}
      </div>

      <div className="v19-toolbar">
        <input className="v19-search" value={query} onChange={(e) => setQuery(e.target.value)} onKeyDown={onKeyDown} placeholder={t19(lang, "searchPlaceholder")} />
        <button className="v19-secondary" onClick={search}>{loading ? "Aranıyor..." : "Ara"}</button>
        <span className="v19-help">Enter çalışır; bu alan süs değildir.</span>
      </div>

      {error && <div className="v19-alert v19-alert-danger">{error}</div>}

      <div className="v19-card">
        <div className="v19-card-head"><h3>Raf ürünleri</h3><span className="v19-pill">{shelfProducts.length} ürün</span></div>
        <div className="v19-shelf-strip">
          {shelfProducts.map((p) => <button key={p.sku} className="v19-shelf-chip" onClick={() => compare(normalizeProduct(p))}>{p.product_name || p.name || p.sku}</button>)}
          {shelfProducts.length === 0 && <span className="v19-muted">Raf boş. Ürün arayıp etkiyi görebilirsin.</span>}
        </div>
      </div>

      <div className="v19-card">
        <div className="v19-card-head"><h3>Öneri listesi</h3><span className="v19-pill">Güven skoruna göre kıyasla</span></div>
        <div className="v19-suggestion-grid">
          {results.map((p) => (
            <button className="v19-suggestion" key={`${p.sku}-${p.barcode || ""}`} onClick={() => compare(p)}>
              <b>{p.product_name}</b>
              <small>{p.sku} • {p.brand} • {p.storage_type}</small>
              <span>{p.category_l1} / {p.category_l2}</span>
            </button>
          ))}
          {!loading && results.length === 0 && <div className="v19-empty">Ürün aramak için Enter'a bas.</div>}
        </div>
      </div>
    </section>
  );
}
