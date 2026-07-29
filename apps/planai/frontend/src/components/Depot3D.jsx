import { useMemo, useState } from 'react';
import TwinStudio3D from './TwinStudio3D.jsx';
import LayoutEditor from './LayoutEditor.jsx';

function flattenProducts(plan) {
  const products = [];
  (plan?.aisles || []).forEach((aisle) => (aisle.modules || []).forEach((module) => (module.shelves || []).forEach((shelf) => (shelf.products || []).forEach((product) => {
    products.push({ ...product, aisle_id: product.aisle_id || aisle.aisle_id, module_id: product.module_id || module.module_id, shelf_no: product.shelf_no || shelf.shelf_no });
  }))));
  return products;
}

function objectsFromPlan(plan) {
  if (Array.isArray(plan?.layout_objects) && plan.layout_objects.length) return plan.layout_objects;
  return (plan?.aisles || []).map((aisle, index) => ({
    id: String(aisle.aisle_id || `A${index + 1}`),
    label: `Koridor ${aisle.aisle_id || index + 1}`,
    type: 'corridor',
    zone: aisle.zone || aisle.storage_type || 'AMBIENT',
    x: 8 + (index % 3) * 34,
    y: 12 + Math.floor(index / 3) * 22,
    w: 28,
    d: 9,
    h: 2.5,
    modules: aisle.modules?.length || 1,
    shelves: (aisle.modules || []).reduce((sum, module) => sum + (module.shelves?.length || 0), 0),
  }));
}

export default function Depot3D({ plan, onShelfOpen, onLayoutChange, lang = 'tr' }) {
  const [selectedAreaId, setSelectedAreaId] = useState('');
  const [selectedProductSku, setSelectedProductSku] = useState('');
  const [editorOpen, setEditorOpen] = useState(false);
  const objects = useMemo(() => objectsFromPlan(plan), [plan]);
  const products = useMemo(() => flattenProducts(plan), [plan]);

  return (
    <section className="depot3d-foundation">
      <header className="depot3d-foundation-header">
        <div><div className="section-eyebrow">CANONICAL TWIN · V4.2</div><h2>Planogram 3D</h2><p className="muted">Sahne yalnızca doğrulanmış fixture, raf ve yerleşim verisini gösterir.</p></div>
        <button className="btn ghost" onClick={() => setEditorOpen(true)}>Mimariyi düzenle</button>
      </header>
      <TwinStudio3D objects={objects} products={products} cameraPreset="overview" heatmap="sales" selectedAreaId={selectedAreaId} selectedProductSku={selectedProductSku} onSelectArea={(area) => { setSelectedAreaId(area.id); onShelfOpen?.(area); }} onSelectProduct={(product) => setSelectedProductSku(product.sku)} />
      <LayoutEditor open={editorOpen} plan={plan} onClose={() => setEditorOpen(false)} onSave={onLayoutChange} lang={lang} />
    </section>
  );
}

