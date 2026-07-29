import React, { useMemo, useState } from "react";
import "./ArchitectMode.css";
import {
  buildArchitectLayout,
  addObstacle,
  patchNode,
  removeNode,
  moveNode,
  rotateNode,
  computeWarnings,
  createAisleModules,
} from "../../utils/architectEngine";

const OBSTACLE_TYPES = [
  { type: "column", label: "Kolon" },
  { type: "wall", label: "Duvar" },
  { type: "electrical_panel", label: "Elektrik Panosu" },
  { type: "fire_exit", label: "Acil Çıkış" },
  { type: "dispatch_desk", label: "Dispatch Masası" },
];

function n(v, d = 0) {
  const x = Number(String(v ?? "").replace(",", "."));
  return Number.isFinite(x) ? x : d;
}

export default function ArchitectMode({
  planogram,
  onSave,
  onClose,
  storeCode = "default",
}) {
  const [layout, setLayout] = useState(() => buildArchitectLayout(planogram, storeCode));
  const [selectedId, setSelectedId] = useState(null);
  const [mode, setMode] = useState("snap"); // snap | free
  const [drag, setDrag] = useState(null);
  const [zoom, setZoom] = useState(1);

  const selected = useMemo(
    () => layout.nodes.find((x) => x.id === selectedId),
    [layout.nodes, selectedId]
  );

  const warnings = useMemo(() => computeWarnings(layout), [layout]);

  function updateNode(id, patch) {
    setLayout((prev) => patchNode(prev, id, patch));
  }

  function handleGridMouseMove(e) {
    if (!drag) return;

    const rect = e.currentTarget.getBoundingClientRect();
    const cell = layout.grid.cell_px * zoom;
    const rawX = (e.clientX - rect.left) / cell;
    const rawY = (e.clientY - rect.top) / cell;

    const x = mode === "snap" ? Math.round(rawX) : Math.round(rawX * 10) / 10;
    const y = mode === "snap" ? Math.round(rawY) : Math.round(rawY * 10) / 10;

    setLayout((prev) => moveNode(prev, drag.id, x, y));
  }

  function save() {
    onSave?.({
      ...layout,
      exported_at: new Date().toISOString(),
      source: "architect_mode",
    });
  }

  return (
    <div className="arch-shell">
      <div className="arch-topbar">
        <div>
          <div className="arch-kicker">PLONAGRAM LIVE TWIN</div>
          <h2>Architect Mode</h2>
          <p>Koridor, modül, kolon ve engelleri gerçek depo fiziğine göre düzenle.</p>
        </div>

        <div className="arch-actions">
          <button
            className={mode === "snap" ? "active" : ""}
            onClick={() => setMode("snap")}
          >
            Snap
          </button>
          <button
            className={mode === "free" ? "active" : ""}
            onClick={() => setMode("free")}
          >
            Free
          </button>
          <button onClick={() => setZoom((z) => Math.max(.7, z - .1))}>−</button>
          <button onClick={() => setZoom((z) => Math.min(1.7, z + .1))}>+</button>
          <button className="primary" onClick={save}>Kaydet</button>
          {onClose && <button onClick={onClose}>Kapat</button>}
        </div>
      </div>

      <div className="arch-body">
        <aside className="arch-left">
          <h3>Obje Ekle</h3>
          <div className="arch-tool-grid">
            {OBSTACLE_TYPES.map((x) => (
              <button
                key={x.type}
                onClick={() => {
                  const next = addObstacle(layout, x.type);
                  setLayout(next);
                  setSelectedId(next.nodes[next.nodes.length - 1]?.id);
                }}
              >
                {x.label}
              </button>
            ))}
          </div>

          <h3>Koridor Modülleri</h3>
          <button
            onClick={() => {
              const next = createAisleModules(layout, "A", 5, 5);
              setLayout(next);
            }}
          >
            A Koridoru 5L / 5R Oluştur
          </button>

          <div className="arch-warning-box">
            <strong>Operasyon Uyarıları</strong>
            {warnings.length === 0 ? (
              <p className="ok">Kritik çakışma görünmüyor.</p>
            ) : (
              warnings.map((w, i) => (
                <div key={i} className={`warn ${w.level}`}>
                  <b>{w.title}</b>
                  <span>{w.message}</span>
                </div>
              ))
            )}
          </div>
        </aside>

        <main
          className="arch-canvas"
          onMouseMove={handleGridMouseMove}
          onMouseUp={() => setDrag(null)}
          onMouseLeave={() => setDrag(null)}
          style={{
            "--cell": `${layout.grid.cell_px * zoom}px`,
            "--cols": layout.grid.cols,
            "--rows": layout.grid.rows,
          }}
        >
          <div className="arch-floor" />

          {layout.nodes.map((node) => (
            <div
              key={node.id}
              className={`arch-node ${node.kind} ${node.type} ${selectedId === node.id ? "selected" : ""}`}
              style={{
                left: `calc(${node.x} * var(--cell))`,
                top: `calc(${node.y} * var(--cell))`,
                width: `calc(${node.w} * var(--cell))`,
                height: `calc(${node.h} * var(--cell))`,
                transform: `rotate(${node.rotation || 0}deg)`,
              }}
              onMouseDown={(e) => {
                e.stopPropagation();
                setSelectedId(node.id);
                setDrag({ id: node.id });
              }}
              onDoubleClick={(e) => {
                e.stopPropagation();
                setLayout((prev) => removeNode(prev, node.id));
                setSelectedId(null);
              }}
              onContextMenu={(e) => {
                e.preventDefault();
                setLayout((prev) => rotateNode(prev, node.id));
              }}
            >
              <span>{node.label}</span>
              {node.kind === "aisle_way" && <em>{node.walkway_cm || 120} cm</em>}
            </div>
          ))}
        </main>

        <aside className="arch-right">
          <h3>Seçili Obje</h3>

          {!selected ? (
            <p className="muted">Bir koridor, modül veya engel seç.</p>
          ) : (
            <div className="arch-inspector">
              <label>Ad</label>
              <input
                value={selected.label || ""}
                onChange={(e) => updateNode(selected.id, { label: e.target.value })}
              />

              <div className="two">
                <label>X
                  <input
                    type="number"
                    step={mode === "free" ? "0.1" : "1"}
                    value={selected.x}
                    onChange={(e) => updateNode(selected.id, { x: n(e.target.value, selected.x) })}
                  />
                </label>
                <label>Y
                  <input
                    type="number"
                    step={mode === "free" ? "0.1" : "1"}
                    value={selected.y}
                    onChange={(e) => updateNode(selected.id, { y: n(e.target.value, selected.y) })}
                  />
                </label>
              </div>

              <div className="two">
                <label>Genişlik
                  <input
                    type="number"
                    step="0.1"
                    value={selected.w}
                    onChange={(e) => updateNode(selected.id, { w: Math.max(.2, n(e.target.value, selected.w)) })}
                  />
                </label>
                <label>Derinlik
                  <input
                    type="number"
                    step="0.1"
                    value={selected.h}
                    onChange={(e) => updateNode(selected.id, { h: Math.max(.2, n(e.target.value, selected.h)) })}
                  />
                </label>
              </div>

              <label>Yön</label>
              <select
                value={selected.rotation || 0}
                onChange={(e) => updateNode(selected.id, { rotation: Number(e.target.value) })}
              >
                <option value={0}>0°</option>
                <option value={90}>90°</option>
                <option value={180}>180°</option>
                <option value={270}>270°</option>
              </select>

              {selected.kind === "module" && (
                <>
                  <label>Raf Tipi</label>
                  <select
                    value={selected.fixture_type || "steel_rack"}
                    onChange={(e) => updateNode(selected.id, { fixture_type: e.target.value })}
                  >
                    <option value="steel_rack">Çelik Raf</option>
                    <option value="steel_rack_new_gen">Yeni Nesil Çelik Raf</option>
                    <option value="hdr_heavy_rack">HDR Ağır Yük</option>
                    <option value="martek_plus4">Martek +4</option>
                    <option value="martek_frozen_minus18">Martek -18</option>
                    <option value="ice_cream_chest_freezer_large">Algida/Golf</option>
                  </select>
                </>
              )}

              <button onClick={() => setLayout((prev) => rotateNode(prev, selected.id))}>
                Döndür
              </button>
              <button className="danger" onClick={() => {
                setLayout((prev) => removeNode(prev, selected.id));
                setSelectedId(null);
              }}>
                Sil
              </button>
            </div>
          )}

          <div className="arch-help">
            <b>Kullanım</b>
            <p>Sürükle: taşı · Sağ tık: döndür · Çift tık: sil</p>
            <p>Snap hızlı kurulum, Free gerçek mimari düzeltme içindir.</p>
          </div>
        </aside>
      </div>
    </div>
  );
}
