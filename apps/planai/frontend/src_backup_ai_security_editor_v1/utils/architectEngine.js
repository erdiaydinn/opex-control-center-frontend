import { rectsOverlap, minGapBetweenRects } from "./collisionEngine";

function uid(prefix) {
  return `${prefix}-${Date.now()}-${Math.random().toString(36).slice(2, 7)}`;
}

export function buildArchitectLayout(planogram = {}, storeCode = "default") {
  const nodes = [];
  const aisles = Array.isArray(planogram?.aisles) ? planogram.aisles : [];

  aisles.forEach((a, i) => {
    const gx = Number(a.layout_position?.grid_x ?? a.grid_x ?? (i % 2) * 8);
    const gy = Number(a.layout_position?.grid_y ?? a.grid_y ?? Math.floor(i / 2) * 4);
    const left = Number(a.left_modules ?? Math.ceil((a.modules?.length || 10) / 2));
    const right = Number(a.right_modules ?? Math.floor((a.modules?.length || 10) / 2));
    const walkway = Number(a.walkway_width_cm ?? a.walkway_width_m * 100 ?? 120);

    nodes.push({
      id: `aisle-${a.aisle_id}`,
      kind: "aisle_way",
      type: "aisle_way",
      aisle_id: a.aisle_id,
      label: a.aisle_id,
      x: gx,
      y: gy + 1.3,
      w: Math.max(left, right) * 1.2,
      h: Math.max(0.8, walkway / 100),
      walkway_cm: walkway,
      rotation: Number(a.layout_position?.rotation ?? a.rotation ?? 0),
      source: "planogram",
    });

    for (let m = 0; m < left; m++) {
      nodes.push({
        id: `module-${a.aisle_id}-L-${m + 1}`,
        kind: "module",
        type: "rack_module",
        aisle_id: a.aisle_id,
        side: "L",
        module_index: m + 1,
        label: `${a.aisle_id}-L${m + 1}`,
        fixture_type: "steel_rack",
        x: gx + m * 1.2,
        y: gy,
        w: 1,
        h: .55,
        rotation: 0,
      });
    }

    for (let m = 0; m < right; m++) {
      nodes.push({
        id: `module-${a.aisle_id}-R-${m + 1}`,
        kind: "module",
        type: "rack_module",
        aisle_id: a.aisle_id,
        side: "R",
        module_index: m + 1,
        label: `${a.aisle_id}-R${m + 1}`,
        fixture_type: "steel_rack",
        x: gx + m * 1.2,
        y: gy + 2.6,
        w: 1,
        h: .55,
        rotation: 0,
      });
    }
  });

  (planogram?.layout_objects || []).forEach((o) => {
    nodes.push({
      id: o.id || uid(o.type || "obj"),
      kind: o.object_kind === "structural" || ["wall", "column", "column_round", "column_rect"].includes(o.type) ? "obstacle" : "object",
      type: o.type || "object",
      label: o.label || o.type || "Object",
      x: Number(o.x ?? 1),
      y: Number(o.y ?? 1),
      w: Number(o.w ?? 2),
      h: Number(o.h ?? 1),
      rotation: Number(o.rotation ?? 0),
      source: "layout_objects",
    });
  });

  return {
    store_code: storeCode,
    version: "architect_v1",
    grid: { cols: 52, rows: 36, cell_px: 22, cell_cm: 50 },
    nodes,
    settings: {
      snap_grid_cm: 10,
      collision_detection: true,
      dynamic_aisle_analysis: true,
    },
  };
}

export function addObstacle(layout, type) {
  const labels = {
    column: "KOLON",
    wall: "DUVAR",
    electrical_panel: "PANO",
    fire_exit: "ACİL",
    dispatch_desk: "DISPATCH",
  };
  const sizes = {
    column: [1, 1],
    wall: [5, .35],
    electrical_panel: [1.2, .5],
    fire_exit: [1.8, .45],
    dispatch_desk: [3, 1.2],
  };
  const [w, h] = sizes[type] || [1, 1];
  return {
    ...layout,
    nodes: [
      ...layout.nodes,
      {
        id: uid(type),
        kind: "obstacle",
        type,
        label: labels[type] || type,
        x: 4,
        y: 4,
        w,
        h,
        rotation: 0,
      },
    ],
  };
}

export function patchNode(layout, id, patch) {
  return {
    ...layout,
    nodes: layout.nodes.map((n) => (n.id === id ? { ...n, ...patch } : n)),
  };
}

export function moveNode(layout, id, x, y) {
  return patchNode(layout, id, { x: Math.max(0, x), y: Math.max(0, y) });
}

export function rotateNode(layout, id) {
  return {
    ...layout,
    nodes: layout.nodes.map((n) =>
      n.id === id ? { ...n, rotation: ((Number(n.rotation) || 0) + 90) % 360 } : n
    ),
  };
}

export function removeNode(layout, id) {
  return { ...layout, nodes: layout.nodes.filter((n) => n.id !== id) };
}

export function createAisleModules(layout, aisleId = "A", left = 5, right = 5) {
  const without = layout.nodes.filter(
    (n) => !(n.aisle_id === aisleId && (n.kind === "module" || n.kind === "aisle_way"))
  );

  const baseX = 5;
  const baseY = 5;
  const nodes = [...without];

  nodes.push({
    id: `aisle-${aisleId}`,
    kind: "aisle_way",
    type: "aisle_way",
    aisle_id: aisleId,
    label: aisleId,
    x: baseX,
    y: baseY + 1.3,
    w: Math.max(left, right) * 1.2,
    h: 1.2,
    walkway_cm: 120,
    rotation: 0,
  });

  for (let i = 0; i < left; i++) {
    nodes.push({
      id: `module-${aisleId}-L-${i + 1}`,
      kind: "module",
      type: "rack_module",
      aisle_id: aisleId,
      side: "L",
      module_index: i + 1,
      label: `${aisleId}-L${i + 1}`,
      fixture_type: "steel_rack",
      x: baseX + i * 1.2,
      y: baseY,
      w: 1,
      h: .55,
      rotation: 0,
    });
  }

  for (let i = 0; i < right; i++) {
    nodes.push({
      id: `module-${aisleId}-R-${i + 1}`,
      kind: "module",
      type: "rack_module",
      aisle_id: aisleId,
      side: "R",
      module_index: i + 1,
      label: `${aisleId}-R${i + 1}`,
      fixture_type: "steel_rack",
      x: baseX + i * 1.2,
      y: baseY + 2.6,
      w: 1,
      h: .55,
      rotation: 0,
    });
  }

  return { ...layout, nodes };
}

export function computeWarnings(layout) {
  const warnings = [];
  const nodes = layout.nodes || [];
  const modules = nodes.filter((n) => n.kind === "module");
  const obstacles = nodes.filter((n) => n.kind === "obstacle");
  const aisles = nodes.filter((n) => n.kind === "aisle_way");

  for (const m of modules) {
    for (const o of obstacles) {
      if (rectsOverlap(m, o)) {
        warnings.push({
          level: "high",
          title: "Modül/engel çakışması",
          message: `${m.label} ile ${o.label} aynı alana giriyor.`,
        });
      } else {
        const gap = minGapBetweenRects(m, o);
        if (gap < .35) {
          warnings.push({
            level: "medium",
            title: "Dar geçiş riski",
            message: `${m.label} ile ${o.label} arası çok dar olabilir.`,
          });
        }
      }
    }
  }

  for (const a of aisles) {
    if (Number(a.walkway_cm || 0) < 100 || Number(a.h || 0) < 1) {
      warnings.push({
        level: "medium",
        title: "Dar koridor",
        message: `${a.label} koridoru picker geçişi için dar olabilir.`,
      });
    }
  }

  return warnings.slice(0, 12);
}
