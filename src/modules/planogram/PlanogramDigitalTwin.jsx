import React, { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { Box, Cuboid, Grid2X2, Rotate3D, Route, ScanLine } from "lucide-react";

import { translatePlanogramDigitalTwin } from "../../platform/i18n/planogramDigitalTwinMessages.js";
import {
  buildPlanogramDigitalTwinModel,
  PLANOGRAM_DIGITAL_TWIN_LIMITS,
} from "./planogramDigitalTwinModel.js";
import "./planogram-digital-twin.css";

const SVG_WIDTH = 1000;
const SVG_MAX_HEIGHT = 620;
const SVG_MIN_HEIGHT = 360;
const VISIBLE_ROUTE_PATHS = 3;
const VISIBLE_ROUTE_ROWS = 5;

function clamp(value, min, max) {
  return Math.min(max, Math.max(min, value));
}

function fixtureClass(type) {
  const normalized = String(type || "").toLowerCase();
  if (normalized.includes("pallet")) return "pallet";
  if (normalized.includes("frozen") || normalized.includes("freezer")) return "frozen";
  if (normalized.includes("chilled") || normalized.includes("cooler")) return "chilled";
  return "regular";
}

function architectureClass(type) {
  return String(type || "unknown").replace(/[^a-z0-9_-]/gi, "-").toLowerCase();
}

function Twin2D({ model, t, formatNumber }) {
  const ratio = model.floor.depthM / Math.max(model.floor.widthM, 0.1);
  const height = clamp(Math.round(SVG_WIDTH * ratio), SVG_MIN_HEIGHT, SVG_MAX_HEIGHT);
  const padding = 34;
  const usableWidth = SVG_WIDTH - padding * 2;
  const usableHeight = height - padding * 2;
  const scale = Math.min(
    usableWidth / Math.max(model.floor.widthM, 0.1),
    usableHeight / Math.max(model.floor.depthM, 0.1)
  );
  const offsetX = (SVG_WIDTH - model.floor.widthM * scale) / 2;
  const offsetY = (height - model.floor.depthM * scale) / 2;
  const y = (value, depth = 0) => offsetY + (model.floor.depthM - value - depth) * scale;
  const routeHotspots = model.route?.available ? model.route.hotspots.slice(0, VISIBLE_ROUTE_PATHS) : [];

  return (
    <div className="eay-twin-2d-wrap">
      <svg className="eay-twin-2d" viewBox={`0 0 ${SVG_WIDTH} ${height}`} role="img" aria-label={t("view2d")}>
        <defs>
          <pattern id="eay-twin-grid" width="20" height="20" patternUnits="userSpaceOnUse">
            <path d="M 20 0 L 0 0 0 20" className="eay-twin-grid-line" fill="none" />
          </pattern>
        </defs>
        <rect x={offsetX} y={offsetY} width={model.floor.widthM * scale} height={model.floor.depthM * scale} className="eay-twin-floor" />
        <rect x={offsetX} y={offsetY} width={model.floor.widthM * scale} height={model.floor.depthM * scale} fill="url(#eay-twin-grid)" pointerEvents="none" />

        {model.elements.map((element) => {
          const width = element.footprintWidthM * scale;
          const depth = element.footprintDepthM * scale;
          const x = offsetX + element.xM * scale;
          const top = y(element.yM, element.footprintDepthM);
          const clearance = element.type === "emergency_exit" ? element.clearanceM * scale : 0;
          return (
            <g key={`element-${element.id}`}>
              {clearance > 0 ? <rect x={x - clearance} y={top - clearance} width={width + clearance * 2} height={depth + clearance * 2} rx="5" className="eay-twin-egress-clearance" /> : null}
              <rect x={x} y={top} width={width} height={depth} rx="3" className={`eay-twin-architecture eay-twin-architecture--${architectureClass(element.type)}`} />
              <title>{`${t("architecture")}: ${element.type} · ${element.id}`}</title>
            </g>
          );
        })}

        {routeHotspots.map((hotspot) => {
          const points = hotspot.pathM.map(([xM, yM]) => `${offsetX + xM * scale},${y(yM)}`).join(" ");
          return points ? (
            <polyline
              key={`route-${hotspot.moduleId}`}
              points={points}
              className="eay-twin-route-path"
              data-route-rank={hotspot.rank}
              vectorEffect="non-scaling-stroke"
            >
              <title>{`${hotspot.moduleId} · ${formatNumber(hotspot.distanceM)} m`}</title>
            </polyline>
          ) : null;
        })}
        {model.route?.pickerEntryM ? (
          <circle
            cx={offsetX + model.route.pickerEntryM[0] * scale}
            cy={y(model.route.pickerEntryM[1])}
            r="7"
            className="eay-twin-route-origin"
            vectorEffect="non-scaling-stroke"
          />
        ) : null}

        {model.modules.map((module) => {
          const width = Math.max(module.footprintWidthM * scale, 10);
          const depth = Math.max(module.footprintDepthM * scale, 8);
          const x = offsetX + module.xM * scale;
          const top = y(module.yM, module.footprintDepthM);
          return (
            <g key={module.key}>
              <rect
                x={x}
                y={top}
                width={width}
                height={depth}
                rx="4"
                className={`eay-twin-module eay-twin-module--${fixtureClass(module.fixtureType)}${module.routeHotspot ? " is-route-hotspot" : ""}`}
                data-coordinate-authority={module.coordinateAuthority}
                data-route-rank={module.routeHotspot?.rank || undefined}
              />
              {width > 54 && depth > 20 ? <text x={x + width / 2} y={top + depth / 2 + 4} className="eay-twin-module-label">{module.aisleId} · {module.moduleId}</text> : null}
              <title>{`${module.aisleId} / ${module.moduleId} · ${t("products")}: ${formatNumber(module.productCount)}${module.routeDistanceM != null ? ` · ${formatNumber(module.routeDistanceM)} m` : ""}`}</title>
            </g>
          );
        })}
      </svg>
      <div className="eay-twin-legend" aria-label={t("fixture")}>
        <span><i className="regular" />{t("fixtureRegular")}</span>
        <span><i className="chilled" />{t("fixtureChilled")}</span>
        <span><i className="frozen" />{t("fixtureFrozen")}</span>
        <span><i className="pallet" />{t("fixturePallet")}</span>
      </div>
    </div>
  );
}

function buildProductInstances(THREE, model) {
  const matrices = [];
  const maxInstances = PLANOGRAM_DIGITAL_TWIN_LIMITS.maxProductInstances3d;
  const up = new THREE.Vector3(0, 1, 0);

  outer: for (const module of model.modules) {
    const rotation = (module.rotationDeg * Math.PI) / 180;
    const quaternion = new THREE.Quaternion().setFromAxisAngle(up, -rotation);
    const shelves = module.shelves || [];
    const shelfCount = Math.max(1, shelves.length);
    const levelHeight = Math.max(0.28, 1.8 / shelfCount);

    for (const [shelfIndex, shelf] of shelves.entries()) {
      const products = shelf?.products || [];
      if (!products.length) continue;
      const perRow = Math.max(1, Math.ceil(Math.sqrt(products.length)));
      const cellW = Math.max(0.06, module.widthM / perRow);
      const rows = Math.max(1, Math.ceil(products.length / perRow));
      const cellD = Math.max(0.05, module.depthM / rows);

      for (const [productIndex, product] of products.entries()) {
        if (matrices.length >= maxInstances) break outer;
        const col = productIndex % perRow;
        const row = Math.floor(productIndex / perRow);
        const rawW = Number(product?.width_cm || 0) / 100;
        const rawH = Number(product?.height_cm || 0) / 100;
        const rawD = Number(product?.depth_cm || 0) / 100;
        const width = clamp(rawW || cellW * 0.72, 0.04, cellW * 0.9);
        const productHeight = clamp(rawH || levelHeight * 0.56, 0.05, levelHeight * 0.72);
        const depth = clamp(rawD || cellD * 0.72, 0.04, cellD * 0.9);
        const localX = -module.widthM / 2 + cellW * (col + 0.5);
        const localZ = -module.depthM / 2 + cellD * (row + 0.5);
        const cos = Math.cos(-rotation);
        const sin = Math.sin(-rotation);
        const worldX = module.centerXM + localX * cos - localZ * sin;
        const worldZ = module.centerYM + localX * sin + localZ * cos;
        const worldY = 0.08 + shelfIndex * levelHeight + productHeight / 2;
        const matrix = new THREE.Matrix4();
        matrix.compose(new THREE.Vector3(worldX, worldY, worldZ), quaternion, new THREE.Vector3(width, productHeight, depth));
        matrices.push(matrix);
      }
    }
  }
  return matrices;
}

function addRouteLines(THREE, scene, model, disposables) {
  for (const hotspot of model.route?.hotspots?.slice(0, VISIBLE_ROUTE_PATHS) || []) {
    if (hotspot.pathM.length < 2) continue;
    const geometry = new THREE.BufferGeometry().setFromPoints(
      hotspot.pathM.map(([xM, yM]) => new THREE.Vector3(xM, 0.035 + hotspot.rank * 0.006, yM))
    );
    const material = new THREE.LineBasicMaterial({
      color: 0xdf1067,
      transparent: true,
      opacity: clamp(1 - (hotspot.rank - 1) * 0.22, 0.42, 1),
    });
    disposables.push(geometry, material);
    scene.add(new THREE.Line(geometry, material));
  }
}

function Twin3D({ model, t, onViewerReady }) {
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

        const host = mountRef.current;
        const scene = new THREE.Scene();
        scene.background = new THREE.Color(0x0a0b10);
        const camera = new THREE.PerspectiveCamera(45, 1, 0.05, 500);
        renderer = new THREE.WebGLRenderer({ antialias: true, alpha: false, powerPreference: "high-performance" });
        renderer.setPixelRatio(Math.min(window.devicePixelRatio || 1, 2));
        renderer.shadowMap.enabled = true;
        renderer.shadowMap.type = THREE.PCFSoftShadowMap;
        host.replaceChildren(renderer.domElement);
        renderer.domElement.setAttribute("role", "img");
        renderer.domElement.setAttribute("aria-label", t("canvasLabel"));
        renderer.domElement.tabIndex = 0;

        scene.add(new THREE.HemisphereLight(0xffffff, 0x172033, 1.25));
        const key = new THREE.DirectionalLight(0xffffff, 2.2);
        key.position.set(model.floor.widthM * 0.35, 12, model.floor.depthM * 0.35);
        key.castShadow = true;
        scene.add(key);

        const floorGeometry = new THREE.PlaneGeometry(model.floor.widthM, model.floor.depthM);
        const floorMaterial = new THREE.MeshStandardMaterial({ color: 0x171922, roughness: 0.9, metalness: 0.05 });
        disposables.push(floorGeometry, floorMaterial);
        const floor = new THREE.Mesh(floorGeometry, floorMaterial);
        floor.rotation.x = -Math.PI / 2;
        floor.position.set(model.floor.widthM / 2, 0, model.floor.depthM / 2);
        floor.receiveShadow = true;
        scene.add(floor);

        const grid = new THREE.GridHelper(Math.max(model.floor.widthM, model.floor.depthM), Math.max(10, Math.round(Math.max(model.floor.widthM, model.floor.depthM))), 0x343845, 0x242733);
        grid.position.set(model.floor.widthM / 2, 0.006, model.floor.depthM / 2);
        scene.add(grid);
        addRouteLines(THREE, scene, model, disposables);

        const architectureMaterials = {
          wall: new THREE.MeshStandardMaterial({ color: 0x4b5563, roughness: 0.85 }),
          column: new THREE.MeshStandardMaterial({ color: 0x64748b, roughness: 0.75 }),
          no_go: new THREE.MeshStandardMaterial({ color: 0x7f1d1d, roughness: 0.8 }),
          technical: new THREE.MeshStandardMaterial({ color: 0x78350f, roughness: 0.8 }),
          emergency_exit: new THREE.MeshStandardMaterial({ color: 0x047857, roughness: 0.65 }),
          picker_entry: new THREE.MeshStandardMaterial({ color: 0xdf1067, roughness: 0.55 }),
          default: new THREE.MeshStandardMaterial({ color: 0x475569, roughness: 0.8 }),
        };
        disposables.push(...Object.values(architectureMaterials));

        for (const element of model.elements) {
          const elementHeight = element.type === "wall" || element.type === "column" ? 2.6 : 0.08;
          const geometry = new THREE.BoxGeometry(element.widthM, elementHeight, element.depthM);
          disposables.push(geometry);
          const mesh = new THREE.Mesh(geometry, architectureMaterials[element.type] || architectureMaterials.default);
          mesh.position.set(element.centerXM, elementHeight / 2, element.centerYM);
          mesh.rotation.y = (-element.rotationDeg * Math.PI) / 180;
          mesh.castShadow = true;
          mesh.receiveShadow = true;
          scene.add(mesh);
        }

        const fixtureMaterials = {
          regular: new THREE.MeshStandardMaterial({ color: 0x7c8597, roughness: 0.55, metalness: 0.2 }),
          chilled: new THREE.MeshStandardMaterial({ color: 0x0891b2, roughness: 0.4, metalness: 0.15 }),
          frozen: new THREE.MeshStandardMaterial({ color: 0x2563eb, roughness: 0.4, metalness: 0.15 }),
          pallet: new THREE.MeshStandardMaterial({ color: 0x92400e, roughness: 0.8 }),
        };
        disposables.push(...Object.values(fixtureMaterials));
        const shelfMaterial = new THREE.MeshStandardMaterial({ color: 0xd1d5db, roughness: 0.45, metalness: 0.25 });
        disposables.push(shelfMaterial);

        for (const module of model.modules) {
          const kind = fixtureClass(module.fixtureType);
          const shelfCount = Math.max(1, module.shelfCount || 1);
          const moduleHeight = kind === "pallet" ? 0.18 : Math.max(1.5, shelfCount * 0.32);
          const frameGeometry = new THREE.BoxGeometry(module.widthM, moduleHeight, module.depthM);
          disposables.push(frameGeometry);
          const frame = new THREE.Mesh(frameGeometry, fixtureMaterials[kind]);
          frame.position.set(module.centerXM, moduleHeight / 2, module.centerYM);
          frame.rotation.y = (-module.rotationDeg * Math.PI) / 180;
          frame.castShadow = true;
          frame.receiveShadow = true;
          scene.add(frame);

          if (kind !== "pallet") {
            for (let shelfIndex = 1; shelfIndex < shelfCount; shelfIndex += 1) {
              const shelfGeometry = new THREE.BoxGeometry(module.widthM * 0.98, 0.025, module.depthM * 0.98);
              disposables.push(shelfGeometry);
              const shelf = new THREE.Mesh(shelfGeometry, shelfMaterial);
              shelf.position.copy(frame.position);
              shelf.position.y = (moduleHeight / shelfCount) * shelfIndex;
              shelf.rotation.y = frame.rotation.y;
              scene.add(shelf);
            }
          }
        }

        const matrices = buildProductInstances(THREE, model);
        if (matrices.length) {
          const productGeometry = new THREE.BoxGeometry(1, 1, 1);
          const productMaterial = new THREE.MeshStandardMaterial({ color: 0xdf1067, roughness: 0.5, metalness: 0.04 });
          disposables.push(productGeometry, productMaterial);
          const products = new THREE.InstancedMesh(productGeometry, productMaterial, matrices.length);
          matrices.forEach((matrix, index) => products.setMatrixAt(index, matrix));
          products.instanceMatrix.needsUpdate = true;
          products.castShadow = true;
          scene.add(products);
        }

        controls = new OrbitControls(camera, renderer.domElement);
        controls.enableDamping = true;
        controls.dampingFactor = 0.07;
        controls.maxPolarAngle = Math.PI / 2.02;
        controls.minDistance = 1.5;
        controls.maxDistance = Math.max(model.floor.widthM, model.floor.depthM) * 4;

        const center = new THREE.Vector3(model.floor.widthM / 2, 0.6, model.floor.depthM / 2);
        const maxDimension = Math.max(model.floor.widthM, model.floor.depthM, 4);
        const setPreset = (preset = "perspective") => {
          if (preset === "top") camera.position.set(center.x, maxDimension * 1.35, center.z + 0.001);
          else if (preset === "front") camera.position.set(center.x, maxDimension * 0.38, model.floor.depthM + maxDimension * 0.85);
          else camera.position.set(model.floor.widthM + maxDimension * 0.45, maxDimension * 0.72, model.floor.depthM + maxDimension * 0.45);
          controls.target.copy(center);
          controls.update();
        };
        setPreset("perspective");
        onViewerReady?.({ setPreset });

        const resize = () => {
          if (!renderer) return;
          const width = Math.max(1, host.clientWidth);
          const sceneHeight = Math.max(320, host.clientHeight || 520);
          renderer.setSize(width, sceneHeight, false);
          camera.aspect = width / sceneHeight;
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
      for (const item of disposables) item?.dispose?.();
      if (mountRef.current) mountRef.current.replaceChildren();
      onViewerReady?.(null);
    };
  }, [model, onViewerReady, t]);

  return (
    <div className="eay-twin-3d-shell">
      {state === "loading" ? <div className="eay-twin-3d-state" role="status">{t("threeLoading")}</div> : null}
      {state === "error" ? <div className="eay-twin-3d-state eay-twin-3d-state--error" role="alert">{t("threeError")}</div> : null}
      <div ref={mountRef} className="eay-twin-3d" data-state={state} />
    </div>
  );
}

function RouteHotspots({ model, formatNumber, t }) {
  const rows = model.route?.available ? model.route.hotspots.slice(0, VISIBLE_ROUTE_ROWS) : [];
  if (!rows.length) return null;
  return (
    <section className="eay-twin-route-hotspots" aria-label={t("route")}>
      <header><Route size={16} aria-hidden="true" /><strong>{t("route")}</strong></header>
      <ol>
        {rows.map((row) => (
          <li key={row.moduleId}>
            <span className="eay-twin-route-rank">{row.rank}</span>
            <code>{row.moduleId}</code>
            <span>{formatNumber(row.distanceM)} m</span>
            <strong>Σ {formatNumber(row.weightedCost)}</strong>
          </li>
        ))}
      </ol>
    </section>
  );
}

export default function PlanogramDigitalTwin({ engineResult, candidate, locale, formatNumber }) {
  const [view, setView] = useState("2d");
  const viewerRef = useRef(null);
  const t = useMemo(() => (key) => translatePlanogramDigitalTwin(locale, key), [locale]);
  const model = useMemo(() => buildPlanogramDigitalTwinModel(engineResult, candidate), [candidate, engineResult]);
  const bindViewer = useCallback((viewer) => { viewerRef.current = viewer; }, []);

  if (!model) return <section className="eay-twin-empty" role="status"><ScanLine size={20} aria-hidden="true" />{t("noGeometry")}</section>;

  const measured = model.geometryAuthority === "measured";
  const routeText = model.route?.available ? `${formatNumber(model.route.value)} m` : t("routeUnavailable");

  return (
    <section className="eay-twin" data-geometry-authority={model.geometryAuthority}>
      <header className="eay-twin-head">
        <div className="eay-twin-title"><Cuboid size={24} aria-hidden="true" /><div><h3>{t("title")}</h3><p>{t("subtitle")}</p></div></div>
        <div className="eay-twin-tabs" role="tablist" aria-label={t("title")}>
          <button type="button" role="tab" aria-selected={view === "2d"} onClick={() => setView("2d")}><Grid2X2 size={17} aria-hidden="true" />{t("view2d")}</button>
          <button type="button" role="tab" aria-selected={view === "3d"} onClick={() => setView("3d")}><Box size={17} aria-hidden="true" />{t("view3d")}</button>
        </div>
      </header>

      <div className={`eay-twin-truth ${measured ? "is-measured" : "is-topology"}`} role="status">
        <strong>{measured ? t("measured") : t("topology")}</strong>
        <span>{measured ? t("measuredHint") : t("topologyWarning")}</span>
        {model.architectureSourceRef ? <code>{model.architectureSourceRef}</code> : null}
      </div>

      <div className="eay-twin-kpis">
        <div><span>{t("modules")}</span><strong>{formatNumber(model.stats.moduleCount)}</strong></div>
        <div><span>{t("products")}</span><strong>{formatNumber(model.stats.placedProductCount)}</strong></div>
        <div><span>{t("facings")}</span><strong>{formatNumber(model.stats.facingCount)}</strong></div>
        <div><span>{t("coordinates")}</span><strong>{formatNumber(model.stats.measuredCoordinatePct)}%</strong></div>
        <div><span><Route size={15} aria-hidden="true" />{t("route")}</span><strong>{routeText}</strong></div>
      </div>
      <RouteHotspots model={model} formatNumber={formatNumber} t={t} />

      {view === "2d" ? <Twin2D model={model} t={t} formatNumber={formatNumber} /> : null}
      {view === "3d" ? <><div className="eay-twin-camera-bar" aria-label={t("view3d")}>
        <button type="button" onClick={() => viewerRef.current?.setPreset("perspective")}><Rotate3D size={16} aria-hidden="true" />{t("perspective")}</button>
        <button type="button" onClick={() => viewerRef.current?.setPreset("top")}>{t("top")}</button>
        <button type="button" onClick={() => viewerRef.current?.setPreset("front")}>{t("front")}</button>
        <button type="button" onClick={() => viewerRef.current?.setPreset("perspective")}>{t("reset")}</button>
      </div><Twin3D model={model} t={t} onViewerReady={bindViewer} /><p className="eay-twin-interaction-hint">{t("interactionHint")}</p></> : null}
    </section>
  );
}
