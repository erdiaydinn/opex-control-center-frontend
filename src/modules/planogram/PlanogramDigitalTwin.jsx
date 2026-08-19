import React, { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { Box, Cuboid, Grid2X2, Rotate3D, Route, ScanLine } from "lucide-react";

import { translatePlanogramDigitalTwin } from "../../platform/i18n/planogramDigitalTwinMessages.js";
import {
  buildPlanogramDigitalTwinModel,
  PLANOGRAM_DIGITAL_TWIN_LIMITS,
} from "./planogramDigitalTwinModel.js";
import {
  engineeringScaleBar,
  rotatedRectSvgPoints,
  svgPointString,
} from "./planogramEngineering2D.js";
import "./planogram-digital-twin.css";

const SVG_WIDTH = 1000;
const SVG_MAX_HEIGHT = 620;
const SVG_MIN_HEIGHT = 360;
const VISIBLE_ROUTE_PATHS = 3;
const VISIBLE_ROUTE_ROWS = 5;
const FIXTURE_POST_M = 0.035;
const SHELF_BOARD_M = 0.025;
const PRODUCT_GAP_M = 0.006;

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

function stableHue(value) {
  const text = String(value || "EAY");
  let hash = 2166136261;
  for (let index = 0; index < text.length; index += 1) {
    hash ^= text.charCodeAt(index);
    hash = Math.imul(hash, 16777619);
  }
  return ((hash >>> 0) % 360) / 360;
}

function productFacingCount(product) {
  const raw = Number(product?.facing_count ?? product?.facing ?? 1);
  return Number.isFinite(raw) ? clamp(Math.round(raw), 1, 40) : 1;
}

function moduleHeight(module) {
  if (fixtureClass(module.fixtureType) === "pallet") return 0.18;
  const shelfCount = Math.max(1, module.shelfCount || 1);
  return Math.max(1.5, shelfCount * 0.32);
}

function Twin2D({ model, t, formatNumber }) {
  const ratio = model.floor.depthM / Math.max(model.floor.widthM, 0.1);
  const height = clamp(Math.round(SVG_WIDTH * ratio), SVG_MIN_HEIGHT, SVG_MAX_HEIGHT);
  const padding = 56;
  const usableWidth = SVG_WIDTH - padding * 2;
  const usableHeight = height - padding * 2;
  const scale = Math.min(
    usableWidth / Math.max(model.floor.widthM, 0.1),
    usableHeight / Math.max(model.floor.depthM, 0.1)
  );
  const offsetX = (SVG_WIDTH - model.floor.widthM * scale) / 2;
  const offsetY = (height - model.floor.depthM * scale) / 2;
  const y = (value) => offsetY + (model.floor.depthM - value) * scale;
  const projection = {
    offsetX,
    offsetY,
    floorDepthM: model.floor.depthM,
    scale,
  };
  const routeHotspots = model.route?.available ? model.route.hotspots.slice(0, VISIBLE_ROUTE_PATHS) : [];
  const floorRightX = offsetX + model.floor.widthM * scale;
  const floorBottomY = offsetY + model.floor.depthM * scale;
  const widthDimensionY = Math.min(height - 18, floorBottomY + 24);
  const depthDimensionX = Math.max(18, offsetX - 24);
  const scaleBar = engineeringScaleBar({ floorWidthM: model.floor.widthM, scale });
  const scaleBarStartX = floorRightX - scaleBar.pixels;
  const scaleBarY = offsetY + 18;

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

        <g className="eay-twin-engineering-dimensions" aria-hidden="true">
          <line x1={offsetX} y1={floorBottomY} x2={offsetX} y2={widthDimensionY} />
          <line x1={floorRightX} y1={floorBottomY} x2={floorRightX} y2={widthDimensionY} />
          <line x1={offsetX} y1={widthDimensionY} x2={floorRightX} y2={widthDimensionY} />
          <text x={(offsetX + floorRightX) / 2} y={widthDimensionY - 5}>{formatNumber(model.floor.widthM)} m</text>
          <line x1={offsetX} y1={offsetY} x2={depthDimensionX} y2={offsetY} />
          <line x1={offsetX} y1={floorBottomY} x2={depthDimensionX} y2={floorBottomY} />
          <line x1={depthDimensionX} y1={offsetY} x2={depthDimensionX} y2={floorBottomY} />
          <text
            x={depthDimensionX - 6}
            y={(offsetY + floorBottomY) / 2}
            transform={`rotate(-90 ${depthDimensionX - 6} ${(offsetY + floorBottomY) / 2})`}
          >
            {formatNumber(model.floor.depthM)} m
          </text>
          <line className="eay-twin-scale-bar" x1={scaleBarStartX} y1={scaleBarY} x2={floorRightX} y2={scaleBarY} />
          <line className="eay-twin-scale-tick" x1={scaleBarStartX} y1={scaleBarY - 5} x2={scaleBarStartX} y2={scaleBarY + 5} />
          <line className="eay-twin-scale-tick" x1={floorRightX} y1={scaleBarY - 5} x2={floorRightX} y2={scaleBarY + 5} />
          <text x={(scaleBarStartX + floorRightX) / 2} y={scaleBarY - 7}>{formatNumber(scaleBar.meters)} m</text>
        </g>

        {model.elements.map((element) => {
          const points = svgPointString(rotatedRectSvgPoints({
            centerXM: element.centerXM,
            centerYM: element.centerYM,
            widthM: element.widthM,
            depthM: element.depthM,
            rotationDeg: element.rotationDeg,
          }, projection));
          const clearancePoints = element.type === "emergency_exit" && element.clearanceM > 0
            ? svgPointString(rotatedRectSvgPoints({
              centerXM: element.centerXM,
              centerYM: element.centerYM,
              widthM: element.widthM + element.clearanceM * 2,
              depthM: element.depthM + element.clearanceM * 2,
              rotationDeg: element.rotationDeg,
            }, projection))
            : "";
          return (
            <g key={`element-${element.id}`} data-rotation-deg={element.rotationDeg}>
              {clearancePoints ? <polygon points={clearancePoints} className="eay-twin-egress-clearance" /> : null}
              <polygon points={points} className={`eay-twin-architecture eay-twin-architecture--${architectureClass(element.type)}`} />
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
          const points = svgPointString(rotatedRectSvgPoints({
            centerXM: module.centerXM,
            centerYM: module.centerYM,
            widthM: module.widthM,
            depthM: module.depthM,
            rotationDeg: module.rotationDeg,
          }, projection));
          const labelX = offsetX + module.centerXM * scale;
          const labelY = y(module.centerYM);
          const visibleSize = Math.max(module.widthM * scale, module.depthM * scale);
          return (
            <g key={module.key} data-rotation-deg={module.rotationDeg}>
              <polygon
                points={points}
                className={`eay-twin-module eay-twin-module--${fixtureClass(module.fixtureType)}${module.routeHotspot ? " is-route-hotspot" : ""}`}
                data-coordinate-authority={module.coordinateAuthority}
                data-route-rank={module.routeHotspot?.rank || undefined}
              />
              {visibleSize > 54 ? <text x={labelX} y={labelY + 4} className="eay-twin-module-label">{module.aisleId} · {module.moduleId}</text> : null}
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

function buildFacingInstances(THREE, model) {
  const instances = [];
  const maxInstances = PLANOGRAM_DIGITAL_TWIN_LIMITS.maxProductInstances3d;
  const up = new THREE.Vector3(0, 1, 0);
  let clippedFacingCount = 0;

  outer: for (const module of model.modules) {
    const rotation = (module.rotationDeg * Math.PI) / 180;
    const quaternion = new THREE.Quaternion().setFromAxisAngle(up, -rotation);
    const shelves = module.shelves || [];
    const shelfCount = Math.max(1, shelves.length);
    const height = moduleHeight(module);
    const levelHeight = fixtureClass(module.fixtureType) === "pallet"
      ? height
      : height / shelfCount;
    const leftEdge = -module.widthM / 2 + FIXTURE_POST_M * 1.6;
    const rightEdge = module.widthM / 2 - FIXTURE_POST_M * 1.6;
    const frontSign = module.side === "R" ? -1 : 1;

    for (const [shelfIndex, shelf] of shelves.entries()) {
      const products = shelf?.products || [];
      if (!products.length) continue;
      let cursorX = leftEdge;

      for (const product of products) {
        const facingCount = productFacingCount(product);
        const rawW = Number(product?.width_cm || 0) / 100;
        const rawH = Number(product?.height_cm || 0) / 100;
        const rawD = Number(product?.depth_cm || 0) / 100;
        const width = clamp(rawW || 0.08, 0.025, Math.max(0.03, module.widthM * 0.45));
        const productHeight = clamp(rawH || Math.min(0.22, levelHeight * 0.62), 0.035, Math.max(0.05, levelHeight * 0.8));
        const depth = clamp(rawD || 0.07, 0.025, Math.max(0.03, module.depthM * 0.82));
        const sku = String(product?.sku ?? product?.SKU ?? product?.product_name ?? "SKU");

        for (let facingIndex = 0; facingIndex < facingCount; facingIndex += 1) {
          if (instances.length >= maxInstances) break outer;
          if (cursorX + width > rightEdge + 1e-9) {
            clippedFacingCount += facingCount - facingIndex;
            break;
          }

          const localX = cursorX + width / 2;
          const frontInset = Math.min(module.depthM * 0.18, 0.045);
          const localZ = frontSign * (module.depthM / 2 - depth / 2 - frontInset);
          const cos = Math.cos(-rotation);
          const sin = Math.sin(-rotation);
          const worldX = module.centerXM + localX * cos - localZ * sin;
          const worldZ = module.centerYM + localX * sin + localZ * cos;
          const shelfBase = fixtureClass(module.fixtureType) === "pallet"
            ? height + SHELF_BOARD_M
            : shelfIndex * levelHeight + SHELF_BOARD_M;
          const worldY = shelfBase + productHeight / 2;
          const matrix = new THREE.Matrix4();
          matrix.compose(
            new THREE.Vector3(worldX, worldY, worldZ),
            quaternion,
            new THREE.Vector3(width, productHeight, depth)
          );
          instances.push({ matrix, hue: stableHue(sku) });
          cursorX += width + PRODUCT_GAP_M;
        }
      }
    }
  }

  return { instances, clippedFacingCount };
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

function addBoxToGroup(THREE, group, disposables, material, size, position, { castShadow = true } = {}) {
  const geometry = new THREE.BoxGeometry(size[0], size[1], size[2]);
  disposables.push(geometry);
  const mesh = new THREE.Mesh(geometry, material);
  mesh.position.set(position[0], position[1], position[2]);
  mesh.castShadow = castShadow;
  mesh.receiveShadow = true;
  group.add(mesh);
  return mesh;
}

function addOpenShelfFixture(THREE, scene, module, materials, disposables) {
  const kind = fixtureClass(module.fixtureType);
  const shelfCount = Math.max(1, module.shelfCount || 1);
  const height = moduleHeight(module);
  const group = new THREE.Group();
  group.position.set(module.centerXM, 0, module.centerYM);
  group.rotation.y = (-module.rotationDeg * Math.PI) / 180;
  scene.add(group);

  if (kind === "pallet") {
    const slab = addBoxToGroup(
      THREE,
      group,
      disposables,
      materials.pallet,
      [module.widthM, 0.12, module.depthM],
      [0, 0.06, 0]
    );
    slab.castShadow = true;
    const slatCount = 5;
    for (let index = 0; index < slatCount; index += 1) {
      const ratio = slatCount === 1 ? 0 : index / (slatCount - 1);
      const x = -module.widthM * 0.42 + module.widthM * 0.84 * ratio;
      addBoxToGroup(
        THREE,
        group,
        disposables,
        materials.shelf,
        [Math.max(0.035, module.widthM * 0.12), 0.025, module.depthM * 0.96],
        [x, 0.135, 0],
        { castShadow: false }
      );
    }
    return;
  }

  const postDepth = Math.max(0.04, Math.min(module.depthM * 0.16, 0.08));
  const postX = Math.max(0, module.widthM / 2 - FIXTURE_POST_M / 2);
  addBoxToGroup(THREE, group, disposables, materials.frame[kind], [FIXTURE_POST_M, height, postDepth], [-postX, height / 2, 0]);
  addBoxToGroup(THREE, group, disposables, materials.frame[kind], [FIXTURE_POST_M, height, postDepth], [postX, height / 2, 0]);
  addBoxToGroup(THREE, group, disposables, materials.frame[kind], [module.widthM, FIXTURE_POST_M, postDepth], [0, height - FIXTURE_POST_M / 2, 0]);

  for (let shelfIndex = 0; shelfIndex < shelfCount; shelfIndex += 1) {
    const y = shelfIndex * (height / shelfCount) + SHELF_BOARD_M / 2;
    addBoxToGroup(
      THREE,
      group,
      disposables,
      materials.shelf,
      [Math.max(0.05, module.widthM - FIXTURE_POST_M * 2.4), SHELF_BOARD_M, module.depthM * 0.94],
      [0, y, 0],
      { castShadow: false }
    );
  }

  if (kind === "chilled" || kind === "frozen") {
    const backDepth = Math.max(0.015, Math.min(0.03, module.depthM * 0.06));
    addBoxToGroup(
      THREE,
      group,
      disposables,
      materials.frame[kind],
      [Math.max(0.05, module.widthM - FIXTURE_POST_M * 2), height * 0.97, backDepth],
      [0, height * 0.49, -module.depthM / 2 + backDepth / 2],
      { castShadow: false }
    );
    const glassGeometry = new THREE.PlaneGeometry(
      Math.max(0.05, module.widthM - FIXTURE_POST_M * 2.5),
      height * 0.92
    );
    disposables.push(glassGeometry);
    const glass = new THREE.Mesh(glassGeometry, materials.glass);
    glass.position.set(0, height * 0.5, module.depthM / 2 + 0.002);
    group.add(glass);
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
        renderer.outputColorSpace = THREE.SRGBColorSpace;
        renderer.toneMapping = THREE.ACESFilmicToneMapping;
        renderer.toneMappingExposure = 1.05;
        host.replaceChildren(renderer.domElement);
        renderer.domElement.setAttribute("role", "img");
        renderer.domElement.setAttribute("aria-label", t("canvasLabel"));
        renderer.domElement.tabIndex = 0;

        scene.add(new THREE.HemisphereLight(0xffffff, 0x172033, 1.4));
        const key = new THREE.DirectionalLight(0xffffff, 2.6);
        key.position.set(model.floor.widthM * 0.35, 12, model.floor.depthM * 0.35);
        key.castShadow = true;
        scene.add(key);
        const fill = new THREE.DirectionalLight(0xbfd7ff, 0.85);
        fill.position.set(model.floor.widthM, 5, model.floor.depthM);
        scene.add(fill);

        const floorGeometry = new THREE.PlaneGeometry(model.floor.widthM, model.floor.depthM);
        const floorMaterial = new THREE.MeshStandardMaterial({ color: 0x171922, roughness: 0.88, metalness: 0.03 });
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
          wall: new THREE.MeshStandardMaterial({ color: 0x4b5563, roughness: 0.9 }),
          column: new THREE.MeshStandardMaterial({ color: 0x64748b, roughness: 0.78 }),
          no_go: new THREE.MeshStandardMaterial({ color: 0x7f1d1d, roughness: 0.82 }),
          technical: new THREE.MeshStandardMaterial({ color: 0x78350f, roughness: 0.82 }),
          emergency_exit: new THREE.MeshStandardMaterial({ color: 0x047857, roughness: 0.67 }),
          picker_entry: new THREE.MeshStandardMaterial({ color: 0xdf1067, roughness: 0.58 }),
          default: new THREE.MeshStandardMaterial({ color: 0x475569, roughness: 0.82 }),
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
          frame: {
            regular: new THREE.MeshStandardMaterial({ color: 0x7c8597, roughness: 0.48, metalness: 0.28 }),
            chilled: new THREE.MeshStandardMaterial({ color: 0x0891b2, roughness: 0.36, metalness: 0.2 }),
            frozen: new THREE.MeshStandardMaterial({ color: 0x2563eb, roughness: 0.36, metalness: 0.2 }),
          },
          pallet: new THREE.MeshStandardMaterial({ color: 0x92400e, roughness: 0.86 }),
          shelf: new THREE.MeshStandardMaterial({ color: 0xd1d5db, roughness: 0.38, metalness: 0.32 }),
          glass: new THREE.MeshPhysicalMaterial({ color: 0xdbeafe, roughness: 0.08, metalness: 0, transparent: true, opacity: 0.16, transmission: 0.55, depthWrite: false }),
        };
        disposables.push(
          ...Object.values(fixtureMaterials.frame),
          fixtureMaterials.pallet,
          fixtureMaterials.shelf,
          fixtureMaterials.glass
        );

        for (const module of model.modules) {
          addOpenShelfFixture(THREE, scene, module, fixtureMaterials, disposables);
        }

        const facingModel = buildFacingInstances(THREE, model);
        if (facingModel.instances.length) {
          const productGeometry = new THREE.BoxGeometry(1, 1, 1);
          const productMaterial = new THREE.MeshStandardMaterial({ color: 0xffffff, roughness: 0.46, metalness: 0.02 });
          disposables.push(productGeometry, productMaterial);
          const products = new THREE.InstancedMesh(productGeometry, productMaterial, facingModel.instances.length);
          facingModel.instances.forEach((instance, index) => {
            products.setMatrixAt(index, instance.matrix);
            const color = new THREE.Color().setHSL(instance.hue, 0.58, 0.56, THREE.SRGBColorSpace);
            products.setColorAt(index, color);
          });
          products.instanceMatrix.needsUpdate = true;
          if (products.instanceColor) products.instanceColor.needsUpdate = true;
          products.castShadow = true;
          products.receiveShadow = true;
          products.userData.clippedFacingCount = facingModel.clippedFacingCount;
          scene.add(products);
        }

        controls = new OrbitControls(camera, renderer.domElement);
        controls.enableDamping = true;
        controls.dampingFactor = 0.07;
        controls.maxPolarAngle = Math.PI / 2.02;
        controls.minDistance = 1.2;
        controls.maxDistance = Math.max(model.floor.widthM, model.floor.depthM) * 4;

        const center = new THREE.Vector3(model.floor.widthM / 2, 0.9, model.floor.depthM / 2);
        const maxDimension = Math.max(model.floor.widthM, model.floor.depthM, 4);
        const setPreset = (preset = "perspective") => {
          if (preset === "top") {
            camera.position.set(center.x, maxDimension * 1.35, center.z + 0.001);
            controls.target.set(center.x, 0, center.z);
          } else if (preset === "front") {
            camera.position.set(center.x, 1.65, model.floor.depthM + Math.max(2, maxDimension * 0.28));
            controls.target.set(center.x, 1.15, center.z);
          } else {
            camera.position.set(model.floor.widthM + maxDimension * 0.38, maxDimension * 0.55, model.floor.depthM + maxDimension * 0.38);
            controls.target.copy(center);
          }
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
