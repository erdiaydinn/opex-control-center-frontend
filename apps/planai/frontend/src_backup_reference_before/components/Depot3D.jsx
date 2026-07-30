import React, { Suspense, useMemo, useRef, useState } from "react";
import "./Depot3D.css";
import "./Depot3D.reference.css";
import { Canvas, useFrame, useThree } from "@react-three/fiber";
import * as THREE from "three";
import { Html, Line, OrbitControls, PerspectiveCamera } from "@react-three/drei";
import LayoutEditor from "./LayoutEditor";


// Fixture editor event bridge.
// 3D obje tıklamalarında parent callback bağlı değilse bile event atar.
const safeOpenFixtureEditor = (payload) => {
  try {
    window.dispatchEvent(new CustomEvent("plonagram:open-fixture-editor", { detail: payload || {} }));
  } catch (_) {}
};




// === PLONAGRAM EMERGENCY HOTFIX V1 ===
// Depot3D içinde setActiveTool tanımsız kalırsa Canvas komple çöküyordu.
// Bu fallback 3D sahneyi ayağa kaldırır. Sonraki sprintte tool state App/Depot3D tarafına temiz bağlanacak.
const __plonagramSetActiveToolFallback = (tool) => {
  try {
    window.__PLONAGRAM_ACTIVE_TOOL__ = tool;
    window.dispatchEvent(new CustomEvent("plonagram:active-tool", { detail: { tool } }));
  } catch (_) {}
};


const setActiveTool = __plonagramSetActiveToolFallback;

function n(v, d = 0) {
  const x = Number(v);
  return Number.isFinite(x) ? x : d;
}

function getAisles(plan) {
  return Array.isArray(plan?.aisles) ? plan.aisles : [];
}

function zoneOf(aisle) {
  const z = String(aisle?.zone_type || aisle?.storage_type || "").toUpperCase();
  const f = String(aisle?.fixture_type || "").toUpperCase();
  if (z.includes("FROZEN") || f.includes("FREEZER") || f.includes("-18")) return "frozen";
  if (z.includes("COLD") || z.includes("CHILLED") || f.includes("+4") || f.includes("COOLER")) return "chilled";
  if (f.includes("HDR") || f.includes("HEAVY")) return "heavy";
  return "ambient";
}

function aislePosition(aisle, i) {
  const lp = aisle?.layout_position || {};
  const gx = n(lp.grid_x ?? lp.x, (i % 3) * 7);
  const gy = n(lp.grid_y ?? lp.y, Math.floor(i / 3) * 4);
  const rot = (n(lp.rotation, 0) * Math.PI) / 180;
  return [(gx - 7) * 1.45, 0, (gy - 4) * 1.25, rot];
}

function GlassBadge({ children, className = "", position = [0, 0, 0] }) {
  return (
    <Html position={position} center distanceFactor={30} transform={false}>
      <div className={`ops-3d-badge ${className}`}>{children}</div>
    </Html>
  );
}

function ShelfProduct({ x, y, z, zone, index }) {
  const color =
    zone === "frozen" ? "#bfdbfe" :
    zone === "chilled" ? "#99f6e4" :
    zone === "heavy" ? "#fde68a" :
    index % 3 === 0 ? "#f9a8d4" : index % 3 === 1 ? "#fef3c7" : "#dbeafe";

  return (
    <mesh position={[x, y, z]} castShadow>
      <boxGeometry args={[0.22, 0.32, 0.18]} />
      <meshStandardMaterial color={color} roughness={0.62} metalness={0.04} />
    </mesh>
  );
}

function MetalRack({ aisle, module, moduleIndex, onShelfOpen, onModuleSelect }) {
  const zone = zoneOf(aisle);
  const shelves = Array.isArray(module?.shelves) ? module.shelves : [];
  const lp = module?.layout_position || {};
  const custom = lp.x !== undefined || lp.grid_x !== undefined;

  const mx = custom ? (n(lp.x ?? lp.grid_x, moduleIndex) * 1.34) : moduleIndex * 2.72;
  const mz = custom ? (n(lp.y ?? lp.grid_y, 0) * 1.18) : 0;
  const rotY = (n(lp.rotation ?? module.layout_rotation, 0) % 180 === 90) ? Math.PI / 2 : 0;

  const shelfCount = Math.max(5, Math.min(7, shelves.length || 5));

  return (
    <group
      position={[mx, 0, mz]}
      rotation={[0, rotY, 0]}
      onClick={(e) => {
        e.stopPropagation();
        onModuleSelect?.({ aisleId: aisle.aisle_id, moduleId: module.module_id });
      }}
    >
      <mesh position={[0, 0.06, 0]} receiveShadow castShadow>
        <boxGeometry args={[2.45, 0.12, 0.72]} />
        <meshStandardMaterial color="#9aa8b8" roughness={0.48} metalness={0.58} />
      </mesh>

      {[-1.24, 1.24].map((x) =>
        [-0.36, 0.36].map((z) => (
          <mesh key={`${x}-${z}`} position={[x, 1.44, z]} castShadow>
            <boxGeometry args={[0.075, 2.82, 0.075]} />
            <meshStandardMaterial color="#64748b" roughness={0.34} metalness={0.72} />
          </mesh>
        ))
      )}

      {Array.from({ length: shelfCount }).map((_, shelfIndex) => {
        const y = 0.28 + shelfIndex * 0.42;
        return (
          <group key={shelfIndex}>
            <mesh position={[0, y, 0]} castShadow receiveShadow>
              <boxGeometry args={[2.55, 0.06, 0.74]} />
              <meshStandardMaterial color="#cbd5e1" roughness={0.42} metalness={0.42} />
            </mesh>
            <mesh
              position={[0, y + 0.04, 0]}
              onClick={(e) => {
                e.stopPropagation();
                onShelfOpen?.({
                  aisle_id: aisle.aisle_id,
                  module_id: module.module_id,
                  shelf_no: shelfIndex + 1,
                  shelf: shelves[shelfIndex] || {},
                });
              }}
            >
              <boxGeometry args={[2.65, 0.08, 0.82]} />
              <meshBasicMaterial transparent opacity={0} />
            </mesh>
            {Array.from({ length: 8 }).map((_, p) => (
              <ShelfProduct
                key={p}
                x={-1.02 + p * 0.29}
                y={y + 0.20}
                z={p % 2 ? 0.12 : -0.12}
                zone={zone}
                index={p + shelfIndex}
              />
            ))}
          </group>
        );
      })}

      <mesh position={[0, 1.48, 0]} castShadow>
        <boxGeometry args={[2.62, 2.72, 0.03]} />
        <meshStandardMaterial color="#e2e8f0" roughness={0.08} metalness={0.04} transparent opacity={0.08} />
      </mesh>
    </group>
  );
}

function CoolerBank({ type = "chilled", position = [0, 0, 0], label = "+4" }) {
  const cyan = type === "chilled";
  const frozen = type === "frozen";
  return (
    <group position={position}>
      <mesh position={[0, 1.1, 0]} castShadow receiveShadow>
        <boxGeometry args={[3.2, 2.2, 0.78]} />
        <meshStandardMaterial
          color={frozen ? "#dbeafe" : cyan ? "#cffafe" : "#fecaca"}
          roughness={0.18}
          metalness={0.18}
          transparent
          opacity={0.78}
        />
      </mesh>
      <mesh position={[0, 1.1, -0.41]} castShadow>
        <boxGeometry args={[3.3, 2.28, 0.05]} />
        <meshStandardMaterial
          color="#e0f2fe"
          roughness={0.04}
          metalness={0.02}
          transparent
          opacity={0.38}
        />
      </mesh>
      <pointLight position={[0, 1.3, -0.8]} intensity={cyan ? 0.55 : 0.72} color={frozen ? "#60a5fa" : cyan ? "#22d3ee" : "#fb7185"} distance={5} />
      <GlassBadge className={type} position={[0, 2.65, -0.6]}>
        {label}
      </GlassBadge>
    </group>
  );
}

function PalletStack({ position = [0, 0, 0] }) {
  return (
    <group position={position}>
      {Array.from({ length: 9 }).map((_, i) => (
        <mesh key={i} position={[(i % 3) * 0.48, 0.18 + Math.floor(i / 3) * 0.34, Math.floor(i / 3) * 0.04]} castShadow>
          <boxGeometry args={[0.42, 0.30, 0.42]} />
          <meshStandardMaterial color="#e5e7eb" roughness={0.68} metalness={0.02} />
        </mesh>
      ))}
    </group>
  );
}

function Transpallet({ position = [0, 0, 0] }) {
  return (
    <group position={position} rotation={[0, -0.3, 0]}>
      <mesh position={[0, 0.08, 0]} castShadow>
        <boxGeometry args={[1.15, 0.12, 0.22]} />
        <meshStandardMaterial color="#f59e0b" roughness={0.45} metalness={0.12} />
      </mesh>
      <mesh position={[0.58, 0.22, 0]} castShadow>
        <boxGeometry args={[0.22, 0.34, 0.34]} />
        <meshStandardMaterial color="#ea580c" roughness={0.5} />
      </mesh>
      <mesh position={[0.70, 0.65, 0]} rotation={[0, 0, -0.55]} castShadow>
        <boxGeometry args={[0.05, 0.9, 0.05]} />
        <meshStandardMaterial color="#cbd5e1" metalness={0.6} roughness={0.3} />
      </mesh>
    </group>
  );
}

function ZoneBeam({ zone, position, size }) {
  const color = zone === "frozen" ? "#8b5cf6" : zone === "chilled" ? "#22d3ee" : zone === "refill" ? "#eab308" : "#ef4444";
  return (
    <mesh position={position} rotation={[-Math.PI / 2, 0, 0]}>
      <planeGeometry args={size} />
      <meshBasicMaterial color={color} transparent opacity={0.055} />
    </mesh>
  );
}

function PulsingHotspot({ position, type = "congestion", label = "CONGESTION" }) {
  const ref = useRef();
  useFrame(({ clock }) => {
    if (!ref.current) return;
    const s = 1 + Math.sin(clock.elapsedTime * 4) * 0.18;
    ref.current.scale.set(s, s, s);
  });
  const color = type === "refill" ? "#eab308" : type === "cold" ? "#22d3ee" : "#ef4444";
  return (
    <group position={position}>
      <mesh ref={ref} rotation={[-Math.PI / 2, 0, 0]}>
        <ringGeometry args={[0.35, 0.55, 48]} />
        <meshBasicMaterial color={color} transparent opacity={0.86} />
      </mesh>
      <GlassBadge className={type} position={[0, 0.75, 0]}>
        {label}
      </GlassBadge>
    </group>
  );
}

function AnimatedRoute({ routeMode }) {
  const ref = useRef();
  const points = useMemo(
    () => [
      [-11, 0.08, 8],
      [-7, 0.08, 3],
      [-2, 0.08, 4],
      [2, 0.08, -1],
      [6, 0.08, -2],
      [9, 0.08, 5],
      [12, 0.08, 2],
    ],
    []
  );

  useFrame(({ clock }) => {
    if (ref.current) ref.current.material.dashOffset = -clock.elapsedTime * 0.55;
  });

  return (
    <Line
      ref={ref}
      points={points}
      color={routeMode === "ai" ? "#67e8f9" : "#ff62ad"}
      lineWidth={3}
      dashed
      dashSize={0.8}
      gapSize={0.42}
    />
  );
}

function AisleIsland({ aisle, index, selectedAisle, onShelfOpen, onModuleSelect }) {
  const modules = Array.isArray(aisle?.modules) ? aisle.modules : [];
  const [x, y, z, rot] = aislePosition(aisle, index);
  const zone = zoneOf(aisle);

  if (selectedAisle !== "ALL" && String(selectedAisle) !== String(aisle.aisle_id)) return null;

  const custom = modules.some((m) => m?.layout_position);
  const width = Math.max(1, Math.min(modules.length || 1, 14)) * 2.72;
  const centerOffset = custom ? 0 : -width / 2 + 1.36;

  return (
    <group position={[x, y, z]} rotation={[0, rot, 0]}>
      <GlassBadge className={zone} position={[0, 3.35, -0.95]}>
        {aisle.aisle_id}
      </GlassBadge>
      <group position={[centerOffset, 0, 0]}>
        {modules.slice(0, 90).map((m, i) => (
          <MetalRack key={m.module_id || i} aisle={aisle} module={m} moduleIndex={i} onShelfOpen={onShelfOpen} onModuleSelect={onModuleSelect} />
        ))}
      </group>
      <ZoneBeam zone={zone} position={[0, 0.012, 0]} size={[width + 1.8, 2.1]} />
    </group>
  );
}

function LayoutObject3D({ obj }) {
  const type = obj?.type || "object";
  const x = n(obj.x, 0) * 1.4 - 10;
  const z = n(obj.y, 0) * 1.25 - 6;
  const w = Math.max(0.4, n(obj.w, 2));
  const d = Math.max(0.25, n(obj.h, 1));
  const rot = (n(obj.rotation, 0) * Math.PI) / 180;

  const isWall = type === "wall";
  const isColumn = type.includes("column");
  const isDispatch = type.includes("dispatch");

  const height = isWall ? 1.2 : isColumn ? 2.4 : isDispatch ? 0.85 : 0.7;
  const color = isWall ? "#dbe2ea" : isColumn ? "#b8c2ce" : isDispatch ? "#dffbea" : "#cbd5e1";

  return (
    <group position={[x, height / 2, z]} rotation={[0, rot, 0]}>
      <mesh castShadow receiveShadow>
        <boxGeometry args={[w, height, d]} />
        <meshStandardMaterial color={color} roughness={0.45} metalness={isColumn ? 0.45 : 0.1} />
      </mesh>
      <GlassBadge className="object" position={[0, height / 2 + 0.3, 0]}>
        {obj.label || type}
      </GlassBadge>
    </group>
  );
}

function targetForPreset(preset) {
  if (preset === "chilled") return { pos: [-11, 8, 9], look: [-8, 0.8, -5] };
  if (preset === "frozen") return { pos: [15, 8, -5], look: [10, 1, -5] };
  if (preset === "dispatch") return { pos: [15, 7, 9], look: [10, 0.7, 5] };
  if (preset === "top") return { pos: [0, 28, 0.001], look: [0, 0, 0] };
  if (preset === "sku") return { pos: [-4, 6, 7], look: [-2.6, 1, 1.2] };
  return { pos: [0, 18, 22], look: [0, 0.7, 1.5] };
}

function CameraController({ preset }) {
  const { camera } = useThree();
  const desired = useMemo(() => new THREE.Vector3(), []);
  const look = useMemo(() => new THREE.Vector3(), []);
  useFrame(() => {
    const t = targetForPreset(preset);
    desired.set(...t.pos);
    look.set(...t.look);
    camera.position.lerp(desired, 0.085);
    camera.lookAt(look);
  });
  return null;
}

function Scene({ plan, selectedAisle, onShelfOpen, onModuleSelect, cameraPreset, routeMode }) {
  const aisles = getAisles(plan);
  const objects = Array.isArray(plan?.layout_objects) ? plan.layout_objects : [];

  const camPos =
    cameraPreset === "chilled" ? [-10, 10, 10] :
    cameraPreset === "frozen" ? [13, 9, -5] :
    cameraPreset === "dispatch" ? [16, 7, 9] :
    [0, 22, 26];

  return (
    <>
      <PerspectiveCamera makeDefault position={targetForPreset(cameraPreset).pos} fov={36} />\n      <CameraController preset={cameraPreset} />
      <color attach="background" args={["#f8fbfc"]} />
      <fog attach="fog" args={["#f8fbfc", 34, 92]} />

      <ambientLight intensity={1.05} />
      <hemisphereLight intensity={0.88} groundColor="#dce7ea" />
      <directionalLight position={[15, 22, 10]} intensity={1.18} castShadow shadow-mapSize-width={2048} shadow-mapSize-height={2048} />
      <pointLight position={[-8, 4, 8]} color="#ff2d87" intensity={0.36} distance={18} />
      <pointLight position={[8, 4, -4]} color="#18c7df" intensity={0.38} distance={20} />

      <mesh rotation={[-Math.PI / 2, 0, 0]} position={[0, -0.035, 0]} receiveShadow>
        <planeGeometry args={[70, 70]} />
        <meshStandardMaterial color="#f4f8fa" roughness={0.18} metalness={0.32} />
      </mesh>

      <gridHelper args={[70, 70, "#c8d6de", "#e7eef2"]} position={[0, 0.006, 0]} />

      <mesh rotation={[-Math.PI / 2, 0, 0]} position={[0, 0.009, 0]}>
        <planeGeometry args={[30, 18]} />
        <meshBasicMaterial color="#ff0f7b" transparent opacity={0.032} />
      </mesh>

      <ZoneBeam zone="chilled" position={[-7, 0.018, 0]} size={[3.2, 16]} />
      <ZoneBeam zone="frozen" position={[10, 0.02, -1]} size={[5, 14]} />
      <ZoneBeam zone="refill" position={[0, 0.021, 6]} size={[12, 2]} />

      {objects.map((obj) => <LayoutObject3D key={obj.id || obj.label} obj={obj} />)}

      {aisles.map((aisle, i) => (
        <AisleIsland
          key={aisle.aisle_id || i}
          aisle={aisle}
          index={i}
          selectedAisle={selectedAisle}
          onShelfOpen={onShelfOpen}
          onModuleSelect={onModuleSelect}
        />
      ))}

      <CoolerBank type="chilled" label="+4 CHILLED" position={[-9, 0, -7]} />
      <CoolerBank type="frozen" label="-18 FROZEN" position={[10, 0, -7]} />
      <CoolerBank type="ice" label="ALGIDA" position={[13, 0, 2]} />

      <PalletStack position={[-9, 0, 8]} />
      <PalletStack position={[0, 0, 9]} />
      <Transpallet position={[-5, 0.02, 9.3]} />

      <AnimatedRoute routeMode={routeMode} />
      <PulsingHotspot position={[4, 0.08, 3.2]} type="congestion" label="CONGESTION" />
      <PulsingHotspot position={[0, 0.08, -1.8]} type="refill" label="REFILL RISK" />
      <PulsingHotspot position={[-8.8, 0.08, -4.2]} type="cold" label="+4 ZONE" />

      <GlassBadge className="dispatch" position={[13, 1.4, 7.2]}>
        DISPATCH
      </GlassBadge>

      <OrbitControls
        makeDefault
        target={[0, 0.7, 1.5]}
        enableDamping
        dampingFactor={0.08}
        rotateSpeed={0.34}
        zoomSpeed={0.48}
        panSpeed={0.46}
        minDistance={11}
        maxDistance={48}
        minPolarAngle={0.45}
        maxPolarAngle={1.18}
      />
    </>
  );
}

function MiniMap({ selectedAisle, setSelectedAisle, aisles }) {
  return (
    <div className="ops-minimap">
      <div className="ops-panel-title">MINIMAP</div>
      <div className="ops-map-grid">
        {aisles.slice(0, 20).map((a) => (
          <button
            key={a.aisle_id}
            className={String(selectedAisle) === String(a.aisle_id) ? "active" : ""}
            onClick={() => setSelectedAisle(a.aisle_id)}
          >
            {a.aisle_id}
          </button>
        ))}
      </div>
      <button className="ops-mini-action" onClick={() => setSelectedAisle("ALL")}>Overview</button>
    </div>
  );
}

function AiInsights() {
  return (
    <div className="ops-ai-insights">
      <div className="ops-panel-title">AI INSIGHTS</div>
      <div className="ops-alert red"><b>Congestion detected</b><span>Corridor D · high traffic</span></div>
      <div className="ops-alert yellow"><b>Refill risk</b><span>Corridor F · 12 SKUs</span></div>
      <div className="ops-alert cyan"><b>Temperature transition</b><span>Chilled → Ambient stable</span></div>
      <div className="ops-alert green"><b>Efficiency opportunity</b><span>Optimize slotting · +8%</span></div>
    </div>
  );
}

function SearchSkuPanel({ onFly }) {
  const [q, setQ] = useState("Eti Burçak");
  return (
    <div className="ops-search-panel">
      <div className="ops-panel-title">SEARCH SKU</div>
      <input value={q} onChange={(e) => setQ(e.target.value)} placeholder="SKU / ürün ara" />
      <div className="ops-search-result">
        <div className="thumb" />
        <div><b>{q || "Eti Burçak"}</b><span>Corridor: E · Module: E-04 · Shelf: 3</span></div>
      </div>
      <button onClick={() => onFly("sku")}>Fly to Location</button>
    </div>
  );
}

function BootConsole() {
  return (
    <div className="ops-boot-console">
      <div className="ops-panel-title">EA INTELLIGENCE CONSOLE</div>
      {["Booting Digital Twin", "Loading Layout", "Connecting Systems", "Analyzing Traffic", "Optimizing Routes", "EA Intelligence Core"].map((x, i) => (
        <div key={x} className="boot-step">
          <i className={i === 5 ? "online" : ""}>{i === 5 ? "✓" : "●"}</i>
          <span>{x}</span>
          <b>{i === 5 ? "ONLINE" : "100%"}</b>
        </div>
      ))}
    </div>
  );
}

export default function Depot3D({
  plan,
  onShelfOpen,
  onAddModule,
  onAddShelf,
  onModuleSize,
  onPrintModule,
  onLayoutChange,
  onAddAisle,
  onDeleteAisle,
  onDeleteModule,
  lang = "tr",
}) {
  const [selectedAisle, setSelectedAisle] = useState("ALL");
  const [selectedModule, setSelectedModule] = useState(null);
  const [layoutOpen, setLayoutOpen] = useState(false);
  const [cameraPreset, setCameraPreset] = useState("overview");
  const [routeMode, setRouteMode] = useState("ai");

  const aisles = getAisles(plan);

  const stats = useMemo(() => {
    const modules = aisles.reduce((s, a) => s + (a.modules?.length || 0), 0);
    const shelves = aisles.reduce((s, a) => s + (a.modules || []).reduce((m, x) => m + (x.shelves?.length || 0), 0), 0);
    return { aisles: aisles.length, modules, shelves };
  }, [aisles]);

  function saveLayout(payload) {
    const positions = payload.aisles.map((a) => ({
      aisle_id: a.aisle_id,
      grid_x: a.grid_x,
      grid_y: a.grid_y,
      rotation: a.rotation,
      module_count: a.module_count,
      module_orientations: (a.module_layouts || []).map((m) => m.orientation || "vertical"),
      module_layouts: a.module_layouts || [],
      walkway_m: a.walkway_m,
    }));
    onLayoutChange?.(positions, payload.objects);
  }

  const selectedAisleObj = aisles.find((a) => String(a.aisle_id) === String(selectedModule?.aisleId));
  const selectedModuleObj = selectedAisleObj?.modules?.find((m) => String(m.module_id) === String(selectedModule?.moduleId));

  return (
    <section className="ops-twin-shell">
      <aside className="ops-left-rail">
        <div className="ops-logo-mini">P</div>
        {["3D Studio", "2D Plan", "Heatmap", "Operations", "Products", "Tasks", "Alerts", "Reports"].map((x, i) => (
          <button key={x} className={i === 0 ? "active" : ""}>{x}</button>
        ))}
        <div className="ops-zone-card">
          <b>ZONE STATUS</b>
          <span>Ambient <em>82%</em></span>
          <span>Chilled <em>74%</em></span>
          <span>Frozen <em>68%</em></span>
          <span>Dispatch <em>92%</em></span>
        </div>
      </aside>

      <main className="ops-main-stage">
        <header className="ops-command-header">
          <div>
            <div className="ops-kicker">EA INTELLIGENCE CORE · ONLINE</div>
            <h2>DEPO / MARKET-44</h2>
            <p>3.250 m² · {stats.aisles} Corridor · {stats.modules} Module · {stats.shelves} Shelf</p>
          </div>

          <div className="ops-zone-tabs">
            <button>AMBIENT +22°C</button>
            <button>CHILLED +4°C</button>
            <button>FROZEN -18°C</button>
          </div>

          <div className="ops-top-actions">
            <select value={selectedAisle} onChange={(e) => setSelectedAisle(e.target.value)}>
              <option value="ALL">All corridors</option>
              {aisles.map((a) => <option key={a.aisle_id} value={a.aisle_id}>{a.aisle_id}</option>)}
            </select>
            <button onClick={() => setLayoutOpen(true)}>Architect Mode</button>
            <button onClick={() => onAddAisle?.()}>+ Corridor</button>
          </div>
        </header>

        <div className="ops-canvas-wrap">
          <Canvas shadows dpr={[1, 1.8]} gl={{ antialias: true }}>
            <Suspense fallback={null}>
              <Scene
                key={`${cameraPreset}-${selectedAisle}`}
                plan={plan}
                selectedAisle={selectedAisle}
                onShelfOpen={onShelfOpen}
                onModuleSelect={setSelectedModule}
                cameraPreset={cameraPreset}
                routeMode={routeMode}
              />
            </Suspense>
          </Canvas>

          <div className="ops-floating-toolbar">
            {["Orbit", "Fly", "Top", "Focus", "Follow", "Measure", "Label", "Path"].map((x) => (
              <button key={x} onClick={() => { setActiveTool?.(x.toLowerCase?.() || x); if(x==="Top") setCameraPreset("top"); if(x==="Focus") setCameraPreset("sku"); if(x==="Fly") setCameraPreset("dispatch"); if(x==="Path") setRouteMode(routeMode === "ai" ? "pick" : "ai"); }}>{x}</button>
            ))}
          </div>

          <div className="ops-quick-jump">
            <span>QUICK JUMP CORRIDOR</span>
            {aisles.slice(0, 12).map((a) => (
              <button key={a.aisle_id} onClick={() => setSelectedAisle(a.aisle_id)}>{a.aisle_id}</button>
            ))}
          </div>

          {selectedModule && (
            <div className="ops-module-popover">
              <b>{selectedModule.aisleId} / Module {selectedModule.moduleId}</b>
              <button onClick={() => onAddShelf?.(selectedModule.aisleId, selectedModule.moduleId)}>+ Shelf</button>
              <button onClick={() => onAddModule?.(selectedModule.aisleId)}>+ Module</button>
              <button onClick={() => onModuleSize?.(selectedModule.aisleId, selectedModule.moduleId)}>Dimensions</button>
              <button onClick={() => selectedAisleObj && selectedModuleObj && onPrintModule?.(selectedAisleObj, selectedModuleObj)}>Print</button>
              <button className="danger" onClick={() => onDeleteModule?.(selectedModule.aisleId, selectedModule.moduleId)}>Delete module</button>
              <button onClick={() => setSelectedModule(null)}>Close</button>
            </div>
          )}
        </div>

        <BootConsole />
      </main>

      <aside className="ops-right-hud">
        <MiniMap selectedAisle={selectedAisle} setSelectedAisle={setSelectedAisle} aisles={aisles} />
        <AiInsights />
        <SearchSkuPanel onFly={() => { setSelectedAisle("E"); setCameraPreset("overview"); }} />
        <div className="ops-camera-panel">
          <div className="ops-panel-title">CAMERA PRESETS</div>
          <button onClick={() => setCameraPreset("overview")}>Overview</button>
          <button onClick={() => setCameraPreset("chilled")}>Chilled Zone</button>
          <button onClick={() => setCameraPreset("frozen")}>Frozen Zone</button>
          <button onClick={() => setCameraPreset("dispatch")}>Dispatch Area</button>
        </div>
      </aside>

      <LayoutEditor open={layoutOpen} plan={plan} onClose={() => setLayoutOpen(false)} onSave={saveLayout} lang={lang} />
    </section>
  );
}
