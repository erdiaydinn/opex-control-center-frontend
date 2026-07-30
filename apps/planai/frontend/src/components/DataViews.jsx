import { useEffect, useMemo, useState } from 'react';
import { fixtures, insights, storeMetrics, stores } from '../data/mock.js';
import { tt } from '../i18n/dictionary.js';
import { api } from '../services/api.js';
import { ProductThumb, storageTone } from './ProductVisuals.jsx';

const labels = {
  tr: {
    dataCenter: 'Veri Merkezi',
    productLibrary: 'Ürün Kütüphanesi',
    productSubtitle: 'SKU, barkod, ürün adı, marka, kategori, storage type, ölçü, satış ve ürün görseli.',
    productPool: 'Ürün havuzu',
    placed: 'Yerleşen',
    candidate: 'Aday / Atanmayan',
    source: 'Kütüphane kaynağı',
    active: 'Aktif',
    empty: 'Boş',
    uploadedPlaced: 'Yüklenen + yerleşen',
    activePlan: 'Aktif plan',
    waitingPool: 'Plan bekleyen havuz',
    backendCatalog: 'Backend catalog',
    statePool: 'State havuzu',
    searchPlaceholder: 'SKU, barkod, ürün veya marka ara...',
    search: 'Ara',
    reset: 'Temizle',
    productImages: 'Ürün görselleri',
    noProducts: 'Ürün bulunamadı. SKU dosyası yükle veya arama filtresini temizle.',
    sku: 'SKU',
    barcode: 'Barkod',
    product: 'Ürün',
    brand: 'Marka',
    category: 'Kategori',
    storage: 'Storage',
    rawStorage: 'Ham Storage',
    fixture: 'Fixture',
    casePack: 'Koli İçi',
    sales: 'Satış',
    facing: 'Facing',
    depth: 'Depth',
    confidence: 'Güven',
    fixtureLibrary: 'Ekipman Kütüphanesi',
    delta: 'Delta Planogram',
    publishing: 'Yayınlama',
    tasks: 'Görevler',
    photos: 'Fotoğraf Kanıtı',
    reports: 'Raporlar',
    admin: 'Admin',
    priority: 'Öncelik',
    status: 'Durum',
    deadline: 'Deadline',
    owner: 'Sorumlu',
    open: 'Açık',
    inProgress: 'Başladı',
    done: 'Tamamlandı',
    blocked: 'Bloke',
    approved: 'Onaylandı',
    pending: 'Onay Bekliyor',
    rejected: 'Reddedildi',
    high: 'Yüksek',
    medium: 'Orta',
    low: 'Düşük',
  },
  en: {
    dataCenter: 'Data Center',
    productLibrary: 'Product Library',
    productSubtitle: 'SKU, barcode, product name, brand, category, storage type, dimensions, sales and image.',
    productPool: 'Product pool',
    placed: 'Placed',
    candidate: 'Candidate / Unplaced',
    source: 'Library source',
    active: 'Active',
    empty: 'Empty',
    uploadedPlaced: 'Uploaded + placed',
    activePlan: 'Active plan',
    waitingPool: 'Waiting pool',
    backendCatalog: 'Backend catalog',
    statePool: 'State pool',
    searchPlaceholder: 'Search SKU, barcode, product or brand...',
    search: 'Search',
    reset: 'Reset',
    productImages: 'Product images',
    noProducts: 'No products found. Upload a SKU file or clear the filter.',
    sku: 'SKU',
    barcode: 'Barcode',
    product: 'Product',
    brand: 'Brand',
    category: 'Category',
    storage: 'Storage',
    rawStorage: 'Raw Storage',
    fixture: 'Fixture',
    casePack: 'Case Pack',
    sales: 'Sales',
    facing: 'Facing',
    depth: 'Depth',
    confidence: 'Confidence',
    fixtureLibrary: 'Fixture Library',
    delta: 'Delta Planogram',
    publishing: 'Publishing',
    tasks: 'Tasks',
    photos: 'Photo Evidence',
    reports: 'Reports',
    admin: 'Admin',
    priority: 'Priority',
    status: 'Status',
    deadline: 'Deadline',
    owner: 'Owner',
    open: 'Open',
    inProgress: 'In Progress',
    done: 'Done',
    blocked: 'Blocked',
    approved: 'Approved',
    pending: 'Pending',
    rejected: 'Rejected',
    high: 'High',
    medium: 'Medium',
    low: 'Low',
  },
  de: {
    dataCenter: 'Datenzentrum',
    productLibrary: 'Produktbibliothek',
    productSubtitle: 'SKU, Barcode, Produktname, Marke, Kategorie, Lagerart, Maße, Verkauf und Bild.',
    productPool: 'Produktpool',
    placed: 'Platziert',
    candidate: 'Kandidat / Nicht platziert',
    source: 'Bibliotheksquelle',
    active: 'Aktiv',
    empty: 'Leer',
    uploadedPlaced: 'Hochgeladen + platziert',
    activePlan: 'Aktiver Plan',
    waitingPool: 'Wartender Pool',
    backendCatalog: 'Backend-Katalog',
    statePool: 'State-Pool',
    searchPlaceholder: 'SKU, Barcode, Produkt oder Marke suchen...',
    search: 'Suchen',
    reset: 'Zurücksetzen',
    productImages: 'Produktbilder',
    noProducts: 'Keine Produkte gefunden. SKU-Datei hochladen oder Filter löschen.',
    sku: 'SKU',
    barcode: 'Barcode',
    product: 'Produkt',
    brand: 'Marke',
    category: 'Kategorie',
    storage: 'Lagerart',
    rawStorage: 'Roh-Lagerart',
    fixture: 'Fixture',
    casePack: 'Kolli',
    sales: 'Verkauf',
    facing: 'Facing',
    depth: 'Depth',
    confidence: 'Vertrauen',
    fixtureLibrary: 'Fixture-Bibliothek',
    delta: 'Delta Planogramm',
    publishing: 'Veröffentlichung',
    tasks: 'Aufgaben',
    photos: 'Fotobeleg',
    reports: 'Berichte',
    admin: 'Admin',
    priority: 'Priorität',
    status: 'Status',
    deadline: 'Frist',
    owner: 'Owner',
    open: 'Offen',
    inProgress: 'Gestartet',
    done: 'Erledigt',
    blocked: 'Blockiert',
    approved: 'Genehmigt',
    pending: 'Wartet',
    rejected: 'Abgelehnt',
    high: 'Hoch',
    medium: 'Mittel',
    low: 'Niedrig',
  },
  ar: {
    dataCenter: 'مركز البيانات',
    productLibrary: 'مكتبة المنتجات',
    productSubtitle: 'SKU، الباركود، اسم المنتج، العلامة، الفئة، نوع التخزين، الأبعاد، المبيعات والصورة.',
    productPool: 'مجموعة المنتجات',
    placed: 'تم التوزيع',
    candidate: 'مرشح / غير موزع',
    source: 'مصدر المكتبة',
    active: 'نشط',
    empty: 'فارغ',
    uploadedPlaced: 'مرفوع + موزع',
    activePlan: 'الخطة النشطة',
    waitingPool: 'قائمة الانتظار',
    backendCatalog: 'كتالوج النظام',
    statePool: 'بيانات الشاشة',
    searchPlaceholder: 'ابحث عن SKU أو باركود أو منتج أو علامة...',
    search: 'بحث',
    reset: 'مسح',
    productImages: 'صور المنتجات',
    noProducts: 'لم يتم العثور على منتجات. ارفع ملف SKU أو امسح الفلتر.',
    sku: 'SKU',
    barcode: 'الباركود',
    product: 'المنتج',
    brand: 'العلامة',
    category: 'الفئة',
    storage: 'التخزين',
    rawStorage: 'التخزين الخام',
    fixture: 'المعدة',
    casePack: 'عدد الكرتون',
    sales: 'المبيعات',
    facing: 'Facing',
    depth: 'Depth',
    confidence: 'الثقة',
    fixtureLibrary: 'مكتبة المعدات',
    delta: 'دلتا بلانوجرام',
    publishing: 'النشر',
    tasks: 'المهام',
    photos: 'إثبات الصور',
    reports: 'التقارير',
    admin: 'الإدارة',
    priority: 'الأولوية',
    status: 'الحالة',
    deadline: 'الموعد',
    owner: 'المسؤول',
    open: 'مفتوح',
    inProgress: 'بدأ',
    done: 'مكتمل',
    blocked: 'محظور',
    approved: 'موافق',
    pending: 'قيد الانتظار',
    rejected: 'مرفوض',
    high: 'عالٍ',
    medium: 'متوسط',
    low: 'منخفض',
  },
};

function L(lang, key) {
  return labels[lang]?.[key] || labels.tr[key] || key;
}

function trPriority(value, lang = 'tr') {
  const v = String(value || '').toLowerCase();
  if (v.includes('high') || v.includes('yüksek')) return L(lang, 'high');
  if (v.includes('low') || v.includes('düşük')) return L(lang, 'low');
  return L(lang, 'medium');
}

function trStatus(value, lang = 'tr') {
  const v = String(value || '').toLowerCase();
  if (v.includes('progress') || v.includes('başladı')) return L(lang, 'inProgress');
  if (v.includes('done') || v.includes('tamam')) return L(lang, 'done');
  if (v.includes('blocked') || v.includes('bloke')) return L(lang, 'blocked');
  if (v.includes('approved') || v.includes('onaylandı')) return L(lang, 'approved');
  if (v.includes('pending') || v.includes('bekliyor')) return L(lang, 'pending');
  if (v.includes('rejected') || v.includes('redd')) return L(lang, 'rejected');
  return L(lang, 'open');
}

function n(v, fallback = 0) {
  const x = Number(String(v ?? '').replace(',', '.'));
  return Number.isFinite(x) ? x : fallback;
}

function productId(raw, idx = 0) {
  return String(raw?.sku || raw?.SKU || raw?.barcode || raw?.product_barcodes || raw?.platform_product_id || `ROW-${idx + 1}`).trim();
}

function normalizeLibraryProduct(raw = {}, idx = 0) {
  const sku = productId(raw, idx);
  const storage = String(raw.storage || raw.storage_type || raw.storage_class || raw.catalog_storage_type || 'AMBIENT').toUpperCase();
  return {
    ...raw,
    sku,
    barcode: raw.barcode || raw.product_barcodes || raw.Barcode || '',
    name: raw.name || raw.product_name || raw.product_name_local || raw.title || sku,
    brand: raw.brand || raw.brand_name || raw.supplier || raw.manufacturer || '-',
    category: raw.category || raw.category_l1 || raw.frontend_category_local || raw.kategori_level_1 || raw.category_l2 || raw.frontend_subcategory_local || '-',
    subcategory: raw.category_l2 || raw.frontend_subcategory_local || '',
    storage,
    storageRaw: raw.storage_raw || raw.storageRaw || '',
    fixture: raw.fixture_kind || raw.required_fixture_kind || '',
    casePack: raw.case_pack_qty || raw.case_pack || '',
    sales: raw.sales ?? raw.sales_qty_30d ?? raw.sales_qty_14d ?? raw.sales_qty_7d ?? raw.daily_sales ?? raw.order_frequency_30d ?? raw['% Orders'] ?? 0,
    facing: raw.facing ?? raw.facing_count ?? raw.fronts ?? raw.recommended_facing ?? 1,
    depth: raw.depth ?? raw.depth_units ?? raw.recommended_depth ?? raw.depth_count ?? 1,
    confidence: raw.placement_confidence ?? raw.product_confidence ?? '',
    image_url: raw.image_url || raw.catalog_image_url || raw.pim_image_url || '',
  };
}

function confidenceTone(score) {
  const s = Number(score || 0);
  if (!s) return 'muted';
  if (s >= 85) return 'green';
  if (s >= 65) return 'amber';
  return 'red';
}

export function Rules({ lang }) {
  return (
    <div className="page">
      <div className="section-eyebrow">RULE ENGINE</div>
      <h1 style={{ fontSize: 42, margin: '8px 0' }}>{tt(lang, 'rules') || 'Kural Motoru'}</h1>
      <p className="page-sub">
        Storage, fixture, kategori, marka, case pack ve saha uygulanabilirliği kuralları Komuta Merkezi ile aynı mantıktan beslenir.
      </p>
    </div>
  );
}

export function ProductLibrary({ lang, products = [], unplacedProducts = [], notify }) {
  const [backendRows, setBackendRows] = useState([]);
  const [draft, setDraft] = useState('');
  const [query, setQuery] = useState('');
  const [storage, setStorage] = useState('');
  const [loading, setLoading] = useState(false);
  const [sourceName, setSourceName] = useState('state');
  const [error, setError] = useState('');

  const stateRows = useMemo(() => {
    const source = [
      ...(Array.isArray(products) ? products : []),
      ...(Array.isArray(unplacedProducts) ? unplacedProducts : []),
    ];
    const seen = new Set();
    return source
      .map(normalizeLibraryProduct)
      .filter((p) => {
        if (!p.sku || seen.has(p.sku)) return false;
        seen.add(p.sku);
        return true;
      });
  }, [products, unplacedProducts]);

  async function loadCatalog(nextQuery = query, nextStorage = storage) {
    setLoading(true);
    setError('');
    try {
      const res = nextQuery || nextStorage
        ? await api.searchProductLibrary({ q: nextQuery, storage: nextStorage, limit: 500 })
        : await api.productLibrary(1000, 0);
      const rows = Array.isArray(res?.products) ? res.products.map(normalizeLibraryProduct) : [];
      setBackendRows(rows);
      setSourceName('backend');
      if (!rows.length && (nextQuery || nextStorage)) {
        setError(L(lang, 'noProducts'));
      }
    } catch (err) {
      setError(err?.message || 'Product Library API okunamadı.');
      setSourceName('state');
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    loadCatalog('', '');
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const baseRows = backendRows.length ? backendRows : stateRows;

  const visibleRows = useMemo(() => {
    const q = query.trim().toLowerCase();
    return baseRows
      .filter((p) => {
        const hay = `${p.sku} ${p.barcode} ${p.name} ${p.brand} ${p.category} ${p.subcategory} ${p.storageRaw}`.toLowerCase();
        if (storage && p.storage !== storage) return false;
        if (q && !hay.includes(q)) return false;
        return true;
      })
      .slice(0, 1000);
  }, [baseRows, query, storage]);

  const cards = visibleRows.slice(0, 80);

  function submitSearch() {
    setQuery(draft.trim());
    loadCatalog(draft.trim(), storage);
  }

  function clearSearch() {
    setDraft('');
    setQuery('');
    setStorage('');
    loadCatalog('', '');
  }

  return (
    <div className="page">
      <div className="section-eyebrow">{L(lang, 'dataCenter')}</div>
      <h1 style={{ fontSize: 42, margin: '8px 0' }}>{L(lang, 'productLibrary')}</h1>
      <p className="page-sub">{L(lang, 'productSubtitle')}</p>

      <div className="grid cols-4" style={{ marginBottom: 18 }}>
        <div className="card kpi">
          <div className="kpi-label">{L(lang, 'productPool')}</div>
          <div className="kpi-value">{baseRows.length.toLocaleString('tr-TR')}</div>
          <div className="kpi-trend">{L(lang, 'uploadedPlaced')}</div>
        </div>
        <div className="card kpi">
          <div className="kpi-label">{L(lang, 'placed')}</div>
          <div className="kpi-value">{(products || []).length.toLocaleString('tr-TR')}</div>
          <div className="kpi-trend">{L(lang, 'activePlan')}</div>
        </div>
        <div className="card kpi">
          <div className="kpi-label">{L(lang, 'candidate')}</div>
          <div className="kpi-value">{(unplacedProducts || []).length.toLocaleString('tr-TR')}</div>
          <div className="kpi-trend">{L(lang, 'waitingPool')}</div>
        </div>
        <div className="card kpi">
          <div className="kpi-label">{L(lang, 'source')}</div>
          <div className="kpi-value">{sourceName === 'backend' ? L(lang, 'backendCatalog') : L(lang, 'statePool')}</div>
          <div className="kpi-trend">{loading ? 'Loading...' : error ? 'API warning' : L(lang, 'active')}</div>
        </div>
      </div>

      <div className="card pad">
        <div style={{ display: 'flex', gap: 10, flexWrap: 'wrap', alignItems: 'center', marginBottom: 14 }}>
          <input
            className="search"
            value={draft}
            placeholder={L(lang, 'searchPlaceholder')}
            onChange={(e) => setDraft(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === 'Enter') submitSearch();
            }}
            style={{ minWidth: 320, flex: '1 1 360px' }}
          />
          <select
            className="search"
            value={storage}
            onChange={(e) => {
              setStorage(e.target.value);
              loadCatalog(query, e.target.value);
            }}
            style={{ maxWidth: 180 }}
          >
            <option value="">Storage: All</option>
            <option value="AMBIENT">AMBIENT</option>
            <option value="CHILLED">CHILLED</option>
            <option value="FROZEN">FROZEN</option>
          </select>
          <button className="btn primary" type="button" onClick={submitSearch}>{L(lang, 'search')}</button>
          <button className="btn ghost" type="button" onClick={clearSearch}>{L(lang, 'reset')}</button>
        </div>

        {error && <p className="muted" style={{ color: '#E84A4A' }}>{error}</p>}

        <h3>{L(lang, 'productImages')}</h3>
        {cards.length ? (
          <div className="product-card-grid">
            {cards.map((p) => (
              <div className="product-card" key={p.sku}>
                <ProductThumb product={p} />
                <div>
                  <b>{p.name}</b>
                  <br />
                  <span className="muted">{p.sku} • {p.brand}</span>
                  <br />
                  <span className={`badge ${storageTone(p.storage)}`}>{p.storage}</span>
                  {p.confidence ? <span className={`badge ${confidenceTone(p.confidence)}`} style={{ marginLeft: 6 }}>{L(lang, 'confidence')} {p.confidence}</span> : null}
                </div>
              </div>
            ))}
          </div>
        ) : (
          <p className="muted">{L(lang, 'noProducts')}</p>
        )}

        <table className="table" style={{ marginTop: 18 }}>
          <thead>
            <tr>
              <th>{L(lang, 'sku')}</th>
              <th>{L(lang, 'barcode')}</th>
              <th>{L(lang, 'product')}</th>
              <th>{L(lang, 'brand')}</th>
              <th>{L(lang, 'category')}</th>
              <th>{L(lang, 'storage')}</th>
              <th>{L(lang, 'rawStorage')}</th>
              <th>{L(lang, 'fixture')}</th>
              <th>{L(lang, 'casePack')}</th>
              <th>{L(lang, 'sales')}</th>
              <th>{L(lang, 'facing')}</th>
              <th>{L(lang, 'depth')}</th>
            </tr>
          </thead>
          <tbody>
            {visibleRows.map((p) => (
              <tr key={p.sku}>
                <td>{p.sku}</td>
                <td>{p.barcode}</td>
                <td>{p.name}</td>
                <td>{p.brand}</td>
                <td>{p.category}</td>
                <td><span className={`badge ${storageTone(p.storage)}`}>{p.storage}</span></td>
                <td>{p.storageRaw}</td>
                <td>{p.fixture}</td>
                <td>{p.casePack}</td>
                <td>{p.sales}</td>
                <td>{p.facing}</td>
                <td>{p.depth}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}

export function FixtureLibrary({ lang }) {
  return (
    <div className="page">
      <div className="section-eyebrow">FIXTURE LIBRARY</div>
      <h1 style={{ fontSize: 42, margin: '8px 0' }}>{L(lang, 'fixtureLibrary')}</h1>
      <p className="page-sub">Raf, +4 dolap, -18 donuk dolap, Algida, yatay dolap, kolon, duvar ve operasyon alanları tek ekipman sözlüğünde yönetilir.</p>
      <div className="grid cols-3">
        {(fixtures || []).map((f) => (
          <div className="card pad" key={f.id}>
            <div className="section-eyebrow">{f.id}</div>
            <h2>{f.name}</h2>
            <p className="muted">{f.type} • {f.width}×{f.depth}×{f.height} cm • {f.shelves} raf</p>
            <span className={`badge ${f.frozen ? 'purple' : f.cold ? 'cyan' : 'green'}`}>
              {f.frozen ? 'FROZEN' : f.cold ? 'CHILLED' : 'AMBIENT'}
            </span>
            <p className="muted">Depolar: {(f.stores || []).join(', ')}</p>
          </div>
        ))}
      </div>
    </div>
  );
}

export function Delta({ lang }) {
  const rows = [
    ['SKU-77881', 'A.1.2 → A.1.1', 'Facing 5 → 6', L(lang, 'high'), 'Satış hızı yüksek, ön hatta alınmalı.'],
    ['SKU-98712', 'C.2.1 → +4 Oda', 'Zone düzeltmesi', L(lang, 'high'), 'Ürün +4 zincir gerektiriyor.'],
    ['SKU-55431', 'A koridoru → arka ambient', 'Gıda izolasyonu', L(lang, 'medium'), 'Non-food ürün gıda koridorundan ayrılmalı.'],
  ];

  return (
    <div className="page">
      <div className="section-eyebrow">DELTA PLANOGRAM</div>
      <h1 style={{ fontSize: 42, margin: '8px 0' }}>{L(lang, 'delta')}</h1>
      <div className="card pad">
        <p className="muted">Saha için komple plan değil, yapılacak aksiyon listesi gösterilir.</p>
        <table className="table">
          <thead><tr><th>SKU</th><th>Taşıma</th><th>Değişiklik</th><th>Öncelik</th><th>Neden</th></tr></thead>
          <tbody>{rows.map((r) => <tr key={r[0]}>{r.map((c, i) => <td key={i}>{i === 3 ? <span className={`badge ${c === L(lang, 'high') ? 'red' : 'amber'}`}>{c}</span> : c}</td>)}</tr>)}</tbody>
        </table>
      </div>
    </div>
  );
}

export function Publishing({ lang, tasks = [] }) {
  return (
    <div className="page">
      <div className="section-eyebrow">PUBLISHING</div>
      <h1 style={{ fontSize: 42, margin: '8px 0' }}>{L(lang, 'publishing')}</h1>
      <div className="grid cols-3">
        <div className="card kpi"><div className="kpi-label">Yayına hazır plan</div><div className="kpi-value">1</div><div className="kpi-trend">Merkez onayı bekliyor</div></div>
        <div className="card kpi"><div className="kpi-label">Açık görev</div><div className="kpi-value">{tasks.length}</div><div className="kpi-trend">Saha takibi</div></div>
        <div className="card kpi"><div className="kpi-label">Fotoğraf kanıtı</div><div className="kpi-value">0</div><div className="kpi-trend">Uygulama sonrası yüklenecek</div></div>
      </div>
    </div>
  );
}

export function Tasks({ lang, tasks = [], setTasks }) {
  return (
    <div className="page">
      <div className="section-eyebrow">TASKS</div>
      <h1 style={{ fontSize: 42, margin: '8px 0' }}>{L(lang, 'tasks')}</h1>
      <div className="card pad">
        <table className="table">
          <thead>
            <tr><th>ID</th><th>Store</th><th>Görev</th><th>{L(lang, 'owner')}</th><th>{L(lang, 'priority')}</th><th>{L(lang, 'deadline')}</th><th>{L(lang, 'status')}</th></tr>
          </thead>
          <tbody>
            {(tasks || []).map((t) => (
              <tr key={t.id}>
                <td>{t.id}</td>
                <td>{t.store}</td>
                <td>{t.title}</td>
                <td>{t.owner}</td>
                <td><span className={`badge ${String(t.priority).toLowerCase().includes('high') ? 'red' : 'amber'}`}>{trPriority(t.priority, lang)}</span></td>
                <td>{t.deadline}</td>
                <td>{trStatus(t.status, lang)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}

export function PhotoEvidence({ lang }) {
  return (
    <div className="page">
      <div className="section-eyebrow">PHOTO DOCUMENTATION</div>
      <h1 style={{ fontSize: 42, margin: '8px 0' }}>{L(lang, 'photos')}</h1>
      <div className="card pad">
        <p className="muted">Depo uygulama sonrası fotoğrafı store, koridor, modül, raf ve planogram versiyonu ile bağlanacak.</p>
        <button className="btn primary" type="button">Fotoğraf yükle</button>
      </div>
    </div>
  );
}

export function Reports({ lang, products = [], unplacedProducts = [], objects = [] }) {
  const metrics = [
    ['Planogram Score', Math.max(0, 100 - (unplacedProducts || []).length)],
    ['Active SKU', (products || []).length],
    ['Unplaced SKU', (unplacedProducts || []).length],
    ['Fixture Count', (objects || []).length],
  ];

  return (
    <div className="page">
      <div className="section-eyebrow">EXECUTIVE VIEW</div>
      <h1 style={{ fontSize: 42, margin: '8px 0' }}>{L(lang, 'reports')}</h1>
      <div className="grid cols-4">
        {metrics.map(([k, v]) => (
          <div className="card kpi" key={k}>
            <div className="kpi-label">{k}</div>
            <div className="kpi-value">{v}</div>
            <div className="kpi-trend">Live state</div>
          </div>
        ))}
      </div>
      <div className="card pad" style={{ marginTop: 18 }}>
        <h3>AI / Council Notu</h3>
        <p className="muted">Sabit metin yerine gerçek skor, diagnostics ve unplaced raporu üzerinden yorum üretilecek.</p>
      </div>
    </div>
  );
}

export function Admin({
  lang,
  products = [],
  unplacedProducts = [],
  objects = [],
  readiness,
  notify,
}) {
  const [audit, setAudit] = useState([]);
  const [pending, setPending] = useState([]);
  const [loadingAdmin, setLoadingAdmin] = useState(true);
  const [adminError, setAdminError] = useState('');

  async function loadAdmin() {
    setLoadingAdmin(true);
    setAdminError('');
    const results = await Promise.allSettled([
      api.auditLogs({ limit: 50 }),
      api.pendingDimensionChanges(),
    ]);
    const auditResult = results[0].status === 'fulfilled' ? results[0].value : null;
    const pendingResult = results[1].status === 'fulfilled' ? results[1].value : null;
    setAudit(auditResult?.logs || []);
    setPending(pendingResult?.requests || pendingResult?.pending || []);
    const failures = results.filter((result) => result.status === 'rejected');
    if (failures.length === results.length) {
      setAdminError(failures[0]?.reason?.message || 'Admin verileri alınamadı.');
    }
    setLoadingAdmin(false);
  }

  useEffect(() => {
    loadAdmin();
  }, []);

  async function review(requestId, approve) {
    try {
      await api.approveDimensionChange({ request_id: requestId, approve });
      notify?.(approve ? 'Ürün master değişikliği onaylandı.' : 'Ürün master değişikliği reddedildi.');
      await loadAdmin();
    } catch (error) {
      notify?.(error?.message || 'Onay işlemi tamamlanamadı.');
    }
  }

  const missingDimensions = [...products, ...unplacedProducts].filter(
    (product) =>
      product?.dimension_source === 'missing' ||
      !Number(product?.width_cm) ||
      !Number(product?.height_cm) ||
      !Number(product?.depth_cm)
  ).length;
  const dataQualityScore = Math.max(
    0,
    Math.round(
      100 -
        (missingDimensions / Math.max(1, products.length + unplacedProducts.length)) * 100
    )
  );

  return (
    <div className="page">
      <div className="section-eyebrow">PLANOGRAM OPERATIONS</div>
      <h1 style={{ fontSize: 42, margin: '8px 0' }}>{L(lang, 'admin')}</h1>
      <p className="muted">
        Kullanıcı ve rol yönetimi OPEX Access Control’dadır. Bu ekran yalnızca planogram
        onayları, veri kalitesi ve audit kayıtlarını yönetir.
      </p>

      <div className="grid cols-4">
        <div className="card kpi"><div className="kpi-label">Veri Kalitesi</div><div className="kpi-value">%{dataQualityScore}</div><div className="kpi-trend">{missingDimensions} eksik ölçü</div></div>
        <div className="card kpi"><div className="kpi-label">Yerleşen SKU</div><div className="kpi-value">{products.length}</div><div className="kpi-trend">Aktif plan</div></div>
        <div className="card kpi"><div className="kpi-label">Atanamayan SKU</div><div className="kpi-value">{unplacedProducts.length}</div><div className="kpi-trend">Gerekçeli aksiyon havuzu</div></div>
        <div className="card kpi"><div className="kpi-label">Onay Kuyruğu</div><div className="kpi-value">{pending.length}</div><div className="kpi-trend">{objects.length} fixture · {readiness?.status || 'durum bekliyor'}</div></div>
      </div>

      {adminError ? <div className="auth-error" style={{ marginTop: 18 }}>{adminError}</div> : null}

      <div className="grid cols-2" style={{ marginTop: 18 }}>
        <section className="card pad">
          <div className="section-eyebrow">MASTER DEĞİŞİKLİK ONAYI</div>
          <h3>Bekleyen ürün ölçüsü talepleri</h3>
          {loadingAdmin ? <p className="muted">Yükleniyor…</p> : pending.length ? (
            <div style={{ display: 'grid', gap: 10 }}>
              {pending.map((item) => (
                <div className="card pad" key={item.id || item.request_id}>
                  <strong>{item.product_name || item.sku || 'Ürün değişikliği'}</strong>
                  <p className="muted">SKU: {item.sku || '-'} · Talep eden: {item.requested_by || item.actor || '-'}</p>
                  <div style={{ display: 'flex', gap: 8 }}>
                    <button className="btn primary" onClick={() => review(item.id || item.request_id, true)}>Onayla</button>
                    <button className="btn ghost" onClick={() => review(item.id || item.request_id, false)}>Reddet</button>
                  </div>
                </div>
              ))}
            </div>
          ) : <p className="muted">Bekleyen master değişikliği yok.</p>}
        </section>

        <section className="card pad">
          <div className="section-eyebrow">AUDIT LOG</div>
          <h3>Son 50 işlem</h3>
          <div style={{ overflow: 'auto', maxHeight: 420 }}>
            <table className="table">
              <thead><tr><th>Zaman</th><th>İşlem</th><th>Kullanıcı</th><th>Depo</th></tr></thead>
              <tbody>
                {audit.map((row) => (
                  <tr key={row.id}>
                    <td>{row.created_at || '-'}</td>
                    <td>{row.action || '-'}</td>
                    <td>{row.actor || '-'}</td>
                    <td>{row.store_code || '-'}</td>
                  </tr>
                ))}
              </tbody>
            </table>
            {!loadingAdmin && !audit.length ? <p className="muted">Audit kaydı bulunamadı.</p> : null}
          </div>
        </section>
      </div>
    </div>
  );
}
