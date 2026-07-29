import { api } from '../../services/api.js';
import StoreDNASetupWizard from './StoreDNASetupWizard.jsx';
import ABCCatalogUploadPanel from './ABCCatalogUploadPanel.jsx';

export default function StoreDNAWorkspace({ store, storeName, storeDna, setStoreDna, setProducts, notify, setActive, setReadiness }) {
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
          <div className="section-eyebrow">STORE DNA & DATA SETUP</div>
          <h1 className="page-title">Depo kurulum merkezi</h1>
          <p className="page-sub">Önce fiziksel depo gerçekliği, sonra ABC + Catalog ürün grafiği. Planogram ancak bu üçlü tamamlanınca güvenilir olur.</p>
        </div>
        <button className="btn ghost" onClick={() => setActive?.('architect')}>Serbest editöre geç</button>
      </section>

      {storeDna ? (
        <div className="card pad dna-ready-card">
          <div className="section-eyebrow">STORE DNA HAZIR</div>
          <h2>{storeDna.store_name || store}</h2>
          <p className="muted">Bu depo için kayıtlı Store DNA var. Gerekirse aşağıdan yeniden oluşturabilir ya da Layout Architect’te düzenleyebilirsin.</p>
          <div className="summary-chips">
            <span>{storeDna.fixture_summary?.total_objects || storeDna.layout_objects?.length || 0} obje</span>
            <span>{storeDna.fixture_summary?.total_modules || 0} modül</span>
            <span>{storeDna.fixture_summary?.total_shelves || 0} raf</span>
          </div>
        </div>
      ) : null}

      <StoreDNASetupWizard
        storeCode={store}
        storeName={storeName || store}
        onComplete={async (dna) => { setStoreDna?.(dna); notify?.('Store DNA kaydedildi.'); try { setReadiness?.(await api.readiness(store)); } catch(e) {} }}
        onOpenArchitect={() => setActive?.('architect')}
      />

      <ABCCatalogUploadPanel storeCode={store} onMergeComplete={handleMergeComplete} notify={notify} />
    </div>
  );
}
