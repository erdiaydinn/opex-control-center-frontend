import React, { useMemo, useState } from 'react';
import { buildPlacementDiagnostics, toCsv } from '../../utils/placementDiagnostics';
import './PlacementDiagnostics.css';

function downloadFile(filename, content, type = 'text/csv;charset=utf-8') {
  const blob = new Blob([content], { type });
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url;
  a.download = filename;
  a.click();
  URL.revokeObjectURL(url);
}

const reasonLabel = {
  missing_dimensions: 'Ölçü eksik',
  no_product_fixture: 'Ürün alabilen fixture yok',
  no_matching_storage_shelf: 'Storage rafı yok',
  product_too_tall: 'Yükseklik uyumsuz',
  product_too_deep: 'Derinlik uyumsuz',
  insufficient_capacity: 'Kapasite yetersiz',
  not_returned_by_engine_but_not_placed: 'Motor nedeni döndürmedi',
  unknown: 'Bilinmeyen',
};

export default function PlacementDiagnostics({ products = [], planogram = {}, unplacedProducts = [], compact = false }) {
  const [open, setOpen] = useState(!compact);
  const [filter, setFilter] = useState('ALL');
  const [search, setSearch] = useState('');

  const diagnostics = useMemo(
    () => buildPlacementDiagnostics({ products, planogram, unplacedProducts }),
    [products, planogram, unplacedProducts]
  );

  const reasons = Object.entries(diagnostics.reasonCounts).sort((a, b) => b[1] - a[1]);
  const filtered = diagnostics.unplaced.filter((row) => {
    if (filter !== 'ALL' && row.reason_code !== filter) return false;
    const q = search.trim().toLocaleLowerCase('tr-TR');
    if (!q) return true;
    return `${row.sku} ${row.product_name} ${row.brand} ${row.category_l1} ${row.category_l2}`.toLocaleLowerCase('tr-TR').includes(q);
  });

  return (
    <section className="pd-card">
      <div className="pd-head">
        <div>
          <p className="pd-kicker">PLACEMENT DIAGNOSTICS</p>
          <h2>Yerleşmeyen SKU nedeni</h2>
          <span>
            {diagnostics.summary.total_products} SKU içinde {diagnostics.summary.placed_unique_skus} benzersiz SKU yerleşti; {diagnostics.summary.unplaced_count} SKU için aksiyon gerekiyor.
          </span>
        </div>
        <div className="pd-actions">
          <button onClick={() => downloadFile('plonagram_unplaced_diagnostics.csv', toCsv(filtered))}>CSV indir</button>
          <button onClick={() => setOpen((v) => !v)}>{open ? 'Gizle' : 'Detayı aç'}</button>
        </div>
      </div>

      <div className="pd-kpis">
        <div><b>{diagnostics.summary.placement_rate_pct}%</b><span>Placement rate</span></div>
        <div><b>{diagnostics.summary.product_allowed_shelves}</b><span>Ürün alan raf</span></div>
        <div><b>{diagnostics.summary.duplicate_sku_count}</b><span>Duplicate SKU</span></div>
        <div><b>{diagnostics.summary.unplaced_count}</b><span>Yerleşmeyen</span></div>
      </div>

      <div className="pd-reasons">
        <button className={filter === 'ALL' ? 'active' : ''} onClick={() => setFilter('ALL')}>Tümü</button>
        {reasons.map(([code, count]) => (
          <button key={code} className={filter === code ? 'active' : ''} onClick={() => setFilter(code)}>
            {reasonLabel[code] || code} <b>{count}</b>
          </button>
        ))}
      </div>

      {open && (
        <>
          <div className="pd-storage-grid">
            {Object.entries(diagnostics.capacityByStorage).map(([storage, x]) => (
              <div key={storage} className="pd-storage-card">
                <strong>{storage}</strong>
                <span>{x.shelves} raf</span>
                <em>{Math.round(x.used)} / {Math.round(x.capacity)} cm</em>
                <small>Kalan {Math.round(x.remaining)} cm</small>
              </div>
            ))}
          </div>

          <div className="pd-toolbar">
            <input value={search} onChange={(e) => setSearch(e.target.value)} placeholder="SKU, ürün, marka veya kategori ara..." />
            <span>{filtered.length} kayıt gösteriliyor</span>
          </div>

          <div className="pd-table-wrap">
            <table className="pd-table">
              <thead>
                <tr>
                  <th>SKU</th>
                  <th>Ürün</th>
                  <th>Storage</th>
                  <th>Ölçü</th>
                  <th>Neden</th>
                  <th>Önerilen aksiyon</th>
                </tr>
              </thead>
              <tbody>
                {filtered.slice(0, 500).map((row, idx) => (
                  <tr key={`${row.sku}-${idx}`} className={`severity-${row.severity}`}>
                    <td>{row.sku}</td>
                    <td><b>{row.product_name}</b><small>{row.brand || '-'} · {row.category_l2 || row.category_l1 || '-'}</small></td>
                    <td><i>{row.storage_type}</i></td>
                    <td>{row.width_cm}×{row.depth_cm}×{row.height_cm} cm</td>
                    <td><strong>{reasonLabel[row.reason_code] || row.reason_code}</strong><small>{row.reason}</small></td>
                    <td>{row.suggested_action}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          {filtered.length > 500 && <p className="pd-note">İlk 500 kayıt gösteriliyor. Tümünü görmek için CSV indir.</p>}
        </>
      )}
    </section>
  );
}
