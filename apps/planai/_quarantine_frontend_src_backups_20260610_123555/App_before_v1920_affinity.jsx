import { useEffect, useRef, useState } from 'react';
import Shell from './components/Shell.jsx';
import LoadingScreen from './components/LoadingScreen.jsx';
import OperationLoadingOverlay from './components/OperationLoadingOverlay.jsx';
import CommandCenter from './components/CommandCenter.jsx';
import Live3D from './components/Live3D.jsx';
import LayoutArchitect from './components/LayoutArchitect.jsx';
import ProductPlacementStudio from './components/ProductPlacementStudio.jsx';
import PlanogramWorkspace from './components/PlanogramWorkspace.jsx';
import StoreDNAWorkspace from './components/StoreDNA/StoreDNAWorkspace.jsx';
import { Admin, Delta, FixtureLibrary, PhotoEvidence, ProductLibrary, Publishing, Reports, Rules, Tasks } from './components/DataViews.jsx';
import { initialObjects, initialTasks, productsSeed } from './data/mock.js';
import { api } from './services/api.js';
import { normalizeProductsForBackend, parseCsvProducts, parseJsonLayout } from './utils/fileParsers.js';
import { buildStorePlan, normalizeProduct, updateObjectsFromPlan } from './utils/planogramAllocatorV2.js';

function isAbort(err) {
  return err?.name === 'AbortError' || String(err?.message || '').toLowerCase().includes('abort');
}

function normalizeBackendProduct(p, idx = 0) {
  return normalizeProduct(p, idx);
}

function productsFromPlanogram(result, fallbackProducts) {
  const plan = result?.planogram || result?.layout || null;
  const out = [];
  if (plan?.aisles) {
    plan.aisles.forEach((aisle) => {
      (aisle.modules || []).forEach((module) => {
        (module.shelves || []).forEach((shelf) => {
          (shelf.products || []).forEach((p, idx) => out.push(normalizeBackendProduct({ ...p, aisle_id: aisle.aisle_id, module_id: module.module_id, shelf_no: shelf.shelf_no }, idx)));
        });
      });
    });
  }
  return out.length ? out : fallbackProducts;
}

function objectsFromLayout(layout, fallbackObjects) {
  if (!layout) return fallbackObjects;
  if (Array.isArray(layout.objects)) return layout.objects;
  if (Array.isArray(layout.layout_objects) && layout.layout_objects.length) {
    return [
      ...fallbackObjects.filter((o) => ['corridor', 'chilled_room', 'frozen_room', 'dispatch', 'receiving', 'algida_fridge', 'horizontal_fridge', 'steel_rack'].includes(o.type)),
      ...layout.layout_objects.map((o, idx) => ({
        id: o.id || `${o.type || 'OBJ'}_${idx + 1}`,
        label: o.label || String(o.type || 'Nesne').toUpperCase(),
        type: o.type || 'structure',
        zone: o.zone || (String(o.type || '').includes('column') ? 'STRUCTURE' : 'AMBIENT'),
        x: Number(o.x || o.grid_x || 8),
        y: Number(o.y || o.grid_y || 8),
        w: Number(o.w || o.width || 2),
        d: Number(o.d || o.depth || 2),
        h: Number(o.h || o.height || 3),
        rotation: Number(o.rotation || 0),
        modules: Number(o.modules || 0),
        shelves: Number(o.shelves || 0),
        utilization: Number(o.utilization || 0),
        changed: Number(o.changed || 0),
      }))
    ];
  }
  if (Array.isArray(layout.aisles)) {
    const aisles = layout.aisles.map((a, idx) => ({
      id: String(a.aisle_id || `A${idx + 1}`),
      label: String(a.aisle_id || `A${idx + 1}`),
      type: 'corridor',
      zone: a.zone_type?.includes('FROZEN') ? 'FROZEN' : a.zone_type?.includes('COLD') ? 'CHILLED' : 'AMBIENT',
      x: Math.min(112, 12 + (idx % 3) * 38),
      y: Math.min(86, 24 + Math.floor(idx / 3) * 22),
      w: 30,
      d: 8,
      h: 2.5,
      rotation: Number(a.layout_position?.rotation || 0),
      modules: Number(a.modules?.length || 6),
      shelves: Number((a.modules || []).reduce((s, m) => s + (m.shelves?.length || 0), 0) || 24),
      utilization: 70,
      changed: 0,
    }));
    return [...fallbackObjects.filter((o) => !/^[A-Z]$/.test(o.id)), ...aisles];
  }
  return fallbackObjects;
}

function councilOptimizeProducts(list, currentObjects = initialObjects) {
  const plan = buildStorePlan(list, currentObjects);
  return plan.placed;
}

function recalcObjectsFromProducts(objects, products) {
  return updateObjectsFromPlan(objects, buildStorePlan(products, objects));
}


function productKey(p = {}, idx = 0) {
  return String(
    p.sku ||
    p.SKU ||
    p.barcode ||
    p.Barcodes ||
    p.product.sku ||
    p.SKU ||
    p.barcode ||
    p.Barcodes ||
    p.product_barcodes ||
    p.name ||
    p.product_name ||
    `ROW-${idx}`
  ).trim();
}


function objectCapacityScore(list = []) {
  return (list || []).reduce((sum, o) => {
    return sum + Math.max(1, Number(o.modules || 0)) * Math.max(1, Number(o.shelves || 0));
  }, 0);
}

function collectObjectArrays(value, out = [], seen = new Set()) {
  if (!value || typeof value !== 'object' || seen.has(value)) return out;
  seen.add(value);

  if (Array.isArray(value)) {
    if (value.length && value.some((x) => x && typeof x === 'object' && ('modules' in x || 'shelves' in x || 'type' in x || 'zone' in x))) {
      out.push(value);
    }
    value.forEach((x) => collectObjectArrays(x, out, seen));
    return out;
  }

  Object.values(value).forEach((x) => collectObjectArrays(x, out, seen));
  return out;
}

function resolvePlanObjects(currentObjects = [], storeDna = null) {
  const candidates = [
    currentObjects,
    ...(collectObjectArrays(storeDna) || []),
  ].filter((x) => Array.isArray(x) && x.length);

  if (!candidates.length) return currentObjects;

  return candidates
    .map((list) => ({ list, score: objectCapacityScore(list), count: list.length }))
    .sort((a, b) => b.score - a.score || b.count - a.count)[0].list;
}

function mergeCandidateProducts(...lists) {
  const map = new Map();

  for (const list of lists) {
    for (const item of list || []) {
      if (!item) continue;
      const key = productKey(item, map.size);
      if (!key) continue;

      const prev = map.get(key) || {};
      map.set(key, {
        ...prev,
        ...item,
        sku: item.sku || item.SKU || prev.sku || prev.SKU || key,
      });
    }
  }

  return [...map.values()];
}


export default function App() {
  const [loading, setLoading] = useState(true);
  const [active, setActive] = useState('command');
  const [lang, setLang] = useState('tr');
  const [store, setStore] = useState('ANKA');
  const [objects, setObjects] = useState(initialObjects);
  const [products, setProducts] = useState(productsSeed);
  const [unplacedProducts, setUnplacedProducts] = useState([]);
  const [tasks, setTasks] = useState(initialTasks);
  const [storeDna, setStoreDna] = useState(null);
  const [readiness, setReadiness] = useState(null);
  const [toast, setToast] = useState('');
  const [operation, setOperation] = useState({ open: false, mode: 'plan', progress: 0, title: '', subtitle: '' });
  const skuInput = useRef(null);
  const layoutInput = useRef(null);
  const abortRef = useRef(null);

  useEffect(() => {
    const timer = window.setTimeout(() => setLoading(false), 1150);
    return () => window.clearTimeout(timer);
  }, []);

  useEffect(() => {
    let mounted = true;
    async function loadPersistedState() {
      try {
        const boot = await api.bootstrap(store);
        if (!mounted || !boot || boot.status !== 'success') return;

        const savedLayout = boot.layout?.payload;
        const savedPlan = boot.planogram?.payload;
        if (boot.dna) setStoreDna(boot.dna);
        try { const ready = await api.readiness(store); if (mounted) setReadiness(ready); } catch (e) {}

        if (savedLayout?.objects?.length) {
          setObjects(savedLayout.objects);
        }

        if (savedPlan?.products?.length) {
          setProducts(savedPlan.products.map(normalizeBackendProduct));
        }
        if (Array.isArray(savedPlan?.unplacedProducts)) {
          setUnplacedProducts(savedPlan.unplacedProducts);
        }
        if (!savedLayout?.objects?.length && savedPlan?.objects?.length) {
          setObjects(savedPlan.objects);
        }
        if (boot.tasks?.length) {
          setTasks(boot.tasks.map((t) => ({
            id: t.external_id || t.id,
            store: t.store_code || store,
            title: t.title,
            owner: t.owner || 'Store Manager',
            priority: t.priority || 'Medium',
            deadline: t.deadline || '',
            status: t.status || 'Open',
            response: t.response || '',
          })));
        }
      } catch (err) {
        // DB kapalıysa ürün deneyimini düşürme; local state ile devam et.
      }
    }
    loadPersistedState();
    return () => { mounted = false; };
  }, [store]);

  function notify(msg) {
    setToast(msg);
    window.setTimeout(() => setToast(''), 3000);
  }

  async function runOperation(meta, work) {
    const controller = new AbortController();
    abortRef.current = controller;
    let p = 8;
    setOperation({ open: true, progress: p, ...meta });
    const timer = window.setInterval(() => {
      p = Math.min(88, p + Math.random() * 12 + 4);
      setOperation((prev) => ({ ...prev, progress: p }));
    }, 420);
    try {
      const result = await work(controller.signal);
      window.clearInterval(timer);
      setOperation((prev) => ({ ...prev, progress: 100 }));
      await new Promise((resolve) => window.setTimeout(resolve, 380));
      return result;
    } catch (err) {
      if (!isAbort(err)) throw err;
      notify('İşlem iptal edildi. Mevcut plan korunuyor.');
      return null;
    } finally {
      window.clearInterval(timer);
      abortRef.current = null;
      setOperation((prev) => ({ ...prev, open: false }));
      if (skuInput.current) skuInput.current.value = '';
      if (layoutInput.current) layoutInput.current.value = '';
    }
  }

  function cancelOperation() {
    abortRef.current?.abort();
    setOperation((prev) => ({ ...prev, open: false }));
  }

  async function handleSkuFile(file) {
    if (!file) return;
    await runOperation({ mode: 'sku', title: 'SKU dosyası işleniyor', subtitle: `${file.name} okunuyor. İstersen işlemi iptal edebilirsin.` }, async (signal) => {
      let nextProducts = [];
      const ext = file.name.split('.').pop()?.toLowerCase();
      try {
        const res = await api.uploadProducts(file, signal);
        nextProducts = (res.products || []).map(normalizeBackendProduct);
      } catch (err) {
        if (isAbort(err)) throw err;
        if (ext === 'csv') nextProducts = await parseCsvProducts(file);
        else throw new Error('XLSX/Excel okuma için backend açık olmalı. CSV yükleme tarayıcı içinde çalışır.');
      }
      if (!nextProducts.length) throw new Error('Dosyada okunabilir SKU bulunamadı. Header alanlarını kontrol et: sku, product_name, brand, storage_type, sales_qty_7d veya % Orders.');
      const assigned = buildStorePlan(nextProducts, objects);
      setProducts(assigned.placed);
      setUnplacedProducts(assigned.unplaced);
      const nextObjects = updateObjectsFromPlan(objects, assigned);
      setObjects(nextObjects);
      try {
        await api.savePlanogram(store, { products: assigned.placed, unplacedProducts: assigned.unplaced, objects: nextObjects, source: 'sku_upload' }, { placed: assigned.placed.length, unplaced: assigned.unplaced.length }, 'SKU upload auto-save', signal);
      } catch (err) {}
      notify(`${nextProducts.length} SKU okundu. ${assigned.placed.length} ürün fixture/raf state'ine dağıtıldı, ${assigned.unplaced.length} ürün atanamadı raporuna düştü.`);
      return assigned.placed;
    }).catch((err) => notify(err.message || 'SKU yükleme başarısız.'));
  }

  async function handleLayoutFile(file) {
    if (!file) return;
    await runOperation({ mode: 'layout', title: 'Layout dijital ikize çevriliyor', subtitle: `${file.name} içinden oda, fixture ve koridor bilgisi okunuyor.` }, async (signal) => {
      const ext = file.name.split('.').pop()?.toLowerCase();
      let nextObjects = null;
      if (ext === 'json') {
        nextObjects = await parseJsonLayout(file);
      } else {
        const res = await api.uploadLayout(file, store, signal);
        if (!res?.success) throw new Error(res?.message || 'Layout parse edilemedi.');
        nextObjects = objectsFromLayout(res.layout, objects);
      }
      if (!nextObjects?.length) throw new Error('Layout içinde kullanılabilir obje bulunamadı.');
      setObjects(nextObjects);
      try {
        await api.saveLayout(store, { objects: nextObjects, source_file: file.name }, 'Layout upload auto-save', signal);
      } catch (err) {}
      setActive('architect');
      notify(`${file.name} yüklendi. Layout Architect ve 3D twin aynı state ile güncellendi.`);
      return nextObjects;
    }).catch((err) => {
      if (!isAbort(err)) notify(err.message || 'Layout yükleme başarısız.');
    });
  }

  async function generateOptimalPlan() {
    if (!storeDna) {
      notify('Bu depo için Store DNA eksik. Önce Depo Kurulumu ekranında layout/fixture gerçekliğini kaydet.');
      setActive('storeDna');
      return;
    }
    await runOperation({ mode: 'plan', title: 'Council Engine planogram üretiyor', subtitle: 'Satış, storage, fixture, facing, depth ve refill maliyeti birlikte hesaplanıyor.' }, async (signal) => {
      // V1.9.17:
      // Tek yerle?tirme do?rusu lokal domain-aware allocator.
      // products state'i ?nceki yerle?enleri, unplacedProducts ise ?nceki atanamayanlar? tutar.
      // Optimum plan ?retirken ikisini tekrar tek aday havuzuna toplamazsak 2800+ SKU sonsuza kadar d??ar?da kal?r.
      const sourceProducts = mergeCandidateProducts(products, unplacedProducts);

      if (!sourceProducts.length) {
        throw new Error('Plan ?retmek i?in aday SKU bulunamad?. ?nce ABC/SKU dosyas? y?kle.');
      }

      try {
        // Backend yaln?zca sa?l?k/enrichment kontrol? i?in ?a?r?labilir; sonucu placement source olarak kullanm?yoruz.
        // Eski backend plan? sourceProducts ?zerine yazarsa tek motor ilkesi bozulur.
        const payload = { products: normalizeProductsForBackend(sourceProducts.slice(0, 250)), layout: null, mode: 'COUNCIL_HEALTH_CHECK' };
        await api.generatePlanogramCouncil(payload, signal);
      } catch (err) {
        if (isAbort(err)) throw err;
      }

      const planObjects = resolvePlanObjects(objects, storeDna);
      const assigned = buildStorePlan(sourceProducts, planObjects, { forceFrontBalance: true });
      const nextObjects = updateObjectsFromPlan(planObjects, assigned);
      const nextTask = { id: `T-${Date.now().toString().slice(-5)}`, store: 'Anka (İstanbul)', title: `Council planogram sonrası ${assigned.unplaced.length} atanamayan SKU kontrolü`, owner: 'Store Manager', priority: assigned.unplaced.length ? 'High' : 'Medium', deadline: 'Bugün', status: 'Open', response: '' };
      setProducts(assigned.placed);
      setUnplacedProducts(assigned.unplaced);
      setObjects(nextObjects);
      setTasks((prev) => [nextTask, ...prev]);
      try {
        await api.savePlanogram(store, { products: assigned.placed, unplacedProducts: assigned.unplaced, objects: nextObjects, source: 'council_engine' }, { placed: assigned.placed.length, unplaced: assigned.unplaced.length }, 'Council Engine generated plan', signal);
        await api.saveLayout(store, { objects: nextObjects, source: 'council_engine' }, 'Layout state after Council plan', signal);
        await api.createTask({ ...nextTask, store_code: store, external_id: nextTask.id }, signal);
      } catch (err) {}
      notify(`Council Engine planı uygulandı. ${assigned.placed.length} ürün yerleşti, ${assigned.unplaced.length} ürün atanamadı raporlandı.`);
      setActive('planogram');
      return assigned.placed;
    }).catch((err) => {
      if (!isAbort(err)) notify(err.message || 'Optimum plan üretilemedi.');
    });
  }

  if (loading) return <LoadingScreen lang={lang} />;

  const common = { lang, objects, setObjects, products, setProducts, unplacedProducts, setUnplacedProducts, tasks, setTasks, store, notify, setActive, onGenerate: generateOptimalPlan, storeDna, setStoreDna, readiness, setReadiness };
  const pages = {
    command: <CommandCenter {...common} />,
    storeDna: <StoreDNAWorkspace {...common} storeName={store} />,
    live3d: <Live3D {...common} />,
    architect: <LayoutArchitect {...common} />,
    placement: <ProductPlacementStudio {...common} />,
    library: <ProductLibrary {...common} />,
    fixture: <FixtureLibrary {...common} />,
    planogram: <PlanogramWorkspace {...common} />,
    rules: <Rules {...common} />,
    delta: <Delta {...common} />,
    publishing: <Publishing {...common} />,
    tasks: <Tasks {...common} />,
    photos: <PhotoEvidence {...common} />,
    reports: <Reports {...common} />,
    admin: <Admin {...common} />,
  };

  return (
    <>
      <input ref={skuInput} type="file" accept=".csv,.xlsx" hidden onChange={(e) => handleSkuFile(e.target.files?.[0])} />
      <input ref={layoutInput} type="file" accept=".dxf,.json,.csv" hidden onChange={(e) => handleLayoutFile(e.target.files?.[0])} />
      <Shell
        lang={lang}
        setLang={setLang}
        active={active}
        setActive={setActive}
        store={store}
        setStore={setStore}
        onGenerate={generateOptimalPlan}
        onUploadSku={() => skuInput.current?.click()}
        onUploadLayout={() => layoutInput.current?.click()}
      >
        {pages[active] || pages.command}
      </Shell>
      <OperationLoadingOverlay {...operation} onCancel={cancelOperation} />
      {toast && <div className="toast">{toast}</div>}
    </>
  );
}
