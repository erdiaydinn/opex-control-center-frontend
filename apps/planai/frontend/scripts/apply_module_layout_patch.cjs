const fs = require("fs");
const path = require("path");

const appPath = path.join(process.cwd(), "src", "App.jsx");
if (!fs.existsSync(appPath)) {
  console.error("src/App.jsx bulunamadı. Bu script frontend klasöründen çalıştırılmalı.");
  process.exit(1);
}

let src = fs.readFileSync(appPath, "utf8");

const start = src.indexOf("function syncAisleModules(");
const end = src.indexOf("function handleLayoutChange", start);

if (start === -1 || end === -1) {
  console.error("syncAisleModules bloğu bulunamadı. App.jsx zaten farklı olabilir.");
  process.exit(1);
}

const replacement = `function syncAisleModules(aisle, pos) {
  const targetCount = Number(pos.module_count ?? aisle.modules?.length ?? 0);
  if (!Number.isFinite(targetCount) || targetCount < 0) return aisle;

  const current = Array.isArray(aisle.modules) ? aisle.modules : [];
  const orientations = Array.isArray(pos.module_orientations) ? pos.module_orientations : [];
  const layouts = Array.isArray(pos.module_layouts) ? pos.module_layouts : [];

  let nextModules = current.slice(0, targetCount).map((m, idx) => {
    const lay = layouts[idx] || layouts.find((x) => String(x.module_id) === String(idx + 1)) || {};
    const orientation = lay.orientation || orientations[idx] || m.layout_orientation || "vertical";
    return {
      ...m,
      module_id: idx + 1,
      side: lay.side || m.side || (idx % 2 ? "R" : "L"),
      fixture_type: lay.fixture_type || m.fixture_type,
      layout_orientation: orientation,
      layout_rotation: Number(lay.rotation ?? (orientation === "horizontal" ? 90 : 0)),
      layout_position: {
        x: Number(lay.x ?? m.layout_position?.x ?? m.layout_position?.grid_x ?? 0),
        y: Number(lay.y ?? m.layout_position?.y ?? m.layout_position?.grid_y ?? 0),
        w: Number(lay.w ?? m.layout_position?.w ?? 1),
        h: Number(lay.h ?? m.layout_position?.h ?? 1),
        rotation: Number(lay.rotation ?? m.layout_position?.rotation ?? (orientation === "horizontal" ? 90 : 0)),
      },
    };
  });

  const template = current[current.length - 1] || current[0];

  while (nextModules.length < targetCount) {
    const idx = nextModules.length;
    const lay = layouts[idx] || {};
    const orientation = lay.orientation || orientations[idx] || "vertical";
    nextModules.push({
      ...cloneModuleFromTemplate(template, idx + 1, orientation),
      side: lay.side || (idx % 2 ? "R" : "L"),
      fixture_type: lay.fixture_type || template?.fixture_type,
      layout_position: {
        x: Number(lay.x ?? 0),
        y: Number(lay.y ?? 0),
        w: Number(lay.w ?? 1),
        h: Number(lay.h ?? 1),
        rotation: Number(lay.rotation ?? (orientation === "horizontal" ? 90 : 0)),
      },
    });
  }

  return {
    ...aisle,
    walkway_m: Number(pos.walkway_m ?? aisle.walkway_m ?? aisle.walkway_width_m ?? 1.2),
    modules: nextModules,
  };
}

`;

src = src.slice(0, start) + replacement + src.slice(end);

fs.writeFileSync(appPath, src, "utf8");
console.log("App.jsx güncellendi: module_layouts artık kalıcı ve 3D'ye yansıyacak.");
