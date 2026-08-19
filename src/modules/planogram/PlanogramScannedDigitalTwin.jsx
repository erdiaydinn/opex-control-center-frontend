import React, { useEffect, useMemo, useRef, useState } from "react";
import { Box, ScanSearch } from "lucide-react";

import { translatePlanogramScannedTwin } from "../../platform/i18n/planogramScannedTwinMessages.js";
import "./planogram-scanned-twin.css";

const OPERATIONAL_TYPES = new Set([
  "picker_entry",
  "picker_exit",
  "inbound",
  "dispatch",
  "no_go",
  "technical",
]);

function elementHeight(type) {
  if (type === "wall" || type === "column") return 2.7;
  if (type === "chiller" || type === "freezer") return 1.9;
  if (type === "door" || type === "emergency_exit") return 2.1;
  return 0.06;
}

function elementColor(type) {
  const colors = {
    wall: 0x64748b,
    column: 0x475569,
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

function disposeMaterial(material) {
  if (!material) return;
  for (const row of Array.isArray(material) ? material : [material]) row?.dispose?.();
}

function ScannedTwinScene({ architecture, fixtures, preset, t }) {
  const mountRef = useRef(null);
  const [state, setState] = useState("loading");

  useEffect(() => {
    let disposed = false;
    let renderer;
    let controls;
    let resizeObserver;
    let frame;
    const disposables = [];

    async function mount() {
      setState("loading");
      try {
        const THREE = await import("three");
        const { OrbitControls } = await import("three/examples/jsm/controls/OrbitControls.js");
        if (disposed || !mountRef.current) return;

        const scene = new THREE.Scene();
        scene.background = new THREE.Color(0x090b10);
        scene.fog = new THREE.Fog(0x090b10, 20, 70);
        const camera = new THREE.PerspectiveCamera(52, 1, 0.04, 200);
        renderer = new THREE.WebGLRenderer({ antialias: true, powerPreference: "high-performance" });
        renderer.setPixelRatio(Math.min(window.devicePixelRatio || 1, 2));
        renderer.shadowMap.enabled = true;
        renderer.outputColorSpace = THREE.SRGBColorSpace;
        renderer.toneMapping = THREE.ACESFilmicToneMapping;
        renderer.toneMappingExposure = 1.08;
        mountRef.current.replaceChildren(renderer.domElement);
        renderer.domElement.tabIndex = 0;
        renderer.domElement.setAttribute("role", "img");
        renderer.domElement.setAttribute("aria-label", t("title"));

        scene.add(new THREE.HemisphereLight(0xffffff, 0x111827, 1.6));
        const key = new THREE.DirectionalLight(0xffffff, 2.3);
        key.position.set(architecture.floor_width_m * 0.35, 10, architecture.floor_depth_m * 0.25);
        key.castShadow = true;
        scene.add(key);

        const floorGeometry = new THREE.PlaneGeometry(architecture.floor_width_m, architecture.floor_depth_m);
        const floorMaterial = new THREE.MeshStandardMaterial({ color: 0x171a22, roughness: 0.92 });
        disposables.push(floorGeometry, floorMaterial);
        const floor = new THREE.Mesh(floorGeometry, floorMaterial);
        floor.rotation.x = -Math.PI / 2;
        floor.position.set(architecture.floor_width_m / 2, 0, architecture.floor_depth_m / 2);
        floor.receiveShadow = true;
        scene.add(floor);

        for (const element of architecture.elements || []) {
          const type = String(element.element_type || "");
          const height = elementHeight(type);
          if (type === "picker_entry" || type === "picker_exit") {
            const geometry = new THREE.CylinderGeometry(0.16, 0.16, 0.05, 24);
            const material = new THREE.MeshStandardMaterial({ color: elementColor(type), emissive: elementColor(type), emissiveIntensity: 0.25 });
            disposables.push(geometry, material);
            const marker = new THREE.Mesh(geometry, material);
            marker.position.set(element.center_x_m, 0.04, element.center_y_m);
            scene.add(marker);
            continue;
          }
          const geometry = new THREE.BoxGeometry(element.width_m, height, element.depth_m);
          const operational = OPERATIONAL_TYPES.has(type);
          const material = new THREE.MeshStandardMaterial({
            color: elementColor(type),
            roughness: operational ? 0.72 : 0.58,
            metalness: 0.04,
            transparent: operational,
            opacity: operational ? 0.38 : 0.9,
          });
          disposables.push(geometry, material);
          const mesh = new THREE.Mesh(geometry, material);
          mesh.position.set(element.center_x_m, height / 2, element.center_y_m);
          mesh.rotation.y = (-Number(element.rotation_deg || 0) * Math.PI) / 180;
          mesh.castShadow = !operational;
          mesh.receiveShadow = true;
          scene.add(mesh);
        }

        for (const fixture of fixtures || []) {
          const geometry = new THREE.BoxGeometry(fixture.width_m, 1.6, fixture.depth_m);
          const material = new THREE.MeshStandardMaterial({ color: 0xdf1067, roughness: 0.5, metalness: 0.08, transparent: true, opacity: 0.42 });
          disposables.push(geometry, material);
          const mesh = new THREE.Mesh(geometry, material);
          mesh.position.set(fixture.center_x_m, 0.8, fixture.center_y_m);
          mesh.rotation.y = (-Number(fixture.rotation_deg || 0) * Math.PI) / 180;
          mesh.castShadow = true;
          mesh.receiveShadow = true;
          scene.add(mesh);
        }

        const picker = (architecture.elements || []).find((row) => row.element_type === "picker_entry");
        const center = new THREE.Vector3(architecture.floor_width_m / 2, 1.2, architecture.floor_depth_m / 2);
        if (preset === "picker" && picker) {
          camera.position.set(picker.center_x_m, 1.62, picker.center_y_m);
          const dispatch = (architecture.elements || []).find((row) => row.element_type === "dispatch");
          const target = dispatch
            ? new THREE.Vector3(dispatch.center_x_m, 1.2, dispatch.center_y_m)
            : center;
          camera.lookAt(target);
          center.copy(target);
        } else {
          const span = Math.max(architecture.floor_width_m, architecture.floor_depth_m);
          camera.position.set(
            architecture.floor_width_m * 0.52,
            Math.max(6.5, span * 0.72),
            architecture.floor_depth_m + Math.max(5.5, span * 0.45)
          );
          camera.lookAt(center);
        }

        controls = new OrbitControls(camera, renderer.domElement);
        controls.enableDamping = true;
        controls.dampingFactor = 0.08;
        controls.target.copy(center);
        controls.maxDistance = Math.max(14, Math.max(architecture.floor_width_m, architecture.floor_depth_m) * 2.2);
        controls.update();

        const resize = () => {
          const width = Math.max(1, mountRef.current?.clientWidth || 1);
          const height = Math.max(380, mountRef.current?.clientHeight || 520);
          renderer.setSize(width, height, false);
          camera.aspect = width / height;
          camera.updateProjectionMatrix();
        };
        resizeObserver = new ResizeObserver(resize);
        resizeObserver.observe(mountRef.current);
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
      for (const item of disposables) item?.dispose?.();
      if (mountRef.current) mountRef.current.replaceChildren();
    };
  }, [architecture, fixtures, preset, t]);

  return (
    <div className="eay-scanned-twin-scene">
      {state === "loading" ? <div className="eay-scanned-twin-state" role="status">{t("loading")}</div> : null}
      {state === "error" ? <div className="eay-scanned-twin-state is-error" role="alert">{t("error")}</div> : null}
      <div ref={mountRef} className="eay-scanned-twin-canvas" data-state={state} />
    </div>
  );
}

export default function PlanogramScannedDigitalTwin({ reviewedResult, scan, locale, formatNumber }) {
  const t = useMemo(() => (key) => translatePlanogramScannedTwin(locale, key), [locale]);
  const [preset, setPreset] = useState("overview");
  const architecture = reviewedResult?.reviewed_store_dna_v2_preview?.architecture || null;
  if (!architecture?.elements?.length) return null;
  const operationalCount = architecture.elements.filter((row) => OPERATIONAL_TYPES.has(row.element_type)).length;
  const measuredCount = architecture.elements.length - operationalCount;
  const fixtureCount = scan?.recognized_fixtures?.length || 0;

  return (
    <section className="eay-scanned-twin">
      <header>
        <div><ScanSearch size={21} aria-hidden="true" /><div><h3>{t("title")}</h3><p>{t("subtitle")}</p></div></div>
        <span>{t("previewOnly")}</span>
      </header>
      <div className="eay-scanned-twin-metrics">
        <div><Box size={16} aria-hidden="true" /><span>{t("measuredElements")}</span><strong>{formatNumber(measuredCount)}</strong></div>
        <div><span>{t("operationalZones")}</span><strong>{formatNumber(operationalCount)}</strong></div>
        <div><span>{t("fixtures")}</span><strong>{formatNumber(fixtureCount)}</strong></div>
      </div>
      <div className="eay-scanned-twin-presets">
        <button type="button" aria-pressed={preset === "overview"} onClick={() => setPreset("overview")}>{t("overview")}</button>
        <button type="button" aria-pressed={preset === "picker"} onClick={() => setPreset("picker")}>{t("pickerView")}</button>
      </div>
      <ScannedTwinScene architecture={architecture} fixtures={scan?.recognized_fixtures || []} preset={preset} t={t} />
      <p className="eay-scanned-twin-boundary">{t("boundary")}</p>
    </section>
  );
}
