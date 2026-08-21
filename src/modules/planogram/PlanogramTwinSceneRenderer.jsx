import React, { useEffect, useRef, useState } from "react";

function elementHeight(type) {
  if (type === "wall" || type === "column") return 2.7;
  if (type === "chiller" || type === "freezer") return 1.9;
  if (type === "door" || type === "emergency_exit") return 2.1;
  return 0.06;
}

function elementColor(type) {
  const colors = {
    wall: 0x9ca3af,
    column: 0x64748b,
    door: 0x22c55e,
    emergency_exit: 0x16a34a,
    chiller: 0x0891b2,
    freezer: 0x2563eb,
    inbound: 0x38bdf8,
    dispatch: 0x22c55e,
    no_go: 0xef4444,
    technical: 0xf59e0b,
    picker_entry: 0xdf1067,
    picker_exit: 0xa855f7,
  };
  return colors[type] ?? 0x94a3b8;
}

function fixtureColor(type) {
  const value = String(type || "").toUpperCase();
  if (value.includes("CHILLED") || value.includes("CHILLER") || value.includes("COOLER")) return 0x0891b2;
  if (value.includes("FROZEN") || value.includes("FREEZER")) return 0x2563eb;
  if (value.includes("PALLET")) return 0x9a6b3d;
  return 0xdf1067;
}

function disposeMaterial(material, seen) {
  for (const row of (Array.isArray(material) ? material : [material])) {
    if (!row || seen.has(row)) continue;
    seen.add(row);
    for (const key of ["map", "normalMap", "roughnessMap", "metalnessMap", "aoMap", "emissiveMap"]) {
      const texture = row[key];
      if (texture && !seen.has(texture)) {
        seen.add(texture);
        texture.dispose?.();
      }
    }
    row.dispose?.();
  }
}

export default function PlanogramTwinSceneRenderer({
  sceneModel,
  preset = "overview",
  ariaLabel,
  loadingLabel,
  errorLabel,
}) {
  const mountRef = useRef(null);
  const [state, setState] = useState("loading");

  useEffect(() => {
    let disposed = false;
    let renderer;
    let controls;
    let resizeObserver;
    let frame;
    let environmentTarget;
    const disposables = [];

    async function mount() {
      setState("loading");
      try {
        const THREE = await import("three");
        const { OrbitControls } = await import("three/examples/jsm/controls/OrbitControls.js");
        const { RoomEnvironment } = await import("three/examples/jsm/environments/RoomEnvironment.js");
        if (disposed || !mountRef.current || !sceneModel?.floor) return;

        const host = mountRef.current;
        const scene = new THREE.Scene();
        scene.background = new THREE.Color(0x090b10);
        const span = Math.max(sceneModel.floor.widthM, sceneModel.floor.depthM, 4);
        scene.fog = new THREE.Fog(0x090b10, Math.max(18, span * 1.2), Math.max(70, span * 5));
        const camera = new THREE.PerspectiveCamera(50, 1, 0.04, Math.max(220, span * 12));
        renderer = new THREE.WebGLRenderer({ antialias: true, powerPreference: "high-performance" });
        renderer.setPixelRatio(Math.min(window.devicePixelRatio || 1, 2));
        renderer.shadowMap.enabled = true;
        renderer.shadowMap.type = THREE.PCFSoftShadowMap;
        renderer.outputColorSpace = THREE.SRGBColorSpace;
        renderer.toneMapping = THREE.ACESFilmicToneMapping;
        renderer.toneMappingExposure = 1.08;

        const pmrem = new THREE.PMREMGenerator(renderer);
        environmentTarget = pmrem.fromScene(new RoomEnvironment(), 0.04);
        pmrem.dispose();
        scene.environment = environmentTarget.texture;

        host.replaceChildren(renderer.domElement);
        renderer.domElement.tabIndex = 0;
        renderer.domElement.setAttribute("role", "img");
        renderer.domElement.setAttribute("aria-label", ariaLabel || "Planogram digital twin");
        renderer.domElement.dataset.twinSceneContract = sceneModel.contract;
        renderer.domElement.dataset.geometryAuthority = sceneModel.geometryAuthority;
        renderer.domElement.dataset.sourceKind = sceneModel.sourceKind;

        scene.add(new THREE.HemisphereLight(0xffffff, 0x111827, 1.45));
        const key = new THREE.DirectionalLight(0xffffff, 2.45);
        key.position.set(sceneModel.floor.widthM * 0.35, 10, sceneModel.floor.depthM * 0.25);
        key.castShadow = true;
        key.shadow.mapSize.set(2048, 2048);
        scene.add(key);
        const fill = new THREE.DirectionalLight(0xbfd7ff, 0.65);
        fill.position.set(sceneModel.floor.widthM, 5, sceneModel.floor.depthM);
        scene.add(fill);

        const floorGeometry = new THREE.PlaneGeometry(sceneModel.floor.widthM, sceneModel.floor.depthM);
        const floorMaterial = new THREE.MeshPhysicalMaterial({
          color: 0x242a33,
          roughness: 0.82,
          metalness: 0.01,
          clearcoat: 0.05,
          envMapIntensity: 0.62,
        });
        disposables.push(floorGeometry, floorMaterial);
        const floor = new THREE.Mesh(floorGeometry, floorMaterial);
        floor.rotation.x = -Math.PI / 2;
        floor.position.set(sceneModel.floor.widthM / 2, 0, sceneModel.floor.depthM / 2);
        floor.receiveShadow = true;
        scene.add(floor);

        const operationalTypes = new Set(["picker_entry", "picker_exit", "inbound", "dispatch", "no_go", "technical"]);
        for (const element of sceneModel.architecture || []) {
          const type = String(element.type || "");
          if (type === "picker_entry" || type === "picker_exit") {
            const geometry = new THREE.CylinderGeometry(0.16, 0.16, 0.05, 24);
            const material = new THREE.MeshPhysicalMaterial({
              color: elementColor(type),
              emissive: elementColor(type),
              emissiveIntensity: 0.24,
              roughness: 0.42,
            });
            disposables.push(geometry, material);
            const marker = new THREE.Mesh(geometry, material);
            marker.position.set(element.centerXM, 0.04, element.centerYM);
            scene.add(marker);
            continue;
          }
          const height = elementHeight(type);
          const operational = operationalTypes.has(type);
          const geometry = new THREE.BoxGeometry(element.widthM, height, element.depthM);
          const material = new THREE.MeshPhysicalMaterial({
            color: elementColor(type),
            roughness: operational ? 0.72 : 0.58,
            metalness: operational ? 0.02 : 0.08,
            transparent: operational,
            opacity: operational ? 0.38 : 0.93,
            clearcoat: operational ? 0 : 0.04,
            envMapIntensity: 0.72,
          });
          disposables.push(geometry, material);
          const mesh = new THREE.Mesh(geometry, material);
          mesh.position.set(element.centerXM, height / 2, element.centerYM);
          mesh.rotation.y = (-Number(element.rotationDeg || 0) * Math.PI) / 180;
          mesh.castShadow = !operational;
          mesh.receiveShadow = true;
          mesh.userData.coordinateAuthority = element.coordinateAuthority;
          scene.add(mesh);
        }

        const architectureEquipmentIds = new Set(
          (sceneModel.architecture || [])
            .filter((row) => ["chiller", "freezer"].includes(String(row.type || "")))
            .map((row) => String(row.id || ""))
        );
        for (const fixture of sceneModel.fixtures || []) {
          if (architectureEquipmentIds.has(String(fixture.id || ""))) continue;
          const height = Number(fixture.heightM) > 0 ? Number(fixture.heightM) : 1.6;
          const geometry = new THREE.BoxGeometry(
            Math.max(0.02, Number(fixture.widthM) || 0.6),
            height,
            Math.max(0.02, Number(fixture.depthM) || 0.45)
          );
          const material = new THREE.MeshPhysicalMaterial({
            color: fixtureColor(fixture.fixtureType),
            roughness: 0.43,
            metalness: 0.12,
            transparent: sceneModel.sourceKind === "reviewed_store_scan_preview",
            opacity: sceneModel.sourceKind === "reviewed_store_scan_preview" ? 0.48 : 0.96,
            clearcoat: 0.08,
            envMapIntensity: 0.86,
          });
          disposables.push(geometry, material);
          const mesh = new THREE.Mesh(geometry, material);
          mesh.position.set(fixture.centerXM, height / 2, fixture.centerYM);
          mesh.rotation.y = (-Number(fixture.rotationDeg || 0) * Math.PI) / 180;
          mesh.castShadow = true;
          mesh.receiveShadow = true;
          mesh.userData.coordinateAuthority = fixture.coordinateAuthority;
          scene.add(mesh);
        }

        const center = new THREE.Vector3(sceneModel.floor.widthM / 2, 1.2, sceneModel.floor.depthM / 2);
        const picker = (sceneModel.architecture || []).find((row) => row.type === "picker_entry");
        if (preset === "picker" && picker) {
          camera.position.set(picker.centerXM, 1.62, picker.centerYM);
          const dispatch = (sceneModel.architecture || []).find((row) => row.type === "dispatch");
          const target = dispatch
            ? new THREE.Vector3(dispatch.centerXM, 1.2, dispatch.centerYM)
            : center;
          camera.lookAt(target);
          center.copy(target);
        } else if (preset === "top") {
          camera.position.set(center.x, span * 1.35, center.z + 0.001);
        } else {
          camera.position.set(
            sceneModel.floor.widthM * 0.52,
            Math.max(6.5, span * 0.72),
            sceneModel.floor.depthM + Math.max(5.5, span * 0.45)
          );
          camera.lookAt(center);
        }

        controls = new OrbitControls(camera, renderer.domElement);
        controls.enableDamping = true;
        controls.dampingFactor = 0.075;
        controls.target.copy(center);
        controls.maxDistance = Math.max(14, span * 2.6);
        controls.update();

        const resize = () => {
          if (!renderer || !mountRef.current) return;
          const width = Math.max(1, mountRef.current.clientWidth || 1);
          const height = Math.max(380, mountRef.current.clientHeight || 520);
          renderer.setSize(width, height, false);
          camera.aspect = width / height;
          camera.updateProjectionMatrix();
        };
        resizeObserver = new ResizeObserver(resize);
        resizeObserver.observe(host);
        resize();

        const animate = () => {
          if (disposed) return;
          controls.update();
          renderer.render(scene, camera);
          frame = requestAnimationFrame(animate);
        };
        animate();
        setState("ready");
      } catch {
        if (!disposed) setState("error");
      }
    }

    mount();
    return () => {
      disposed = true;
      if (frame) cancelAnimationFrame(frame);
      resizeObserver?.disconnect();
      controls?.dispose();
      renderer?.dispose();
      environmentTarget?.dispose?.();
      const seen = new Set();
      for (const item of disposables) {
        if (!item || seen.has(item)) continue;
        seen.add(item);
        if (item.material) disposeMaterial(item.material, seen);
        item.dispose?.();
      }
      if (mountRef.current) mountRef.current.replaceChildren();
    };
  }, [ariaLabel, errorLabel, loadingLabel, preset, sceneModel]);

  return (
    <div className="eay-scanned-twin-scene">
      {state === "loading" ? <div className="eay-scanned-twin-state" role="status">{loadingLabel}</div> : null}
      {state === "error" ? <div className="eay-scanned-twin-state is-error" role="alert">{errorLabel}</div> : null}
      <div
        ref={mountRef}
        className="eay-scanned-twin-canvas"
        data-state={state}
        data-scene-contract={sceneModel?.contract || "missing"}
        data-source-kind={sceneModel?.sourceKind || "missing"}
        data-geometry-authority={sceneModel?.geometryAuthority || "missing"}
      />
    </div>
  );
}
