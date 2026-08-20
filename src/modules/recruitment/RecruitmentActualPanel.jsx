import React, { useRef, useState } from "react";
import { AlertTriangle, BadgeCheck, FileSpreadsheet, RefreshCw, ShieldCheck, Upload, Users } from "lucide-react";

import { importRecruitmentHrActual } from "./recruitmentApi.js";
import { parseRecruitmentHrActualFile } from "./recruitmentImporters.js";


function today() { return new Date().toISOString().slice(0, 10); }
function valueOrDash(value) { return value == null ? "—" : value; }

export default function RecruitmentActualPanel({ data, refresh, flash, setError }) {
  const fileRef = useRef(null);
  const [asOf, setAsOf] = useState(data?.actualSnapshot?.asOf || today());
  const [busy, setBusy] = useState(false);
  const snapshot = data?.actualSnapshot;
  const rows = data?.dashboard?.warehouseRows || [];

  async function upload(file) {
    if (!file) return;
    setBusy(true);
    try {
      const parsed = await parseRecruitmentHrActualFile(file);
      if (!parsed.rows.length) throw new Error("Dosyada Employee ID/TCKN ve depo içeren HR Actual satırı bulunamadı.");
      const result = await importRecruitmentHrActual(parsed.rows, file.name, asOf);
      flash(`HR Actual yüklendi: ${result.activeRows} aktif kayıt · eşleşme %${result.matchRate}.`);
      await refresh();
    } catch (error) {
      setError(error.message || "HR Actual dosyası yüklenemedi.");
    } finally {
      setBusy(false);
      if (fileRef.current) fileRef.current.value = "";
    }
  }

  return <section className="rec-content rec-actual-stack">
    <div className="rec-panel rec-actual-hero">
      <div>
        <span className="rec-kicker">HEADCOUNT AUTHORITY</span>
        <h2>Norm × HR Actual × Employee Master</h2>
        <p>İK'nın resmi mevcut çalışan snapshot'ı ile operasyonel Employee Master aynı tabloda mutabakatlanır. TCKN yalnız eşleştirme sırasında backend'e gider; snapshot'a kaydedilmez.</p>
      </div>
      <div className="rec-actual-upload">
        <label>Veri tarihi<input type="date" value={asOf} onChange={(event) => setAsOf(event.target.value)} /></label>
        <input ref={fileRef} type="file" accept=".xlsx,.xls,.csv" hidden onChange={(event) => upload(event.target.files?.[0])} />
        <button className="rec-primary" disabled={busy} onClick={() => fileRef.current?.click()}><Upload size={17} />{busy ? "İşleniyor…" : "HR Actual yükle"}</button>
      </div>
    </div>

    <div className="rec-metrics">
      <article className="rec-metric tone-pink"><span><Users size={19} /></span><div><small>HR Actual</small><strong>{valueOrDash(snapshot?.activeRows)}</strong><p>{snapshot ? `${snapshot.activeFte} FTE · ${snapshot.asOf}` : "Henüz resmi snapshot yüklenmedi"}</p></div></article>
      <article className="rec-metric tone-green"><span><BadgeCheck size={19} /></span><div><small>Employee Master eşleşmesi</small><strong>{snapshot ? `%${snapshot.matchRate}` : "—"}</strong><p>{snapshot ? `${snapshot.matchedRows}/${snapshot.sourceRows} satır canonical kimliğe bağlandı` : "HR snapshot sonrası hesaplanır"}</p></div></article>
      <article className="rec-metric tone-amber"><span><AlertTriangle size={19} /></span><div><small>Eşleşmeyen</small><strong>{valueOrDash(snapshot?.unmatchedRows)}</strong><p>İşe alım kararından önce kimlik/depo mutabakatı gerekir</p></div></article>
      <article className="rec-metric tone-purple"><span><FileSpreadsheet size={19} /></span><div><small>Kaynak kanıtı</small><strong>{snapshot?.sourceSha256 ? snapshot.sourceSha256.slice(0, 8) : "—"}</strong><p>{snapshot?.sourceName || "Dosya yüklenmedi"}</p></div></article>
    </div>

    <div className="rec-panel">
      <div className="rec-panel-head"><div><span className="rec-kicker">STAFFING RECONCILIATION</span><h2>Depo kadro mutabakatı</h2></div><button className="rec-secondary" onClick={refresh}><RefreshCw size={16} /> Yenile</button></div>
      <div className="rec-table-wrap"><table className="rec-actual-table"><thead><tr><th>Depo</th><th>Norm</th><th>HR Actual</th><th>FTE</th><th>Employee Master</th><th>HR↔EM farkı</th><th>Açık Req.</th><th>Net boşluk</th><th>Veri kalitesi</th></tr></thead><tbody>
        {rows.map((row) => <tr key={row.warehouseName}>
          <td><strong>{row.warehouseName}</strong><small>{row.normRecord?.regionalExecutive || "BY eşleşmesi bekliyor"}</small></td>
          <td><strong>{row.capacity}</strong><small>{row.normStatus === "TEMPORARY_ACTIVE" ? "Geçici norm aktif" : "Kapasite"}</small></td>
          <td><strong>{valueOrDash(row.hrActual)}</strong><small>{row.hrActualAsOf || "Snapshot yok"}</small></td>
          <td>{valueOrDash(row.hrActualFte)}</td>
          <td><strong>{row.active}</strong><small>Operasyonel actual</small></td>
          <td><span className={`rec-status ${row.hrActualDelta == null ? "neutral" : row.hrActualDelta === 0 ? "success" : "warning"}`}>{valueOrDash(row.hrActualDelta)}</span></td>
          <td>{row.openPositions}</td>
          <td><strong>{row.available}</strong></td>
          <td>{row.hrActualUnmatched ? <span className="rec-status warning">{row.hrActualUnmatched} eşleşmedi</span> : snapshot ? <span className="rec-status success">Mutabık</span> : <span className="rec-status neutral">HR snapshot bekliyor</span>}</td>
        </tr>)}
      </tbody></table>{!rows.length && <div className="rec-empty">Kapsamınızda staffing satırı bulunamadı.</div>}</div>
      <p className="rec-config-note"><ShieldCheck size={15} />Karar motoru şimdilik fail-safe olarak Employee Master actual'ını kullanır. HR Actual farkı görünür ve denetlenebilir hale getirilmiştir; resmi authority geçişi yalnız mutabakat/evidence gate tamamlandıktan sonra yapılacaktır.</p>
    </div>
  </section>;
}
