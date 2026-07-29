import { useEffect, useMemo, useRef, useState } from 'react';
import { Canvas, useFrame, useThree } from '@react-three/fiber';
import { OrbitControls, PerspectiveCamera, Text, Line, Html } from '@react-three/drei';
import { EffectComposer, Bloom } from '@react-three/postprocessing';
import * as THREE from 'three';
import { buildTwinModel, cameraPresetTarget, zoneColor, zoneName } from './twinDataAdapter.js';
import './TwinStudio3D.css';

const FLOOR_HEIGHT = 6.2;

function getFloor(item) {
  return Number(item?.floor ?? item?.floor_level ?? item?.level ?? 0) || 0;
}

function floorVisible(itemFloor, currentFloor, showAllFloors) {
  return showAllFloors || Number(itemFloor || 0) === Number(currentFloor || 0);
}

function floorOpacity(itemFloor, currentFloor, showAllFloors) {
  if (!showAllFloors) return 1;
  return Number(itemFloor || 0) === Number(currentFloor || 0) ? 1 : 0.22;
}

function shelfColor(seed, zone) {
  const palette = String(zone || '').toUpperCase() === 'FROZEN'
    ? ['#7b61ff', '#a78bfa', '#c4b5fd', '#eef2ff']
    : String(zone || '').toUpperCase() === 'CHILLED'
      ? ['#18c7df', '#67e8f9', '#dffafe', '#f0fdfa']
      : ['#df1067', '#f5b900', '#10131a', '#ffffff', '#d9dee8'];
  return palette[Math.abs(seed) % palette.length];
}


function WarehouseShell({ floor }) {
  const w = floor?.width || 170;
  const d = floor?.depth || 122;
  const wallH = 18;
  const trussColor = '#d7dde8';
  return (
    <group>
      <mesh position={[0, wallH / 2, -d / 2 - 0.22]} receiveShadow>
        <boxGeometry args={[w, wallH, .18]} />
        <meshStandardMaterial color="#ffffff" transparent opacity={0.28} roughness={0.62} metalness={0.02} />
      </mesh>
      <mesh position={[-w / 2 - 0.22, wallH / 2, 0]} receiveShadow>
        <boxGeometry args={[.18, wallH, d]} />
        <meshStandardMaterial color="#ffffff" transparent opacity={0.18} roughness={0.62} metalness={0.02} />
      </mesh>
      {Array.from({ length: 9 }).map((_, i) => {
        const x = -w / 2 + 10 + i * ((w - 20) / 8);
        return (
          <group key={`truss-${i}`}>
            <mesh position={[x, wallH + 1.1, -d / 2 - 0.1]} rotation={[Math.PI / 2, 0, 0]}>
              <cylinderGeometry args={[.075, .075, d * .78, 8]} />
              <meshStandardMaterial color={trussColor} metalness={0.7} roughness={0.28} transparent opacity={0.5} />
            </mesh>
            <mesh position={[x, wallH / 2, -d / 2 - .35]}>
              <boxGeometry args={[.18, wallH, .18]} />
              <meshStandardMaterial color={trussColor} metalness={0.52} roughness={0.3} transparent opacity={0.44} />
            </mesh>
          </group>
        );
      })}
      {Array.from({ length: 8 }).map((_, i) => {
        const x = -w / 2 + 18 + i * ((w - 36) / 7);
        return (
          <mesh key={`window-${i}`} position={[x, wallH - 4.5, -d / 2 - .42]}>
            <boxGeometry args={[8.8, 3.4, .08]} />
            <meshStandardMaterial color="#eaf8ff" transparent opacity={0.36} emissive="#18c7df" emissiveIntensity={0.06} />
          </mesh>
        );
      })}
      {Array.from({ length: 7 }).map((_, i) => {
        const z = -d / 2 + 16 + i * ((d - 32) / 6);
        return (
          <Line key={`lane-${i}`} points={[[-w / 2 + 4, .055, z], [w / 2 - 4, .055, z]]} color="#d4dae6" lineWidth={1} transparent opacity={0.35} />
        );
      })}
      <Line points={[[-w/2 + 10, .07, d/2 - 18], [w/2 - 10, .07, d/2 - 18]]} color="#df1067" lineWidth={3} transparent opacity={0.62} />
      <Line points={[[-w/2 + 10, .072, -d/2 + 18], [w/2 - 10, .072, -d/2 + 18]]} color="#18c7df" lineWidth={2} transparent opacity={0.42} />
    </group>
  );
}

function RackCrossBrace({ moduleWidth, worldD, worldH, opacity }) {
  const x = moduleWidth * .47;
  const z = worldD * .43;
  const y1 = -worldH / 2 + .24;
  const y2 = worldH / 2 - .24;
  return (
    <group>
      <Line points={[[-x, y1, -z], [x, y2, -z]]} color="#222936" lineWidth={1.4} transparent opacity={0.42 * opacity} />
      <Line points={[[x, y1, -z], [-x, y2, -z]]} color="#222936" lineWidth={1.4} transparent opacity={0.32 * opacity} />
      <Line points={[[-x, y1, z], [x, y2, z]]} color="#222936" lineWidth={1.2} transparent opacity={0.22 * opacity} />
    </group>
  );
}

function ShelfSlotTicks({ moduleWidth, worldD, y, count, opacity }) {
  return Array.from({ length: Math.min(12, Math.max(3, count)) }).map((_, i) => {
    const x = -moduleWidth * .42 + i * (moduleWidth * .84 / Math.max(1, Math.min(12, count) - 1));
    return (
      <mesh key={`tick-${i}`} position={[x, y + .105, worldD * .43]}>
        <boxGeometry args={[.035, .11, .18]} />
        <meshStandardMaterial color="#94a3b8" roughness={0.4} metalness={0.38} transparent opacity={0.46 * opacity} />
      </mesh>
    );
  });
}

function RackPackages({ moduleWidth, shelfY, worldD, count, zone, moduleIndex, shelfIndex, opacity }) {
  const safeCount = Math.max(1, Math.min(12, count));
  return Array.from({ length: safeCount }).map((_, k) => {
    const seed = (moduleIndex + 1) * 37 + (shelfIndex + 1) * 17 + k * 13;
    const pkgW = Math.max(.28, Math.min(.66, moduleWidth / Math.max(8, safeCount + 3)));
    const pkgH = .34 + (seed % 5) * .09;
    const pkgD = .38 + (seed % 4) * .09;
    const x = -moduleWidth * .38 + k * (moduleWidth * .76 / Math.max(1, safeCount - 1));
    const z = ((seed % 5) - 2) * worldD * .052;
    const color = shelfColor(seed, zone);
    const capColor = String(zone || '').toUpperCase() === 'FROZEN' ? '#312e81' : String(zone || '').toUpperCase() === 'CHILLED' ? '#0e7490' : '#1f2937';
    return (
      <group key={`pkg-${k}`} position={[x, shelfY + .31 + pkgH / 2, z]} rotation={[0, ((seed % 3) - 1) * 0.025, 0]}>
        <mesh castShadow receiveShadow>
          <boxGeometry args={[pkgW, pkgH, pkgD]} />
          <meshStandardMaterial color={color} roughness={0.42} metalness={0.03} transparent opacity={0.86 * opacity} />
        </mesh>
        <mesh position={[0, pkgH / 2 + .018, 0]}>
          <boxGeometry args={[pkgW * .96, .032, pkgD * .96]} />
          <meshStandardMaterial color={capColor} transparent opacity={0.18 * opacity} />
        </mesh>
        <mesh position={[0, 0.02, pkgD / 2 + .007]}>
          <boxGeometry args={[pkgW * .56, pkgH * .34, .014]} />
          <meshBasicMaterial color="#ffffff" transparent opacity={0.72 * opacity} />
        </mesh>
        {seed % 3 === 0 && <Line points={[[0, -pkgH * .45, pkgD / 2 + .018], [0, pkgH * .45, pkgD / 2 + .018]]} color="#df1067" lineWidth={1} transparent opacity={0.48 * opacity} />}
      </group>
    );
  });
}

function RackMesh({ fixture, heatmap, selected, currentFloor, showAllFloors, onSelect, onBeginDrag }) {
  const ref = useRef();
  const [hovered, setHovered] = useState(false);
  const { world, color, utilization } = fixture;
  const floor = getFloor(fixture);
  const visible = floorVisible(floor, currentFloor, showAllFloors);
  const opacity = floorOpacity(floor, currentFloor, showAllFloors);
  const modules = Math.max(1, Number(fixture.modules || 1));
  const shelves = Math.max(3, Math.min(8, Number(fixture.shelves || 5)));
  const moduleWidth = Math.max(1.25, world.w / modules);
  const heat = heatmap === 'refill' ? Math.min(1, Number(fixture.changed || 0) / 22) : heatmap === 'cold' ? (fixture.zone === 'CHILLED' || fixture.zone === 'FROZEN' ? 1 : .12) : heatmap === 'traffic' ? Math.min(1, utilization / 100) : Math.min(1, utilization / 100);
  const activeColor = heatmap === 'refill' ? '#f5b900' : heatmap === 'traffic' ? '#e84a4a' : color;
  const baseY = world.y + floor * FLOOR_HEIGHT;

  useFrame((state) => {
    if (!ref.current) return;
    const pulse = hovered || selected ? 1 + Math.sin(state.clock.elapsedTime * 4) * 0.018 : 1;
    ref.current.scale.setScalar(pulse);
  });

  if (!visible) return null;

  return (
    <group ref={ref} position={[world.x, baseY, world.z]} rotation={[0, world.rotation, 0]} onPointerDown={(e) => onBeginDrag?.(fixture, e)}>
      {Array.from({ length: modules }).map((_, i) => {
        const x = -world.w / 2 + moduleWidth / 2 + i * moduleWidth;
        const shelfStep = world.h / (shelves + 1);
        return (
          <group key={i} position={[x, 0, 0]}>
            {[[-.46, -.43], [.46, -.43], [-.46, .43], [.46, .43]].map(([px, pz], postIdx) => (
              <mesh key={`post-${postIdx}`} position={[px * moduleWidth, 0, pz * world.d]} castShadow receiveShadow>
                <cylinderGeometry args={[0.075, 0.075, world.h, 10]} />
                <meshStandardMaterial color={selected || hovered ? '#1f2937' : '#485467'} metalness={0.84} roughness={0.22} transparent opacity={0.78 + opacity * 0.22} />
              </mesh>
            ))}
            <RackCrossBrace moduleWidth={moduleWidth} worldD={world.d} worldH={world.h} opacity={opacity} />
            {Array.from({ length: shelves }).map((__, shelfIdx) => {
              const y = -world.h / 2 + shelfStep * (shelfIdx + 1);
              const pkgCount = Math.max(2, Math.min(9, Math.round((utilization || 45) / 14) + ((i + shelfIdx) % 2)));
              return (
                <group key={`shelf-group-${shelfIdx}`}>
                  <mesh
                    position={[0, y, 0]}
                    castShadow
                    receiveShadow
                    onClick={(e) => { e.stopPropagation(); onSelect?.(fixture, { module: i + 1, shelf: shelfIdx + 1 }); }}
                    onPointerOver={(e) => { e.stopPropagation(); setHovered(true); document.body.style.cursor = 'pointer'; }}
                    onPointerOut={() => { setHovered(false); document.body.style.cursor = 'default'; }}
                  >
                    <boxGeometry args={[moduleWidth * .92, .13, world.d * .82]} />
                    <meshStandardMaterial
                      color={hovered || selected ? '#ffffff' : '#e7ebf2'}
                      transparent
                      opacity={(0.78 + heat * .16) * opacity}
                      roughness={0.31}
                      metalness={0.42}
                      emissive={activeColor}
                      emissiveIntensity={((hovered || selected ? .14 : .025) + heat * .04) * opacity}
                    />
                  </mesh>
                  <ShelfSlotTicks moduleWidth={moduleWidth} worldD={world.d} y={y} count={pkgCount} opacity={opacity} />
                  <RackPackages moduleWidth={moduleWidth} shelfY={y} worldD={world.d} count={pkgCount} zone={fixture.zone} moduleIndex={i} shelfIndex={shelfIdx} opacity={opacity} />
                </group>
              );
            })}
            <mesh position={[0, -world.h / 2 + .18, 0]}>
              <boxGeometry args={[moduleWidth * .94, .18, world.d * .84]} />
              <meshStandardMaterial color="#cbd5e1" metalness={0.58} roughness={0.22} transparent opacity={opacity} />
            </mesh>
          </group>
        );
      })}
      {(hovered || selected) && (
        <mesh>
          <boxGeometry args={[world.w + .48, world.h + .42, world.d + .48]} />
          <meshBasicMaterial color={activeColor} wireframe transparent opacity={0.82 * opacity} />
        </mesh>
      )}
      <Text position={[0, world.h / 2 + 1.6, 0]} rotation={[-0.45, 0, 0]} fontSize={1.35} color={selected ? '#df1067' : '#10131a'} anchorX="center" anchorY="middle" outlineWidth={0.035} outlineColor="#ffffff">
        {fixture.label}
      </Text>
      <Html position={[0, world.h / 2 + 3.1, 0]} center distanceFactor={80} style={{ pointerEvents: 'none' }}>
        <div className={`twin-util-pill ${selected ? 'is-selected' : ''}`}>{utilization}% dolu · {fixture.changed} değişim</div>
      </Html>
    </group>
  );
}

function RoomMesh({ fixture, selected, currentFloor, showAllFloors, onSelect, onBeginDrag }) {
  const [hovered, setHovered] = useState(false);
  const { world, color } = fixture;
  const floor = getFloor(fixture);
  const visible = floorVisible(floor, currentFloor, showAllFloors);
  const opacity = floorOpacity(floor, currentFloor, showAllFloors);
  const height = fixture.type === 'dispatch' ? Math.min(world.h, 2.8) : world.h;
  if (!visible) return null;
  return (
    <group position={[world.x, height / 2 + floor * FLOOR_HEIGHT, world.z]} rotation={[0, world.rotation, 0]}>
      <mesh receiveShadow castShadow onPointerDown={(e) => onBeginDrag?.(fixture, e)} onClick={(e) => { e.stopPropagation(); onSelect?.(fixture); }} onPointerOver={(e) => { e.stopPropagation(); setHovered(true); document.body.style.cursor = 'pointer'; }} onPointerOut={() => { setHovered(false); document.body.style.cursor = 'default'; }}>
        <boxGeometry args={[world.w, height, world.d]} />
        <meshStandardMaterial color={color} transparent opacity={(hovered || selected ? 0.23 : 0.11) * opacity} roughness={0.55} metalness={0.05} emissive={color} emissiveIntensity={(hovered || selected ? .13 : .04) * opacity} />
      </mesh>
      <mesh>
        <boxGeometry args={[world.w + .15, height + .15, world.d + .15]} />
        <meshBasicMaterial color={color} wireframe transparent opacity={(selected ? .95 : .42) * opacity} />
      </mesh>
      <Text position={[0, height / 2 + 1.5, 0]} rotation={[-0.52, 0, 0]} fontSize={fixture.type === 'dispatch' ? 1.15 : 1.35} color={color} anchorX="center" anchorY="middle" outlineWidth={0.04} outlineColor="#ffffff">
        {fixture.label}
      </Text>
    </group>
  );
}

function ColumnMesh({ fixture, currentFloor, showAllFloors, selected, onSelect, onBeginDrag }) {
  const { world } = fixture;
  const floor = getFloor(fixture);
  const [hovered, setHovered] = useState(false);
  if (!floorVisible(floor, currentFloor, showAllFloors)) return null;
  const opacity = floorOpacity(floor, currentFloor, showAllFloors);
  return (
    <group position={[world.x, world.h / 2 + floor * FLOOR_HEIGHT, world.z]}
      onPointerDown={(e) => onBeginDrag?.(fixture, e)}
      onClick={(e) => { e.stopPropagation(); onSelect?.(fixture); }}
      onPointerOver={(e) => { e.stopPropagation(); setHovered(true); document.body.style.cursor = 'pointer'; }}
      onPointerOut={() => { setHovered(false); document.body.style.cursor = 'default'; }}>
      <mesh castShadow receiveShadow>
        <cylinderGeometry args={[0.42, 0.42, world.h, 12]} />
        <meshStandardMaterial color={selected || hovered ? '#df1067' : '#4b5565'} emissive={selected ? '#df1067' : '#000000'} emissiveIntensity={selected ? .28 : 0} metalness={0.45} roughness={0.3} transparent opacity={opacity} />
      </mesh>
      {(selected || hovered) && <mesh>
        <cylinderGeometry args={[0.58, 0.58, world.h + .24, 12]} />
        <meshBasicMaterial color="#df1067" wireframe transparent opacity={0.9 * opacity} />
      </mesh>}
      {selected && <Html position={[0, world.h / 2 + 1.35, 0]} center distanceFactor={70} style={{ pointerEvents: 'none' }}><div className="twin-util-pill is-selected">{fixture.label}</div></Html>}
    </group>
  );
}

function FloorPlatform({ floor, active, visible }) {
  if (!visible || Number(floor.level) === 0) return null;
  const opacity = active ? 0.48 : 0.16;
  return (
    <group position={[0, floor.height, 0]}>
      <mesh rotation={[-Math.PI / 2, 0, 0]} receiveShadow>
        <planeGeometry args={[floor.width || 96, floor.depth || 78]} />
        <meshStandardMaterial color="#c2cad8" transparent opacity={opacity} metalness={0.58} roughness={0.25} side={THREE.DoubleSide} />
      </mesh>
      <gridHelper args={[floor.width || 96, 32, '#697386', '#9aa6b8']} position={[0, 0.05, 0]} />
      {[ [0, 1, (floor.depth || 78) / 2, [floor.width || 96, .12, .12]], [0, 1, -(floor.depth || 78) / 2, [floor.width || 96, .12, .12]], [(floor.width || 96) / 2, 1, 0, [.12, .12, floor.depth || 78]], [-(floor.width || 96) / 2, 1, 0, [.12, .12, floor.depth || 78]] ].map(([x, y, z, dims], i) => (
        <mesh key={i} position={[x, y, z]}>
          <boxGeometry args={dims} />
          <meshStandardMaterial color="#f5b900" metalness={0.55} roughness={0.32} transparent opacity={active ? .92 : .35} />
        </mesh>
      ))}
      <Html position={[0, 2.4, -(floor.depth || 78) / 2 + 4]} center distanceFactor={88}>
        <div className={`twin-floor-label ${active ? 'active' : ''}`}>{floor.name}</div>
      </Html>
    </group>
  );
}

function StairsMesh({ stair, currentFloor, onFloorChange, visible }) {
  const [hovered, setHovered] = useState(false);
  if (!visible) return null;
  const position = stair.position || [-20, 0, 10];
  const goTo = Number(currentFloor) === 0 ? 1 : 0;
  return (
    <group position={position}>
      {Array.from({ length: 13 }).map((_, i) => (
        <mesh key={i} position={[i * .32, i * .44, 0]} castShadow receiveShadow>
          <boxGeometry args={[.34, .38, 2.15]} />
          <meshStandardMaterial color="#64748b" metalness={0.52} roughness={0.46} />
        </mesh>
      ))}
      {[-1.16, 1.16].map((z) => (
        <mesh key={z} position={[2.05, 2.85, z]} rotation={[0, 0, Math.PI / 2.55]}>
          <cylinderGeometry args={[.055, .055, 5.7, 8]} />
          <meshStandardMaterial color="#f5b900" metalness={0.8} roughness={0.22} />
        </mesh>
      ))}
      <group position={[2.2, currentFloor === 0 ? 1.05 : 6.25, 0]} onPointerOver={(e) => { e.stopPropagation(); setHovered(true); document.body.style.cursor = 'pointer'; }} onPointerOut={() => { setHovered(false); document.body.style.cursor = 'default'; }} onClick={(e) => { e.stopPropagation(); onFloorChange?.(goTo); }}>
        <mesh>
          <cylinderGeometry args={[.9, .9, .18, 32]} />
          <meshStandardMaterial color={hovered ? '#17a66a' : '#f5b900'} emissive={hovered ? '#17a66a' : '#f5b900'} emissiveIntensity={0.42} />
        </mesh>
        <Text position={[0, 1.35, 0]} fontSize={.55} color="#ffffff" anchorX="center" outlineWidth={0.05} outlineColor="#10131a">
          {goTo === 1 ? 'Asma Kata Çık' : 'Zemin Kata İn'}
        </Text>
      </group>
    </group>
  );
}

function WorkerMesh({ worker, currentFloor, visible }) {
  const ref = useRef();
  const floor = getFloor(worker);
  const seed = useMemo(() => String(worker.id || worker.name || '').split('').reduce((a, c) => a + c.charCodeAt(0), 0) % 100 / 100, [worker]);
  const curve = useMemo(() => new THREE.CatmullRomCurve3((worker.path || [[0, .5, 0], [6, .5, 4], [12, .5, 0]]).map((p) => new THREE.Vector3(p[0], p[1] + floor * FLOOR_HEIGHT, p[2]))), [worker, floor]);

  useFrame((state) => {
    if (!ref.current || !visible || Number(currentFloor) !== floor) return;
    const t = (seed + state.clock.elapsedTime * (worker.speed || .035)) % 1;
    const pos = curve.getPoint(t);
    const next = curve.getPoint((t + .012) % 1);
    ref.current.position.lerp(pos, .12);
    ref.current.lookAt(next);
    ref.current.rotation.z = Math.sin(state.clock.elapsedTime * 4) * .04;
  });

  if (!visible || Number(currentFloor) !== floor) return null;
  const activity = worker.activity || 'picking';
  return (
    <group ref={ref}>
      <mesh position={[0, .9, 0]} castShadow>
        <capsuleGeometry args={[.25, 1, 8, 14]} />
        <meshStandardMaterial color={activity === 'picking' ? '#df1067' : activity === 'carrying' ? '#f5b900' : '#18c7df'} roughness={0.68} />
      </mesh>
      <mesh position={[0, 1.72, 0]} castShadow>
        <sphereGeometry args={[.2, 16, 16]} />
        <meshStandardMaterial color="#d4a574" />
      </mesh>
      <mesh position={[0, 2, 0]} castShadow>
        <cylinderGeometry args={[.25, .28, .22, 16]} />
        <meshStandardMaterial color="#f5b900" metalness={0.58} roughness={0.3} />
      </mesh>
      {activity === 'picking' && (
        <mesh position={[.45, .38, .52]} castShadow>
          <boxGeometry args={[.54, .62, .54]} />
          <meshStandardMaterial color="#64748b" metalness={0.36} />
        </mesh>
      )}
      <Html position={[0, 2.55, 0]} center distanceFactor={60} style={{ pointerEvents: 'none' }}>
        <div className="twin-worker-label"><b>{worker.name}</b><span>{activity === 'picking' ? 'Toplama' : activity === 'carrying' ? 'Taşıma' : 'Yürüme'}</span></div>
      </Html>
    </group>
  );
}

function ProductMarker({ product, selected, currentFloor, showAllFloors, onSelect }) {
  const ref = useRef();
  const floor = getFloor(product);
  const visible = floorVisible(floor, currentFloor, showAllFloors);
  const rawImage = String(product.image || product.image_url || '').trim();
  const hasImageUrl = /^https?:\/\//i.test(rawImage);
  const label = product.name || product.product_name || product.sku;
  useFrame((state) => {
    if (ref.current && selected) ref.current.position.y = product.world[1] + floor * FLOOR_HEIGHT + Math.sin(state.clock.elapsedTime * 4) * .18;
  });
  if (!visible) return null;
  return (
    <group ref={ref} position={[product.world[0], product.world[1] + floor * FLOOR_HEIGHT, product.world[2]]} onClick={(e) => { e.stopPropagation(); onSelect?.(product); }}>
      <mesh castShadow>
        <boxGeometry args={[1.25, 1.25, 1.25]} />
        <meshStandardMaterial color={product.color} emissive={product.color} emissiveIntensity={selected ? .6 : .16} roughness={0.32} metalness={0.2} transparent opacity={floorOpacity(floor, currentFloor, showAllFloors)} />
      </mesh>
      <Html center distanceFactor={68} style={{ pointerEvents: 'none' }}>
        <div className={`twin-product-label ${selected ? 'is-selected' : ''}`}>
          {hasImageUrl ? <img src={rawImage} alt="" /> : <span className="twin-product-token">▣</span>}
          <span>{label}</span>
        </div>
      </Html>
    </group>
  );
}

function AnimatedPath({ points, color = '#df1067', visible = true, floor = 0, currentFloor = 0 }) {
  const [progress, setProgress] = useState(0);
  const shifted = useMemo(() => points.map((p) => [p[0], p[1] + floor * FLOOR_HEIGHT, p[2]]), [points, floor]);
  const curve = useMemo(() => new THREE.CatmullRomCurve3(shifted.map((p) => new THREE.Vector3(...p))), [shifted]);
  const basePoints = useMemo(() => curve.getPoints(100), [curve]);
  const animatedPoints = useMemo(() => {
    const pts = [];
    const count = 110;
    const start = Math.floor(progress * count);
    for (let i = 0; i < 34; i++) pts.push(curve.getPoint(((start + i) % count) / count));
    return pts;
  }, [curve, progress]);
  useFrame((state) => { if (Number(floor) === Number(currentFloor)) setProgress((state.clock.elapsedTime * .24) % 1); });
  if (!visible || Number(floor) !== Number(currentFloor)) return null;
  return (
    <group>
      <Line points={basePoints} color={color} lineWidth={2} transparent opacity={0.26} />
      <Line points={animatedPoints} color={color} lineWidth={5} transparent opacity={0.86} />
      <Line points={animatedPoints} color={color} lineWidth={13} transparent opacity={0.16} />
    </group>
  );
}

function Vehicle({ points, color = '#df1067', floor = 0, currentFloor = 0 }) {
  const ref = useRef();
  const shifted = useMemo(() => points.map((p) => [p[0], p[1] + floor * FLOOR_HEIGHT, p[2]]), [points, floor]);
  const curve = useMemo(() => new THREE.CatmullRomCurve3(shifted.map((p) => new THREE.Vector3(...p))), [shifted]);
  useFrame((state) => {
    if (Number(floor) !== Number(currentFloor)) return;
    const t = (state.clock.elapsedTime * .045) % 1;
    const pos = curve.getPoint(t);
    const next = curve.getPoint((t + .01) % 1);
    if (!ref.current) return;
    ref.current.position.copy(pos);
    ref.current.lookAt(next);
  });
  if (Number(floor) !== Number(currentFloor)) return null;
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

function AlertMarker({ alert, visible, currentFloor }) {
  const ref = useRef();
  const floor = getFloor(alert);
  useFrame((state) => {
    if (!ref.current || Number(floor) !== Number(currentFloor)) return;
    const pulse = 1 + Math.sin(state.clock.elapsedTime * 3) * .14;
    ref.current.scale.set(pulse, pulse, pulse);
  });
  if (!visible || Number(floor) !== Number(currentFloor)) return null;
  return (
    <group position={[alert.position[0], alert.position[1] + floor * FLOOR_HEIGHT, alert.position[2]]}>
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

function CameraController({ preset, selectedFixture, selectedProduct, currentFloor, controlsRef, manualCamera }) {
  const { camera } = useThree();
  const focusActiveRef = useRef(true);
  const desired = useMemo(() => cameraPresetTarget(preset, selectedFixture, selectedProduct, currentFloor, FLOOR_HEIGHT), [preset, selectedFixture, selectedProduct, currentFloor]);
  const desiredPosition = useMemo(() => new THREE.Vector3(...desired.position), [desired]);
  const desiredTarget = useMemo(() => new THREE.Vector3(...desired.target), [desired]);

  useEffect(() => { focusActiveRef.current = true; }, [desiredPosition, desiredTarget]);

  useFrame(() => {
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

function Scene({ model, cameraPreset, heatmap, layerState, currentFloor, showAllFloors, selectedAreaId, selectedProductSku, onSelectArea, onSelectProduct, onFloorChange, editorMode = false, dragMode = false, onMoveObject }) {
  const controlsRef = useRef();
  const [manualCamera, setManualCamera] = useState(false);
  const selectedFixture = model.fixtures.find((f) => String(f.id) === String(selectedAreaId));
  const selectedProduct = model.productMarkers.find((p) => String(p.sku) === String(selectedProductSku));
  const [draggingId, setDraggingId] = useState(null);

  function beginDrag(fixture, event) {
    if (!editorMode || !dragMode) return;
    event.stopPropagation();
    setDraggingId(fixture.id);
    onSelectArea?.(fixture);
  }

  useEffect(() => {
    if (!draggingId || !onMoveObject) return undefined;
    const move = (event) => onMoveObject(draggingId, { dx: event.movementX * 0.085, dy: event.movementY * 0.085 });
    const up = () => setDraggingId(null);
    window.addEventListener('pointermove', move);
    window.addEventListener('pointerup', up, { once: true });
    return () => { window.removeEventListener('pointermove', move); window.removeEventListener('pointerup', up); };
  }, [draggingId, onMoveObject]);

  useEffect(() => { setManualCamera(false); }, [cameraPreset, selectedAreaId, selectedProductSku, currentFloor]);

  return (
    <>
      <PerspectiveCamera makeDefault position={[84, 70, 86]} fov={45} />
      <OrbitControls
        ref={controlsRef}
        enableDamping
        dampingFactor={0.075}
        enableRotate={!dragMode || !editorMode}
        enableZoom
        enablePan={!dragMode || !editorMode}
        rotateSpeed={0.95}
        zoomSpeed={1.65}
        panSpeed={1.45}
        keyPanSpeed={18}
        minDistance={14}
        maxDistance={280}
        minPolarAngle={0.16}
        maxPolarAngle={Math.PI / 2.02}
        screenSpacePanning
        target={[0, currentFloor * FLOOR_HEIGHT, 0]}
        mouseButtons={{ LEFT: THREE.MOUSE.ROTATE, MIDDLE: THREE.MOUSE.DOLLY, RIGHT: THREE.MOUSE.PAN }}
        touches={{ ONE: THREE.TOUCH.ROTATE, TWO: THREE.TOUCH.DOLLY_PAN }}
        onStart={() => setManualCamera(true)}
        makeDefault
      />
      <CameraController preset={cameraPreset} selectedFixture={selectedFixture} selectedProduct={selectedProduct} currentFloor={currentFloor} controlsRef={controlsRef} manualCamera={manualCamera} />
      <KeyboardCameraController controlsRef={controlsRef} />

      <ambientLight intensity={0.52} />
      <directionalLight position={[60, 92, 70]} intensity={0.96} castShadow shadow-mapSize={[2048, 2048]} shadow-camera-left={-100} shadow-camera-right={100} shadow-camera-top={100} shadow-camera-bottom={-100} />
      <directionalLight position={[-50, 34, -45]} intensity={0.24} />
      <pointLight position={[0, 25 + currentFloor * FLOOR_HEIGHT, 0]} intensity={0.35} color="#df1067" />
      <WarehouseShell floor={model.floor} />

      <mesh rotation={[-Math.PI / 2, 0, 0]} position={[0, -0.08, 0]} receiveShadow>
        <planeGeometry args={[model.floor.width, model.floor.depth]} />
        <meshStandardMaterial color="#f0f3f8" roughness={0.68} metalness={0.02} />
      </mesh>
      <gridHelper args={[model.floor.width, 56, '#cbd5e0', '#e2e8f0']} position={[0, 0, 0]} />

      {model.floors.map((floor) => <FloorPlatform key={floor.level} floor={floor} active={Number(currentFloor) === Number(floor.level)} visible={layerState.floors} />)}
      {model.roomFixtures.map((f) => <RoomMesh key={f.id} fixture={f} currentFloor={currentFloor} showAllFloors={showAllFloors} selected={String(f.id) === String(selectedAreaId)} onSelect={onSelectArea} onBeginDrag={beginDrag} />)}
      {model.rackFixtures.map((f) => <RackMesh key={f.id} fixture={f} currentFloor={currentFloor} showAllFloors={showAllFloors} heatmap={heatmap} selected={String(f.id) === String(selectedAreaId)} onSelect={onSelectArea} onBeginDrag={beginDrag} />)}
      {model.columns.map((f) => <ColumnMesh key={f.id} fixture={f} currentFloor={currentFloor} showAllFloors={showAllFloors} selected={String(f.id) === String(selectedAreaId)} onSelect={onSelectArea} onBeginDrag={beginDrag} />)}
      {layerState.products && model.productMarkers.map((p) => <ProductMarker key={p.sku} product={p} currentFloor={currentFloor} showAllFloors={showAllFloors} selected={String(p.sku) === String(selectedProductSku)} onSelect={onSelectProduct} />)}

      {model.stairs.map((s) => <StairsMesh key={s.id} stair={s} currentFloor={currentFloor} onFloorChange={onFloorChange} visible={layerState.floors} />)}
      {model.workers.map((w) => <WorkerMesh key={w.id} worker={w} currentFloor={currentFloor} visible={layerState.workers} />)}
      {model.routes.map((r) => <AnimatedPath key={r.id} points={r.points} color={r.color} floor={r.floor || 0} currentFloor={currentFloor} visible={layerState.route} />)}
      {model.coldRoutes.map((r) => <AnimatedPath key={r.id} points={r.points} color={r.color} floor={r.floor || 0} currentFloor={currentFloor} visible={layerState.cold} />)}
      {model.alerts.map((a) => <AlertMarker key={a.id} alert={a} currentFloor={currentFloor} visible={layerState.alerts} />)}

      <EffectComposer>
        <Bloom luminanceThreshold={0.62} luminanceSmoothing={0.92} intensity={0.35} />
      </EffectComposer>
    </>
  );
}

export default function TwinStudio3D({ objects, products, cameraPreset, heatmap, selectedAreaId, selectedProductSku, onSelectArea, onSelectProduct, editorMode = false, dragMode = false, onMoveObject }) {
  const model = useMemo(() => buildTwinModel(objects, products), [objects, products]);
  const [currentFloor, setCurrentFloor] = useState(0);
  const [showAllFloors, setShowAllFloors] = useState(false);
  const [layerState, setLayerState] = useState({ route: true, cold: true, alerts: true, products: true, workers: false, floors: false });

  useEffect(() => {
    setLayerState((prev) => ({ ...prev, cold: heatmap === 'cold' || prev.cold, alerts: heatmap === 'refill' || heatmap === 'traffic' || prev.alerts }));
  }, [heatmap]);

  useEffect(() => {
    const selectedProduct = model.productMarkers.find((p) => String(p.sku) === String(selectedProductSku));
    const selectedFixture = model.fixtures.find((f) => String(f.id) === String(selectedAreaId));
    const nextFloor = selectedProduct ? getFloor(selectedProduct) : selectedFixture ? getFloor(selectedFixture) : currentFloor;
    if (Number.isFinite(nextFloor) && Number(nextFloor) !== Number(currentFloor)) setCurrentFloor(nextFloor);
  }, [model, selectedAreaId, selectedProductSku, currentFloor]);

  return (
    <div className="twin-studio-canvas">
      <Canvas shadows gl={{ antialias: true, alpha: true }} dpr={[1, 1.75]} onContextMenu={(e) => e.preventDefault()}>
        <Scene model={model} cameraPreset={cameraPreset} heatmap={heatmap} layerState={layerState} currentFloor={currentFloor} showAllFloors={showAllFloors} selectedAreaId={selectedAreaId} selectedProductSku={selectedProductSku} onSelectArea={onSelectArea} onSelectProduct={onSelectProduct} onFloorChange={setCurrentFloor} editorMode={editorMode} dragMode={dragMode} onMoveObject={onMoveObject} />
      </Canvas>
      {model.floors.length > 1 && <div className="twin-floor-dock">
        {model.floors.map((floor) => (
          <button key={floor.level} className={Number(currentFloor) === Number(floor.level) ? 'active' : ''} onClick={() => setCurrentFloor(floor.level)}>
            {Number(currentFloor) === Number(floor.level) ? '●' : '○'} {floor.name}
          </button>
        ))}
        <button className={showAllFloors ? 'active ghosted' : 'ghosted'} onClick={() => setShowAllFloors((v) => !v)}>Tüm katları göster</button>
      </div>}
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
        <button className={layerState.workers ? 'active' : ''} onClick={() => setLayerState((p) => ({ ...p, workers: !p.workers }))}>Picker</button>
        <button className={layerState.floors ? 'active' : ''} onClick={() => setLayerState((p) => ({ ...p, floors: !p.floors }))}>Katlar</button>
      </div>
      <div className="twin-legend">
        {['AMBIENT', 'CHILLED', 'FROZEN', 'DISPATCH'].map((z) => <span key={z}><i style={{ background: zoneColor(z) }} />{zoneName(z)}</span>)}
      </div>
    </div>
  );
}
