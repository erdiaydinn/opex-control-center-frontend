import React, { useEffect, useRef, useState } from "react";

import { createPlanogramThreeAssetRuntime } from "./planogramThreeAssetRuntime.js";
import {
  buildPlanogramWalkthroughNavigation,
  resolvePlanogramWalkthroughStep,
} from "./planogramWalkthroughNavigation.js";

const WALK_SPEED_MPS = 2.15;
const TURN_SPEED_RAD_PER_SEC = 1.8;
const MAX_WALK_FACINGS = 900;
const PRODUCT_GAP_M = 0.006;

function clamp(value, min, max) {
  return Math.min(max, Math.max(min, value));
}

function fixtureKind(type) {
  const value = String(type || "").toUpperCase();
  if (value.includes("CHILLED") || value.includes("CHILLER") || value.includes("COOLER")) return "chilled";
  if (value.includes("FROZEN") || value.includes("FREEZER")) return "frozen";
  if (value.includes("PALLET")) return "pallet";
  return "regular";
}

function elementHeight(type) {
  if (type === "wall" || type === "column" || type === "window") return 2.7;
  if (type === "chiller" || type === "freezer") return 1.9;
  if (type === "door" || type === "emergency_exit") return 2.1;
  return 0.06;
}

function elementColor(type) {
  const colors = {
    wall: 0x9ca3af,
    window: 0x93c5fd,
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

function stableHue(value) {
  const text = String(value || "EAY");
  let hash = 2166136261;
  for (let index = 0; index < text.length; index += 1) {
    hash ^= text.charCodeAt(index);
    hash = Math.imul(hash, 16777619);
  }
  return ((hash >>> 0) % 360) / 360;
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

function buildFacingInstances(THREE, sceneModel, visualPlan) {
  const textureIndex = new Map(
    (visualPlan?.productTextures || []).map((row) => [
      `${row.moduleKey}:${row.shelfIndex}:${row.productIndex}`,
      row,
    ])
  );
  const instances = [];
  for (const fixture of sceneModel.fixtures || []) {
    if (!Array.isArray(fixture.products) || !fixture.products.length) continue;
    const rotation = (Number(fixture.rotationDeg || 0) * Math.PI) / 180;
    const quaternion = new THREE.Quaternion().setFromAxisAngle(new THREE.Vector3(0, 1, 0), -rotation);
    const frontSign = String(fixture.side || "").toUpperCase() === "R" ? -1 : 1;
    const shelfCount = Math.max(1, Number(fixture.shelfCount) || 1);
    const fixtureHeight = Math.max(0.18, Number(fixture.heightM) || 1.6);
    const levelHeight = fixtureKind(fixture.fixtureType) === "pallet" ? fixtureHeight : fixtureHeight / shelfCount;
    const rowsByShelf = new Map();
    for (const product of fixture.products) {
      if (!rowsByShelf.has(product.shelfIndex)) rowsByShelf.set(product.shelfIndex, []);
      rowsByShelf.get(product.shelfIndex).push(product);
    }
    for (const [shelfIndex, products] of rowsByShelf.entries()) {
      let cursorX = -fixture.widthM / 2 + PRODUCT_GAP_M;
      const rightEdge = fixture.widthM / 2 - PRODUCT_GAP_M;
      for (const product of products) {
        const width = clamp(Number(product.widthM) || 0.08, 0.025, Math.max(0.03, fixture.widthM * 0.45));
        const height = clamp(Number(product.heightM) || 0.18, 0.035, Math.max(0.05, levelHeight * 0.8));
        const depth = clamp(Number(product.depthM) || 0.07, 0.025, Math.max(0.03, fixture.depthM * 0.82));
        const allowedTexture = textureIndex.get(`${fixture.moduleKey}:${product.shelfIndex}:${product.productIndex}`);
        for (let facingIndex = 0; facingIndex < Math.max(1, Number(product.facingCount) || 1); facingIndex += 1) {
          if (instances.length >= MAX_WALK_FACINGS || cursorX + width > rightEdge + 1e-9) break;
          const localX = cursorX + width / 2;
          const frontInset = Math.min(fixture.depthM * 0.18, 0.045);
          const localZ = frontSign * (fixture.depthM / 2 - depth / 2 - frontInset);
          const cos = Math.cos(-rotation);
          const sin = Math.sin(-rotation);
          const worldX = fixture.centerXM + localX * cos - localZ * sin;
          const worldZ = fixture.centerYM + localX * sin + localZ * cos;
          const shelfBase = fixtureKind(fixture.fixtureType) === "pallet"
            ? fixtureHeight + 0.025
            : shelfIndex * levelHeight + 0.025;
          const worldY = shelfBase + height / 2;
          const matrix = new THREE.Matrix4();
          matrix.compose(new THREE.Vector3(worldX, worldY, worldZ), quaternion, new THREE.Vector3(width, height, depth));
          let frontMatrix = null;
          if (allowedTexture && facingIndex < allowedTexture.facingCount) {
            const planeLocalZ = frontSign * (fixture.depthM / 2 - frontInset + 0.002);
            const planeWorldX = fixture.centerXM + localX * cos - planeLocalZ * sin;
            const planeWorldZ = fixture.centerYM + localX * sin + planeLocalZ * cos;
            const planeQuaternion = quaternion.clone();
            if (frontSign < 0) planeQuaternion.multiply(new THREE.Quaternion().setFromAxisAngle(new THREE.Vector3(0, 1, 0), Math.PI));
            frontMatrix = new THREE.Matrix4();
            frontMatrix.compose(new THREE.Vector3(planeWorldX, worldY, planeWorldZ), planeQuaternion, new THREE.Vector3(width * 0.94, height * 0.94, 1));
          }
          instances.push({
            matrix,
            frontMatrix,
            sku: String(product.sku || "SKU").toUpperCase(),
            hue: stableHue(product.sku),
            fallbackImagePath: allowedTexture?.frontImagePath || null,
          });
          cursorX += width + PRODUCT_GAP_M;
        }
      }
    }
  }
  return instances;
}

export default function PlanogramFirstPersonWalkthrough({
  sceneModel,
  visualPlan = null,
  deliveryPlan = null,
  ariaLabel,
  loadingLabel,
  errorLabel,
}) {
  const mountRef = useRef(null);
  const [state, setState] = useState("loading");

  useEffect(() => {
    let disposed = false;
    let renderer;
    let pointerControls;
    let resizeObserver;
    let frame;
    let environmentTarget;
    let requestLock;
    let keyDown;
    let keyUp;
    let lastTimestamp = performance.now();
    const disposables = [];
    const assetRoots = [];
    const pressed = new Set();
    const navigation = buildPlanogramWalkthroughNavigation(sceneModel);

    async function mount() {
      setState("loading");
      try {
        const THREE = await import("three");
        const { PointerLockControls } = await import("three/examples/jsm/controls/PointerLockControls.js");
        const { RoomEnvironment } = await import("three/examples/jsm/environments/RoomEnvironment.js");
        if (disposed || !mountRef.current || !sceneModel?.floor || !navigation) return;

        const host = mountRef.current;
        const scene = new THREE.Scene();
        scene.background = new THREE.Color(0x090b10);
        const span = Math.max(sceneModel.floor.widthM, sceneModel.floor.depthM, 4);
        scene.fog = new THREE.Fog(0x090b10, Math.max(18, span * 1.2), Math.max(70, span * 5));
        const camera = new THREE.PerspectiveCamera(64, 1, 0.04, Math.max(220, span * 12));
        camera.position.set(navigation.start.x, navigation.eyeHeightM, navigation.start.y);
        const dispatch = (sceneModel.architecture || []).find((row) => row.type === "dispatch");
        camera.lookAt(dispatch
          ? new THREE.Vector3(dispatch.centerXM, 1.2, dispatch.centerYM)
          : new THREE.Vector3(sceneModel.floor.widthM / 2, 1.2, sceneModel.floor.depthM / 2));

        renderer = new THREE.WebGLRenderer({ antialias: true, powerPreference: "high-performance" });
        renderer.setPixelRatio(Math.min(window.devicePixelRatio || 1, 2));
        renderer.shadowMap.enabled = true;
        renderer.shadowMap.type = THREE.PCFSoftShadowMap;
        renderer.outputColorSpace = THREE.SRGBColorSpace;
        renderer.toneMapping = THREE.ACESFilmicToneMapping;
        renderer.toneMappingExposure = 1.08;
        const assetRuntime = createPlanogramThreeAssetRuntime({ THREE, renderer });
        const pmrem = new THREE.PMREMGenerator(renderer);
        environmentTarget = pmrem.fromScene(new RoomEnvironment(), 0.04);
        pmrem.dispose();
        scene.environment = environmentTarget.texture;

        host.replaceChildren(renderer.domElement);
        renderer.domElement.tabIndex = 0;
        renderer.domElement.setAttribute("role", "application");
        renderer.domElement.setAttribute("aria-label", ariaLabel || "");
        renderer.domElement.dataset.walkthroughContract = navigation.contract;
        renderer.domElement.dataset.geometryAuthority = navigation.geometryAuthority;
        renderer.domElement.dataset.productionReleaseAllowed = "false";
        renderer.domElement.dataset.collisionObstacleCount = String(navigation.obstacles.length);

        pointerControls = new PointerLockControls(camera, renderer.domElement);
        requestLock = () => pointerControls?.lock?.();
        renderer.domElement.addEventListener("click", requestLock);
        keyDown = (event) => {
          const key = String(event.code || event.key || "");
          if (["KeyW", "KeyA", "KeyS", "KeyD", "ArrowUp", "ArrowDown", "ArrowLeft", "ArrowRight"].includes(key)) {
            event.preventDefault();
            pressed.add(key);
          }
        };
        keyUp = (event) => pressed.delete(String(event.code || event.key || ""));
        renderer.domElement.addEventListener("keydown", keyDown);
        renderer.domElement.addEventListener("keyup", keyUp);
        window.addEventListener("keyup", keyUp);

        scene.add(new THREE.HemisphereLight(0xffffff, 0x111827, 1.45));
        const keyLight = new THREE.DirectionalLight(0xffffff, 2.35);
        keyLight.position.set(sceneModel.floor.widthM * 0.35, 10, sceneModel.floor.depthM * 0.25);
        keyLight.castShadow = true;
        keyLight.shadow.mapSize.set(2048, 2048);
        scene.add(keyLight);

        const floorGeometry = new THREE.PlaneGeometry(sceneModel.floor.widthM, sceneModel.floor.depthM);
        const floorMaterial = new THREE.MeshPhysicalMaterial({ color: 0x242a33, roughness: 0.82, metalness: 0.01, clearcoat: 0.05 });
        disposables.push(floorGeometry, floorMaterial);
        const floor = new THREE.Mesh(floorGeometry, floorMaterial);
        floor.rotation.x = -Math.PI / 2;
        floor.position.set(sceneModel.floor.widthM / 2, 0, sceneModel.floor.depthM / 2);
        floor.receiveShadow = true;
        scene.add(floor);

        for (const element of sceneModel.architecture || []) {
          if (element.type === "picker_entry" || element.type === "picker_exit") continue;
          const height = elementHeight(element.type);
          const operational = ["inbound", "dispatch", "no_go", "technical"].includes(element.type);
          const geometry = new THREE.BoxGeometry(element.widthM, height, element.depthM);
          const material = new THREE.MeshPhysicalMaterial({
            color: elementColor(element.type), roughness: operational ? 0.72 : 0.55, metalness: 0.04,
            transparent: operational, opacity: operational ? 0.38 : 0.94, clearcoat: operational ? 0 : 0.05,
          });
          disposables.push(geometry, material);
          const mesh = new THREE.Mesh(geometry, material);
          mesh.position.set(element.centerXM, height / 2, element.centerYM);
          mesh.rotation.y = (-Number(element.rotationDeg || 0) * Math.PI) / 180;
          mesh.castShadow = !operational;
          mesh.receiveShadow = true;
          scene.add(mesh);
        }

        const visualByModule = new Map((visualPlan?.fixtureInstances || []).map((row) => [row.moduleKey, row]));
        const deliveryByType = new Map((deliveryPlan?.fixtures || []).map((row) => [String(row.fixtureType || "").toUpperCase(), row]));
        for (const fixture of sceneModel.fixtures || []) {
          const geometry = new THREE.BoxGeometry(Math.max(0.05, fixture.widthM), Math.max(0.18, fixture.heightM || 1.6), Math.max(0.05, fixture.depthM));
          const material = new THREE.MeshPhysicalMaterial({
            color: fixtureKind(fixture.fixtureType) === "pallet" ? 0x8b5e34 : 0x9aa3b1,
            roughness: 0.44,
            metalness: fixtureKind(fixture.fixtureType) === "pallet" ? 0.01 : 0.22,
          });
          disposables.push(geometry, material);
          const fallback = new THREE.Mesh(geometry, material);
          fallback.position.set(fixture.centerXM, Math.max(0.18, fixture.heightM || 1.6) / 2, fixture.centerYM);
          fallback.rotation.y = (-Number(fixture.rotationDeg || 0) * Math.PI) / 180;
          fallback.castShadow = true;
          fallback.receiveShadow = true;
          scene.add(fallback);

          const visual = visualByModule.get(fixture.moduleKey);
          if (!visual) continue;
          const delivery = deliveryByType.get(String(fixture.fixtureType || "").toUpperCase());
          const levels = delivery?.levels?.length
            ? delivery.levels
            : [{ quality: visual.lodQuality || "near", modelPath: visual.modelPath, distanceM: 0 }];
          const lod = await assetRuntime.loadFixtureLod({ levels, targetEnvelopeM: visual.targetEnvelopeM });
          if (!lod || disposed) continue;
          lod.position.x = fixture.centerXM;
          lod.position.z = fixture.centerYM;
          lod.rotation.y = (-Number(fixture.rotationDeg || 0) * Math.PI) / 180;
          scene.add(lod);
          assetRoots.push(lod);
          fallback.visible = false;
        }

        const facings = buildFacingInstances(THREE, sceneModel, visualPlan);
        if (facings.length) {
          const productGeometry = new THREE.BoxGeometry(1, 1, 1);
          const productMaterial = new THREE.MeshPhysicalMaterial({ color: 0xffffff, roughness: 0.43, metalness: 0.01, clearcoat: 0.07 });
          disposables.push(productGeometry, productMaterial);
          const mesh = new THREE.InstancedMesh(productGeometry, productMaterial, facings.length);
          facings.forEach((row, index) => {
            mesh.setMatrixAt(index, row.matrix);
            mesh.setColorAt(index, new THREE.Color().setHSL(row.hue, 0.48, 0.66, THREE.SRGBColorSpace));
          });
          mesh.instanceMatrix.needsUpdate = true;
          if (mesh.instanceColor) mesh.instanceColor.needsUpdate = true;
          mesh.castShadow = true;
          mesh.receiveShadow = true;
          scene.add(mesh);
        }

        const deliveryBySku = new Map((deliveryPlan?.products || []).map((row) => [String(row.sku || "").toUpperCase(), row]));
        const planeGeometry = new THREE.PlaneGeometry(1, 1);
        disposables.push(planeGeometry);
        const materialCache = new Map();
        for (const facing of facings.filter((row) => row.frontMatrix && row.fallbackImagePath)) {
          const delivery = deliveryBySku.get(facing.sku) || {
            sku: facing.sku,
            mode: "packshot",
            path: facing.fallbackImagePath,
            fallbackPath: facing.fallbackImagePath,
          };
          const cacheKey = JSON.stringify([delivery.mode, delivery.path, delivery.fallbackPath, delivery.atlasUv || null]);
          let material = materialCache.get(cacheKey);
          if (!material) {
            try {
              const loaded = await assetRuntime.loadProductTexture(delivery);
              material = new THREE.MeshStandardMaterial({
                map: loaded.texture, color: 0xffffff, roughness: 0.48, transparent: true, alphaTest: 0.025,
                side: THREE.DoubleSide, polygonOffset: true, polygonOffsetFactor: -1, polygonOffsetUnits: -1,
              });
              disposables.push(material, loaded.texture);
              materialCache.set(cacheKey, material);
            } catch {
              continue;
            }
          }
          const plane = new THREE.Mesh(planeGeometry, material);
          plane.matrixAutoUpdate = false;
          plane.matrix.copy(facing.frontMatrix);
          plane.renderOrder = 4;
          scene.add(plane);
        }

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

        const forward = new THREE.Vector3();
        const right = new THREE.Vector3();
        const move = new THREE.Vector3();
        const animate = (timestamp) => {
          if (disposed) return;
          const deltaSeconds = Math.min(0.05, Math.max(0, (timestamp - lastTimestamp) / 1000));
          lastTimestamp = timestamp;
          const forwardInput = (pressed.has("KeyW") || pressed.has("ArrowUp") ? 1 : 0)
            - (pressed.has("KeyS") || pressed.has("ArrowDown") ? 1 : 0);
          const strafeInput = (pressed.has("KeyD") ? 1 : 0) - (pressed.has("KeyA") ? 1 : 0);
          const turnInput = (pressed.has("ArrowRight") ? 1 : 0) - (pressed.has("ArrowLeft") ? 1 : 0);
          if (turnInput) camera.rotateY(-turnInput * TURN_SPEED_RAD_PER_SEC * deltaSeconds);
          if (forwardInput || strafeInput) {
            camera.getWorldDirection(forward);
            forward.y = 0;
            if (forward.lengthSq() > 0) forward.normalize();
            right.set(-forward.z, 0, forward.x);
            move.copy(forward).multiplyScalar(forwardInput).addScaledVector(right, strafeInput);
            if (move.lengthSq() > 0) move.normalize().multiplyScalar(WALK_SPEED_MPS * deltaSeconds);
            const step = resolvePlanogramWalkthroughStep(
              navigation,
              { x: camera.position.x, y: camera.position.z },
              { x: move.x, y: move.z }
            );
            if (step.position) camera.position.set(step.position.x, navigation.eyeHeightM, step.position.y);
            renderer.domElement.dataset.lastMovementResolution = step.reason;
          }
          renderer.render(scene, camera);
          frame = requestAnimationFrame(animate);
        };
        frame = requestAnimationFrame(animate);
        setState("ready");
      } catch {
        if (!disposed) setState("error");
      }
    }

    mount();
    return () => {
      disposed = true;
      if (renderer?.domElement && requestLock) renderer.domElement.removeEventListener("click", requestLock);
      if (renderer?.domElement && keyDown) renderer.domElement.removeEventListener("keydown", keyDown);
      if (renderer?.domElement && keyUp) renderer.domElement.removeEventListener("keyup", keyUp);
      if (keyUp) window.removeEventListener("keyup", keyUp);
      if (frame) cancelAnimationFrame(frame);
      resizeObserver?.disconnect();
      pointerControls?.unlock?.();
      pointerControls?.dispose?.();
      renderer?.dispose();
      environmentTarget?.dispose?.();
      const seen = new Set();
      for (const root of assetRoots) {
        root?.traverse?.((node) => {
          if (node.geometry && !seen.has(node.geometry)) {
            seen.add(node.geometry);
            node.geometry.dispose?.();
          }
          if (node.material) disposeMaterial(node.material, seen);
        });
      }
      for (const item of disposables) {
        if (!item || seen.has(item)) continue;
        seen.add(item);
        item.dispose?.();
      }
      if (mountRef.current) mountRef.current.replaceChildren();
    };
  }, [ariaLabel, deliveryPlan, errorLabel, loadingLabel, sceneModel, visualPlan]);

  return (
    <div className="eay-scanned-twin-scene" data-first-person-walkthrough="true">
      {state === "loading" ? <div className="eay-scanned-twin-state" role="status">{loadingLabel}</div> : null}
      {state === "error" ? <div className="eay-scanned-twin-state is-error" role="alert">{errorLabel}</div> : null}
      <div ref={mountRef} className="eay-scanned-twin-canvas" data-state={state} />
    </div>
  );
}
