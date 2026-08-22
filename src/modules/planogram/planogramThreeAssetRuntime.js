const DEFAULT_TRANSCODER_PATH = "/planogram-assets/basis/";
const GOVERNED_PREFIX = "/planogram-assets/";

function safeGovernedPath(value) {
  const path = String(value ?? "").trim();
  if (!path.startsWith(GOVERNED_PREFIX) || path.startsWith("//") || path.includes("\\")) return false;
  if (path.includes("#") || /%(?:2e|2f|5c|00)/i.test(path)) return false;
  const pathname = path.split("?", 1)[0];
  return !pathname.split("/").some((segment) => segment === "." || segment === "..");
}

function textureTransform(atlasUv) {
  if (!Array.isArray(atlasUv) || atlasUv.length !== 4) return null;
  const [u0, v0, u1, v1] = atlasUv.map(Number);
  if (![u0, v0, u1, v1].every(Number.isFinite)) return null;
  if (u0 < 0 || v0 < 0 || u1 > 1 || v1 > 1 || u1 <= u0 || v1 <= v0) return null;
  return Object.freeze({
    offsetU: u0,
    offsetV: v0,
    repeatU: u1 - u0,
    repeatV: v1 - v0,
  });
}

function configureTexture(THREE, texture, renderer) {
  texture.colorSpace = THREE.SRGBColorSpace;
  texture.wrapS = THREE.ClampToEdgeWrapping;
  texture.wrapT = THREE.ClampToEdgeWrapping;
  const maxAnisotropy = renderer?.capabilities?.getMaxAnisotropy?.() || 1;
  texture.anisotropy = Math.min(8, maxAnisotropy);
  texture.needsUpdate = true;
  return texture;
}

async function loadTextureWithFallback({ THREE, renderer, delivery, transcoderPath }) {
  const fallbackPath = String(delivery?.fallbackPath || delivery?.path || "");
  if (fallbackPath && !safeGovernedPath(fallbackPath)) throw new Error("unsafe_packshot_path");

  if (delivery?.mode === "ktx2" && safeGovernedPath(delivery.path)) {
    let loader;
    try {
      const { KTX2Loader } = await import("three/examples/jsm/loaders/KTX2Loader.js");
      loader = new KTX2Loader();
      loader.setTranscoderPath(transcoderPath);
      loader.detectSupport(renderer);
      const texture = await loader.loadAsync(delivery.path);
      return Object.freeze({
        texture: configureTexture(THREE, texture, renderer),
        mode: "ktx2",
        fallbackUsed: false,
      });
    } catch {
      // Runtime acceleration failure must degrade to the governed packshot.
    } finally {
      loader?.dispose?.();
    }
  }

  if (delivery?.mode === "atlas" && safeGovernedPath(delivery.path)) {
    const transform = textureTransform(delivery.atlasUv);
    if (transform) {
      try {
        const baseTexture = await new THREE.TextureLoader().loadAsync(delivery.path);
        configureTexture(THREE, baseTexture, renderer);
        const texture = baseTexture.clone();
        texture.offset.set(transform.offsetU, transform.offsetV);
        texture.repeat.set(transform.repeatU, transform.repeatV);
        texture.needsUpdate = true;
        baseTexture.dispose();
        return Object.freeze({ texture, mode: "atlas", fallbackUsed: false });
      } catch {
        // Atlas delivery failure must degrade to the governed packshot.
      }
    }
  }

  if (!fallbackPath) throw new Error("governed_packshot_fallback_missing");
  const texture = await new THREE.TextureLoader().loadAsync(fallbackPath);
  return Object.freeze({
    texture: configureTexture(THREE, texture, renderer),
    mode: "packshot",
    fallbackUsed: delivery?.mode !== "packshot",
  });
}

function metricEnvelopeScale(THREE, root, envelope) {
  const box = new THREE.Box3().setFromObject(root);
  const size = new THREE.Vector3();
  const center = new THREE.Vector3();
  box.getSize(size);
  box.getCenter(center);
  if (size.x <= 0 || size.y <= 0 || size.z <= 0) return null;
  root.position.sub(center);
  return new THREE.Vector3(
    Number(envelope.widthM) / size.x,
    Number(envelope.heightM) / size.y,
    Number(envelope.depthM) / size.z
  );
}

export function createPlanogramThreeAssetRuntime({ THREE, renderer, transcoderPath = DEFAULT_TRANSCODER_PATH }) {
  if (!THREE || !renderer) throw new Error("three_runtime_required");
  if (!safeGovernedPath(transcoderPath)) throw new Error("unsafe_transcoder_path");

  return Object.freeze({
    contract: "eay.planogram.three-asset-runtime.v1",
    geometryAuthority: "canonical_store_scene",
    productionReleaseAllowed: false,
    async loadProductTexture(delivery) {
      return loadTextureWithFallback({ THREE, renderer, delivery, transcoderPath });
    },
    async loadFixtureLod({ levels, targetEnvelopeM }) {
      if (!Array.isArray(levels) || !levels.length) return null;
      const { GLTFLoader } = await import("three/examples/jsm/loaders/GLTFLoader.js");
      const loader = new GLTFLoader();
      const lod = new THREE.LOD();
      let added = 0;
      for (const level of levels) {
        const modelPath = String(level?.modelPath ?? level?.path ?? "").trim();
        if (!safeGovernedPath(modelPath) || !/\.glb(\?.*)?$/i.test(modelPath)) continue;
        try {
          const gltf = await loader.loadAsync(modelPath);
          const root = gltf.scene.clone(true);
          const scale = metricEnvelopeScale(THREE, root, targetEnvelopeM);
          if (!scale) continue;
          const group = new THREE.Group();
          group.add(root);
          group.scale.copy(scale);
          group.position.y = Number(targetEnvelopeM.heightM) / 2;
          group.userData.geometryAuthority = "canonical_store_scene";
          group.userData.visualAssetAuthority = "attested_same_origin_glb_lod";
          group.userData.quality = level.quality;
          group.userData.modelPath = modelPath;
          group.traverse((node) => {
            if (!node.isMesh) return;
            node.castShadow = true;
            node.receiveShadow = true;
          });
          lod.addLevel(group, Math.max(0, Number(level.distanceM) || 0));
          added += 1;
        } catch {
          // A missing LOD level must not hide the metric primitive fallback.
        }
      }
      if (!added) return null;
      lod.userData.geometryAuthority = "canonical_store_scene";
      lod.userData.productionReleaseAllowed = false;
      return lod;
    },
  });
}

export const PLANOGRAM_THREE_ASSET_RUNTIME = Object.freeze({
  contract: "eay.planogram.three-asset-runtime.v1",
  defaultTranscoderPath: DEFAULT_TRANSCODER_PATH,
  geometryAuthority: "canonical_store_scene",
  productionReleaseAllowed: false,
});
