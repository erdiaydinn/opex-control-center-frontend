
import React, { Suspense, useMemo, useRef, useState } from "react";
import { Canvas, useFrame, useThree } from "@react-three/fiber";
import { Html, OrbitControls, Line, ContactShadows, Environment } from "@react-three/drei";
import * as THREE from "three";

const cameraPresets = {
  overview: { pos: [34, 26, 34], target: [0, 0, 0] },
  top: { pos: [0, 54, 0.001], target: [0, 0, 0] },
  chilled: { pos: [34, 18, -14], target: [20, 0, -8] },
  frozen: { pos: [34, 18, 12], target: [20, 0, 8] },
  dispatch: { pos: [42, 16, 24], target: [26, 0, 16] },
};

function normalizeStorage(value = "AMBIENT") {
  const v = String(value).toUpperCase();
  if (v.includes("CHILL") || v.includes("+4") || v.includes("COLD")) return "CHILLED";
  if (v.includes("FROZEN") || v.includes("-18") || v.includes("DONUK")) return "FROZEN";
  return "AMBIENT";
}

function CameraRig({ preset = "overview", focus }) {
  const controls = useRef();
  const { camera } = useThree();
  useFrame(() => {
    const cfg = focus ? { pos: [focus.x + 8, 8, focus.z + 9], target: [focus.x, 1.2, focus.z] } : cameraPresets[preset] || cameraPresets.overview;
    const desired = new THREE.Vector3(...cfg.pos);
    camera.position.lerp(desired, 0.055);
    if (controls.current) {
      const t = new THREE.Vector3(...cfg.target);
      controls.current.target.lerp(t, 0.08);
      controls.current.update();
    }
  });
  return <OrbitControls ref={controls} makeDefault enableDamping dampingFactor={0.08} minDistance={7} maxDistance={90} maxPolarAngle={Math.PI / 2.12} />;
}

function WarehouseFloor({ width = 68, depth = 44 }) {
  return (
    <group>
      <mesh rotation={[-Math.PI / 2, 0, 0]} receiveShadow>
        <planeGeometry args={[width, depth]} />
        <meshStandardMaterial color="#f7f8fa" roughness={0.52} metalness={0.04} />
      </mesh>
      <gridHelper args={[width, 34, "#d8dde5", "#eef1f5"]} position={[0, 0.012, 0]} />
    </group>
  );
}

function ZoneVolume({ zone }) {
  const color = zone.type === "chilled" ? "#19c8df" : zone.type === "frozen" ? "#7c5cff" : zone.type === "dispatch" ? "#27d889" : zone.type === "receiving" ? "#ffb547" : "#df1067";
  return (
    <group position={[zone.x, 0.03, zone.z]}>
      <mesh receiveShadow>
        <boxGeometry args={[zone.w, 0.08, zone.d]} />
        <meshStandardMaterial color={color} transparent opacity={0.18} roughness={0.45} />
      </mesh>
      <mesh position={[0, 1.05, 0]}>
        <boxGeometry args={[zone.w, 2.1, zone.d]} />
        <meshStandardMaterial color={color} transparent opacity={0.06} roughness={0.3} />
      </mesh>
      <Html center position={[0, 2.55, 0]} className="r3f-label zone-label"><b>{zone.label}</b></Html>
    </group>
  );
}

function ProductBlock({ p, idx, onPick }) {
  const storage = normalizeStorage(p.storage_type);
  const color = storage === "CHILLED" ? "#18c7df" : storage === "FROZEN" ? "#7b61ff" : idx % 3 === 0 ? "#df1067" : idx % 3 === 1 ? "#ffd86b" : "#f2f4f7";
  const x = -0.48 + (idx % 3) * 0.48;
  const y = 0.44 + Math.floor((idx % 6) / 3) * 0.52;
  const z = idx < 6 ? -0.19 : 0.21;
  return (
    <mesh castShadow position={[x, y, z]} onClick={(e) => { e.stopPropagation(); onPick?.(p); }}>
      <boxGeometry args={[0.30, 0.42, 0.26]} />
      <meshStandardMaterial color={color} roughness={0.44} metalness={0.02} />
    </mesh>
  );
}

function RackMesh({ aisle, products = [], onPick, onAisle }) {
  const storage = normalizeStorage(aisle.storage);
  const tint = storage === "CHILLED" ? "#c7f7ff" : storage === "FROZEN" ? "#e2dbff" : "#ffffff";
  return (
    <group position={[aisle.x, 0, aisle.z]} rotation={[0, aisle.rotation || 0, 0]} onClick={(e) => { e.stopPropagation(); onAisle?.(aisle); }}>
      <mesh castShadow receiveShadow position={[0, 0.35, 0]}>
        <boxGeometry args={[aisle.width, 0.16, aisle.depth]} />
        <meshStandardMaterial color="#dfe5ec" roughness={0.34} metalness={0.12} />
      </mesh>
      {[-aisle.width / 2 + 0.45, aisle.width / 2 - 0.45].map((x) => (
        <mesh key={x} castShadow position={[x, 1.15, -aisle.depth / 2 + 0.15]}>
          <boxGeometry args={[0.08, 2.4, 0.08]} />
          <meshStandardMaterial color="#5b6470" roughness={0.35} metalness={0.65} />
        </mesh>
      ))}
      {Array.from({ length: 4 }, (_, i) => 0.45 + i * 0.5).map((y) => (
        <mesh key={y} castShadow receiveShadow position={[0, y, 0]}>
          <boxGeometry args={[aisle.width - 0.36, 0.055, aisle.depth - 0.30]} />
          <meshStandardMaterial color={tint} roughness={0.28} metalness={0.25} transparent opacity={0.82} />
        </mesh>
      ))}
      {products.slice(0, 18).map((p, idx) => (
        <group key={`${p.sku}-${idx}`} position={[-aisle.width / 2 + 1.0 + (idx % 9) * 1.18, 0, idx > 8 ? 0.72 : -0.72]}>
          <ProductBlock p={p} idx={idx} onPick={onPick} />
        </group>
      ))}
      <Html center position={[0, 2.9, 0]} className="r3f-label aisle-label"><b>{aisle.aisle_id}</b></Html>
    </group>
  );
}

function RoutePath() {
  const points = [[-31, .08, 17], [-21, .08, 10], [-8, .08, 11], [3, .08, 3], [12, .08, 5], [24, .08, 17], [31, .08, 17]];
  return <Line points={points} color="#df1067" lineWidth={4} dashed dashScale={0.8} dashSize={1.2} gapSize={0.6} />;
}

function RefillPulse() {
  const ref = useRef();
  useFrame(({ clock }) => {
    if (ref.current) {
      ref.current.scale.setScalar(1 + Math.sin(clock.elapsedTime * 2.3) * 0.05);
    }
  });
  return <group ref={ref} position={[0, 2.6, 2]}><Html center className="r3f-alert refill">REFILL RISK</Html></group>;
}

function CongestionPulse() {
  const ref = useRef();
  useFrame(({ clock }) => {
    if (ref.current) ref.current.material.opacity = 0.12 + Math.abs(Math.sin(clock.elapsedTime * 2.1)) * 0.22;
  });
  return <mesh ref={ref} position={[5, .07, 6]} rotation={[-Math.PI / 2, 0, 0]}><circleGeometry args={[3.4, 64]} /><meshBasicMaterial color="#ef4444" transparent opacity={0.22} /></mesh>;
}

function Scene({ plan, products, preset, focus, onPick, onAisle }) {
  const byAisle = useMemo(() => {
    const map = new Map();
    products.forEach((p, i) => {
      const aisle = plan.aisles[i % plan.aisles.length]?.aisle_id || "A";
      if (!map.has(aisle)) map.set(aisle, []);
      map.get(aisle).push(p);
    });
    return map;
  }, [products, plan.aisles]);

  return (
    <>
      <ambientLight intensity={1.5} />
      <directionalLight castShadow position={[18, 22, 12]} intensity={1.35} shadow-mapSize-width={2048} shadow-mapSize-height={2048} />
      <WarehouseFloor />
      {plan.zones.map((z) => <ZoneVolume key={z.id} zone={z} />)}
      {plan.aisles.map((a) => <RackMesh key={a.aisle_id} aisle={a} products={byAisle.get(a.aisle_id) || []} onPick={onPick} onAisle={onAisle} />)}
      <RoutePath />
      <RefillPulse />
      <CongestionPulse />
      <ContactShadows opacity={0.28} scale={56} blur={2.8} far={11} position={[0, 0.02, 0]} />
      <Environment preset="city" />
      <CameraRig preset={preset} focus={focus} />
    </>
  );
}

export default function LiveDigitalTwin({ plan, products, compact = false }) {
  const [preset, setPreset] = useState("overview");
  const [selected, setSelected] = useState(null);
  const [query, setQuery] = useState("Eti");

  const focus = useMemo(() => {
    if (!selected) return null;
    const idx = products.findIndex((p) => p.sku === selected.sku);
    const aisle = plan.aisles[Math.max(0, idx) % plan.aisles.length];
    return aisle ? { x: aisle.x, z: aisle.z } : null;
  }, [selected, products, plan.aisles]);

  const hit = products.find((p) => `${p.product_name} ${p.sku} ${p.brand}`.toLowerCase().includes(query.toLowerCase())) || products[0];

  return (
    <div className={compact ? "digitalTwin compact" : "digitalTwin"}>
      <div className="sceneWrap">
        <Canvas shadows dpr={[1, 1.75]} camera={{ position: [34, 24, 34], fov: 40 }}>
          <Suspense fallback={null}>
            <Scene plan={plan} products={products} preset={preset} focus={focus} onPick={setSelected} onAisle={(a) => setSelected({ sku: `AISLE-${a.aisle_id}`, product_name: `Koridor ${a.aisle_id}`, brand: a.storage, storage_type: a.storage })} />
          </Suspense>
        </Canvas>
        <div className="cameraDock">
          {[
            ["overview", "Overview"], ["top", "Top"], ["chilled", "Chilled"], ["frozen", "Frozen"], ["dispatch", "Dispatch"]
          ].map(([key, label]) => <button key={key} className={preset === key ? "on" : ""} onClick={() => setPreset(key)}>{label}</button>)}
        </div>
      </div>
      {!compact && (
        <aside className="studioRight">
          <div className="panelBox"><h3>Camera Presets</h3><div className="presetGrid">{["overview", "top", "chilled", "frozen", "dispatch"].map((p) => <button key={p} onClick={() => setPreset(p)}>{p}</button>)}</div></div>
          <div className="panelBox"><h3>Search SKU</h3><div className="searchRow"><input value={query} onChange={(e) => setQuery(e.target.value)} /><button onClick={() => setSelected(hit)}>Bul</button></div>{hit && <div className="skuHit"><b>{hit.image || "□"}</b><span>{hit.product_name}<small>{hit.sku} · {hit.brand}</small></span></div>}<button className="primary full" onClick={() => setSelected(hit)}>Fly to Location</button></div>
          <div className="panelBox"><h3>Selected</h3>{selected ? <><b>{selected.product_name}</b><p>{selected.sku}</p><small>{selected.brand} · {selected.storage_type}</small></> : <p>Raf veya SKU seç.</p>}</div>
          <div className="panelBox ai"><h3>AI Insights</h3><p><b>Refill opportunity</b><small>High velocity SKU'larda facing/depth kontrolü.</small></p><p><b>Congestion alert</b><small>Koridor D pik saatlerde yoğun.</small></p><p><b>Cold chain</b><small>+4 ve -18 zone ayrımı stabil.</small></p></div>
        </aside>
      )}
    </div>
  );
}
