import { api } from '../../services/api.js';
import StoreDNASetupWizard from './StoreDNASetupWizard.jsx';
import ABCCatalogUploadPanel from './ABCCatalogUploadPanel.jsx';

export default function StoreDNAWorkspace({ lang = 'tr', store, storeName, storeProfile, storeDna, setStoreDna, setProducts, setObjects, notify, setActive, setReadiness }) {
  const copy = ({
    tr: { eyebrow: 'DEPO DNA & VERİ KURULUMU', title: 'Depo kurulum merkezi', sub: 'Seçili depoya ait fiziksel yerleşim, onaylı ekipman envanteri ve ürün verisi tek kaynaktan yönetilir.', editor: 'Mimari Düzenleyici', ready: 'DEPO DNA HAZIR', readyText: 'Bu depo için kayıtlı yapı var. Aşağıdaki değerler seçili depo ve ekipman master’ıyla eşleşir.', object: 'obje', module: 'modül', shelf: 'raf' },
    en: { eyebrow: 'STORE DNA & DATA SETUP', title: 'Depot setup center', sub: 'Physical layout, approved fixture inventory and product data for the selected depot are managed from one source.', editor: 'Layout Architect', ready: 'STORE DNA READY', readyText: 'A saved structure exists for this depot. The values below match the selected depot and equipment master.', object: 'objects', module: 'modules', shelf: 'shelves' },
    de: { eyebrow: 'LAGER-DNA & DATEN', title: 'Lager-Einrichtungszentrum', sub: 'Physisches Layout, freigegebener Ausstattungsbestand und Produktdaten werden aus einer Quelle verwaltet.', editor: 'Layout-Architekt', ready: 'LAGER-DNA BEREIT', readyText: 'Für dieses Lager ist eine Struktur gespeichert. Die Werte entsprechen dem Lager- und Ausstattungsmaster.', object: 'Objekte', module: 'Module', shelf: 'Regale' },
    ar: { eyebrow: 'بيانات وإعداد المستودع', title: 'مركز إعداد المستودع', sub: 'تتم إدارة التخطيط الفعلي وسجل المعدات المعتمد وبيانات المنتجات من مصدر واحد.', editor: 'مصمم التخطيط', ready: 'بيانات المستودع جاهزة', readyText: 'يوجد هيكل محفوظ لهذا المستودع والقيم مطابقة لسجل المستودع والمعدات.', object: 'عنصر', module: 'وحدة', shelf: 'رف' },
  })[lang] || {};
  async function handleMergeComplete(result) {
    if (Array.isArray(result.merged_products) && result.merged_products.length) {
      setProducts?.(result.merged_products);
    }
    try {
      const ready = await api.readiness(store);
      setReadiness?.(ready);
    } catch (e) {}
  }

  return (
    <div className="page">
      <section className="page-head">
        <div>
          <div className="section-eyebrow">{copy.eyebrow}</div>
          <h1 className="page-title">{copy.title}</h1>
          <p className="page-sub">{copy.sub}</p>
        </div>
        <button className="btn ghost" onClick={() => setActive?.('architect')}>{copy.editor}</button>
      </section>

      {storeDna ? (
        <div className="card pad dna-ready-card">
          <div className="section-eyebrow">{copy.ready}</div>
          <h2>{storeDna.store_name || store}</h2>
          <p className="muted">{copy.readyText}</p>
          <div className="summary-chips">
            <span>{storeDna.fixture_summary?.total_objects || storeDna.layout_objects?.length || 0} {copy.object}</span>
            <span>{storeDna.fixture_summary?.total_modules || 0} {copy.module}</span>
            <span>{storeDna.fixture_summary?.total_shelves || 0} {copy.shelf}</span>
          </div>
        </div>
      ) : null}

      <StoreDNASetupWizard
        lang={lang}
        storeCode={store}
        storeName={storeName || store}
        storeProfile={storeProfile}
        initialDna={storeDna}
        onComplete={async (dna) => {
          setStoreDna?.(dna);
          if (dna?.layout_objects?.length) setObjects?.(dna.layout_objects);
          notify?.('Store DNA kaydedildi.');
          try { setReadiness?.(await api.readiness(store)); } catch(e) {}
        }}
        onOpenArchitect={() => setActive?.('architect')}
      />

      <ABCCatalogUploadPanel storeCode={store} onMergeComplete={handleMergeComplete} notify={notify} />
    </div>
  );
}
