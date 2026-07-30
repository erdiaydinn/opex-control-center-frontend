// PLONAGRAM FUNCTIONAL APP.JSX - SAFE RESTORE VERSION
// Bu sürüm çalışan motoru korur.
// Reference UI CSS importları kaldırıldı çünkü mevcut pe-app / pe-main yapısıyla uyumsuzdu.
// Korunanlar: Depot3D, Planogram2D, RuleEnginePanel, AnalyticsPanel, ShelfEditor, CSV/DXF upload, layout edit, rule flow.

import PlonagramAuth from "./components/auth/PlonagramAuth";
import React, { useMemo, useState } from "react";
import "./App.css";
import "./App.extra.css";
import TopBar from "./components/TopBar";
import Depot3D from "./components/Depot3D";
import Planogram2D from "./components/Planogram2D";
import RuleEnginePanel from "./components/RuleEnginePanel";
import AnalyticsPanel from "./components/AnalyticsPanel";
import ShelfEditor from "./components/ShelfEditor";
import { RuleDialog, SizeDialog } from "./components/EditDialogs";
import { printModule, printShelf } from "./components/FieldPrint";
import { apiPost, apiUploadLayout } from "./services/api";
import {
  clone,
  compareByRule,
  computeMetrics,
  DEFAULT_PRODUCTS,
  findShelf,
  generateDefaultLayout,
  localGeneratePlanogram,
  makeShelves,
  n,
  normalizeProduct,
  parseCSV,
  productWidth,
  recalcShelf,
} from "./utils/planogram";

const DEFAULT_SCORE_WEIGHTS = {
  sales: 1.35,
  picking: 1.2,
  ergonomics: 1,
  refill: 0.85,
  risk: 1.15,
  fixture: 1.4,
};

function normalizeResult(data, fallbackLayout) {
  const planogram = data?.planogram || data?.plan || data?.layout || fallbackLayout;
  return {
    planogram,
    summary:
      data?.summary || {
        total_products: 0,
        placed_products: 0,
        unplaced_products: 0,
        capacity_utilization_pct: 0,
      },
    unplaced_products: data?.unplaced_products || data?.unplaced || [],
  };
}

function normText(v) {
  return String(v || "").trim().toLocaleLowerCase("tr-TR");
}

function storageFromZone(zone) {
  const z = normText(zone);
  if (z.includes("soğuk") || z.includes("chilled") || z.includes("+4")) return "CHILLED";
  if (z.includes("donuk") || z.includes("frozen") || z.includes("-18")) return "FROZEN";
  return "AMBIENT";
}

function productMatchesAdvancedRule(product, rule) {
  const p = normalizeProduct(product);
  const type = normText(rule?.type || rule?.ruleType || "");
  const value = normText(rule?.value || rule?.query || "");
  if (!value) return false;

  if (type.includes("marka") || type.includes("brand")) {
    return normText(p.brand || p.brand_name).includes(value);
  }
  if (type.includes("alt") || type.includes("subcategory")) {
    return normText(p.category_l2 || p.frontend_subcategory_local).includes(value);
  }
  if (type.includes("sku")) {
    return normText(p.sku).includes(value) || normText(p.barcode).includes(value);
  }
  return (
    normText(p.category_l1 || p.frontend_category_local).includes(value) ||
    normText(p.product_name).includes(value)
  );
}

function shelfStorageOk(product, shelf, targetZone) {
  const wantedStorage = storageFromZone(targetZone || shelf?.allowed_storage_type);
  const allowed = String(shelf?.allowed_storage_type || "AMBIENT").toUpperCase();
  const productStorage = String(product?.storage_type || "AMBIENT").toUpperCase();
  return allowed === wantedStorage && productStorage === wantedStorage;
}

function removeProductsBySku(plan, skuSet) {
  for (const aisle of plan.aisles || []) {
    for (const module of aisle.modules || []) {
      for (const shelf of module.shelves || []) {
        shelf.products = (shelf.products || []).filter((p) => !skuSet.has(String(p.sku)));
        recalcShelf(shelf);
      }
    }
  }
}

function collectTargetShelves(plan, rule) {
  const side = String(rule?.side || rule?.taraf || "ANY").toUpperCase();
  const targetStorage = storageFromZone(rule?.zone || rule?.targetZone || "Kuru zone");
  const shelves = [];

  for (const aisle of plan.aisles || []) {
    for (const module of aisle.modules || []) {
      const moduleSide = String(module.side || "").toUpperCase();
      if (side !== "ANY" && side !== "FARK ETMEZ" && moduleSide && moduleSide !== side) continue;
      for (const shelf of module.shelves || []) {
        const allowed = String(shelf.allowed_storage_type || "AMBIENT").toUpperCase();
        if (allowed !== targetStorage) continue;
        shelves.push({ aisle, module, shelf });
      }
    }
  }

  return shelves.sort((a, b) => {
    const ad = Number(a.aisle.distance_to_dispatch || 999);
    const bd = Number(b.aisle.distance_to_dispatch || 999);
    if (ad !== bd) return ad - bd;
    return Number(a.module.module_id || 0) - Number(b.module.module_id || 0);
  });
}

function packProductsToShelves(plan, productsToPlace, rule, scoreWeights) {
  const shelves = collectTargetShelves(plan, rule);
  const sorted = [...productsToPlace]
    .map(normalizeProduct)
    .sort(compareByRule(rule?.priority === "Sales" ? "SALES" : "DARKSTORE_AI", scoreWeights));

  const unplaced = [];
  for (const raw of sorted) {
    let placed = false;
    let facing = Math.max(1, Math.min(8, Number(raw.facing_count || raw.facing || 1)));

    while (!placed && facing >= 1) {
      const p = { ...raw, facing_count: facing, facing };
      const width = productWidth(p);
      for (const target of shelves) {
        const shelf = target.shelf;
        if (!shelfStorageOk(p, shelf, rule?.zone || rule?.targetZone)) continue;
        const cap = Number(shelf.shelf_width_cm || 100);
        const used = Number(shelf.used_width_cm || 0);
        if (used + width > cap * 0.92) continue;
        shelf.products = [
          ...(shelf.products || []),
          {
            ...p,
            aisle_id: target.aisle.aisle_id,
            module_id: target.module.module_id,
            shelf_no: shelf.shelf_no,
            position_order: (shelf.products || []).length + 1,
          },
        ];
        recalcShelf(shelf);
        placed = true;
        break;
      }
      if (!placed) facing -= 1;
    }
    if (!placed) unplaced.push(raw);
  }
  return unplaced;
}

function applyAdvancedRulesToPlan(basePlan, allProducts, rules, scoreWeights) {
  const next = clone(basePlan);
  if (!Array.isArray(rules) || !rules.length) return { plan: next, touched: 0, unplaced: [] };

  let touched = 0;
  const unplacedAll = [];

  for (const rule of rules) {
    const matched = (allProducts || []).map(normalizeProduct).filter((p) => productMatchesAdvancedRule(p, rule));
    if (!matched.length) continue;
    const skuSet = new Set(matched.map((p) => String(p.sku)));
    removeProductsBySku(next, skuSet);
    const unplaced = packProductsToShelves(next, matched, rule, scoreWeights);
    touched += matched.length - unplaced.length;
    unplacedAll.push(...unplaced.map((p) => ({ ...p, rule })));
  }

  return { plan: next, touched, unplaced: unplacedAll };
}

export default function App() {
  const [authUser, setAuthUser] = useState(() => {
    const isAuth = localStorage.getItem("plonagram_auth") === "1";
    if (!isAuth) return null;
    return {
      username: localStorage.getItem("plonagram_user") || "user",
      role: localStorage.getItem("plonagram_role") || "USER",
    };
  });

  const [user, setUser] = useState(() => ({
    username: localStorage.getItem("plonagram_user") || "local",
    role: localStorage.getItem("plonagram_role") || "USER",
  }));
  const [storeCode, setStoreCode] = useState("ACIBADEM");
  const [layout, setLayout] = useState(() => generateDefaultLayout("ACIBADEM"));
  const [planogram, setPlanogram] = useState(() => generateDefaultLayout("ACIBADEM"));
  const [products, setProducts] = useState(DEFAULT_PRODUCTS.map(normalizeProduct));
  const [rule, setRule] = useState("DARKSTORE_AI");
  const [view, setView] = useState("3D");
  const [status, setStatus] = useState("Hazır. Ürün yükle, kural seç, planogram üret.");
  const [generating, setGenerating] = useState(false);
  const [selectedShelf, setSelectedShelf] = useState(null);
  const [sizeTarget, setSizeTarget] = useState(null);
  const [ruleTarget, setRuleTarget] = useState(null);
  const [logs, setLogs] = useState([]);
  const [advancedRules, setAdvancedRules] = useState([]);
  const [scoreWeights, setScoreWeights] = useState(DEFAULT_SCORE_WEIGHTS);
  const [pickingFlow, setPickingFlow] = useState(["AMBIENT", "CHILLED", "FROZEN", "HEAVY_LAST"]);
  const [uploadStats, setUploadStats] = useState({ loaded: DEFAULT_PRODUCTS.length, file: "sample", columns: 0 });
  const [lastSummary, setLastSummary] = useState(null);

  const metrics = useMemo(() => computeMetrics(planogram), [planogram]);

  if (!authUser) return <PlonagramAuth onLogin={(u) => { setAuthUser(u); setUser(u || { username: "local", role: "USER" }); }} />;

  function log(action, payload = {}) {
    setLogs((prev) => [
      ...prev,
      { ts: new Date().toISOString(), user: user?.username || "local", role: user?.role || "USER", action, payload },
    ].slice(-1000));
  }

  function commitPlan(next, action, payload) {
    const normalized = { ...next, store_code: storeCode };
    setPlanogram(normalized);
    setLayout(clone(normalized));
    if (action) log(action, payload);
  }

  function logout() {
    localStorage.removeItem("plonagram_auth");
    localStorage.removeItem("plonagram_user");
    localStorage.removeItem("plonagram_role");
    setAuthUser(null);
    setStatus("Çıkış yapıldı.");
  }

  async function handleProducts(e) {
    const file = e.target.files?.[0];
    if (!file) return;
    const text = await file.text();
    const rows = parseCSV(text);
    const header = String(text || "").split(/\r?\n/)[0] || "";
    const colCount = header.includes(";") ? header.split(";").length : header.split(",").length;
    setProducts(rows);
    setUploadStats({ loaded: rows.length, file: file.name, columns: colCount });
    setStatus(`${rows.length} ürün yüklendi. Planogram üretince yerleşen/yerleşmeyen sayısı burada görünecek.`);
    log("products_uploaded", { file: file.name, rows: rows.length, columns: colCount });
    e.target.value = "";
  }

  async function handleLayout(e) {
    const file = e.target.files?.[0];
    if (!file) return;
    const name = file.name.toLowerCase();
    try {
      if (name.endsWith(".json")) {
        const parsed = JSON.parse(await file.text());
        if (!Array.isArray(parsed.aisles)) throw new Error("JSON içinde aisles array yok.");
        const next = { ...parsed, store_code: storeCode };
        setLayout(next);
        setPlanogram(clone(next));
        setStatus(`${file.name} JSON planı yüklendi.`);
        log("layout_json_uploaded", { file: file.name });
        return;
      }
      if (name.endsWith(".dxf")) {
        setStatus(`${file.name} DXF parser'a gönderiliyor...`);
        const data = await apiUploadLayout(file, storeCode);
        if (!data?.success || !data?.layout?.aisles) throw new Error(data?.message || "DXF parse edilemedi.");
        const next = { ...data.layout, store_code: storeCode };
        setLayout(next);
        setPlanogram(clone(next));
        setStatus(`${file.name} okundu: ${next.aisles.length} koridor.`);
        log("layout_dxf_uploaded", { file: file.name, aisles: next.aisles.length });
        return;
      }
      setStatus("Şimdilik JSON ve DXF aktif. DWG/PDF için DXF'e çevir.");
    } catch (err) {
      setStatus(`Layout okunamadı: ${err.message}`);
    } finally {
      e.target.value = "";
    }
  }

  function loadSample() {
    const next = generateDefaultLayout(storeCode);
    const sample = DEFAULT_PRODUCTS.map(normalizeProduct);
    setProducts(sample);
    setUploadStats({ loaded: sample.length, file: "sample", columns: 0 });
    setLayout(next);
    setPlanogram(clone(next));
    setLastSummary(null);
    setStatus("Sample ürün ve default depo iskeleti yüklendi.");
    log("sample_loaded");
  }

  async function generatePlanogram() {
    setGenerating(true);
    try {
      const ruleEngine = { mode: rule, score_weights: scoreWeights, advanced_rules: advancedRules, picking_flow: pickingFlow, user_role: user?.role || "USER" };
      const payload = { products, layout: { ...layout, store_code: storeCode }, mode: rule, rule_engine: ruleEngine };
      let data;
      try {
        data = await apiPost("/generate-planogram", payload);
      } catch (backendErr) {
        data = localGeneratePlanogram(products, layout, rule, ruleEngine);
        data.backend_warning = backendErr.message;
      }
      let normalized = normalizeResult(data, layout);
      const applied = applyAdvancedRulesToPlan(normalized.planogram, products, advancedRules, scoreWeights);
      normalized.planogram = applied.plan;
      normalized.unplaced_products = [...(normalized.unplaced_products || []), ...applied.unplaced];
      normalized.summary = {
        ...normalized.summary,
        placed_products: computeMetrics(normalized.planogram).total_products,
        unplaced_products: normalized.unplaced_products.length,
        advanced_rule_applied_products: applied.touched,
      };
      setLastSummary(normalized.summary);
      commitPlan(normalized.planogram, "planogram_generated", { rule, advancedRules, scoreWeights, pickingFlow, summary: normalized.summary, backend_warning: data.backend_warning });
      setStatus(`Planogram üretildi: ${normalized.summary.placed_products}/${products.length} ürün yerleşti, ${normalized.summary.unplaced_products || 0} yerleşmedi.`);
      setView("3D");
    } catch (err) {
      setStatus(`Planogram üretilemedi: ${err.message}`);
    } finally {
      setGenerating(false);
    }
  }

  function applyRulesNow(nextRules = advancedRules) {
    const applied = applyAdvancedRulesToPlan(planogram, products, nextRules, scoreWeights);
    commitPlan(applied.plan, "advanced_rules_applied_now", { rules: nextRules, touched: applied.touched, unplaced: applied.unplaced.length });
    setStatus(`Kural uygulandı: ${applied.touched} ürün yeniden konumlandı, ${applied.unplaced.length} ürün sığmadı.`);
  }

  function handleAdvancedRulesChange(nextRules) {
    setAdvancedRules(nextRules);
    applyRulesNow(nextRules);
  }

  function addModule(aisleId) {
    const next = clone(planogram);
    const aisle = (next.aisles || []).find((a) => String(a.aisle_id) === String(aisleId));
    if (!aisle) return;
    const id = Math.max(0, ...(aisle.modules || []).map((m) => Number(m.module_id) || 0)) + 1;
    const cold = aisle.zone_type === "COLD_ZONE";
    const frozen = aisle.zone_type === "FROZEN_ZONE";
    aisle.modules = [...(aisle.modules || []), { module_id: id, side: id % 2 ? "L" : "R", module_type: frozen ? "freezer" : cold ? "fridge" : "regular_shelf", module_width_cm: cold || frozen ? 150 : 100, module_depth_cm: cold || frozen ? 60 : 50, module_height_cm: 210, shelves: makeShelves(frozen ? 4 : cold ? 5 : 6, frozen ? "FROZEN" : cold ? "CHILLED" : "AMBIENT", cold || frozen ? 150 : 100, frozen ? 40 : 35, cold || frozen ? 60 : 50) }];
    commitPlan(next, "module_added", { aisleId, moduleId: id });
  }

  function addShelf(aisleId, moduleId) {
    const next = clone(planogram);
    const module = (next.aisles || []).find((a) => String(a.aisle_id) === String(aisleId))?.modules?.find((m) => String(m.module_id) === String(moduleId));
    if (!module) return;
    const base = module.shelves?.[module.shelves.length - 1] || {};
    const shelf = { ...base, shelf_no: (module.shelves || []).length + 1, products: [], used_width_cm: 0, used_volume_cm3: 0, zone_type: "top" };
    module.shelves = [...(module.shelves || []), shelf];
    commitPlan(next, "shelf_added", { aisleId, moduleId, shelfNo: shelf.shelf_no });
  }

  function addAisle() {
    const next = clone(planogram);
    const existing = new Set((next.aisles || []).map((a) => String(a.aisle_id)));
    const letters = "ABCDEFGHIJKLMNOPQRSTUVWXYZ";
    let id = "A";
    for (const ch of letters) if (!existing.has(ch)) { id = ch; break; }
    if (existing.has(id)) id = `K${(next.aisles || []).length + 1}`;
    next.aisles = [...(next.aisles || []), { aisle_id: id, row: Math.floor((next.aisles || []).length / 4) + 1, position: ((next.aisles || []).length % 4) + 1, direction: "LTR", distance_to_dispatch: (next.aisles || []).length + 1, aisle_type: "double_sided", sides: ["L", "R"], modules: [{ module_id: 1, side: "L", module_type: "regular_shelf", module_width_cm: 100, module_depth_cm: 50, module_height_cm: 210, shelves: makeShelves(6, "AMBIENT", 100, 35, 50, 45) }] }];
    commitPlan(next, "aisle_added", { aisleId: id });
    setStatus(`Koridor ${id} eklendi.`);
  }

  function deleteAisle(aisleId) {
    if (!window.confirm(`Koridor ${aisleId} silinsin mi? Bu koridordaki tüm modül ve raflar silinir.`)) return;
    const next = clone(planogram);
    next.aisles = (next.aisles || []).filter((a) => String(a.aisle_id) !== String(aisleId));
    commitPlan(next, "aisle_deleted", { aisleId });
    setSelectedShelf(null);
    setStatus(`Koridor ${aisleId} silindi.`);
  }

  function deleteModule(aisleId, moduleId) {
    if (!window.confirm(`Koridor ${aisleId} / Modül ${moduleId} silinsin mi?`)) return;
    const next = clone(planogram);
    const aisle = (next.aisles || []).find((a) => String(a.aisle_id) === String(aisleId));
    if (!aisle) return;
    aisle.modules = (aisle.modules || []).filter((m) => String(m.module_id) !== String(moduleId));
    commitPlan(next, "module_deleted", { aisleId, moduleId });
    setSelectedShelf(null);
    setStatus(`Koridor ${aisleId} / Modül ${moduleId} silindi.`);
  }

  function deleteShelf(aisleId, moduleId, shelfNo) {
    if (!window.confirm(`Koridor ${aisleId} / Modül ${moduleId} / Raf ${shelfNo} silinsin mi?`)) return;
    const next = clone(planogram);
    const module = (next.aisles || []).find((a) => String(a.aisle_id) === String(aisleId))?.modules?.find((m) => String(m.module_id) === String(moduleId));
    if (!module) return;
    module.shelves = (module.shelves || []).filter((s) => String(s.shelf_no) !== String(shelfNo)).map((s, i) => ({ ...s, shelf_no: i + 1 }));
    commitPlan(next, "shelf_deleted", { aisleId, moduleId, shelfNo });
    setSelectedShelf(null);
    setStatus(`Koridor ${aisleId} / Modül ${moduleId} / Raf ${shelfNo} silindi.`);
  }

  function cloneModuleFromTemplate(template, moduleId, orientation = "vertical") {
  const base = template || {
    module_type: "regular_shelf",
    module_width_cm: 100,
    module_depth_cm: 50,
    module_height_cm: 210,
    shelves: makeShelves(6, "AMBIENT", 100, 35, 50, 45),
  };

  return {
    ...clone(base),
    module_id: moduleId,
    layout_rotation: orientation === "horizontal" ? 90 : 0,
    layout_orientation: orientation,
    shelves: (base.shelves?.length ? clone(base.shelves) : makeShelves(6, "AMBIENT", 100, 35, 50, 45)).map((s, i) => ({
      ...s,
      shelf_no: i + 1,
      products: s.products || [],
    })),
  };
}

function syncAisleModules(aisle, pos) {
  const targetCount = Number(pos.module_count ?? aisle.modules?.length ?? 0);
  if (!Number.isFinite(targetCount) || targetCount < 0) return aisle;

  const current = Array.isArray(aisle.modules) ? aisle.modules : [];
  const orientations = Array.isArray(pos.module_orientations) ? pos.module_orientations : [];

  let nextModules = current.slice(0, targetCount).map((m, idx) => ({
    ...m,
    module_id: idx + 1,
    layout_orientation: orientations[idx] || m.layout_orientation || "vertical",
    layout_rotation: (orientations[idx] || m.layout_orientation) === "horizontal" ? 90 : 0,
  }));

  const template = current[current.length - 1] || current[0];

  while (nextModules.length < targetCount) {
    const idx = nextModules.length;
    nextModules.push(
      cloneModuleFromTemplate(
        template,
        idx + 1,
        orientations[idx] || "vertical"
      )
    );
  }

  return {
    ...aisle,
    modules: nextModules,
  };
}

function handleLayoutChange(nextPositions = [], nextObjects = null) {
  const next = clone(planogram);

  next.aisles = (next.aisles || []).map((aisle) => {
    const pos = nextPositions.find((p) => String(p.aisle_id) === String(aisle.aisle_id));
    if (!pos) return aisle;

    const moved = {
      ...aisle,
      layout_position: {
        grid_x: n(pos.grid_x ?? pos.x, 0),
        grid_y: n(pos.grid_y ?? pos.y, 0),
        rotation: n(pos.rotation, 0),
      },
    };

    return syncAisleModules(moved, pos);
  });

  if (nextObjects) {
    next.layout_objects = nextObjects;
  }

  commitPlan(next, "layout_positions_updated", {
    positions: nextPositions,
    objects: nextObjects,
  });

  setStatus("Layout kaydedildi: koridor pozisyonu, modül sayısı ve modül yönleri güncellendi.");
}


  function openModuleSize(aisleId, moduleId) {
    const module = (planogram.aisles || []).find((a) => String(a.aisle_id) === String(aisleId))?.modules?.find((m) => String(m.module_id) === String(moduleId));
    if (!module) return;
    setSizeTarget({ kind: "module", aisleId, moduleId, title: `Koridor ${aisleId} / Modül ${moduleId}`, values: { module_width_cm: module.module_width_cm || 100, module_depth_cm: module.module_depth_cm || 50, module_height_cm: module.module_height_cm || 210 } });
  }

  function openShelfSize(aisleId, moduleId, shelfNo) {
    const found = findShelf(planogram, aisleId, moduleId, shelfNo);
    if (!found?.shelf) return;
    setSizeTarget({ kind: "shelf", aisleId, moduleId, shelfNo, title: `Koridor ${aisleId} / Modül ${moduleId} / Raf ${shelfNo}`, values: { shelf_width_cm: found.shelf.shelf_width_cm || 100, shelf_depth_cm: found.shelf.shelf_depth_cm || 50, shelf_height_cm: found.shelf.shelf_height_cm || 35 } });
  }

  function saveSize(values) {
    const next = clone(planogram);
    if (sizeTarget.kind === "module") {
      const aisle = next.aisles.find((a) => String(a.aisle_id) === String(sizeTarget.aisleId));
      const module = aisle?.modules?.find((m) => String(m.module_id) === String(sizeTarget.moduleId));
      if (module) Object.entries(values).forEach(([k, v]) => { module[k] = n(v, module[k]); });
      commitPlan(next, "module_size_updated", { ...sizeTarget, values });
    } else {
      const found = findShelf(next, sizeTarget.aisleId, sizeTarget.moduleId, sizeTarget.shelfNo);
      if (found?.shelf) { Object.entries(values).forEach(([k, v]) => { found.shelf[k] = n(v, found.shelf[k]); }); recalcShelf(found.shelf); }
      commitPlan(next, "shelf_size_updated", { ...sizeTarget, values });
    }
    setSizeTarget(null);
  }

  function openRule(kind, aisleId, moduleId, shelfNo = null) { setRuleTarget({ kind, aisleId, moduleId, shelfNo }); }

  function saveRule(ruleObj) {
    const next = clone(planogram);
    if (ruleTarget.kind === "module") {
      const module = next.aisles.find((a) => String(a.aisle_id) === String(ruleTarget.aisleId))?.modules?.find((m) => String(m.module_id) === String(ruleTarget.moduleId));
      if (module) module.assignment_rule = ruleObj;
    } else {
      const found = findShelf(next, ruleTarget.aisleId, ruleTarget.moduleId, ruleTarget.shelfNo);
      if (found?.shelf) { found.shelf.assignment_rule = ruleObj; if (ruleObj.allowed_storage_type) found.shelf.allowed_storage_type = ruleObj.allowed_storage_type; }
    }
    commitPlan(next, `${ruleTarget.kind}_rule_updated`, { target: ruleTarget, rule: ruleObj });
    setRuleTarget(null);
  }

  function refreshSelectedShelf(nextPlan, selected = selectedShelf) {
    if (!selected) return;
    const found = findShelf(nextPlan, selected.aisle_id, selected.module_id, selected.shelf?.shelf_no || selected.shelf_no);
    if (found?.shelf) setSelectedShelf({ ...selected, shelf: found.shelf });
  }

  function changeFacing(sku, delta) {
    const next = clone(planogram);
    for (const a of next.aisles || []) for (const m of a.modules || []) for (const s of m.shelves || []) {
      const p = (s.products || []).find((x) => String(x.sku) === String(sku));
      if (p) { p.facing_count = Math.max(1, Math.min(24, n(p.facing_count ?? p.facing, 1) + delta)); p.facing = p.facing_count; recalcShelf(s); }
    }
    commitPlan(next, "facing_changed", { sku, delta });
    refreshSelectedShelf(next);
  }

  function removeProduct(sku) {
    const next = clone(planogram);
    for (const a of next.aisles || []) for (const m of a.modules || []) for (const s of m.shelves || []) { s.products = (s.products || []).filter((p) => String(p.sku) !== String(sku)); recalcShelf(s); }
    commitPlan(next, "product_removed", { sku });
    refreshSelectedShelf(next);
  }

  function addProductToShelf(target, product) {
    const next = clone(planogram);
    const found = findShelf(next, target.aisle_id, target.module_id, target.shelf.shelf_no);
    if (!found?.shelf) return;
    const p = { ...normalizeProduct(product), facing: 1, facing_count: 1, aisle_id: target.aisle_id, module_id: target.module_id, shelf_no: target.shelf.shelf_no, position_order: (found.shelf.products || []).length + 1 };
    if (productWidth(p) + (found.shelf.used_width_cm || 0) > (found.shelf.shelf_width_cm || 100)) { setStatus("Ürün bu rafa sığmıyor. Facing/raf ölçüsü kontrol et."); return; }
    found.shelf.products.push(p);
    recalcShelf(found.shelf);
    commitPlan(next, "product_added_to_shelf", { sku: p.sku, target });
    refreshSelectedShelf(next, target);
  }

  function sortShelf(target, ruleId) {
    const next = clone(planogram);
    const found = findShelf(next, target.aisle_id, target.module_id, target.shelf.shelf_no);
    if (!found?.shelf) return;
    found.shelf.products = [...(found.shelf.products || [])].sort(compareByRule(ruleId, scoreWeights)).map((p, i) => ({ ...p, position_order: i + 1 }));
    recalcShelf(found.shelf);
    commitPlan(next, "shelf_sorted", { ruleId, target });
    refreshSelectedShelf(next, target);
  }

  function moveProduct(target, sku, direction) {
    const next = clone(planogram);
    const found = findShelf(next, target.aisle_id, target.module_id, target.shelf.shelf_no);
    const arr = found?.shelf?.products || [];
    const idx = arr.findIndex((p) => String(p.sku) === String(sku));
    if (idx < 0) return;
    const ni = direction === "left" ? Math.max(0, idx - 1) : Math.min(arr.length - 1, idx + 1);
    [arr[idx], arr[ni]] = [arr[ni], arr[idx]];
    found.shelf.products = arr.map((p, i) => ({ ...p, position_order: i + 1 }));
    commitPlan(next, "product_moved", { sku, direction });
    refreshSelectedShelf(next, target);
  }

  function exportJSON() {
    const payload = { store_code: storeCode, exported_at: new Date().toISOString(), selected_rule: rule, rule_engine: { advancedRules, scoreWeights, pickingFlow }, uploadStats, lastSummary, metrics, logs, products, layout, planogram };
    const blob = new Blob([JSON.stringify(payload, null, 2)], { type: "application/json" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = `${storeCode}_plonagram_export.json`;
    a.click();
    URL.revokeObjectURL(url);
  }

  function printAll() {
    const firstAisle = planogram.aisles?.[0];
    const firstModule = firstAisle?.modules?.[0];
    if (firstAisle && firstModule) printModule(firstAisle, firstModule);
  }

  return (
    <div className="pe-app">
      <TopBar view={view} setView={setView} status={status} storeCode={storeCode} setStoreCode={setStoreCode} onUploadProducts={handleProducts} onUploadLayout={handleLayout} onLoadSample={loadSample} onExport={exportJSON} onPrintAll={printAll} onLogout={logout} uploadStats={uploadStats} lastSummary={lastSummary} />
      <main className="pe-main">
        <RuleEnginePanel rule={rule} setRule={setRule} products={products} onGenerate={generatePlanogram} generating={generating} advancedRules={advancedRules} onAdvancedRulesChange={handleAdvancedRulesChange} scoreWeights={scoreWeights} onScoreWeightsChange={setScoreWeights} pickingFlow={pickingFlow} onPickingFlowChange={setPickingFlow} uploadStats={uploadStats} lastSummary={lastSummary} onApplyRulesNow={() => applyRulesNow()} />

        {view === "3D" && <Depot3D plan={planogram} shelfEditorOpen={!!selectedShelf} onShelfOpen={setSelectedShelf} onAddModule={addModule} onAddShelf={addShelf} onModuleSize={openModuleSize} onShelfSize={openShelfSize} onPrintModule={printModule} onLayoutChange={handleLayoutChange} onAddAisle={addAisle} onDeleteAisle={deleteAisle} onDeleteModule={deleteModule} onDeleteShelf={deleteShelf} />}

        {view === "2D" && <Planogram2D plan={planogram} onShelfOpen={setSelectedShelf} onAddModule={addModule} onAddShelf={addShelf} onModuleSize={openModuleSize} onShelfSize={openShelfSize} onRule={openRule} onPrintModule={printModule} onAddAisle={addAisle} onDeleteAisle={deleteAisle} onDeleteModule={deleteModule} onDeleteShelf={deleteShelf} />}

        {view === "ANALYTICS" && <AnalyticsPanel metrics={metrics} logs={logs} onExport={exportJSON} />}
      </main>

      <ShelfEditor selected={selectedShelf} plan={planogram} products={products} onClose={() => setSelectedShelf(null)} onFacing={changeFacing} onRemove={removeProduct} onAddProduct={addProductToShelf} onSortShelf={sortShelf} onMoveProduct={moveProduct} onPrintShelf={printShelf} onShelfSize={openShelfSize} />
      <SizeDialog target={sizeTarget} onClose={() => setSizeTarget(null)} onSave={saveSize} />
      <RuleDialog target={ruleTarget} products={products} onClose={() => setRuleTarget(null)} onSave={saveRule} />
    </div>
  );
}
