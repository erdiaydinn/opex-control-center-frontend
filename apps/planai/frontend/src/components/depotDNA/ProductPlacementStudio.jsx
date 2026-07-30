import { useState } from 'react';
import { products } from '../data/mock.js';
import { tt } from '../i18n/dictionary.js';

export default function ProductPlacementStudio({ lang }) {
  const [items, setItems] = useState(products);
  const [selectedSku, setSelectedSku] = useState(products[0].sku);
  const selected = items.find((p) => p.sku === selectedSku) || items[0];
  const t = (k) => tt(lang, k);
  const updateSelected = (patch) => setItems(items.map((p) => p.sku === selected.sku ? { ...p, ...patch } : p));
  const aiFacing = () => {
    const suggested = selected.sales >= 180 ? 6 : selected.sales >= 120 ? 4 : selected.sales >= 70 ? 3 : 1;
    updateSelected({ facing: suggested, depth: Math.max(selected.depth, Math.ceil(selected.sales / 45)) });
  };
  const sortSales = () => setItems([...items].sort((a, b) => b.sales - a.sales));
  const sortBrand = () => setItems([...items].sort((a, b) => a.brand.localeCompare(b.brand, 'tr')));
  return (
    <div className="page">
      <div className="section-eyebrow">PRODUCT PLACEMENT STUDIO</div>
      <h1 style={{ fontSize: 42, margin: '8px 0' }}>{t('placement')}</h1>
      <p className="page-sub">Görsel raf + teknik grid aynı ekranda. Facing, depth ve refill riski anlık değişir.</p>
      <div className="grid cols-2" style={{ marginTop: 22 }}>
        <div className="card pad">
          <div style={{ display: 'flex', justifyContent: 'space-between', gap: 12, flexWrap: 'wrap' }}>
            <div><div className="section-eyebrow">VISUAL SHELF</div><h2>Module A.1</h2></div>
            <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap' }}>
              <button className="btn ghost" onClick={sortSales}>{t('sortSales')}</button>
              <button className="btn ghost" onClick={sortBrand}>{t('sortBrand')}</button>
              <button className="btn primary" onClick={aiFacing}>{t('aiFacing')}</button>
            </div>
          </div>
          {[1,2,3,4,5].map((shelfNo) => (
            <div className="shelf" key={shelfNo}>
              <b style={{ width: 72, fontSize: 12 }}>Shelf {shelfNo}</b>
              {items.slice((shelfNo - 1), (shelfNo - 1) + 5).map((p) => Array.from({ length: Math.min(p.facing, 6) }, (_, i) => (
                <button key={`${p.sku}-${i}`} className={`product-chip ${p.storage}`} title={p.name} onClick={() => setSelectedSku(p.sku)}>{p.brand.slice(0,2)}</button>
              )))}
            </div>
          ))}
        </div>
        <div className="card pad">
          <div className="section-eyebrow">SELECTED PRODUCT</div>
          <h2>{selected.name}</h2>
          <p className="muted">{selected.sku} • {selected.brand} • {selected.category} • {selected.storage}</p>
          <div className="grid cols-3" style={{ marginTop: 20 }}>
            <div className="card pad"><b>Sales/day</b><div className="kpi-value">{selected.sales}</div></div>
            <div className="card pad"><b>Facing</b><div className="kpi-value pink">{selected.facing}</div></div>
            <div className="card pad"><b>Depth</b><div className="kpi-value cyan">{selected.depth}</div></div>
          </div>
          <div className="grid cols-2" style={{ marginTop: 16 }}>
            <button className="btn ghost" onClick={() => updateSelected({ facing: Math.max(1, selected.facing - 1) })}>{t('facingDown')}</button>
            <button className="btn ghost" onClick={() => updateSelected({ facing: selected.facing + 1 })}>{t('facingUp')}</button>
            <button className="btn ghost" onClick={() => updateSelected({ depth: selected.depth + 1 })}>{t('depthUp')}</button>
            <button className="btn primary" onClick={aiFacing}>{t('aiFacing')}</button>
          </div>
          <div className="card pad" style={{ marginTop: 18 }}>
            <b>Refill logic</b>
            <p className="muted">daily_sales / shelf_capacity = refill_per_day. Bu üründe tahmini refill: <b>{(selected.sales / Math.max(selected.facing * selected.depth * 12, 1)).toFixed(2)}</b> / gün.</p>
          </div>
        </div>
      </div>
      <div className="card pad" style={{ marginTop: 22 }}>
        <div className="section-eyebrow">TECHNICAL GRID</div>
        <table className="table"><thead><tr><th>SKU</th><th>Ürün</th><th>Marka</th><th>Storage</th><th>Facing</th><th>Depth</th><th>Risk</th></tr></thead><tbody>{items.map((p) => <tr key={p.sku} onClick={() => setSelectedSku(p.sku)}><td>{p.sku}</td><td>{p.name}</td><td>{p.brand}</td><td><span className={`badge ${p.storage === 'CHILLED' ? 'cyan' : p.storage === 'FROZEN' ? 'purple' : 'green'}`}>{p.storage}</span></td><td>{p.facing}</td><td>{p.depth}</td><td>{p.risk}</td></tr>)}</tbody></table>
      </div>
    </div>
  );
}
