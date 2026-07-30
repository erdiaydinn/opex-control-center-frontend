
const fs = require("fs");
const path = require("path");

const appPath = path.join(process.cwd(), "src", "App.jsx");
if (fs.existsSync(appPath)) {
  let src = fs.readFileSync(appPath, "utf8");
  src = src.replace(/<section className="os-hero">[\s\S]*?<\/section>/, "");
  src = src.replace(/Digital Twin Studio/g, "AI Operations Digital Twin");
  src = src.replace(/Darkstore Live Twin/g, "Omniverse Live Twin");
  src = src.replace(/Your Warehouse\. Digitally Perfect\.?/g, "Live Operations Command Center");
  fs.writeFileSync(appPath, src, "utf8");
}

const depotPath = path.join(process.cwd(), "src", "components", "Depot3D.jsx");
if (fs.existsSync(depotPath)) {
  let src = fs.readFileSync(depotPath, "utf8");

  if (!src.includes("function targetForPreset(")) {
    src = src.replace(
      /function Scene\(\{ plan, selectedAisle, onShelfOpen, onModuleSelect, cameraPreset, routeMode \}\) \{/,
`function targetForPreset(preset) {
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

function Scene({ plan, selectedAisle, onShelfOpen, onModuleSelect, cameraPreset, routeMode }) {`
    );
  }

  if (!src.includes("CameraController preset={cameraPreset}")) {
    src = src.replace(/<PerspectiveCamera makeDefault position=\{camPos\} fov=\{36\} \/>/, '<PerspectiveCamera makeDefault position={targetForPreset(cameraPreset).pos} fov={36} />\\n      <CameraController preset={cameraPreset} />');
  }

  if (!src.includes('if(x==="Top") setCameraPreset("top")')) {
    src = src.replace(
      /onClick=\{\(\) => x === "Path" && setRouteMode\(routeMode === "ai" \? "pick" : "ai"\)\}/g,
      `onClick={() => { setActiveTool?.(x.toLowerCase?.() || x); if(x==="Top") setCameraPreset("top"); if(x==="Focus") setCameraPreset("sku"); if(x==="Fly") setCameraPreset("dispatch"); if(x==="Path") setRouteMode(routeMode === "ai" ? "pick" : "ai"); }}`
    );
  }

  src = src.replace(/cameraPreset === "chilled" \? \[-2, 15, 16\] :\s*cameraPreset === "frozen" \? \[12, 14, 13\] :\s*cameraPreset === "dispatch" \? \[16, 10, 10\] :\s*\[0, 22, 26\];/g, 'targetForPreset(cameraPreset).pos;');

  fs.writeFileSync(depotPath, src, "utf8");
}

console.log("Premium header true 3D auth + functional camera command center applied.");
