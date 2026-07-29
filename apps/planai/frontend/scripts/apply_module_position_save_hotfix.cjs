const fs = require("fs");
const path = require("path");

const appPath = path.join(process.cwd(), "src", "App.jsx");

if (!fs.existsSync(appPath)) {
  console.error("src/App.jsx bulunamadı. Bu script frontend klasöründen çalıştırılmalı.");
  process.exit(1);
}

let src = fs.readFileSync(appPath, "utf8");

function findFunctionBlock(source, fnName) {
  const start = source.indexOf(`function ${fnName}(`);
  if (start === -1) return null;
  const braceStart = source.indexOf("{", start);
  if (braceStart === -1) return null;
  let depth = 0;
  for (let i = braceStart; i < source.length; i++) {
    const ch = source[i];
    if (ch === "{") depth++;
    if (ch === "}") {
      depth--;
      if (depth === 0) return { start, end: i + 1 };
    }
  }
  return null;
}

function replaceFunction(fnName, replacement) {
  const block = findFunctionBlock(src, fnName);
  if (!block) {
    console.warn(`${fnName} bulunamadı, atlandı.`);
    return false;
  }
  src = src.slice(0, block.start) + replacement.trim() + "\n\n" + src.slice(block.end);
  console.log(`${fnName} güncellendi.`);
  return true;
}

const syncReplacement = `
function syncAisleModules(aisle, pos) {
  const targetCount = Number(pos.module_count ?? aisle.modules?.length ?? 0);
  if (!Number.isFinite(targetCount) || targetCount < 0) return aisle;

  const current = Array.isArray(aisle.modules) ? aisle.modules : [];
  const orientations = Array.isArray(pos.module_orientations) ? pos.module_orientations : [];
  const layouts = Array.isArray(pos.module_layouts) ? pos.module_layouts : [];

  let nextModules = current.slice(0, targetCount).map((m, idx) => {
    const lay = layouts[idx] || layouts.find((x) => String(x.module_id) === String(idx + 1)) || {};
    const existingPos = m.layout_position || {};
    const orientation = lay.orientation || orientations[idx] || m.layout_orientation || ((Number(existingPos.rotation || m.layout_rotation || 0) % 180 === 90) ? "horizontal" : "vertical");

    return {
      ...m,
      module_id: idx + 1,
      side: lay.side || m.side || (idx % 2 ? "R" : "L"),
      fixture_type: lay.fixture_type || m.fixture_type || "regular_shelf",
      module_type: lay.fixture_type || m.module_type || m.fixture_type,
      layout_orientation: orientation,
      layout_rotation: Number(lay.rotation ?? existingPos.rotation ?? m.layout_rotation ?? (orientation === "horizontal" ? 90 : 0)),
      layout_position: {
        x: Number(lay.x ?? existingPos.x ?? existingPos.grid_x ?? 0),
        y: Number(lay.y ?? existingPos.y ?? existingPos.grid_y ?? 0),
        grid_x: Number(lay.x ?? existingPos.x ?? existingPos.grid_x ?? 0),
        grid_y: Number(lay.y ?? existingPos.y ?? existingPos.grid_y ?? 0),
        w: Number(lay.w ?? existingPos.w ?? 1),
        h: Number(lay.h ?? existingPos.h ?? 1),
        rotation: Number(lay.rotation ?? existingPos.rotation ?? m.layout_rotation ?? (orientation === "horizontal" ? 90 : 0)),
      },
    };
  });

  const template = current[current.length - 1] || current[0];

  while (nextModules.length < targetCount) {
    const idx = nextModules.length;
    const lay = layouts[idx] || {};
    const orientation = lay.orientation || orientations[idx] || "vertical";
    const created = cloneModuleFromTemplate(template, idx + 1, orientation);

    nextModules.push({
      ...created,
      side: lay.side || (idx % 2 ? "R" : "L"),
      fixture_type: lay.fixture_type || created.fixture_type || "regular_shelf",
      module_type: lay.fixture_type || created.module_type || created.fixture_type,
      layout_position: {
        x: Number(lay.x ?? 0),
        y: Number(lay.y ?? 0),
        grid_x: Number(lay.x ?? 0),
        grid_y: Number(lay.y ?? 0),
        w: Number(lay.w ?? 1),
        h: Number(lay.h ?? 1),
        rotation: Number(lay.rotation ?? (orientation === "horizontal" ? 90 : 0)),
      },
    });
  }

  return {
    ...aisle,
    walkway_m: Number(pos.walkway_m ?? aisle.walkway_m ?? aisle.walkway_width_m ?? 1.2),
    walkway_width_m: Number(pos.walkway_m ?? aisle.walkway_m ?? aisle.walkway_width_m ?? 1.2),
    module_layouts: layouts,
    module_orientations: orientations,
    modules: nextModules,
  };
}
`;

const handleReplacement = `
function handleLayoutChange(nextPositions = [], nextObjects = null) {
  const next = clone(planogram);

  next.aisles = (next.aisles || []).map((aisle) => {
    const pos = nextPositions.find((p) => String(p.aisle_id) === String(aisle.aisle_id));
    if (!pos) return aisle;

    const moved = {
      ...aisle,
      layout_position: {
        grid_x: n(pos.grid_x ?? pos.x, aisle.layout_position?.grid_x ?? 0),
        grid_y: n(pos.grid_y ?? pos.y, aisle.layout_position?.grid_y ?? 0),
        x: n(pos.grid_x ?? pos.x, aisle.layout_position?.x ?? 0),
        y: n(pos.grid_y ?? pos.y, aisle.layout_position?.y ?? 0),
        rotation: n(pos.rotation, aisle.layout_position?.rotation ?? 0),
      },
      module_layouts: Array.isArray(pos.module_layouts) ? pos.module_layouts : [],
      module_orientations: Array.isArray(pos.module_orientations) ? pos.module_orientations : [],
      walkway_m: Number(pos.walkway_m ?? aisle.walkway_m ?? aisle.walkway_width_m ?? 1.2),
      walkway_width_m: Number(pos.walkway_m ?? aisle.walkway_m ?? aisle.walkway_width_m ?? 1.2),
    };

    return syncAisleModules(moved, pos);
  });

  if (Array.isArray(nextObjects)) {
    next.layout_objects = nextObjects;
  }

  next.layout_updated_at = new Date().toISOString();

  try {
    localStorage.setItem(\`plonagram_layout_\${storeCode}\`, JSON.stringify(next));
  } catch (err) {
    console.warn("LOCAL_LAYOUT_SAVE_ERROR", err);
  }

  commitPlan(next, "layout_positions_updated", {
    positions: nextPositions,
    objects: nextObjects,
  });

  setStatus("Layout kaydedildi: koridor, modül pozisyonları, kolon/duvar ve modül içi ayarlar kaydedildi.");
}
`;

const commitReplacement = `
function commitPlan(next, action, payload) {
  const normalized = { ...next, store_code: storeCode };
  setPlanogram(normalized);
  setLayout(clone(normalized));

  try {
    localStorage.setItem(\`plonagram_layout_\${storeCode}\`, JSON.stringify(normalized));
  } catch (err) {
    console.warn("LOCAL_LAYOUT_SAVE_ERROR", err);
  }

  if (action) log(action, payload);
}
`;

replaceFunction("syncAisleModules", syncReplacement);
replaceFunction("handleLayoutChange", handleReplacement);
replaceFunction("commitPlan", commitReplacement);

// Patch initial backend boot layout selection to prefer local saved layout
src = src.replace(
  /const baseLayout = generateDefaultLayout\(nextCode\);\s*setLayout\(baseLayout\);\s*setPlanogram\(baseLayout\);/,
  `let baseLayout = generateDefaultLayout(nextCode);
          try {
            const saved = localStorage.getItem(\`plonagram_layout_\${nextCode}\`);
            if (saved) baseLayout = JSON.parse(saved);
          } catch (err) {
            console.warn("LOCAL_LAYOUT_LOAD_ERROR", err);
          }
          setLayout(baseLayout);
          setPlanogram(baseLayout);`
);

// Patch store change to prefer local saved layout
src = src.replace(
  /const nextLayout = generateDefaultLayout\(nextCode\);\s*setLayout\(nextLayout\);\s*setPlanogram\(clone\(nextLayout\)\);/,
  `let nextLayout = generateDefaultLayout(nextCode);
    try {
      const saved = localStorage.getItem(\`plonagram_layout_\${nextCode}\`);
      if (saved) nextLayout = JSON.parse(saved);
    } catch (err) {
      console.warn("LOCAL_LAYOUT_LOAD_ERROR", err);
    }
    setLayout(nextLayout);
    setPlanogram(clone(nextLayout));`
);

fs.writeFileSync(appPath, src, "utf8");
console.log("Module position save hotfix tamamlandı.");
