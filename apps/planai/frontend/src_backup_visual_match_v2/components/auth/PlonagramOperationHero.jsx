import React, { useMemo, useRef } from "react";
import { Canvas, useFrame } from "@react-three/fiber";
import { Html } from "@react-three/drei";
import * as THREE from "three";
import "./PlonagramOperationHero.css";

const ZONES = [
  { key: "AMBIENT", label: "AMBIENT", color: "#64748b", x: -10, z: -2 },
  { key: "CHILLED", label: "CHILLED +4", color: "#22d3ee", x: -3.5, z: -2 },
  { key: "FROZEN", label: "FROZEN -18", color: "#2563eb", x: 3.5, z: -2 },
  { key: "HEAVY", label: "HEAVY LAST", color: "#df1067", x: 10, z: -2 },
];

function roundedPath(points) {
  return new THREE.CatmullRomCurve3(points.map(([x, y, z]) => new THREE.Vector3(x, y, z)), false, "catmullrom", 0.18);
}

function CameraTour({ curve }) {
  useFrame(({ camera, clock }) => {
    const t = (clock.getElapsedTime() * 0.045) % 1;
    const p = curve.getPointAt(t);
    const look = curve.getPointAt(Math.min(t + 0.035, 1));

    const height = 7.5 + Math.sin(t * Math.PI * 2) * 1.7;
    camera.position.lerp(new THREE.Vector3(p.x, height, p.z + 7), 0.035);
    camera.lookAt(new THREE.Vector3(look.x, 0.8, look.z));
  });
  return null;
}

function ShelfRack({ x, z, zone, index, side = 1 }) {
  const color = zone.color;
  const rows = 4;
  const cols = 6;
  return (
    <group position={[x, 0, z]} rotation={[0, side < 0 ? Math.PI : 0, 0]}>
      {/* back posts */}
      {[-1.55, 1.55].map((px) => (
        <mesh key={px} position={[px, 1.35, -0.16]} castShadow>
          <boxGeometry args={[0.08, 2.7, 0.08]} />
          <meshStandardMaterial color="#5f6b7a" metalness={0.35} roughness={0.48} />
        </mesh>
      ))}
      {/* shelves */}
      {Array.from({ length: rows }).map((_, r) => {
        const y = 0.42 + r * 0.55;
        return (
          <group key={r}>
            <mesh position={[0, y, 0]} castShadow receiveShadow>
              <boxGeometry args={[3.35, 0.06, 0.62]} />
              <meshStandardMaterial color="#cbd5e1" metalness={0.25} roughness={0.42} />
            </mesh>
            <mesh position={[0, y + 0.05, -0.34]}>
              <boxGeometry args={[3.35, 0.04, 0.05]} />
              <meshStandardMaterial color={color} emissive={color} emissiveIntensity={0.25} />
            </mesh>
            {Array.from({ length: cols }).map((__, c) => {
              const px = -1.28 + c * 0.52;
              const h = 0.2 + ((c + r + index) % 3) * 0.07;
              return (
                <mesh key={c} position={[px, y + 0.08 + h / 2, -0.06]} castShadow>
                  <boxGeometry args={[0.28, h, 0.22]} />
                  <meshStandardMaterial color={["#fff7ed", "#fef3c7", "#e0f2fe", "#fce7f3"][(c + r) % 4]} roughness={0.65} />
                </mesh>
              );
            })}
          </group>
        );
      })}
    </group>
  );
}

function ZoneBlock({ zone, zoneIndex }) {
  const racks = [];
  // 3 rack islands per zone, two faces each; walkway remains open between zones.
  for (let row = 0; row < 3; row++) {
    for (let face = 0; face < 2; face++) {
      racks.push({
        x: zone.x + (face === 0 ? -1.0 : 1.0),
        z: zone.z + row * 2.2,
        side: face === 0 ? 1 : -1,
        index: zoneIndex * 10 + row * 2 + face,
      });
    }
  }
  return (
    <group>
      {racks.map((r, i) => (
        <ShelfRack key={i} x={r.x} z={r.z} side={r.side} zone={zone} index={r.index} />
      ))}
      <Html position={[zone.x, 0.04, zone.z - 1.45]} center transform rotation={[-Math.PI / 2, 0, 0]}>
        <div className="plh-floor-label" style={{ color: zone.color }}>{zone.label}</div>
      </Html>
      <Html position={[zone.x, 3.1, zone.z - 0.2]} center>
        <div className="plh-zone-chip" style={{ borderColor: zone.color, color: zone.color }}>{zone.label}</div>
      </Html>
    </group>
  );
}

function Picker({ curve }) {
  const ref = useRef();
  const box = useRef();
  useFrame(({ clock }) => {
    const t = (clock.getElapsedTime() * 0.095) % 1;
    const p = curve.getPointAt(t);
    const next = curve.getPointAt(Math.min(t + 0.01, 1));
    if (ref.current) {
      ref.current.position.set(p.x, 0.22, p.z);
      ref.current.lookAt(next.x, 0.22, next.z);
    }
    if (box.current) box.current.position.y = 0.25 + Math.sin(clock.getElapsedTime() * 5) * 0.03;
  });
  return (
    <group ref={ref}>
      <mesh position={[0, 0.55, 0]} castShadow>
        <capsuleGeometry args={[0.16, 0.48, 6, 12]} />
        <meshStandardMaterial color="#0f172a" roughness={0.5} />
      </mesh>
      <mesh ref={box} position={[0.38, 0.25, 0.1]} castShadow>
        <boxGeometry args={[0.38, 0.28, 0.32]} />
        <meshStandardMaterial color="#df1067" emissive="#df1067" emissiveIntensity={0.18} />
      </mesh>
    </group>
  );
}

function RouteLine({ curve }) {
  const tube = useMemo(() => new THREE.TubeGeometry(curve, 120, 0.035, 8, false), [curve]);
  const pulse = useRef();
  useFrame(({ clock }) => {
    if (pulse.current) pulse.current.material.opacity = 0.35 + Math.sin(clock.getElapsedTime() * 2.5) * 0.18;
  });
  return (
    <group>
      <mesh geometry={tube} position={[0, 0.035, 0]} ref={pulse}>
        <meshStandardMaterial color="#df1067" emissive="#df1067" emissiveIntensity={0.8} transparent opacity={0.42} />
      </mesh>
    </group>
  );
}

function Scene() {
  // Route uses clear walkways, not rack centers: starts dispatch -> ambient aisle -> chilled -> frozen -> heavy -> dispatch.
  const route = useMemo(() => roundedPath([
    [-12.5, 0, 6.3], [-11, 0, 3.4], [-9.8, 0, 1.0], [-6.7, 0, 5.3],
    [-3.7, 0, 1.1], [-0.7, 0, 5.4], [3.4, 0, 1.1], [6.7, 0, 5.5],
    [10.2, 0, 1.0], [12.8, 0, 6.1], [0, 0, 8.6]
  ]), []);

  return (
    <>
      <color attach="background" args={["#f2f6fb"]} />
      <fog attach="fog" args={["#f2f6fb", 18, 48]} />
      <ambientLight intensity={1.2} />
      <directionalLight position={[8, 14, 9]} intensity={1.7} castShadow shadow-mapSize-width={2048} shadow-mapSize-height={2048} />
      <hemisphereLight intensity={0.8} groundColor="#dbe3ec" />
      <mesh rotation={[-Math.PI / 2, 0, 0]} receiveShadow position={[0, -0.02, 3]}>
        <planeGeometry args={[36, 22]} />
        <meshStandardMaterial color="#edf2f7" roughness={0.96} />
      </mesh>
      <gridHelper args={[36, 36, "#cfd8e3", "#e3e9f0"]} position={[0, 0.01, 3]} />
      {ZONES.map((z, i) => <ZoneBlock key={z.key} zone={z} zoneIndex={i} />)}
      <Html position={[0, 0.08, 8.8]} center transform rotation={[-Math.PI / 2, 0, 0]}>
        <div className="plh-dispatch">DISPATCH</div>
      </Html>
      <RouteLine curve={route} />
      <Picker curve={route} />
      <CameraTour curve={route} />
    </>
  );
}

export default function PlonagramOperationHero() {
  return (
    <div className="plh-hero3d">
      <Canvas shadows dpr={[1, 1.7]} camera={{ position: [0, 12, 17], fov: 42, near: 0.1, far: 100 }}>
        <Scene />
      </Canvas>
      <div className="plh-caption">AI route: AMBIENT → CHILLED → FROZEN → HEAVY LAST → DISPATCH</div>
    </div>
  );
}
