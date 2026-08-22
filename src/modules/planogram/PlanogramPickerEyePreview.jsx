import React, { useEffect, useMemo, useRef, useState } from "react";
import { Eye, Image, PackageSearch } from "lucide-react";

import { translatePlanogramPickerEye } from "../../platform/i18n/planogramPickerEyeMessages.js";
import { buildFixtureAssetIndex, buildProductAssetIndex } from "./planogramAssetManifest.js";
import { buildPlanogramDigitalTwinModel } from "./planogramDigitalTwinModel.js";
import "./planogram-picker-eye.css";

const EYE_HEIGHT_M = 1.62;
const WALK_SPEED_MPS = 2.35;
const COLLISION_RADIUS_M = 0.24;
const MAX_PRODUCT_BOXES = 900;
const MAX_TEXTURED_FACINGS = 240;
const PRODUCT_GAP_M = 0.006;

function clamp(value, min, max) { return Math.min(max, Math.max(min, value)); }
function fixtureKind(type) {
  const value = String(type || "").toLowerCase();
  if (value.includes("pallet")) return "pallet";
  if (value.includes("frozen") || value.includes("freezer")) return "frozen";
  if (value.includes("chilled") || value.includes("cooler")) return "chilled";
  return "regular";
}
function fixtureHeight(module) {
  if (fixtureKind(module.fixtureType) === "pallet") return 0.18;
  return Math.max(1.5, Math.max(1, module.shelfCount || 1) * 0.32);
}
function productDimensions(product, levelHeight, module) {
  const width = clamp(Number(product?.width_cm || 0) / 100 || 0.08, 0.025, Math.max(0.03, module.widthM * 0.45));
  const height = clamp(Number(product?.height_cm || 0) / 100 || Math.min(0.22, levelHeight * 0.62), 0.035, Math.max(0.05, levelHeight * 0.8));
  const depth = clamp(Number(product?.depth_cm || 0) / 100 || 0.07, 0.025, Math.max(0.03, module.depthM * 0.82));
  return { width, height, depth };
}
function countFacings(product) {
  const raw = Number(product?.facing_count ?? product?.facing ?? 1);
  return Number.isFinite(raw) ? clamp(Math.round(raw), 1, 40) : 1;
}
function disposeMaterial(material) {
  if (!material) return;
  for (const row of (Array.isArray(material) ? material : [material])) {
    row?.map?.dispose?.();
    row?.normalMap?.dispose?.();
    row?.roughnessMap?.dispose?.();
    row?.dispose?.();
  }
}
function disposeObject(root) {
  root?.traverse?.((node) => { node.geometry?.dispose?.(); disposeMaterial(node.material); });
}
function pointInsideRotatedRect(x, z, row, margin = 0) {
  const rotation = (Number(row.rotationDeg || 0) * Math.PI) / 180;
  const dx = x - Number(row.centerXM || 0);
  const dz = z - Number(row.centerYM || 0);
  const cos = Math.cos(rotation);
  const sin = Math.sin(rotation);
  const localX = dx * cos + dz * sin;
  const localZ = -dx * sin + dz * cos;
  return Math.abs(localX) <= Number(row.widthM || 0) / 2 + margin
    && Math.abs(localZ) <= Number(row.depthM || 0) / 2 + margin;
}
function blockedAt(x, z, model) {
  const architecture = model.elements.filter((row) => ["wall", "column", "chiller", "freezer", "no_go"].includes(row.type));
  return architecture.some((row) => pointInsideRotatedRect(x, z, row, COLLISION_RADIUS_M))
    || model.modules.some((row) => pointInsideRotatedRect(x, z, row, COLLISION_RADIUS_M));
}

async function loadFixtureModels(GLTFLoader, manifest) {
  const loader = new GLTFLoader();
  const unique = [...new Set((manifest?.fixture_assets || []).map((row) => row.model_path))];
  const loaded = new Map();
  await Promise.all(unique.map(async (path) => {
    try { loaded.set(path, (await loader.loadAsync(path)).scene); }
    catch { loaded.set(path, null); }
  }));
  return loaded;
}

function addFallbackFixture(THREE, scene, module, disposables) {
  const height = fixtureHeight(module);
  const kind = fixtureKind(module.fixtureType);
  const colors = { regular: 0x667085, chilled: 0x0891b2, frozen: 0x2563eb, pallet: 0x8b5e34 };
  const geometry = new THREE.BoxGeometry(module.widthM, height, module.depthM);
  const material = new THREE.MeshPhysicalMaterial({
    color: colors[kind], roughness: kind === "pallet" ? 0.86 : 0.34,
    metalness: kind === "pallet" ? 0.02 : 0.38, clearcoat: kind === "pallet" ? 0 : 0.18,
    clearcoatRoughness: 0.32, transparent: true, opacity: 0.48, envMapIntensity: 0.8,
  });
  disposables.push(geometry, material);
  const mesh = new THREE.Mesh(geometry, material);
  mesh.position.set(module.centerXM, height / 2, module.centerYM);
  mesh.rotation.y = (-module.rotationDeg * Math.PI) / 180;
  mesh.castShadow = true; mesh.receiveShadow = true; scene.add(mesh);
}

function addFixtureAsset(THREE, scene, module, source) {
  const root = source.clone(true);
  const box = new THREE.Box3().setFromObject(root);
  const size = new THREE.Vector3(); const center = new THREE.Vector3();
  box.getSize(size); box.getCenter(center);
  if (size.x <= 0 || size.y <= 0 || size.z <= 0) return null;
  root.position.sub(center);
  const group = new THREE.Group(); group.add(root);
  group.scale.set(module.widthM / size.x, fixtureHeight(module) / size.y, module.depthM / size.z);
  group.position.set(module.centerXM, fixtureHeight(module) / 2, module.centerYM);
  group.rotation.y = (-module.rotationDeg * Math.PI) / 180;
  group.traverse((node) => {
    if (!node.isMesh) return;
    node.castShadow = true; node.receiveShadow = true;
    if (node.material) {
      const materials = Array.isArray(node.material) ? node.material : [node.material];
      for (const material of materials) {
        if ("envMapIntensity" in material) material.envMapIntensity = 1;
      }
    }
  });
  scene.add(group); return group;
}

function addProducts(THREE, scene, model, productAssets, disposables, maxAnisotropy) {
  const textureLoader = new THREE.TextureLoader();
  const textureMaterials = new Map();
  const planeGeometry = new THREE.PlaneGeometry(1, 1);
  const boxGeometry = new THREE.BoxGeometry(1, 1, 1);
  const boxMaterial = new THREE.MeshPhysicalMaterial({ color: 0xdfe3e8, roughness: 0.43, metalness: 0.01, clearcoat: 0.08, envMapIntensity: 0.7 });
  disposables.push(planeGeometry, boxGeometry, boxMaterial);
  let productBoxes = 0; let texturedFacings = 0;
  const materialFor = (asset) => {
    if (!asset || texturedFacings >= MAX_TEXTURED_FACINGS) return null;
    if (textureMaterials.has(asset.front_image_path)) return textureMaterials.get(asset.front_image_path);
    const material = new THREE.MeshStandardMaterial({ color: 0xffffff, transparent: true, side: THREE.DoubleSide, roughness: 0.48, metalness: 0.01 });
    textureMaterials.set(asset.front_image_path, material); disposables.push(material);
    textureLoader.load(asset.front_image_path, (texture) => {
      texture.colorSpace = THREE.SRGBColorSpace;
      texture.anisotropy = Math.min(8, maxAnisotropy || 1);
      material.map = texture; material.needsUpdate = true; disposables.push(texture);
    }, undefined, () => {});
    return material;
  };

  outer: for (const module of model.modules) {
    const rotation = (-module.rotationDeg * Math.PI) / 180;
    const cos = Math.cos(rotation); const sin = Math.sin(rotation);
    const shelves = module.shelves || [];
    const levelHeight = fixtureHeight(module) / Math.max(1, shelves.length || 1);
    const left = -module.widthM / 2 + 0.04; const right = module.widthM / 2 - 0.04;
    const frontSign = module.side === "R" ? -1 : 1;
    for (const [shelfIndex, shelf] of shelves.entries()) {
      let cursor = left;
      for (const product of shelf?.products || []) {
        const { width, height, depth } = productDimensions(product, levelHeight, module);
        const sku = String(product?.sku ?? product?.SKU ?? "").trim().toUpperCase();
        const asset = productAssets.get(sku);
        for (let facing = 0; facing < countFacings(product); facing += 1) {
          if (productBoxes >= MAX_PRODUCT_BOXES) break outer;
          if (cursor + width > right) break;
          const localX = cursor + width / 2;
          const localZ = frontSign * (module.depthM / 2 - depth / 2 - 0.025);
          const worldX = module.centerXM + localX * cos - localZ * sin;
          const worldZ = module.centerYM + localX * sin + localZ * cos;
          const worldY = shelfIndex * levelHeight + 0.025 + height / 2;
          const box = new THREE.Mesh(boxGeometry, boxMaterial);
          box.position.set(worldX, worldY, worldZ); box.rotation.y = rotation; box.scale.set(width, height, depth);
          box.castShadow = true; box.receiveShadow = true; scene.add(box); productBoxes += 1;
          const material = materialFor(asset);
          if (material && texturedFacings < MAX_TEXTURED_FACINGS) {
            const plane = new THREE.Mesh(planeGeometry, material);
            const planeLocalZ = frontSign * (module.depthM / 2 + 0.004);
            plane.position.set(module.centerXM + localX * cos - planeLocalZ * sin, worldY, module.centerYM + localX * sin + planeLocalZ * cos);
            plane.rotation.y = rotation + (frontSign < 0 ? Math.PI : 0);
            plane.scale.set(width * 0.94, height * 0.94, 1); plane.renderOrder = 3; scene.add(plane); texturedFacings += 1;
          }
          cursor += width + PRODUCT_GAP_M;
        }
      }
    }
  }
  return { productBoxes, texturedFacings };
}

function PickerEyeScene({ model, assetManifest, t }) {
  const mountRef = useRef(null);
  const [state, setState] = useState("loading");
  const [walking, setWalking] = useState(false);

  useEffect(() => {
    let disposed = false; let renderer; let orbitControls; let pointerControls; let resizeObserver; let frame; let environment;
    const disposables = []; const addedAssets = []; const keys = new Set();
    const onKeyDown = (event) => keys.add(event.code);
    const onKeyUp = (event) => keys.delete(event.code);

    async function mount() {
      setState("loading");
      try {
        const THREE = await import("three");
        const { OrbitControls } = await import("three/examples/jsm/controls/OrbitControls.js");
        const { PointerLockControls } = await import("three/examples/jsm/controls/PointerLockControls.js");
        const { GLTFLoader } = await import("three/examples/jsm/loaders/GLTFLoader.js");
        const { RoomEnvironment } = await import("three/examples/jsm/environments/RoomEnvironment.js");
        if (disposed || !mountRef.current) return;

        const scene = new THREE.Scene(); scene.background = new THREE.Color(0x0d1118); scene.fog = new THREE.Fog(0x0d1118, 22, 70);
        const camera = new THREE.PerspectiveCamera(61, 1, 0.035, 220);
        renderer = new THREE.WebGLRenderer({ antialias: true, powerPreference: "high-performance" });
        renderer.setPixelRatio(Math.min(window.devicePixelRatio || 1, 2)); renderer.shadowMap.enabled = true;
        renderer.shadowMap.type = THREE.PCFSoftShadowMap; renderer.outputColorSpace = THREE.SRGBColorSpace;
        renderer.toneMapping = THREE.ACESFilmicToneMapping; renderer.toneMappingExposure = 1.12;
        const pmrem = new THREE.PMREMGenerator(renderer); environment = pmrem.fromScene(new RoomEnvironment(), 0.04).texture; pmrem.dispose(); scene.environment = environment;
        mountRef.current.replaceChildren(renderer.domElement); renderer.domElement.tabIndex = 0;
        renderer.domElement.setAttribute("role", "application"); renderer.domElement.setAttribute("aria-label", t("title"));

        scene.add(new THREE.HemisphereLight(0xffffff, 0x172033, 1.35));
        const key = new THREE.DirectionalLight(0xffffff, 2.7); key.position.set(model.floor.widthM * 0.35, 8, model.floor.depthM * 0.15); key.castShadow = true;
        key.shadow.mapSize.set(2048, 2048); scene.add(key);

        const floorGeometry = new THREE.PlaneGeometry(model.floor.widthM, model.floor.depthM);
        const floorMaterial = new THREE.MeshPhysicalMaterial({ color: 0x303640, roughness: 0.78, metalness: 0.01, clearcoat: 0.08, envMapIntensity: 0.65 });
        disposables.push(floorGeometry, floorMaterial);
        const floor = new THREE.Mesh(floorGeometry, floorMaterial); floor.rotation.x = -Math.PI / 2; floor.position.set(model.floor.widthM / 2, 0, model.floor.depthM / 2); floor.receiveShadow = true; scene.add(floor);

        for (const element of model.elements) {
          if (!["wall", "column", "chiller", "freezer"].includes(element.type)) continue;
          const height = element.type === "wall" || element.type === "column" ? 2.7 : 1.9;
          const geometry = new THREE.BoxGeometry(element.widthM, height, element.depthM);
          const cold = element.type === "chiller" || element.type === "freezer";
          const material = new THREE.MeshPhysicalMaterial({ color: cold ? 0x26394b : 0xb6bcc5, roughness: cold ? 0.3 : 0.72, metalness: cold ? 0.28 : 0.02, clearcoat: cold ? 0.25 : 0.02, envMapIntensity: 0.85 });
          disposables.push(geometry, material);
          const mesh = new THREE.Mesh(geometry, material); mesh.position.set(element.centerXM, height / 2, element.centerYM); mesh.rotation.y = (-element.rotationDeg * Math.PI) / 180;
          mesh.castShadow = true; mesh.receiveShadow = true; scene.add(mesh);
        }

        const fixtureIndex = buildFixtureAssetIndex(assetManifest);
        const loadedModels = await loadFixtureModels(GLTFLoader, assetManifest);
        for (const module of model.modules) {
          const asset = fixtureIndex.get(String(module.fixtureType || "").toUpperCase());
          const source = asset ? loadedModels.get(asset.model_path) : null;
          if (source) { const group = addFixtureAsset(THREE, scene, module, source); if (group) addedAssets.push(group); else addFallbackFixture(THREE, scene, module, disposables); }
          else addFallbackFixture(THREE, scene, module, disposables);
        }
        addProducts(THREE, scene, model, buildProductAssetIndex(assetManifest), disposables, renderer.capabilities.getMaxAnisotropy());

        const entry = model.route?.pickerEntryM || [model.floor.widthM / 2, 0.6];
        const next = model.route?.hotspots?.[0]?.pathM?.[1] || [model.floor.widthM / 2, model.floor.depthM / 2];
        camera.position.set(clamp(entry[0], 0.3, model.floor.widthM - 0.3), EYE_HEIGHT_M, clamp(entry[1], 0.3, model.floor.depthM - 0.3)); camera.lookAt(next[0], 1.35, next[1]);
        orbitControls = new OrbitControls(camera, renderer.domElement); orbitControls.enableDamping = true; orbitControls.dampingFactor = 0.08; orbitControls.enablePan = false; orbitControls.target.set(next[0], 1.35, next[1]); orbitControls.update();
        pointerControls = new PointerLockControls(camera, renderer.domElement);
        pointerControls.addEventListener("lock", () => { orbitControls.enabled = false; setWalking(true); });
        pointerControls.addEventListener("unlock", () => { orbitControls.enabled = true; orbitControls.target.set(camera.position.x, 1.35, camera.position.z - 1); orbitControls.update(); setWalking(false); keys.clear(); });
        const startWalk = () => { if (!pointerControls.isLocked) pointerControls.lock(); };
        renderer.domElement.addEventListener("dblclick", startWalk);
        window.addEventListener("keydown", onKeyDown); window.addEventListener("keyup", onKeyUp);

        const resize = () => {
          const width = Math.max(1, mountRef.current?.clientWidth || 1); const height = Math.max(360, mountRef.current?.clientHeight || 540);
          renderer.setSize(width, height, false); camera.aspect = width / height; camera.updateProjectionMatrix();
        };
        resizeObserver = new ResizeObserver(resize); resizeObserver.observe(mountRef.current); resize();
        const clock = new THREE.Clock();
        const animate = () => {
          if (disposed) return;
          const delta = Math.min(0.05, clock.getDelta());
          if (pointerControls.isLocked) {
            const previous = camera.position.clone();
            const forward = Number(keys.has("KeyW") || keys.has("ArrowUp")) - Number(keys.has("KeyS") || keys.has("ArrowDown"));
            const right = Number(keys.has("KeyD") || keys.has("ArrowRight")) - Number(keys.has("KeyA") || keys.has("ArrowLeft"));
            if (forward) pointerControls.moveForward(forward * WALK_SPEED_MPS * delta);
            if (right) pointerControls.moveRight(right * WALK_SPEED_MPS * delta);
            camera.position.x = clamp(camera.position.x, 0.2, model.floor.widthM - 0.2); camera.position.z = clamp(camera.position.z, 0.2, model.floor.depthM - 0.2); camera.position.y = EYE_HEIGHT_M;
            if (blockedAt(camera.position.x, camera.position.z, model)) camera.position.copy(previous);
          } else orbitControls.update();
          renderer.render(scene, camera); frame = requestAnimationFrame(animate);
        };
        animate(); setState("ready");
        return () => renderer.domElement.removeEventListener("dblclick", startWalk);
      } catch { if (!disposed) setState("error"); }
      return null;
    }

    let detach = null; mount().then((cleanup) => { detach = cleanup; });
    return () => {
      disposed = true; detach?.(); if (frame) cancelAnimationFrame(frame); resizeObserver?.disconnect(); pointerControls?.unlock?.(); pointerControls?.dispose?.(); orbitControls?.dispose?.();
      window.removeEventListener("keydown", onKeyDown); window.removeEventListener("keyup", onKeyUp);
      renderer?.dispose(); environment?.dispose?.(); for (const item of disposables) item?.dispose?.(); for (const asset of addedAssets) disposeObject(asset);
      if (mountRef.current) mountRef.current.replaceChildren();
    };
  }, [assetManifest, model, t]);

  return (
    <div className="eay-picker-eye-scene" data-walkthrough={walking ? "active" : "orbit"}>
      {state === "loading" ? <div className="eay-picker-eye-state" role="status">{t("loading")}</div> : null}
      {state === "error" ? <div className="eay-picker-eye-state is-error" role="alert">{t("error")}</div> : null}
      <div ref={mountRef} className="eay-picker-eye-canvas" data-state={state} />
    </div>
  );
}

export default function PlanogramPickerEyePreview({ engineResult, candidate, locale, formatNumber }) {
  const t = useMemo(() => (key) => translatePlanogramPickerEye(locale, key), [locale]);
  const model = useMemo(() => buildPlanogramDigitalTwinModel(engineResult, candidate), [candidate, engineResult]);
  const manifest = candidate?.asset_manifest || null;
  if (!model) return null;
  const productCount = manifest?.product_assets?.length || 0; const fixtureCount = manifest?.fixture_assets?.length || 0;
  const placedProducts = Math.max(1, model.stats?.placedProductCount || 0); const productCoverage = Math.min(100, (productCount / placedProducts) * 100);
  return (
    <section className="eay-picker-eye">
      <header><div><Eye size={21} aria-hidden="true" /><div><h3>{t("title")}</h3><p>{t("subtitle")}</p></div></div><span>{t("previewOnly")}</span></header>
      <div className="eay-picker-eye-metrics">
        <div><Image size={16} aria-hidden="true" /><span>{t("productAssets")}</span><strong>{formatNumber(productCount)}</strong></div>
        <div><PackageSearch size={16} aria-hidden="true" /><span>{t("fixtureAssets")}</span><strong>{formatNumber(fixtureCount)}</strong></div>
        <div><span>{t("assetCoverage")}</span><strong>{formatNumber(productCoverage)}%</strong></div>
      </div>
      {!model.route?.pickerEntryM ? <p className="eay-picker-eye-note">{t("noAnchor")}</p> : null}
      <PickerEyeScene model={model} assetManifest={manifest} t={t} />
      <p className="eay-picker-eye-note">{t("interaction")}</p>
    </section>
  );
}
