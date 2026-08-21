import React, { useEffect, useRef, useState } from "react";

import { createPlanogramThreeAssetRuntime } from "./planogramThreeAssetRuntime.js";

const FIXTURE_POST_M = 0.035;
const SHELF_BOARD_M = 0.025;
const PRODUCT_GAP_M = 0.006;
const MAX_PRODUCT_INSTANCES = 1500;

function clamp(value, min, max) {
  return Math.min(max, Math.max(min, value));
}

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

function fixtureKind(type) {
  const value = String(type || "").toUpperCase();
  if (value.includes("CHILLED") || value.includes("CHILLER") || value.includes("COOLER")) return "chilled";
  if (value.includes("FROZEN") || value.includes("FREEZER")) return "frozen";
  if (value.includes("PALLET")) return "pallet";
  return "regular";
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

function addBox(THREE, group, disposables, material, size, position, castShadow = true) {
  const geometry = new THREE.BoxGeometry(size[0], size[1], size[2]);
  disposables.push(geometry);
  const mesh = new THREE.Mesh(geometry, material);
  mesh.position.set(position[0], position[1], position[2]);
  mesh.castShadow = castShadow;
  mesh.receiveShadow = true;
  group.add(mesh);
  return mesh;
}

function addMetricFixtureFallback(THREE, scene, fixture, materials, disposables) {
  const kind = fixtureKind(fixture.fixtureType);
  const height = Math.max(0.18, Number(fixture.heightM) || (kind === "pallet" ? 0.18 : 1.6));
  const width = Math.max(0.05, Number(fixture.widthM) || 0.6);
  const depth = Math.max(0.05, Number(fixture.depthM) || 0.45);
  const shelfCount = Math.max(1, Math.round(Number(fixture.shelfCount) || 1));
  const group = new THREE.Group();
  group.position.set(fixture.centerXM, 0, fixture.centerYM);
  group.rotation.y = (-Number(fixture.rotationDeg || 0) * Math.PI) / 180;
  group.userData.fixtureId = fixture.id;
  group.userData.geometryAuthority = fixture.coordinateAuthority;
  group.userData.visualAuthority = "metric_primitive_fallback";
  scene.add(group);

  if (kind === "pallet") {
    addBox(THREE, group, disposables, materials.pallet, [width, 0.12, depth], [0, 0.06, 0]);
    for (let index = 0; index < 5; index += 1) {
      const ratio = index / 4;
      addBox(
        THREE,
        group,
        disposables,
        materials.shelf,
        [Math.max(0.035, width * 0.12), 0.025, depth * 0.96],
        [-width * 0.42 + width * 0.84 * ratio, 0.135, 0],
        false
      );
    }
    return group;
  }

  const postDepth = Math.max(0.04, Math.min(depth * 0.16, 0.08));
  const postX = Math.max(0, width / 2 - FIXTURE_POST_M / 2);
  addBox(THREE, group, disposables, materials.frame[kind], [FIXTURE_POST_M, height, postDepth], [-postX, height / 2, 0]);
  addBox(THREE, group, disposables, materials.frame[kind], [FIXTURE_POST_M, height, postDepth], [postX, height / 2, 0]);
  addBox(THREE, group, disposables, materials.frame[kind], [width, FIXTURE_POST_M, postDepth], [0, height - FIXTURE_POST_M / 2, 0]);
  for (let shelfIndex = 0; shelfIndex < shelfCount; shelfIndex += 1) {
    const y = shelfIndex * (height / shelfCount) + SHELF_BOARD_M / 2;
    addBox(
      THREE,
      group,
      disposables,
      materials.shelf,
      [Math.max(0.05, width - FIXTURE_POST_M * 2.4), SHELF_BOARD_M, depth * 0.94],
      [0, y, 0],
      false
    );
  }
  if (kind === "chilled" || kind === "frozen") {
    const glassGeometry = new THREE.PlaneGeometry(Math.max(0.05, width - FIXTURE_POST_M * 2.5), height * 0.92);
    disposables.push(glassGeometry);
    const glass = new THREE.Mesh(glassGeometry, materials.glass);
    glass.position.set(0, height * 0.5, depth / 2 + 0.002);
    group.add(glass);
  }
  return group;
}

function productTexturePlanIndex(visualPlan) {
  return new Map(
    (visualPlan?.productTextures || []).map((row) => [
      `${row.moduleKey}:${row.shelfIndex}:${row.productIndex}`,
      row,
    ])
  );
}

function productDeliveryIndex(deliveryPlan) {
  return new Map((deliveryPlan?.products || []).map((row) => [String(row.sku || "").toUpperCase(), row]));
}

function buildFacingInstances(THREE, sceneModel, visualPlan) {
  const instances = [];
  const textureIndex = productTexturePlanIndex(visualPlan);
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
          if (instances.length >= MAX_PRODUCT_INSTANCES || cursorX + width > rightEdge + 1e-9) break;
          const localX = cursorX + width / 2;
          const frontInset = Math.min(fixture.depthM * 0.18, 0.045);
          const localZ = frontSign * (fixture.depthM / 2 - depth / 2 - frontInset);
          const cos = Math.cos(-rotation);
          const sin = Math.sin(-rotation);
          const worldX = fixture.centerXM + localX * cos - localZ * sin;
          const worldZ = fixture.centerYM + localX * sin + localZ * cos;
          const shelfBase = fixtureKind(fixture.fixtureType) === "pallet"
            ? fixtureHeight + SHELF_BOARD_M
            : shelfIndex * levelHeight + SHELF_BOARD_M;
          const worldY = shelfBase + height / 2;
          const matrix = new THREE.Matrix4();
          matrix.compose(
            new THREE.Vector3(worldX, worldY, worldZ),
            quaternion,
            new THREE.Vector3(width, height, depth)
          );
          let frontMatrix = null;
          if (allowedTexture && facingIndex < allowedTexture.facingCount) {
            const planeLocalZ = frontSign * (fixture.depthM / 2 - frontInset + 0.002);
            const planeWorldX = fixture.centerXM + localX * cos - planeLocalZ * sin;
            const planeWorldZ = fixture.centerYM + localX * sin + planeLocalZ * cos;
            const planeQuaternion = quaternion.clone();
            if (frontSign < 0) planeQuaternion.multiply(new THREE.Quaternion().setFromAxisAngle(new THREE.Vector3(0, 1, 0), Math.PI));
            frontMatrix = new THREE.Matrix4();
            frontMatrix.compose(
              new THREE.Vector3(planeWorldX, worldY, planeWorldZ),
              planeQuaternion,
              new THREE.Vector3(width * 0.94, height * 0.94, 1)
            );
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

function addRouteLines(THREE, scene, sceneModel, disposables) {
  for (const hotspot of sceneModel.route?.hotspots?.slice(0, 3) || []) {
    if (!Array.isArray(hotspot.pathM) || hotspot.pathM.length < 2) continue;
    const geometry = new THREE.BufferGeometry().setFromPoints(
      hotspot.pathM.map(([xM, yM]) => new THREE.Vector3(xM, 0.04, yM))
    );
    const material = new THREE.LineBasicMaterial({ color: 0xdf1067, transparent: true, opacity: 0.84 });
    disposables.push(geometry, material);
    scene.add(new THREE.Line(geometry, material));
  }
}

export default function PlanogramTwinSceneRenderer({
  sceneModel,
  visualPlan = null,
  deliveryPlan = null,
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
    const assetRoots = [];

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
        const assetRuntime = createPlanogramThreeAssetRuntime({ THREE, renderer });

        const pmrem = new THREE.PMREMGenerator(renderer);
        environmentTarget = pmrem.fromScene(new RoomEnvironment(), 0.04);
        pmrem.dispose();
        scene.environment = environmentTarget.texture;

        host.replaceChildren(renderer.domElement);
        renderer.domElement.tabIndex = 0;
        renderer.domElement.setAttribute("role", "img");
        renderer.domElement.setAttribute("aria-label", ariaLabel || "");
        renderer.domElement.dataset.twinSceneContract = sceneModel.contract;
        renderer.domElement.dataset.geometryAuthority = sceneModel.geometryAuthority;
        renderer.domElement.dataset.sourceKind = sceneModel.sourceKind;
        renderer.domElement.dataset.assetRuntimeContract = assetRuntime.contract;

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
        addRouteLines(THREE, scene, sceneModel, disposables);

        const operationalTypes = new Set(["picker_entry", "picker_exit", "inbound", "dispatch", "no_go", "technical"]);
        for (const element of sceneModel.architecture || []) {
          const type = String(element.type || "");
          if (type === "picker_entry" || type === "picker_exit") {
            const geometry = new THREE.CylinderGeometry(0.16, 0.16, 0.05, 24);
            const material = new THREE.MeshPhysicalMaterial({
              color: elementColor(type), emissive: elementColor(type), emissiveIntensity: 0.24, roughness: 0.42,
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

        const fixtureMaterials = {
          frame: {
            regular: new THREE.MeshPhysicalMaterial({ color: 0x9aa3b1, roughness: 0.36, metalness: 0.34, clearcoat: 0.12 }),
            chilled: new THREE.MeshPhysicalMaterial({ color: 0x4a9eb5, roughness: 0.28, metalness: 0.26, clearcoat: 0.2 }),
            frozen: new THREE.MeshPhysicalMaterial({ color: 0x5e7fc6, roughness: 0.28, metalness: 0.26, clearcoat: 0.2 }),
          },
          pallet: new THREE.MeshPhysicalMaterial({ color: 0x8b5e34, roughness: 0.84, metalness: 0.01 }),
          shelf: new THREE.MeshPhysicalMaterial({ color: 0xd7dce3, roughness: 0.31, metalness: 0.36, clearcoat: 0.11 }),
          glass: new THREE.MeshPhysicalMaterial({
            color: 0xdbeafe, roughness: 0.06, transparent: true, opacity: 0.14,
            transmission: 0.72, thickness: 0.01, clearcoat: 0.2, depthWrite: false,
          }),
        };
        disposables.push(...Object.values(fixtureMaterials.frame), fixtureMaterials.pallet, fixtureMaterials.shelf, fixtureMaterials.glass);

        const visualByModule = new Map((visualPlan?.fixtureInstances || []).map((row) => [row.moduleKey, row]));
        const deliveryByType = new Map((deliveryPlan?.fixtures || []).map((row) => [String(row.fixtureType || "").toUpperCase(), row]));
        for (const fixture of sceneModel.fixtures || []) {
          const fallback = addMetricFixtureFallback(THREE, scene, fixture, fixtureMaterials, disposables);
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
          lod.userData.moduleKey = fixture.moduleKey;
          lod.userData.fixtureCode = fixture.fixtureCode;
          scene.add(lod);
          assetRoots.push(lod);
          fallback.visible = false;
        }

        const facingInstances = buildFacingInstances(THREE, sceneModel, visualPlan);
        if (facingInstances.length) {
          const geometry = new THREE.BoxGeometry(1, 1, 1);
          const material = new THREE.MeshPhysicalMaterial({ color: 0xffffff, roughness: 0.43, metalness: 0.01, clearcoat: 0.07 });
          disposables.push(geometry, material);
          const mesh = new THREE.InstancedMesh(geometry, material, facingInstances.length);
          facingInstances.forEach((instance, index) => {
            mesh.setMatrixAt(index, instance.matrix);
            mesh.setColorAt(index, new THREE.Color().setHSL(instance.hue, 0.48, 0.66, THREE.SRGBColorSpace));
          });
          mesh.instanceMatrix.needsUpdate = true;
          if (mesh.instanceColor) mesh.instanceColor.needsUpdate = true;
          mesh.castShadow = true;
          mesh.receiveShadow = true;
          scene.add(mesh);
        }

        const deliveryBySku = productDeliveryIndex(deliveryPlan);
        const texturedFacings = facingInstances.filter((row) => row.frontMatrix && row.fallbackImagePath);
        const planeGeometry = texturedFacings.length ? new THREE.PlaneGeometry(1, 1) : null;
        if (planeGeometry) disposables.push(planeGeometry);
        const materialCache = new Map();
        for (const instance of texturedFacings) {
          if (disposed) break;
          const delivery = deliveryBySku.get(instance.sku) || {
            sku: instance.sku,
            mode: "packshot",
            path: instance.fallbackImagePath,
            fallbackPath: instance.fallbackImagePath,
          };
          const cacheKey = JSON.stringify([delivery.mode, delivery.path, delivery.fallbackPath, delivery.atlasUv || null]);
          let material = materialCache.get(cacheKey);
          if (!material) {
            try {
              const loaded = await assetRuntime.loadProductTexture(delivery);
              material = new THREE.MeshStandardMaterial({
                map: loaded.texture,
                color: 0xffffff,
                roughness: 0.48,
                metalness: 0,
                transparent: true,
                alphaTest: 0.025,
                side: THREE.DoubleSide,
                polygonOffset: true,
                polygonOffsetFactor: -1,
                polygonOffsetUnits: -1,
              });
              material.userData.deliveryMode = loaded.mode;
              material.userData.fallbackUsed = loaded.fallbackUsed;
              disposables.push(material, loaded.texture);
              materialCache.set(cacheKey, material);
            } catch {
              continue;
            }
          }
          const plane = new THREE.Mesh(planeGeometry, material);
          plane.matrixAutoUpdate = false;
          plane.matrix.copy(instance.frontMatrix);
          plane.renderOrder = 4;
          plane.userData.sku = instance.sku;
          scene.add(plane);
        }

        const center = new THREE.Vector3(sceneModel.floor.widthM / 2, 1.2, sceneModel.floor.depthM / 2);
        const picker = (sceneModel.architecture || []).find((row) => row.type === "picker_entry");
        if (preset === "picker" && picker) {
          camera.position.set(picker.centerXM, 1.62, picker.centerYM);
          const dispatch = (sceneModel.architecture || []).find((row) => row.type === "dispatch");
          const target = dispatch ? new THREE.Vector3(dispatch.centerXM, 1.2, dispatch.centerYM) : center;
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
        if (item.material) disposeMaterial(item.material, seen);
        item.dispose?.();
      }
      if (mountRef.current) mountRef.current.replaceChildren();
    };
  }, [ariaLabel, deliveryPlan, errorLabel, loadingLabel, preset, sceneModel, visualPlan]);

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
        data-product-instance-cap={MAX_PRODUCT_INSTANCES}
      />
    </div>
  );
}
