import React, { Suspense, useRef, useState } from "react";
import { Canvas } from "@react-three/fiber";
import { OrbitControls, Environment, ContactShadows } from "@react-three/drei";
import FixtureMesh from "./FixtureMesh";
import CameraRig from "./CameraRig";
import TwinFallback2D from "./TwinFallback2D";

function SceneContent({ planogram, selectedSku, onSelectProduct, cameraPreset, controlsRef }) {
  const aisles = planogram?.aisles || [];
  return <>
    <ambientLight intensity={0.72} />
    <directionalLight position={[4, 8, 6]} intensity={1.1} castShadow />
    <CameraRig preset={cameraPreset} controlsRef={controlsRef} />
    <mesh rotation={[-Math.PI / 2, 0, 0]} receiveShadow><planeGeometry args={[40, 28]} /><meshStandardMaterial color="#F7F4EF" roughness={0.86} /></mesh>
    <gridHelper args={[40, 40, "#D8D2C8", "#EEE8DF"]} position={[0, 0.002, 0]} />
    <ContactShadows position={[0, 0.03, 0]} opacity={0.28} scale={28} blur={2.8} />
    {aisles.map((aisle, ai) => <group key={aisle.aisle_id || ai} position={[0, 0.05, -ai * 2.65]}>{(aisle.modules || []).slice(0, 10).map((module, mi) => <FixtureMesh key={`${aisle.aisle_id}-${module.module_id || mi}`} aisle={aisle} module={module} index={mi} selectedSku={selectedSku} onSelectProduct={onSelectProduct} />)}</group>)}
    <Environment preset="warehouse" />
  </>;
}

export default function TwinScene({ planogram, selectedSku, onSelectProduct, cameraPreset }) {
  const controlsRef = useRef(null);
  const [failed, setFailed] = useState(false);
  if (failed) return <TwinFallback2D planogram={planogram} error="3D Canvas render hata verdi." />;
  return (
    <Canvas shadows dpr={[1, 1.7]} camera={{ position: [8, 7, 9], fov: 43 }} onCreated={({ gl }) => { gl.domElement.addEventListener("webglcontextlost", () => setFailed(true), false); }}>
      <Suspense fallback={null}><SceneContent planogram={planogram} selectedSku={selectedSku} onSelectProduct={onSelectProduct} cameraPreset={cameraPreset} controlsRef={controlsRef} /></Suspense>
      <OrbitControls ref={controlsRef} makeDefault enableDamping dampingFactor={0.08} />
    </Canvas>
  );
}
