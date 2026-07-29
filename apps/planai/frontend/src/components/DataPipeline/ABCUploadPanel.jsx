import React, { useMemo, useState } from "react";
import { Upload, Image as ImageIcon, PackageX, AlertTriangle, CheckCircle2 } from "lucide-react";
import "./ABCUploadPanel.css";

const API_BASE = import.meta.env.VITE_PLANOGRAM_API_BASE || "http://127.0.0.1:8001";

async function uploadMergeABC(file) {
  const form = new FormData();
  form.append("file", file);

  const res = await fetch(`${API_BASE}/data-pipeline/abc/upload-merge`, {
    method: "POST",
    body: form,
  });

  if (!res.ok) {
    const text = await res.text();
    throw new Error(`ABC upload failed: ${res.status} ${text}`);
  }

  return res.json();
}

function Metric({ label, value, icon }) {
  return (
    <div className="abc-metric">
      <div className="abc-metric-icon">{icon}</div>
      <div>
        <div className="abc-metric-label">{label}</div>
        <div className="abc-metric-value">{value ?? 0}</div>
      </div>
    </div>
  );
}

export default function ABCUploadPanel({ onPipelineReady }) {
  const [file, setFile] = useState(null);
  const [state, setState] = useState({ status: "idle" });
  const [result, setResult] = useState(null);

  const summary = useMemo(() => {
    if (!result) return {};
    return result.summary || result.merge_summary || result.pipeline_summary || {};
  }, [result]);

  async function handleUpload() {
    if (!file) return;
    setState({ status: "loading", message: "ABC dosyası okunuyor, catalog ile eşleşiyor ve ürün görselleri hazırlanıyor..." });

    try {
      const data = await uploadMergeABC(file);
      setResult(data);
      setState({ status: "success", message: "ABC + Catalog pipeline hazır." });
      onPipelineReady?.(data);
    } catch (err) {
      setState({ status: "error", message: err.message });
    }
  }

  return (
    <section className="abc-panel">
      <div className="abc-panel-head">
        <div>
          <span className="abc-eyebrow">V1.9.3 Data Pipeline</span>
          <h2>ABC Upload & Visual Twin Feed</h2>
          <p>
            ABC dosyası sadece görsel, stok, %Orders, %Stops, ABC ve Rank sinyali verir.
            Lokasyon hedef yerleşim için değil, delta planogram için saklanır.
          </p>
        </div>
        <div className="abc-status-pill">{state.status}</div>
      </div>

      <div className="abc-upload-row">
        <label className="abc-file-drop">
          <Upload size={22} />
          <span>{file ? file.name : "ABC dosyasını seç"}</span>
          <input
            type="file"
            accept=".xlsx,.xls,.csv"
            onChange={(e) => setFile(e.target.files?.[0] || null)}
          />
        </label>

        <button className="abc-primary-btn" onClick={handleUpload} disabled={!file || state.status === "loading"}>
          Pipeline’ı Hazırla
        </button>
      </div>

      {state.message && (
        <div className={`abc-message abc-${state.status}`}>
          {state.status === "success" ? <CheckCircle2 size={18} /> : state.status === "error" ? <AlertTriangle size={18} /> : <Upload size={18} />}
          <span>{state.message}</span>
        </div>
      )}

      {result && (
        <>
          <div className="abc-metric-grid">
            <Metric label="Toplam satır" value={summary.input_rows || summary.total_rows || summary.input_products} icon={<Upload size={18} />} />
            <Metric label="Engine’e gidecek" value={summary.sellable_products} icon={<CheckCircle2 size={18} />} />
            <Metric label="Excluded" value={summary.excluded_products} icon={<PackageX size={18} />} />
            <Metric label="Review" value={summary.review_products} icon={<AlertTriangle size={18} />} />
            <Metric label="Görseli olan" value={summary.with_image || summary.products_with_image} icon={<ImageIcon size={18} />} />
          </div>

          <div className="abc-result-note">
            <strong>Kural:</strong> Shopping Bag, ekipman ve bakery flow ürünleri engine’e gitmez.
            Bunlar unplaced değil, bilinçli olarak excluded/review raporuna düşer.
          </div>
        </>
      )}
    </section>
  );
}