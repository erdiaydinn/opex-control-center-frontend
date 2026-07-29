import { useEffect, useRef, useState } from 'react';
import Shell from './components/Shell.jsx';
import LoadingScreen from './components/LoadingScreen.jsx';
import OperationLoadingOverlay from './components/OperationLoadingOverlay.jsx';
import CommandCenter from './components/CommandCenterOps.jsx';
import Live3D from './components/Live3D.jsx';
import LayoutArchitect from './components/LayoutArchitect.jsx';
import ProductPlacementStudio from './components/ProductPlacementStudio.jsx';
import PlanogramWorkspace from './components/PlanogramWorkspace.jsx';
import RuleEngineReal from './components/RuleEngineReal.jsx';
import PlanogramExportPanel from './components/PlanogramExportPanel.jsx';
import DeltaPlanogramReal from './components/DeltaPlanogramReal.jsx';
import StoreDNAWorkspace from './components/StoreDNA/StoreDNAWorkspace.jsx';
import { Admin, Delta, FixtureLibrary, PhotoEvidence, ProductLibrary, Publishing, Reports, Rules, Tasks } from './components/DataViews.jsx';
import { initialObjects, initialTasks, productsSeed } from './data/mock.js';
import { api } from './services/api.js';
import { normalizeProductsForBackend, parseCsvProducts, parseJsonLayout } from './utils/fileParsers.js';
import { buildStorePlan, normalizeProduct, updateObjectsFromPlan } from './utils/planogramAllocator.js';
import { applyPlacementRulesBeforePlan, DEFAULT_OPTIMIZATION_WEIGHTS, DEFAULT_STRATEGY_PROFILE, loadStrategyProfile } from './utils/placementRuleAdapter.js';

function isAbort(err) {
  return err?.name === 'AbortError' || String(err?.message || '').toLowerCase().includes('abort');
}

function readableError(err) {
  if (!err) return '';
  if (typeof err === 'string') return err;
  if (err.message) return err.message;
  try {
    return JSON.stringify(err);
  } catch {
    return String(err);
  }
}

const BACKEND_PLACEMENT_FIELDS = [
  'brand_block_id',
  'brand_block_name',
  'brand_block_sequence',
  'brand_block_split',
  'brand_block_warning',
  'placed_units',
  'facing_count',
  'depth_units',
  'capacity_compromised',
  'refill_risk',
  'capacity_warning',
  'case_pack_min_fit',
  'placement_reason',
  'placement_confidence',
  'confidence_level',
  'coverage_days',
  'fixture_kind',
  'storage_type',
  'aisle',
  'aisle_id',
  'module_id',
  'shelf_no',
  'position_order',
  'used_width_cm',
  'total_capacity_units',
  'raw_recommended_units',
  'ideal_case_pack_units',
  'max_physical_units',
  'feasible_case_units',
  'case_pack_rounding_applied'
];

function normalizeBackendProduct(p, idx = 0) {
  const normalized = normalizeProduct(p, idx);
  const preserved = {};

  BACKEND_PLACEMENT_FIELDS.forEach((key) => {
    if (p?.[key] !== undefined) preserved[key] = p[key];
  });

  return {
    ...normalized,
    ...preserved,
    placement_source: p?.placement_source || 'backend_engine',
    engine_source: p?.engine_source || 'backend_engine',
    engine_source_of_truth: p?.engine_source_of_truth ?? true
  };
}

// =====================================================================
// HYDRATION PATCH: backend planogram = TEK gorsel kaynak
// Plan uretimi sonrasi 2D/3D/delta/summary AYNI nested planogram'dan beslenir.
// =====================================================================
function normKeyPart(v) {
  return String(v == null ? '' : v).trim().toUpperCase();
}

function normModuleId(moduleRaw, aisleId) {
  let s = normKeyPart(moduleRaw);
  const a = normKeyPart(aisleId);
  if (a && s.startsWith(a)) {
    const rest = s.slice(a.length).replace(/^[.\-_/ M]+/i, '');
    if (rest) s = rest;
  }
  s = s.replace(/^M/i, '');
  const m = s.match(/\d+/);
  if (m) return m[0];
  // rakam yok: aisle harfiyle ayniysa (ornek module="A", aisle="A") -> "1" (tek modul varsayimi)
  if (a && normKeyPart(moduleRaw) === a) return '1';
  return s || '1';
}

function normShelfNo(shelfRaw) {
  let s = normKeyPart(shelfRaw).replace(/^RAF/i, '').replace(/^R/i, '');
  const parts = s.split(/[.\-_/ ]+/).filter(Boolean);
  const last = parts.length ? parts[parts.length - 1] : s;
  const m = String(last).match(/\d+/);
  return m ? m[0] : String(last);
}

function shelfKey(aisleId, moduleId, shelfNo) {
  return `${normKeyPart(aisleId)}|${normModuleId(moduleId, aisleId)}|${normShelfNo(shelfNo)}`;
}

function productWidth(p) {
  return Number(p.used_width_cm) || (Number(p.width_cm || p.width || 8) * Number(p.facing || p.facing_count || 1) * 1.1);
}

function hydrateShelvesFromPlacedProducts(planogram, placedProducts = []) {
  if (!planogram || !Array.isArray(planogram.aisles)) {
    return { planogram, unmatched_placements_count: (placedProducts || []).length,
             unmatched_placements_sample: (placedProducts || []).slice(0, 20),
             missing_shelf_keys: [] };
  }
  const plan = JSON.parse(JSON.stringify(planogram));
  const shelfIndex = new Map();
  plan.aisles.forEach((aisle) => {
    (aisle.modules || []).forEach((module) => {
      (module.shelves || []).forEach((shelf) => {
        const k = shelfKey(aisle.aisle_id, module.module_id, shelf.shelf_no);
        shelfIndex.set(k, { aisle, module, shelf });
        shelf.products = [];
        shelf.used_width_cm = 0;
        shelf.used_weight_kg = 0;
      });
    });
  });

  const missing = new Map();
  let unmatched = 0;
  const unmatchedSample = [];

  // Tek kaynak: placedProducts. Bos ise backend nested products'tan turet.
  let source = placedProducts;
  if (!source || !source.length) {
    source = [];
    (planogram.aisles || []).forEach((aisle) => (aisle.modules || []).forEach((module) =>
      (module.shelves || []).forEach((shelf) => (shelf.products || []).forEach((p) => source.push({
        ...p, aisle_id: p.aisle_id || aisle.aisle_id, module_id: p.module_id || module.module_id,
        shelf_no: p.shelf_no || shelf.shelf_no,
      })))));
  }

  source.forEach((p) => {
    const aisleId = p.aisle_id || p.aisle;
    const k = shelfKey(aisleId, p.module_id, p.shelf_no);
    const hit = shelfIndex.get(k);
    if (!hit) {
      unmatched += 1;
      if (unmatchedSample.length < 20) {
        unmatchedSample.push({ sku: p.sku, product_name: p.product_name,
          aisle_id: aisleId, module_id: p.module_id, shelf_no: p.shelf_no, missing_shelf_key: k });
      }
      missing.set(k, (missing.get(k) || 0) + 1);
      return;
    }
    hit.shelf.products.push(p);
    hit.shelf.used_width_cm = Math.round((hit.shelf.used_width_cm + productWidth(p)) * 10) / 10;
    hit.shelf.used_weight_kg = Math.round((hit.shelf.used_weight_kg + (Number(p.weight_kg) || 0) * Number(p.facing || 1)) * 100) / 100;
  });

  plan.aisles.forEach((aisle) => {
    let aisleSkus = 0, aisleUsed = 0, aisleCap = 0;
    (aisle.modules || []).forEach((module) => {
      let modSkus = 0;
      (module.shelves || []).forEach((shelf) => {
        modSkus += shelf.products.length;
        aisleUsed += Number(shelf.used_width_cm) || 0;
        aisleCap += Number(shelf.shelf_width_cm) || 0;
      });
      module.sku_count = modSkus;
      aisleSkus += modSkus;
    });
    aisle.sku_count = aisleSkus;
    aisle.utilization = aisleCap > 0 ? Math.round((aisleUsed / aisleCap) * 100) : 0;
  });

  return {
    planogram: plan,
    unmatched_placements_count: unmatched,
    unmatched_placements_sample: unmatchedSample,
    missing_shelf_keys: Array.from(missing.entries()).map(([k, n]) => ({ key: k, count: n })).slice(0, 30),
  };
}

function productsFromPlanogram(result, fallbackProducts = []) {
  const plan = result?.planogram || result?.layout || null;
  const out = [];
  if (plan?.aisles) {
    plan.aisles.forEach((aisle) => {
      (aisle.modules || []).forEach((module) => {
        (module.shelves || []).forEach((shelf) => {
          (shelf.products || []).forEach((p, idx) => {
            out.push(normalizeBackendProduct({
              ...p,
              aisle_id: p.aisle_id || aisle.aisle_id,
              aisle: p.aisle || aisle.aisle_id,
              module_id: p.module_id || module.module_id,
              shelf_no: p.shelf_no || shelf.shelf_no
            }, idx));
          });
        });
      });
    });
  }
  return out.length ? out : fallbackProducts;
}

function unplacedFromBackend(result) {
  const raw =
    result?.unplaced_products ||
    result?.unplaced ||
    result?.unassigned_products ||
    [];
  return (Array.isArray(raw) ? raw : []).map((p, idx) =>
    normalizeProduct({
      ...p,
      placement_status: 'UNPLACED',
      placement_source: 'backend_engine',
      engine_source: 'backend_engine'
    }, idx)
  );
}

function storageViolation(p = {}) {
  const storage = String(p.storage_type || p.storage || '').toUpperCase();
  const fixture = String(p.fixture_kind || '').toUpperCase();
  if (storage === 'FROZEN' && fixture && !fixture.includes('FREEZER')) return true;
  if (storage === 'CHILLED' && fixture && !fixture.includes('FRIDGE')) return true;
  if (storage === 'AMBIENT' && fixture && (fixture.includes('FREEZER') || fixture.includes('FRIDGE'))) return true;
  return false;
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

// =====================================================================
// STORE DNA -> BACKEND LAYOUT CONVERTER (V1.9.50)
// Frontend Store DNA / layout objelerini backend engine'in bekledigi
// aisles/modules/shelves formatina cevirir ve her fixture'i dogru
// fixture class'a (AMBIENT/CHILLED/FROZEN/PALLET/PRODUCE) map'ler.
// =====================================================================

// Frontend fixture_type -> backend fixture class + module_type + olculer
// (StoreDNASetupWizard.jsx fixtureTypes tablosuyla birebir)
const FIXTURE_TYPE_MAP = {
  steel_rack:                    { cls: 'AMBIENT', module_type: 'regular_shelf', w: 100, d: 50, h: 35, shelves: 6, maxw: 45 },
  new_generation_steel_rack:     { cls: 'AMBIENT', module_type: 'regular_shelf', w: 100, d: 60, h: 40, shelves: 6, maxw: 50 },
  produce_shelf:                 { cls: 'PRODUCE', module_type: 'produce_rack', w: 120, d: 60, h: 45, shelves: 4, maxw: 50 },
  horizontal_fridge:             { cls: 'CHILLED', module_type: 'fridge', w: 150, d: 70, h: 40, shelves: 3, maxw: 60 },
  martek_plus4:                  { cls: 'CHILLED', module_type: 'fridge', w: 150, d: 55, h: 40, shelves: 5, maxw: 60 },
  martek_frozen_minus18:         { cls: 'FROZEN', module_type: 'freezer', w: 150, d: 60, h: 40, shelves: 4, maxw: 70 },
  ice_cream_chest_freezer_medium:{ cls: 'FROZEN', module_type: 'freezer', w: 120, d: 70, h: 40, shelves: 3, maxw: 70 },
  hdr_heavy_rack:                { cls: 'PALLET', module_type: 'pallet_rack', w: 120, d: 80, h: 120, shelves: 3, maxw: 800 },
};

// zone -> fixture class (fixture_type yoksa fallback)
const ZONE_TO_CLASS = {
  AMBIENT: 'AMBIENT', CHILLED: 'CHILLED', FROZEN: 'FROZEN',
  HEAVY: 'PALLET', PALLET: 'PALLET', PRODUCE: 'PRODUCE',
};

// Serbest metinden fixture class cikar (Algida/Martek/HDR/Golf/Fruit&Veg...)
function inferFixtureClassFromText(text) {
  const t = String(text || '').toUpperCase();
  if (/ALGIDA|GOLF|ICE.?CREAM|DONDURMA|-18|FROZEN|DONUK|FREEZER|MINUS18/.test(t)) return 'FROZEN';
  if (/MARTEK.?\+?4|PLUS4|\+4|CHILL|FRIDGE|DOLAP|SOGUK|YATAY DOLAP|MARTEK/.test(t)) return 'CHILLED';
  if (/HDR|PALLET|PALET|HEAVY|AGIR|BULK|DAMACANA/.test(t)) return 'PALLET';
  if (/PRODUCE|MEYVE|SEBZE|FRUIT|VEG|MANAV/.test(t)) return 'PRODUCE';
  if (/STEEL|CELIK|RAF|SHELF|GONDOLA|AMBIENT|KURU/.test(t)) return 'AMBIENT';
  return '';
}

function resolveFixtureSpec(obj = {}) {
  // 1) fixture_type tam eslesme
  const ft = String(obj.fixture_type || obj.left_fixture_type || '').trim();
  if (ft && FIXTURE_TYPE_MAP[ft]) return { ...FIXTURE_TYPE_MAP[ft], fixture_type: ft };
  // 2) zone
  const zoneCls = ZONE_TO_CLASS[String(obj.zone || obj.storage || obj.storage_type || '').toUpperCase()];
  // 3) serbest metin
  const text = [obj.id, obj.label, obj.name, obj.title, obj.type, obj.fixture_type, obj.zone,
                obj.storage, obj.storage_type, obj.fixture_class].filter(Boolean).join(' ');
  const cls = zoneCls || inferFixtureClassFromText(text) || 'AMBIENT';
  const base = {
    AMBIENT: { module_type: 'regular_shelf', w: 100, d: 50, h: 35, shelves: 6, maxw: 45 },
    CHILLED: { module_type: 'fridge', w: 150, d: 55, h: 40, shelves: 5, maxw: 60 },
    FROZEN: { module_type: 'freezer', w: 150, d: 60, h: 40, shelves: 4, maxw: 70 },
    PALLET: { module_type: 'pallet_rack', w: 120, d: 80, h: 120, shelves: 3, maxw: 800 },
    PRODUCE: { module_type: 'produce_rack', w: 120, d: 60, h: 45, shelves: 4, maxw: 50 },
  }[cls];
  return { cls, fixture_type: ft || cls, ...base };
}

function makeBackendShelves(spec, objOverrides = {}) {
  const count = Math.max(1, Number(objOverrides.shelf_count || objOverrides.shelves || spec.shelves || 5));
  const w = Number(objOverrides.width_cm || objOverrides.w || spec.w);
  const d = Number(objOverrides.depth_cm || objOverrides.d || spec.d);
  const totalH = Number(objOverrides.height_cm || objOverrides.h || (spec.h * count));
  const perShelfH = Math.max(20, Math.round(totalH / count) || spec.h);
  return Array.from({ length: count }, (_, i) => ({
    shelf_no: i + 1,
    allowed_storage_type: spec.cls,
    shelf_width_cm: w,
    shelf_depth_cm: d,
    shelf_height_cm: perShelfH,
    max_weight_kg: spec.maxw,
    used_width_cm: 0,
    used_weight_kg: 0,
    products: [],
  }));
}

// Bir layout objesini backend modulune cevirir
function objectToBackendModule(obj, moduleId, side) {
  const spec = resolveFixtureSpec(obj);
  const moduleCount = Math.max(1, Number(obj.modules || obj.module_count || 1));
  return { spec, moduleCount, build: (mid, sd) => ({
    module_id: mid,
    side: sd || obj.side || 'L',
    module_type: spec.module_type,
    fixture_type: spec.fixture_type,
    fixture_class: spec.cls,
    module_width_cm: spec.w,
    module_depth_cm: spec.d,
    module_height_cm: spec.h * Number(obj.shelf_count || spec.shelves),
    assignment_rule: obj.assignment_rule || null,
    shelves: makeBackendShelves(spec, obj),
  }) };
}

/**
 * convertStoreDnaObjectsToBackendLayout(objects, storeDna)
 * Doner: { store_code, route_strategy, aisles:[...] } veya null (cevrilemezse).
 */
// Store DNA fiziksel gerçeği vs backend layout karşılaştırması (diagnostics)
function buildStoreDnaAuthorityDiag(storeDna, aisles, syntheticLog, source) {
  // Store DNA'nin beklediği modül/raf sayıları
  const sdModulesByAisle = {};
  let sdModuleCount = 0;
  let sdShelfCount = 0;
  const amc = (storeDna && (storeDna.aisle_module_config || storeDna.aisles)) || [];
  if (Array.isArray(amc)) {
    amc.forEach((a, ai) => {
      const aid = a.aisle_id || a.id || `A${ai + 1}`;
      const mods = [...(a.left_modules || []), ...(a.right_modules || []), ...(!a.left_modules && !a.right_modules ? (a.modules || []) : [])];
      sdModulesByAisle[aid] = mods.length;
      sdModuleCount += mods.length;
      mods.forEach((mo) => { sdShelfCount += Number(mo.shelf_count || mo.shelves || 0); });
    });
  }
  // backend gerçek
  const backendModulesByAisle = {};
  const backendShelfByModule = {};
  let backendModuleCount = 0;
  let backendShelfCount = 0;
  aisles.forEach((a) => {
    backendModulesByAisle[a.aisle_id] = a.modules.length;
    backendModuleCount += a.modules.length;
    a.modules.forEach((m) => {
      backendShelfByModule[`${a.aisle_id}.${m.module_id}`] = m.shelves.length;
      backendShelfCount += m.shelves.length;
    });
  });
  // mismatch örnekleri
  const moduleMismatch = [];
  Object.keys(sdModulesByAisle).forEach((aid) => {
    if (sdModulesByAisle[aid] !== backendModulesByAisle[aid]) {
      moduleMismatch.push({ aisle_id: aid, store_dna: sdModulesByAisle[aid], backend: backendModulesByAisle[aid] || 0 });
    }
  });
  const presentClasses = new Set();
  aisles.forEach((a) => a.modules.forEach((m) => presentClasses.add(m.fixture_class)));
  const missingFixtureClasses = ['AMBIENT', 'CHILLED', 'FROZEN', 'PRODUCE', 'PALLET'].filter((c) => !presentClasses.has(c));

  return {
    converter_source: source,
    is_synthetic_layout: syntheticLog.modules > 0 || source.startsWith('default') || source === 'fallback',
    synthetic_modules_added_count: syntheticLog.modules,
    synthetic_shelves_added_count: syntheticLog.shelves,
    store_dna_module_count: sdModuleCount,
    backend_module_count: backendModuleCount,
    store_dna_shelf_count: sdShelfCount,
    backend_shelf_count: backendShelfCount,
    store_dna_shelf_count_by_module: sdModulesByAisle,
    backend_shelf_count_by_module: backendShelfByModule,
    module_count_mismatch_sample: moduleMismatch.slice(0, 20),
    missing_fixture_classes: missingFixtureClasses,
  };
}

function convertStoreDnaObjectsToBackendLayout(objects = [], storeDna = null) {
  const syntheticLog = { modules: 0, shelves: 0 };
  // YOL 1: storeDna.aisle_module_config (Store DNA wizard preview formati)
  const amc = storeDna && (storeDna.aisle_module_config || storeDna.aisles);
  if (Array.isArray(amc) && amc.length && (amc[0].left_modules || amc[0].right_modules || amc[0].modules)) {
    const aisles = amc.map((a, ai) => {
      const mods = [];
      let mid = 0;
      const pushSide = (list, side) => {
        (list || []).forEach((mObj) => {
          const spec = resolveFixtureSpec(mObj);
          mid += 1;
          mods.push({
            module_id: mid, side, module_type: spec.module_type, fixture_type: spec.fixture_type,
            fixture_class: spec.cls, module_width_cm: spec.w, module_depth_cm: spec.d,
            module_height_cm: spec.h * Number(mObj.shelf_count || spec.shelves),
            assignment_rule: mObj.assignment_rule || null,
            shelves: makeBackendShelves(spec, mObj),
          });
        });
      };
      pushSide(a.left_modules, 'L');
      pushSide(a.right_modules, 'R');
      if (!a.left_modules && !a.right_modules && Array.isArray(a.modules)) pushSide(a.modules, 'L');
      const zone = mods.length ? mods[0].fixture_class : 'AMBIENT';
      return { aisle_id: a.aisle_id || a.id || `A${ai + 1}`, zone, modules: mods };
    }).filter((a) => a.modules.length);

    // Store DNA easy-config sayilari (Algida, Martek, produce, HDR) - synthetic DEGIL, Store DNA verisi
    appendCountedFixtures(aisles, storeDna, syntheticLog);
    if (aisles.length) {
      const out = { store_code: storeDna.store_code || 'STORE_DNA', route_strategy: 'STORE_DNA', aisles };
      out.__diag = buildStoreDnaAuthorityDiag(storeDna, aisles, syntheticLog, 'real_store_dna');
      return out;
    }
  }

  // YOL 2: duz layout objects listesi. KORIDOR KIMLIGINI KORU (collapse YASAK).
  // Her obje kendi aisle_id/corridor_id/row/label'ina gore gruplanir; fixture_class'a gore DEGIL.
  if (Array.isArray(objects) && objects.length) {
    const aisleMap = new Map();   // aisleId -> { aisle_id, zone, modules:[] }
    objects.forEach((obj, oi) => {
      const spec = resolveFixtureSpec(obj);
      const moduleCount = Math.max(1, Number(obj.modules || obj.module_count || 1));
      // koridor kimligi: object uzerindeki gercek alanlar (collapse'i onler)
      const aisleId = String(
        obj.aisle_id || obj.corridor_id || obj.row || obj.aisle || obj.label || obj.id || `A${oi + 1}`
      ).trim();
      if (!aisleMap.has(aisleId)) {
        aisleMap.set(aisleId, { aisle_id: aisleId, zone: spec.cls, modules: [] });
      }
      const aisle = aisleMap.get(aisleId);
      for (let i = 0; i < moduleCount; i += 1) {
        aisle.modules.push({
          module_id: aisle.modules.length + 1,
          side: obj.side || (i % 2 === 0 ? 'L' : 'R'),
          module_type: spec.module_type, fixture_type: spec.fixture_type, fixture_class: spec.cls,
          module_width_cm: spec.w, module_depth_cm: spec.d,
          module_height_cm: spec.h * Number(obj.shelf_count || spec.shelves),
          assignment_rule: obj.assignment_rule || null,
          shelves: makeBackendShelves(spec, obj),
        });
      }
    });
    const aisles = Array.from(aisleMap.values()).filter((a) => a.modules.length);
    if (aisles.length) {
      const out = { store_code: storeDna?.store_code || 'LAYOUT_OBJECTS', route_strategy: 'OBJECTS', aisles };
      out.__diag = buildStoreDnaAuthorityDiag(storeDna || {}, aisles, syntheticLog, 'real_store_dna');
      return out;
    }
  }

  return null; // cevrilemezse backend default kullanir (yalniz demo/fallback modunda)
}

// Store DNA easy-config sayilarindan EKSTRA fixture koridorlari uretir.
// SADECE Store DNA acikca sayilari verdiyse calisir; synthetic varsayilan URETMEZ.
function appendCountedFixtures(aisles, storeDna, syntheticLog) {
  if (!storeDna) return;
  const add = (cls, fixtureType, count, namePrefix) => {
    const n = Number(count || 0);
    if (n <= 0) return;   // Store DNA 0/yok dediyse fixture YARATMA
    const spec = resolveFixtureSpec({ fixture_type: fixtureType });
    const existing = aisles.find((a) => a.zone === cls);
    const target = existing || { aisle_id: namePrefix, zone: cls, modules: [] };
    const startId = target.modules.length;
    for (let i = 0; i < n; i += 1) {
      target.modules.push({
        module_id: startId + i + 1, side: 'L', module_type: spec.module_type,
        fixture_type: spec.fixture_type, fixture_class: cls,
        module_width_cm: spec.w, module_depth_cm: spec.d, module_height_cm: spec.h * spec.shelves,
        assignment_rule: null, shelves: makeBackendShelves(spec, {}),
      });
    }
    if (syntheticLog) {
      syntheticLog.modules += n;
      syntheticLog.shelves += n * spec.shelves;
    }
    if (!existing && target.modules.length) aisles.push(target);
  };
  add('FROZEN', 'ice_cream_chest_freezer_medium', storeDna.algida_count, 'ALGIDA');
  add('CHILLED', 'martek_plus4', storeDna.martek_plus4_count, 'MARTEK-4');
  add('FROZEN', 'martek_frozen_minus18', storeDna.martek_frozen_count, 'MARTEK-18');
  add('FROZEN', 'horizontal_fridge', storeDna.horizontal_fridge_count, 'YATAY-DONUK');
  add('PRODUCE', 'produce_shelf', storeDna.produce_module_count, 'MANAV');
  add('AMBIENT', 'new_generation_steel_rack', storeDna.new_gen_steel_rack_count, 'YENI-CELIK');
  // HDR/palet: SADECE Store DNA acikca sayisini verdiyse. Synthetic varsayilan (|| 2) KALDIRILDI.
  const hdrCount = Number(storeDna.hdr_count || storeDna.pallet_count || storeDna.heavy_rack_count || 0);
  add('PALLET', 'hdr_heavy_rack', hdrCount, 'PALLET-HDR');
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


function normalizeStorageTruthForApp(value) {
  const raw = String(value || "").trim().toUpperCase();

  if (!raw || raw === "NULL" || raw === "NAN" || raw === "UNKNOWN") return "";

  if (raw.includes("FROZEN") || raw.includes("DONUK") || raw.includes("-18") || raw.includes("ICE_CREAM")) return "FROZEN";
  if (raw.includes("CHILLED") || raw.includes("SO?UK") || raw.includes("SOGUK") || raw.includes("+4")) return "CHILLED";
  if (raw.includes("AMBIENT")) return "AMBIENT";

  return "";
}

function catalogStorageTruthForApp(product = {}) {
  const catalogStorage =
    product.catalog_storage_type ||
    product.catalog_storage_class ||
    product.catalog_storage ||
    product.catalogStorage ||
    product.master_storage_type ||
    product.master_storage_class ||
    product.master_storage ||
    product.canonical_storage_type ||
    product.source_catalog_storage_type ||
    product.storage_truth ||
    product.catalog?.storage_type ||
    product.catalog?.storage_class ||
    product.master_product?.storage_type ||
    product.master_product?.storage_class ||
    "";

  const catalogTruth = normalizeStorageTruthForApp(catalogStorage);
  if (catalogTruth) return { value: catalogTruth, source: "catalog" };

  const abcStorage =
    product["Storage Type"] ||
    product.abc_storage_type ||
    product.abcStorageType ||
    "";

  const abcTruth = normalizeStorageTruthForApp(abcStorage);
  if (abcTruth) return { value: abcTruth, source: "abc_fallback" };

  return { value: "", source: "" };
}

function normalizeCandidateProductsForAllocator(products = []) {
  return (products || []).map((product) => {
    const truth = catalogStorageTruthForApp(product);

    if (!truth.value) return product;

    return {
      ...product,
      catalog_storage_type: truth.value,
      storage: truth.value,
      storage_type: truth.value,
      storage_class: truth.value,
      storage_source: truth.source,
    };
  });
}

function normalizeLayoutObjectsForAllocator(objects = []) {
  return (objects || []).map((object) => {
    const text = [
      object?.id,
      object?.label,
      object?.name,
      object?.title,
      object?.type,
      object?.zone,
      object?.fixture_type,
      object?.fixture_class,
      object?.storage,
      object?.storage_type,
    ].filter(Boolean).join(" ").toUpperCase();

    const isMartek = text.includes("MARTEK");

    if (!isMartek) return object;

    return {
      ...object,
      modules: Math.max(2, Number(object.modules || 0) || 2),
      shelves: Math.max(10, Number(object.shelves || 0) || 10),
      storage: "CHILLED",
      storage_type: "CHILLED",
      storage_class: "CHILLED",
      fixture_class: "CHILLED",
      fixture_type: object.fixture_type || "MARTEK_CHILLED",
      zone: "CHILLED",
    };
  });
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
  window.__PLONAGRAM_ACTIVE_PIPELINE__ = 'V1.9.47_STRATEGY_FIRST_ACTIVE';
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
  const [backendPlan, setBackendPlan] = useState(null);
  const [optimizationWeights, setOptimizationWeights] = useState(() => {
    try {
      return {
        ...DEFAULT_OPTIMIZATION_WEIGHTS,
        ...JSON.parse(localStorage.getItem('plonagram_optimization_weights') || '{}'),
      };
    } catch (e) {
      return DEFAULT_OPTIMIZATION_WEIGHTS;
    }
  });

  const [placementRules, setPlacementRules] = useState(() => {
    try {
      return JSON.parse(localStorage.getItem('plonagram_placement_rules') || '[]');
    } catch (e) {
      return [];
    }
  });
  const [strategyProfile, setStrategyProfile] = useState(() => loadStrategyProfile());
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

  useEffect(() => {
    try {
      localStorage.setItem('plonagram_optimization_weights', JSON.stringify(optimizationWeights || DEFAULT_OPTIMIZATION_WEIGHTS));
    } catch (e) {}
  }, [optimizationWeights]);

  useEffect(() => {
    try {
      localStorage.setItem('plonagram_placement_rules', JSON.stringify(placementRules || []));
    } catch (e) {}
  }, [placementRules]);

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

      // Düzeltme #1: Yükleme ARTIK otomatik plan üretmez.
      // SKU'lar yalnızca aday havuzu olarak normalize edilip saklanır; yerleştirme,
      // strateji seçilip "Optimum plan üret" çalıştırıldığında yapılır.
      // Böylece strateji-öncesi sessizce plan oluşturma (ve source:'sku_upload' planı kaydetme) ortadan kalkar.
      const candidates = nextProducts.map((p, idx) => normalizeProduct(p, idx));
      setProducts([]);
      setUnplacedProducts(candidates);
      try {
        localStorage.setItem(`plonagram_candidate_products_${store}`, JSON.stringify(candidates));
      } catch (e) {}
      window.__PLONAGRAM_LAST_SKU_UPLOAD_COUNT__ = candidates.length;
      setActive('library');
      // Aday havuzu planogram olarak kaydedilmez.
      // Aksi halde mevcut plan, ürün yükleme anında boş planla ezilebilir.
      notify(`${nextProducts.length} SKU aday havuzuna alındı. Plan üretmek için strateji seç ve "Optimum plan üret"e bas.`);
      return candidates;
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
    let strategyConfirmed = false;
    try {
      strategyConfirmed = localStorage.getItem('plonagram_strategy_confirmed') === '1';
    } catch {}

    const activeStrategy = loadStrategyProfile();
    if (!strategyConfirmed || !activeStrategy?.mode) {
      notify('Önce bir planogram stratejisi seç. Strateji ekranına yönlendiriliyorsun.');
      setActive('rules');
      return;
    }

    setStrategyProfile(activeStrategy);

    const effectiveStoreDna = storeDna || { source: 'backend_default_layout_fallback', objects };
    if (!storeDna) {
      notify('Store DNA bulunamadı; geçici olarak backend default layout ile plan üretilecek.');
    }

    await runOperation(
      {
        mode: 'plan',
        title: 'Backend Engine planogram üretiyor',
        subtitle: `Strateji: ${activeStrategy.label || activeStrategy.mode}. Backend engine storage, fixture, marka blok, kategori, case-pack ve kapasiteyi tek kaynak olarak hesaplıyor.`
      },
      async (signal) => {
        const sourceProducts = normalizeCandidateProductsForAllocator(
          mergeCandidateProducts(products, unplacedProducts)
        );

        if (!sourceProducts.length) {
          throw new Error('Plan üretmek için aday SKU bulunamadı. Önce ABC/SKU dosyası yükle.');
        }

        const planObjects = normalizeLayoutObjectsForAllocator(
          resolvePlanObjects(objects, effectiveStoreDna)
        );

        let backendResult = null;
        let placed = [];
        let unplaced = [];
        let hydratedPlan = null;

        // Store DNA -> backend layout cevirisi (synthetic uretmez; __diag tasir)
        const convertedRaw = convertStoreDnaObjectsToBackendLayout(
          normalizeLayoutObjectsForAllocator(resolvePlanObjects(objects, effectiveStoreDna)),
          effectiveStoreDna
        );
        const converterDiag = convertedRaw?.__diag || {
          converter_source: 'fallback', is_synthetic_layout: true,
          synthetic_modules_added_count: 0, synthetic_shelves_added_count: 0,
          missing_fixture_classes: [], module_count_mismatch_sample: [],
        };
        const convertedLayout = convertedRaw ? (() => { const { __diag, ...rest } = convertedRaw; return rest; })() : null;
        if (!convertedLayout) {
          notify('STORE_DNA: Gerçek layout üretilemedi (converter null). Backend varsayılanına düşülüyor — gerçek mağaza modunda Store DNA tamamlanmalı.');
        }

        try {
          const payload = {
            store_code: store,
            mode: activeStrategy.mode,
            strategy: activeStrategy,
            placement_rules: placementRules,
            optimization_weights: optimizationWeights,
            products: normalizeProductsForBackend(sourceProducts),
            // Store DNA / layout objelerini backend formatina cevir.
            // Real store mode: synthetic uretme; cevrilemezse null (backend kendi davranisina karar verir).
            layout: convertedLayout
          };

          backendResult = await api.generatePlanogramCouncil(payload, signal);

          if (!backendResult) {
            throw new Error('Backend engine boş cevap döndürdü.');
          }
          if (backendResult.error) {
            throw new Error(backendResult.message || String(backendResult.error));
          }

          placed = productsFromPlanogram(backendResult, []);
          unplaced = unplacedFromBackend(backendResult);

          // HYDRATION: backend planogram'i placed urunlerle doldur -> TEK gorsel kaynak
          const hydrationInput = backendResult.planogram || backendResult.layout || null;
          const hydration = hydrateShelvesFromPlacedProducts(hydrationInput, placed);
          hydratedPlan = hydration.planogram;
          // hydration teshislerini diagnostics'e yaz
          backendResult.diagnostics = {
            ...(backendResult.diagnostics || {}),
            ...converterDiag,
            unmatched_placements_count: hydration.unmatched_placements_count,
            unmatched_placements_sample: hydration.unmatched_placements_sample,
            missing_shelf_key: hydration.missing_shelf_keys,
          };
          if (hydration.unmatched_placements_count > 0) {
            notify(`HYDRATION: ${hydration.unmatched_placements_count} yerlesim UI rafina eslesemedi (diagnostics.missing_shelf_key).`);
          }

          if (!placed.length && sourceProducts.length) {
            throw new Error(`Backend engine plan boş döndürdü. Aday SKU: ${sourceProducts.length}, atanamayan: ${unplaced.length}`);
          }
        } catch (err) {
          if (isAbort(err)) throw err;

          // HARD TEST MODE:
          // Backend-first zincir kanıtlanana kadar local allocator'a sessizce düşmek YASAK.
          // Bu blok bilerek fallback çalıştırmaz; gerçek backend hatasını UI'da gösterir.
          throw new Error(`Backend engine failed. Local allocator disabled for test. Detail: ${readableError(err)}`);
        }

        const violations = placed.filter(storageViolation);
        if (violations.length) {
          notify(`STORAGE_VIOLATION: ${violations.length} ürün fixture/storage uyumsuz görünüyor. Yayınlamadan önce kontrol et.`);
        }

        let nextObjects = planObjects;
        try {
          nextObjects = updateObjectsFromPlan(planObjects, { placed, unplaced });
        } catch (err) {
          nextObjects = planObjects;
        }

        const nextTask = {
          id: `T-${Date.now().toString().slice(-5)}`,
          store: store || 'Anka',
          title: `Backend Engine sonrası ${unplaced.length} atanamayan SKU kontrolü`,
          owner: 'Store Manager',
          priority: unplaced.length ? 'High' : 'Medium',
          deadline: 'Bugün',
          status: 'Open',
          response: ''
        };

        setProducts(placed);
        setUnplacedProducts(unplaced);
        setObjects(nextObjects);
        setBackendPlan(hydratedPlan);
        setTasks((prev) => [nextTask, ...prev]);

        try {
          window.__plonagramLastEngineResult = backendResult;
          localStorage.setItem('plonagram_last_engine_result', JSON.stringify({
            summary: backendResult.summary || {},
            diagnostics: backendResult.diagnostics || {},
            brand_blocks: backendResult.brand_blocks || [],
            generated_at: new Date().toISOString()
          }));
        } catch {}

        try {
          await api.savePlanogram(
            store,
            {
              products: placed,
              unplacedProducts: unplaced,
              objects: nextObjects,
              backend_result: backendResult,
              source: placed.some((p) => p.engine_source === 'fallback_allocator') ? 'fallback_allocator' : 'backend_engine',
              strategy_mode: activeStrategy.mode,
              strategy_label: activeStrategy.label
            },
            backendResult.summary || { placed: placed.length, unplaced: unplaced.length },
            'Backend Engine generated plan',
            signal
          );

          await api.saveLayout(
            store,
            { objects: nextObjects, source: 'backend_engine_default_layout' },
            'Layout state after Backend Engine plan',
            signal
          );

          await api.createTask({ ...nextTask, store_code: store, external_id: nextTask.id }, signal);
        } catch (err) {}

        notify(
          `Backend Engine planı uygulandı (${activeStrategy.label || activeStrategy.mode}). ${placed.length} ürün yerleşti, ${unplaced.length} ürün atanamadı.`
        );

        setActive('planogram');
        return placed;
      }
    ).catch((err) => {
      if (!isAbort(err)) notify(readableError(err) || 'Optimum plan üretilemedi.');
    });
  }

  if (loading) return <LoadingScreen lang={lang} />;

  
  


const common = { lang, objects, setObjects, products, setProducts, unplacedProducts, setUnplacedProducts, tasks, setTasks, store, notify, setActive, onGenerate: generateOptimalPlan, storeDna, setStoreDna, readiness, setReadiness, backendPlan, setBackendPlan, placementRules, setPlacementRules, optimizationWeights, setOptimizationWeights, strategyProfile, setStrategyProfile };
  const pages = {
    command: <CommandCenter {...common} />,
    storeDna: <StoreDNAWorkspace {...common} storeName={store} />,
    live3d: <Live3D {...common} />,
    architect: <LayoutArchitect {...common} />,
    placement: <ProductPlacementStudio {...common} />,
    library: <ProductLibrary {...common} />,
    fixture: <FixtureLibrary {...common} />,
    planogram: (
      <>
        <PlanogramExportPanel {...common} />
        <PlanogramWorkspace {...common} />
      </>
    ),
    rules: <RuleEngineReal {...common} />,
    delta: <DeltaPlanogramReal {...common} />,
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
