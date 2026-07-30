import React, { Suspense } from "react";
import { Canvas } from "@react-three/fiber";
import { Html, Line, OrbitControls, PerspectiveCamera } from "@react-three/drei";
import * as THREE from "three";
import "./ReferenceHeroTwin.css";

function Rack({ position, tint = "#ffffff", accent = "#ff4f9a" }) {
  return (
    <group position={position}>
      <mesh position={[0, .12, 0]} castShadow receiveShadow>
        <boxGeometry args={[2.8, .16, .9]} />
        <meshStandardMaterial color="#eef3f5" roughness={.18} metalness={.18} />
      </mesh>
      {[-1.25, 1.25].map((x) => [-.38, .38].map((z) => (
        <mesh key={`${x}-${z}`} position={[x, .92, z]} castShadow>
          <boxGeometry args={[.06, 1.72, .06]} />
          <meshStandardMaterial color="#c7d1d8" roughness={.28} metalness={.56} />
        </mesh>
      )))}
      {Array.from({ length: 4 }).map((_, s) => (
        <group key={s} position={[0, .3 + s * .38, 0]}>
          <mesh castShadow receiveShadow>
            <boxGeometry args={[2.7, .055, .82]} />
            <meshStandardMaterial color="#f8fbfc" roughness={.16} metalness={.22} />
          </mesh>
          {Array.from({ length: 8 }).map((_, i) => (
            <mesh key={i} position={[-1.08 + i * .31, .16, i % 2 ? .13 : -.13]} castShadow>
              <boxGeometry args={[.22, .28, .18]} />
              <meshStandardMaterial color={i % 3 === 0 ? accent : i % 3 === 1 ? "#e8f8fb" : "#f9eef4"} roughness={.48} metalness={.03} />
            </mesh>
          ))}
        </group>
      ))}
    </group>
  );
}

function Room({ position, color, label }) {
  return (
    <group position={position}>
      <mesh position={[0, .72, 0]} castShadow receiveShadow>
        <boxGeometry args={[2.8, 1.44, 1.65]} />
        <meshPhysicalMaterial color={color} roughness={.08} metalness={.02} transparent opacity={.34} transmission={.35} thickness={.7} />
      </mesh>
      <Html center position={[0, 1.75, 0]}>
        <div className="ref-hero-label">{label}</div>
      </Html>
    </group>
  );
}

function Scene() {
  const route = [[-6, .08, 5.2], [-4, .08, 3.7], [-1.8, .08, 3.9], [.6, .08, 2.3], [3.6, .08, 2.5], [5.6, .08, .2], [7.4, .08, -2.1]];
  return (
    <>
      <PerspectiveCamera makeDefault position={[0, 8.6, 12.4]} fov={32} />
      <color attach="background" args={["#f8fbfc"]} />
      <fog attach="fog" args={["#f8fbfc", 13, 38]} />
      <ambientLight intensity={1.15} />
      <hemisphereLight intensity={.85} groundColor="#e1e8eb" />
      <directionalLight position={[8, 12, 8]} intensity={1.18} castShadow />
      <pointLight position={[0, 2, 4]} intensity={.55} color="#ff2d87" distance={12} />
      <mesh rotation={[-Math.PI/2,0,0]} receiveShadow>
        <planeGeometry args={[22, 15]} />
        <meshStandardMaterial color="#f4f8fa" roughness={.2} metalness={.24} />
      </mesh>
      <gridHelper args={[22, 22, "#cddae2", "#edf2f4"]} position={[0,.012,0]} />
      <mesh position={[0,.03,0]} rotation={[-Math.PI/2,0,0]}>
        <planeGeometry args={[21, 14]} />
        <meshBasicMaterial color="#df1067" transparent opacity={.025} />
      </mesh>
      <group rotation={[0, -.08, 0]}>
        <Rack position={[-4.7,0,-2.4]} />
        <Rack position={[-1.45,0,-2.25]} accent="#8ee9f4" />
        <Rack position={[1.8,0,-2.25]} />
        <Rack position={[-3.2,0,.65]} accent="#8ee9f4" />
        <Rack position={[.05,0,.75]} />
        <Rack position={[3.3,0,.65]} accent="#f6d36a" />
        <Rack position={[-1.55,0,3.55]} accent="#8ee9f4" />
        <Rack position={[1.75,0,3.55]} />
      </group>
      <Room position={[6.6,0,-2.2]} color="#b9f6ff" label="+4 CHILLED" />
      <Room position={[7.2,0,1.65]} color="#cfc5ff" label="-18 FROZEN" />
      <Line points={route} color="#df1067" lineWidth={3.2} dashed={false} />
      {route.map((p,i)=><mesh key={i} position={p}><sphereGeometry args={[i===route.length-1?.12:.065,16,16]} /><meshBasicMaterial color="#df1067" /></mesh>)}
      <Html center position={[-5.8,.8,4.7]}><div className="ref-hero-chip amber">Refill Priority<br/><b>High</b></div></Html>
      <Html center position={[1.4,1.1,.2]}><div className="ref-hero-chip red">Congestion<br/><b>Aisle 07</b></div></Html>
      <Html center position={[7.4,.75,-3.5]}><div className="ref-hero-chip green">DISPATCH<br/><b>Zone B-12</b></div></Html>
      <OrbitControls enableZoom={false} enablePan={false} autoRotate autoRotateSpeed={.18} maxPolarAngle={Math.PI/2.35} minPolarAngle={Math.PI/4.2} />
    </>
  );
}

export default function ReferenceHeroTwin() {
  return (
    <div className="ref-hero-twin">
      <Canvas shadows dpr={[1, 1.7]} gl={{ antialias: true, alpha: false }}>
        <Suspense fallback={null}><Scene /></Suspense>
      </Canvas>
    </div>
  );
}
