import React, { useMemo, useState } from "react";
import { uploadAbcAndBuildTwin, summarizeTwinPayload } from "../../services/plonagramV194Api";
import "./ABCUploadPanelV194.css";

export default function ABCUploadPanelV194({ storeCode = "FULYA", onTwinPayloadReady }) {
  const [file, setFile] = useState(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [result, setResult] = useState(null);

  const summary = useMemo(() => summarizeTwinPayload(result?.twin_payload || result), [result]);

  async function handleUpload() {
    if (!file) {
      setError("ABC dosyası seçmelisin.");
      return;
    }
    setLoading(true);
    setError("");
    try {
      const data = await uploadAbcAndBuildTwin(file, { storeCode });
      setResult(data);
      onTwinPayloadReady?.(data?.twin_payload || data);
    } catch (err) {
      setError(err.message || "Upload başarısız.");
    } finally {
      setLoading(false);
    }
  }

  return (
    <section className="abc194-card">
      <div className="abc194-head">
        <div>
          <p className="abc194-eyebrow">V1.9.4 DATA PIPELINE</p>
          <h2>ABC Yükle ve Görsel Twin Hazırla</h2>
          <p>ABC sadece görsel, stok, %orders, %stops, ABC ve rank sinyali verir. Hedef lokasyonu engine belirler.</p>
        </div>
        <span className="abc194-badge">Store: {storeCode}</span>
      </div>

      <div className="abc194-upload-row">
        <label className="abc194-file">
          <input type="file" accept=".xlsx,.xls,.csv" onChange={(e) => setFile(e.target.files?.[0] || null)} />
          <span>{file ? file.name : "ABC dosyası seç"}</span>
        </label>
        <button className="abc194-btn" onClick={handleUpload} disabled={loading}>
          {loading ? "İşleniyor..." : "Upload + Merge + Twin"}
        </button>
      </div>

      {loading && (
        <div className="abc194-loading">
          <div className="abc194-orbit" />
          <div>
            <strong>PLONAGRAM Core çalışıyor</strong>
            <p>ABC parse → Catalog merge → Classification guard → Visual twin payload</p>
          </div>
        </div>
      )}

      {error && <div className="abc194-error">{error}</div>}

      {result && (
        <div className="abc194-grid">
          <Metric label="Sellable" value={summary.sellable} />
          <Metric label="Excluded" value={summary.excluded} />
          <Metric label="Review" value={summary.review} />
          <Metric label="Image Coverage" value={`${summary.imageCoveragePct}%`} />
        </div>
      )}

      {result?.excluded_products?.length > 0 && (
        <div className="abc194-report">
          <h3>Planogram dışı bırakılanlar</h3>
          {result.excluded_products.slice(0, 6).map((p, i) => (
            <div className="abc194-row" key={`${p.sku || i}-${i}`}>
              <span>{p.product_name || p["Product Name"] || p.sku}</span>
              <em>{p.reason_code || p.planogram_class}</em>
            </div>
          ))}
        </div>
      )}
    </section>
  );
}

function Metric({ label, value }) {
  return (
    <div className="abc194-metric">
      <strong>{value}</strong>
      <span>{label}</span>
    </div>
  );
}
