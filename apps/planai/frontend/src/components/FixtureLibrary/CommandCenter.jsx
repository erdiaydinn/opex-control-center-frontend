import { tt } from '../i18n/dictionary.js';
import { insights, storeMetrics } from '../data/mock.js';
import { ProductThumb } from './ProductVisuals.jsx';
import TwinStudio3D from './Live3D/TwinStudio3D.jsx';

function ExecutiveCommandVisual({ products }) {
  const rows = [0,1,2,3,4,5,6,7];
  return (
    <div className="executive-twin-preview command-visual-premium">
      <div className="preview-floor">
        <div className="preview-dispatch">SEVKİYAT</div>
        <div className="preview-room chilled">+4 SOĞUK</div>
        <div className="preview-room frozen">-18 DONUK</div>
        <div className="preview-route" />
        {rows.map((r) => <div key={r} className={`preview-rack rack-${r}`}><span>{String.fromCharCode(65+r)}</span></div>)}
        <div className="preview-pulse p1" />
        <div className="preview-pulse p2" />
        <div className="preview-products">{products.slice(0,5).map(p => <ProductThumb key={p.sku} product={p} small />)}</div>
      </div>
      <div className="float-tag" style={{ left: '10%', top: '58%' }}><span className="pink">Refill önceliği</span><br/>Yüksek</div>
      <div className="float-tag" style={{ right: '9%', top: '20%' }}>Aşırı stok riski<br/><span className="pink">-18%</span></div>
      <div className="float-tag" style={{ right: '7%', bottom: '16%' }}>SEVKİYAT<br/><span className="muted">Zone B-12</span></div>
    </div>
  );
}

function MiniTwin({ objects, products, setActive }) {
  return (
    <div className="mini-real-twin">
      <TwinStudio3D
        objects={objects}
        products={products.slice(0, 220)}
        cameraPreset="overview"
        heatmap="sales"
        selectedAreaId="A"
        selectedProductSku=""
        onSelectArea={() => setActive('live3d')}
        onSelectProduct={() => setActive('live3d')}
      />
    </div>
  );
}

export default function CommandCenter({ lang, setActive, products, store, onGenerate, objects, storeDna, readiness }) {
  const m = storeMetrics[store] || storeMetrics.ANKA;
  const kpis = [
    ['Planogram Skoru', m.score, '/100', 'pink'], ['Alan Kullanımı', m.utilization, '%', 'green'], ['Aktif SKU', products.length.toLocaleString('tr-TR'), '', 'blue'], ['Yerleşen Ürün', products.length.toLocaleString('tr-TR'), '', 'blue'],
    ['Refill İşçilik', '7.5', '%', 'amber'], ['Soğuk Kapasite', m.chilled, '%', 'cyan'], ['Donuk Kapasite', m.frozen, '%', 'purple'], ['Açık Görev', m.tasks, '', 'red'],
  ];
  return (
    <div className="page">
      <section className="hero hero-v3">
        <div className="hero-copy">
          <div className="section-eyebrow">PLONAGRAM OS KOMUTA MERKEZİ</div>
          <h1 className="page-title">{tt(lang, 'title')}</h1>
          <p className="page-sub">{tt(lang, 'subtitle')}</p>
          <div style={{ display: 'flex', gap: 12, marginTop: 26 }}>
            <button className="btn primary" onClick={() => onGenerate ? onGenerate() : setActive('planogram')}>✦ {tt(lang, 'generate')}</button>
            <button className="btn ghost" onClick={() => setActive('live3d')}>▣ {tt(lang, 'open3d')}</button>
          </div>
        </div>
        <ExecutiveCommandVisual products={products} />
      </section>

      <section className="grid cols-3" style={{ marginTop: 22 }}>
        <div className={`card pad setup-status-card ${storeDna ? 'ready' : 'missing'}`}>
          <div className="section-eyebrow">STORE DNA</div>
          <h3>{storeDna ? 'Depo yapısı kayıtlı' : 'Depo kurulumu eksik'}</h3>
          <p className="muted">{storeDna ? `${storeDna.layout_objects?.length || 0} obje, ${storeDna.fixture_summary?.total_modules || 0} modül` : 'Planogram üretmeden önce koridor, raf, soğuk/donuk ve fixture bilgisi kaydedilmeli.'}</p>
          <button className="btn ghost" onClick={() => setActive('storeDna')}>{storeDna ? 'Kurulumu gözden geçir' : 'Kuruluma başla'}</button>
        </div>
        <div className="card pad setup-status-card">
          <div className="section-eyebrow">ABC + CATALOG</div>
          <h3>{readiness?.merged_products ? `${readiness.merged_products} eşleşen ürün` : 'Veri pipeline durumu'}</h3>
          <p className="muted">ABC: {readiness?.abc_items || 0} · Catalog: {readiness?.catalog_products || 0} · Eksik: {(readiness?.missing || []).join(', ') || 'yok'}</p>
          <button className="btn ghost" onClick={() => setActive('storeDna')}>ABC/Catalog yükle</button>
        </div>
        <div className="card pad setup-status-card">
          <div className="section-eyebrow">PLANOGRAM HAZIRLIK</div>
          <h3>{readiness?.ready_for_planogram ? 'Üretime hazır' : 'Eksikler var'}</h3>
          <p className="muted">Store DNA + ABC + Catalog + Merge tamamlanmadan engine default layout’a düşmez.</p>
          <button className="btn primary" onClick={() => readiness?.ready_for_planogram ? onGenerate?.() : setActive('storeDna')}>{readiness?.ready_for_planogram ? 'Planogram üret' : 'Eksikleri tamamla'}</button>
        </div>
      </section>

      <section className="grid cols-4" style={{ marginTop: 22 }}>
        {kpis.map(([label, value, suffix, tone]) => <div className="card kpi" key={label}><div className="kpi-label">{label}</div><div className={`kpi-value ${tone}`}>{value}<small>{suffix}</small></div><div className="kpi-trend">↗ son 7 gün</div></div>)}
      </section>
      <section className="grid cols-2" style={{ marginTop: 22 }}>
        <div className="card pad">
          <div className="section-eyebrow">LIVE DIGITAL TWIN</div>
          <h2>Gerçek zamanlı depo replikası</h2>
          <p className="muted">Bu alan statik resim değil; Canlı 3D ile aynı raf/fixture/SKU state’inden beslenen gerçek WebGL önizlemedir.</p>
          <MiniTwin objects={objects} products={products} setActive={setActive} />
          <button className="btn ghost" style={{ marginTop: 14 }} onClick={() => setActive('live3d')}>3D stüdyoyu aç →</button>
        </div>
        <div className="card pad">
          <div className="section-eyebrow">COUNCIL INTELLIGENCE</div>
          <h2>Akıllı öneriler</h2>
          <p className="muted">Öneriler Store DNA, SKU Graph, fixture durumu, refill maliyeti ve saha geri bildirimi üzerinden okunur.</p>
          <div className="list">{insights.map((i) => <div className="item" key={i.title}><div><b>{i.title}</b><br/><span className="muted">{i.text}</span></div><span className={`badge ${i.tone}`}>{i.impact}</span></div>)}</div>
        </div>
      </section>
    </div>
  );
}
