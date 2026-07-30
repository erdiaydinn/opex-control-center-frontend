import { useEffect, useMemo, useRef, useState } from 'react';
import { Canvas, useFrame, useThree } from '@react-three/fiber';
import { OrbitControls, PerspectiveCamera, Text, Line, Html } from '@react-three/drei';
import { EffectComposer, Bloom } from '@react-three/postprocessing';
import * as THREE from 'three';
import { buildTwinModel, cameraPresetTarget, zoneColor } from './twinDataAdapter.js';
import './TwinStudio3D.css';

function RackMesh({ fixture, heatmap, selected, onSelect }) {
  const ref = useRef();
  const [hovered, setHovered] = useState(false);
  const { world, color, utilization } = fixture;
  const modules = Math.max(1, Number(fixture.modules || 1));
  const moduleWidth = Math.max(1.3, world.w / modules);
  const heat = heatmap === 'refill' ? Math.min(1, Number(fixture.changed || 0) / 22) : heatmap === 'cold' ? (fixture.zone === 'CHILLED' || fixture.zone === 'FROZEN' ? 1 : .12) : heatmap === 'traffic' ? Math.min(1, utilization / 100) : Math.min(1, utilization / 100);
  const activeColor = heatmap === 'refill' ? '#f5b900' : heatmap === 'traffic' ? '#e84a4a' : color;

  useFrame((state) => {
    if (!ref.current) return;
    const pulse = hovered || selected ? 1 + Math.sin(state.clock.elapsedTime * 4) * 0.02 : 1;
    ref.current.scale.setScalar(pulse);
  });

  return (
    <group ref={ref} position={[world.x, world.y, world.z]} rotation={[0, world.rotation, 0]}>
      {Array.from({ length: modules }).map((_, i) => {
        const x = -world.w / 2 + moduleWidth / 2 + i * moduleWidth;
        return (
          <group key={i} position={[x, 0, 0]}>
            <mesh castShadow receiveShadow onClick={(e) => { e.stopPropagation(); onSelect?.(fixture, { module: i + 1, shelf: 1 }); }} onPointerOver={(e) => { e.stopPropagation(); setHovered(true); document.body.style.cursor = 'pointer'; }} onPointerOut={() => { setHovered(false); document.body.style.cursor = 'default'; }}>
              <boxGeometry args={[moduleWidth * .78, world.h, world.d * .62]} />
              <meshStandardMaterial color={hovered || selected ? activeColor : '#ffffff'} transparent opacity={0.38 + heat * .42} roughness={0.36} metalness={0.16} emissive={activeColor} emissiveIntensity={(hovered || selected ? .24 : .08) + heat * .1} />
            </mesh>
            {[.22, .42, .62, .82].map((r) => (
              <mesh key={r} position={[0, world.h * (r - .5), 0]} castShadow>
                <boxGeometry args={[moduleWidth * .86, .08, world.d * .7]} />
                <meshStandardMaterial color="#9aa6b8" metalness={0.55} roughness={0.2} />
              </mesh>
            ))}
            <mesh position={[0, -world.h / 2 + .22, 0]}>
              <boxGeometry args={[moduleWidth * .88, .12, world.d * .72]} />
              <meshStandardMaterial color="#d7dde8" metalness={0.4} roughness={0.25} />
            </mesh>
          </group>
        );
      })}
      {(hovered || selected) && (
        <mesh>
          <boxGeometry args={[world.w + .35, world.h + .3, world.d + .35]} />
          <meshBasicMaterial color={activeColor} wireframe transparent opacity={0.75} />
        </mesh>
      )}
      <Text position={[0, world.h / 2 + 1.6, 0]} rotation={[-0.45, 0, 0]} fontSize={1.5} color={selected ? '#df1067' : '#10131a'} anchorX="center" anchorY="middle" outlineWidth={0.035} outlineColor="#ffffff">
        {fixture.label}
      </Text>
      <Html position={[0, world.h / 2 + 3.4, 0]} center distanceFactor={80} style={{ pointerEvents: 'none' }}>
        <div className={`twin-util-pill ${selected ? 'is-selected' : ''}`}>{utilization}% dolu · {fixture.changed} değişim</div>
      </Html>
    </group>
  );
}

function RoomMesh({ fixture, selected, onSelect }) {
  const [hovered, setHovered] = useState(false);
  const { world, color } = fixture;
  const height = fixture.type === 'dispatch' ? Math.min(world.h, 2.8) : world.h;
  return (
    <group position={[world.x, height / 2, world.z]} rotation={[0, world.rotation, 0]}>
      <mesh receiveShadow castShadow onClick={(e) => { e.stopPropagation(); onSelect?.(fixture); }} onPointerOver={(e) => { e.stopPropagation(); setHovered(true); document.body.style.cursor = 'pointer'; }} onPointerOut={() => { setHovered(false); document.body.style.cursor = 'default'; }}>
        <boxGeometry args={[world.w, height, world.d]} />
        <meshStandardMaterial color={color} transparent opacity={hovered || selected ? 0.23 : 0.11} roughness={0.55} metalness={0.05} emissive={color} emissiveIntensity={hovered || selected ? .13 : .04} />
      </mesh>
      <mesh>
        <boxGeometry args={[world.w + .15, height + .15, world.d + .15]} />
        <meshBasicMaterial color={color} wireframe transparent opacity={selected ? .95 : .42} />
      </mesh>
      <Text position={[0, height / 2 + 1.5, 0]} rotation={[-0.52, 0, 0]} fontSize={fixture.type === 'dispatch' ? 1.15 : 1.35} color={color} anchorX="center" anchorY="middle" outlineWidth={0.04} outlineColor="#ffffff">
        {fixture.label}
      </Text>
    </group>
  );
}

function ColumnMesh({ fixture }) {
  const { world } = fixture;
  return (
    <group position={[world.x, world.h / 2, world.z]}>
      <mesh castShadow receiveShadow>
        <cylinderGeometry args={[0.42, 0.42, world.h, 12]} />
        <meshStandardMaterial color="#4b5565" metalness={0.45} roughness={0.3} />
      </mesh>
    </group>
  );
}

function ProductMarker({ product, selected, onSelect }) {
  const ref = useRef();
  useFrame((state) => {
    if (ref.current && selected) ref.current.position.y = product.world[1] + Math.sin(state.clock.elapsedTime * 4) * .18;
  });
  return (
    <group ref={ref} position={product.world} onClick={(e) => { e.stopPropagation(); onSelect?.(product); }}>
      <mesh castShadow>
        <boxGeometry args={[1.25, 1.25, 1.25]} />
        <meshStandardMaterial color={product.color} emissive={product.color} emissiveIntensity={selected ? .6 : .16} roughness={0.32} metalness={0.2} />
      </mesh>
      <Html center distanceFactor={68} style={{ pointerEvents: 'none' }}>
        <div className={`twin-product-label ${selected ? 'is-selected' : ''}`}>{product.image || '▣'} {product.name}</div>
      </Html>
    </group>
  );
}

function AnimatedPath({ points, color = '#df1067', visible = true }) {
  const [progress, setProgress] = useState(0);
  const curve = useMemo(() => new THREE.CatmullRomCurve3(points.map((p) => new THREE.Vector3(...p))), [points]);
  const basePoints = useMemo(() => curve.getPoints(100), [curve]);
  const animatedPoints = useMemo(() => {
    const pts = [];
    const count = 110;
    const start = Math.floor(progress * count);
    for (let i = 0; i < 34; i++) pts.push(curve.getPoint(((start + i) % count) / count));
    return pts;
  }, [curve, progress]);
  useFrame((state) => setProgress((state.clock.elapsedTime * .24) % 1));
  if (!visible) return null;
  return (
    <group>
      <Line points={basePoints} color={color} lineWidth={2} transparent opacity={0.26} />
      <Line points={animatedPoints} color={color} lineWidth={5} transparent opacity={0.86} />
      <Line points={animatedPoints} color={color} lineWidth={13} transparent opacity={0.16} />
    </group>
  );
}

function Vehicle({ points, color = '#df1067' }) {
  const ref = useRef();
  const curve = useMemo(() => new THREE.CatmullRomCurve3(points.map((p) => new THREE.Vector3(...p))), [points]);
  useFrame((state) => {
    const t = (state.clock.elapsedTime * .045) % 1;
    const pos = curve.getPoint(t);
    const next = curve.getPoint((t + .01) % 1);
    if (!ref.current) return;
    ref.current.position.copy(pos);
    ref.current.lookAt(next);
  });
  return (
    <group ref={ref}>
      <mesh position={[0, .75, 0]} castShadow>
        <boxGeometry args={[2.2, 1.1, 3.1]} />
        <meshStandardMaterial color={color} metalness={0.38} roughness={0.28} emissive={color} emissiveIntensity={0.08} />
      </mesh>
      <mesh position={[0, 1.65, -.45]} castShadow>
        <boxGeometry args={[1.7, 1.25, 1.35]} />
        <meshStandardMaterial color="#10131a" metalness={0.25} roughness={0.46} />
      </mesh>
      {[-.82, .82].map((x) => [-1.05, 1.05].map((z) => <mesh key={`${x}-${z}`} position={[x, .26, z]} rotation={[0, 0, Math.PI / 2]} castShadow><cylinderGeometry args={[.34, .34, .25, 16]} /><meshStandardMaterial color="#222936" /></mesh>))}
      <Text position={[0, 3.3, 0]} fontSize={.75} color="#10131a" anchorX="center" anchorY="middle" outlineWidth={0.04} outlineColor="#ffffff">AKTİF ROTA</Text>
    </group>
  );
}

function AlertMarker({ alert, visible }) {
  const ref = useRef();
  useFrame((state) => {
    if (!ref.current) return;
    const pulse = 1 + Math.sin(state.clock.elapsedTime * 3) * .14;
    ref.current.scale.set(pulse, pulse, pulse);
  });
  if (!visible) return null;
  return (
    <group position={alert.position}>
      <mesh ref={ref}>
        <cylinderGeometry args={[1.15, 1.15, .18, 6]} />
        <meshStandardMaterial color={alert.color} emissive={alert.color} emissiveIntensity={0.54} />
      </mesh>
      <mesh rotation={[-Math.PI / 2, 0, 0]}>
        <ringGeometry args={[1.35, 1.85, 42]} />
        <meshBasicMaterial color={alert.color} transparent opacity={0.25} />
      </mesh>
      <Html position={[0, 2.1, 0]} center distanceFactor={68}>
        <div className="twin-alert-card"><b>{alert.label}</b><span>{alert.sub}</span></div>
      </Html>
    </group>
  );
}

function CameraController({ preset, selectedFixture, selectedProduct, controlsRef, manualCamera }) {
  const { camera } = useThree();
  const focusActiveRef = useRef(true);
  const desired = useMemo(() => cameraPresetTarget(preset, selectedFixture, selectedProduct), [preset, selectedFixture, selectedProduct]);
  const desiredPosition = useMemo(() => new THREE.Vector3(...desired.position), [desired]);
  const desiredTarget = useMemo(() => new THREE.Vector3(...desired.target), [desired]);

  useEffect(() => {
    focusActiveRef.current = true;
  }, [desiredPosition, desiredTarget]);

  useFrame(() => {
    // Eski versiyonda kamera her frame preset noktasına geri çekiliyordu.
    // Bu yüzden mouse ile sürüklerken sahne "lastik gibi" geri dönüyordu.
    // Artık sadece preset / SKU / alan değişiminde kısa bir fly-to çalışır;
    // kullanıcı mouse ile müdahale edince otomatik takip durur.
    if (manualCamera || !focusActiveRef.current) return;

    camera.position.lerp(desiredPosition, 0.105);
    if (controlsRef.current) {
      controlsRef.current.target.lerp(desiredTarget, 0.115);
      controlsRef.current.update();
    }

    const positionDone = camera.position.distanceTo(desiredPosition) < 0.55;
    const targetDone = controlsRef.current ? controlsRef.current.target.distanceTo(desiredTarget) < 0.35 : true;
    if (positionDone && targetDone) focusActiveRef.current = false;
  });
  return null;
}

function KeyboardCameraController({ controlsRef }) {
  const { camera, gl } = useThree();

  useEffect(() => {
    const el = gl.domElement;
    el.tabIndex = 0;

    function moveCamera(event) {
      const tag = String(document.activeElement?.tagName || '').toLowerCase();
      if (['input', 'textarea', 'select'].includes(tag)) return;

      const key = event.key.toLowerCase();
      const valid = ['w', 'a', 's', 'd', 'arrowup', 'arrowdown', 'arrowleft', 'arrowright'].includes(key);
      if (!valid || !controlsRef.current) return;

      event.preventDefault();
      const step = event.shiftKey ? 8 : 3.2;
      const forward = new THREE.Vector3();
      camera.getWorldDirection(forward);
      forward.y = 0;
      forward.normalize();

      const right = new THREE.Vector3().crossVectors(forward, camera.up).normalize().multiplyScalar(-1);
      const delta = new THREE.Vector3();
      if (key === 'w' || key === 'arrowup') delta.add(forward.multiplyScalar(step));
      if (key === 's' || key === 'arrowdown') delta.add(forward.multiplyScalar(-step));
      if (key === 'a' || key === 'arrowleft') delta.add(right.multiplyScalar(-step));
      if (key === 'd' || key === 'arrowright') delta.add(right.multiplyScalar(step));

      camera.position.add(delta);
      controlsRef.current.target.add(delta);
      controlsRef.current.update();
    }

    window.addEventListener('keydown', moveCamera);
    return () => window.removeEventListener('keydown', moveCamera);
  }, [camera, controlsRef, gl]);

  return null;
}

function Scene({ model, cameraPreset, heatmap, layerState, selectedAreaId, selectedProductSku, onSelectArea, onSelectProduct }) {
  const controlsRef = useRef();
  const [manualCamera, setManualCamera] = useState(false);
  const selectedFixture = model.fixtures.find((f) => String(f.id) === String(selectedAreaId));
  const selectedProduct = model.productMarkers.find((p) => String(p.sku) === String(selectedProductSku));

  useEffect(() => {
    setManualCamera(false);
  }, [cameraPreset, selectedAreaId, selectedProductSku]);

  return (
    <>
      <PerspectiveCamera makeDefault position={[84, 70, 86]} fov={45} />
      <OrbitControls
        ref={controlsRef}
        enableDamping
        dampingFactor={0.075}
        enableRotate
        enableZoom
        enablePan
        rotateSpeed={0.95}
        zoomSpeed={1.65}
        panSpeed={1.45}
        keyPanSpeed={18}
        minDistance={16}
        maxDistance={260}
        minPolarAngle={0.18}
        maxPolarAngle={Math.PI / 2.03}
        screenSpacePanning
        target={[0, 0, 0]}
        mouseButtons={{
          LEFT: THREE.MOUSE.ROTATE,
          MIDDLE: THREE.MOUSE.DOLLY,
          RIGHT: THREE.MOUSE.PAN,
        }}
        touches={{
          ONE: THREE.TOUCH.ROTATE,
          TWO: THREE.TOUCH.DOLLY_PAN,
        }}
        onStart={() => setManualCamera(true)}
        makeDefault
      />
      <CameraController preset={cameraPreset} selectedFixture={selectedFixture} selectedProduct={selectedProduct} controlsRef={controlsRef} manualCamera={manualCamera} />
      <KeyboardCameraController controlsRef={controlsRef} />

      <ambientLight intensity={0.52} />
      <directionalLight position={[60, 92, 70]} intensity={0.96} castShadow shadow-mapSize={[2048, 2048]} shadow-camera-left={-100} shadow-camera-right={100} shadow-camera-top={100} shadow-camera-bottom={-100} />
      <directionalLight position={[-50, 34, -45]} intensity={0.24} />
      <pointLight position={[0, 25, 0]} intensity={0.35} color="#df1067" />

      <mesh rotation={[-Math.PI / 2, 0, 0]} position={[0, -0.08, 0]} receiveShadow>
        <planeGeometry args={[model.floor.width, model.floor.depth]} />
        <meshStandardMaterial color="#f0f3f8" roughness={0.68} metalness={0.02} />
      </mesh>
      <gridHelper args={[model.floor.width, 56, '#cbd5e0', '#e2e8f0']} position={[0, 0, 0]} />

      {model.roomFixtures.map((f) => <RoomMesh key={f.id} fixture={f} selected={String(f.id) === String(selectedAreaId)} onSelect={onSelectArea} />)}
      {model.rackFixtures.map((f) => <RackMesh key={f.id} fixture={f} heatmap={heatmap} selected={String(f.id) === String(selectedAreaId)} onSelect={onSelectArea} />)}
      {model.columns.map((f) => <ColumnMesh key={f.id} fixture={f} />)}
      {model.productMarkers.map((p) => <ProductMarker key={p.sku} product={p} selected={String(p.sku) === String(selectedProductSku)} onSelect={onSelectProduct} />)}

      <AnimatedPath points={model.route} color="#df1067" visible={layerState.route} />
      <AnimatedPath points={model.coldRoute} color="#18c7df" visible={layerState.cold} />
      <Vehicle points={model.route} color="#df1067" />
      {model.alerts.map((a) => <AlertMarker key={a.id} alert={a} visible={layerState.alerts} />)}

      <EffectComposer>
        <Bloom luminanceThreshold={0.62} luminanceSmoothing={0.92} intensity={0.35} />
      </EffectComposer>
    </>
  );
}

export default function TwinStudio3D({ objects, products, cameraPreset, heatmap, selectedAreaId, selectedProductSku, onSelectArea, onSelectProduct }) {
  const model = useMemo(() => buildTwinModel(objects, products), [objects, products]);
  const [layerState, setLayerState] = useState({ route: true, cold: true, alerts: true, products: true });

  useEffect(() => {
    setLayerState((prev) => ({ ...prev, cold: heatmap === 'cold' || prev.cold, alerts: heatmap === 'refill' || heatmap === 'traffic' || prev.alerts }));
  }, [heatmap]);

  return (
    <div className="twin-studio-canvas">
      <Canvas shadows gl={{ antialias: true, alpha: true }} dpr={[1, 1.75]} onContextMenu={(e) => e.preventDefault()}>
        <Scene model={model} cameraPreset={cameraPreset} heatmap={heatmap} layerState={layerState} selectedAreaId={selectedAreaId} selectedProductSku={selectedProductSku} onSelectArea={onSelectArea} onSelectProduct={onSelectProduct} />
      </Canvas>
      <div className="twin-camera-help">
        <b>Kamera</b>
        <span>Sol sürükle: döndür</span>
        <span>Sağ sürükle: pan</span>
        <span>Wheel: zoom</span>
        <span>W/A/S/D: sahada kaydır</span>
      </div>
      <div className="twin-layer-dock">
        <button className={layerState.route ? 'active' : ''} onClick={() => setLayerState((p) => ({ ...p, route: !p.route }))}>Rota</button>
        <button className={layerState.cold ? 'active' : ''} onClick={() => setLayerState((p) => ({ ...p, cold: !p.cold }))}>Soğuk akış</button>
        <button className={layerState.alerts ? 'active' : ''} onClick={() => setLayerState((p) => ({ ...p, alerts: !p.alerts }))}>Uyarılar</button>
      </div>
      <div className="twin-legend">
        {['AMBIENT', 'CHILLED', 'FROZEN', 'DISPATCH'].map((z) => <span key={z}><i style={{ background: zoneColor(z) }} />{z}</span>)}
      </div>
    </div>
  );
}
