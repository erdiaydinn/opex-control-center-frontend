import React, { useEffect, useMemo, useRef, useState } from "react";
import * as THREE from "three";
import { OrbitControls } from "three/examples/jsm/controls/OrbitControls.js";

import { translatePlanogramExperience } from "../../platform/i18n/planogramExperienceMessages.js";
import { buildPlanogramScene, moduleByKey } from "./planogramSceneModel.js";
import "./planogram-experience.css";

function fmt(value) {
  const parsed = Number(value);
  return Number.isFinite(parsed) ? parsed.toFixed(parsed >= 10 ? 0 : 1) : "—";
}

function productLabel(product) {
  return `${product.productName} · ${product.sku}`;
}

function Module2D({ module, selectedProductKey, setSelectedProductKey, t }) {
  const width = module.widthCm;
  const height = module.heightCm;
  const padding = Math.max(width, height) * 0.03;
  const viewHeight = height + padding * 2;
  const viewWidth = width + padding * 2;

  return (
    <div className="eay-planogram-2d-wrap">
      <svg
        className="eay-planogram-2d"
        viewBox={`0 0 ${viewWidth} ${viewHeight}`}
        role="img"
        aria-label={`${t("twoD")}: ${t("aisle")} ${module.aisleId}, ${t("module")} ${module.moduleId}`}
      >
        <rect x={padding} y={padding} width={width} height={height} className="fixture-frame" />
        {module.shelves.map((shelf) => {
          const shelfTop = padding + height - shelf.yCm - shelf.heightCm;
          return (
            <g key={shelf.key}>
              <rect
                x={padding}
                y={shelfTop}
                width={shelf.widthCm}
                height={shelf.heightCm}
                className="shelf-zone"
              />
              <line
                x1={padding}
                x2={padding + shelf.widthCm}
                y1={shelfTop + shelf.heightCm}
                y2={shelfTop + shelf.heightCm}
                className="shelf-line"
              />
              {shelf.products.flatMap((product) => {
                const faces = [];
                const faceWidth = product.widthCm;
                for (let face = 0; face < product.facing; face += 1) {
                  const x = padding + product.xCm + face * faceWidth;
                  const productHeight = Math.min(product.heightCm, shelf.heightCm);
                  const y = shelfTop + shelf.heightCm - productHeight;
                  faces.push(
                    <rect
                      key={`${product.key}:${face}`}
                      x={x}
                      y={y}
                      width={faceWidth}
                      height={productHeight}
                      className={selectedProductKey === product.key ? "product-face is-selected" : "product-face"}
                      onClick={() => setSelectedProductKey(product.key)}
                      tabIndex="0"
                      role="button"
                      aria-label={productLabel(product)}
                      onKeyDown={(event) => {
                        if (event.key === "Enter" || event.key === " ") {
                          event.preventDefault();
                          setSelectedProductKey(product.key);
                        }
                      }}
                    />
                  );
                }
                return faces;
              })}
            </g>
          );
        })}
      </svg>
    </div>
  );
}

function disposeObject(object) {
  object.traverse((child) => {
    if (child.geometry) child.geometry.dispose();
    if (child.material) {
      const materials = Array.isArray(child.material) ? child.material : [child.material];
      materials.forEach((material) => material.dispose());
    }
  });
}

function Module3D({ module, selectedProductKey, onUnavailable }) {
  const hostRef = useRef(null);

  useEffect(() => {
    const host = hostRef.current;
    if (!host || !module?.geometryReady) return undefined;

    let renderer;
    try {
      renderer = new THREE.WebGLRenderer({ antialias: true, alpha: true });
    } catch {
      onUnavailable();
      return undefined;
    }

    renderer.setPixelRatio(Math.min(window.devicePixelRatio || 1, 2));
    renderer.outputColorSpace = THREE.SRGBColorSpace;
    host.replaceChildren(renderer.domElement);

    const scene = new THREE.Scene();
    const camera = new THREE.PerspectiveCamera(38, 1, 0.1, 1000);
    const scale = 0.02;
    const width = module.widthCm * scale;
    const height = module.heightCm * scale;
    const depth = module.depthCm * scale;
    camera.position.set(width * 1.25, height * 0.9, Math.max(depth * 3.2, width * 1.6));
    camera.lookAt(0, height * 0.45, 0);

    const reducedMotion = window.matchMedia?.("(prefers-reduced-motion: reduce)")?.matches === true;
    const controls = new OrbitControls(camera, renderer.domElement);
    controls.enableDamping = !reducedMotion;
    controls.enablePan = false;
    controls.minDistance = Math.max(width, height) * 0.8;
    controls.maxDistance = Math.max(width, height) * 6;
    controls.target.set(0, height * 0.45, 0);

    scene.add(new THREE.HemisphereLight(0xffffff, 0x4b5563, 1.6));
    const keyLight = new THREE.DirectionalLight(0xffffff, 2.2);
    keyLight.position.set(width, height * 1.6, depth * 2);
    scene.add(keyLight);

    const frameMaterial = new THREE.MeshStandardMaterial({ color: 0x64748b, roughness: 0.72, metalness: 0.08 });
    const shelfMaterial = new THREE.MeshStandardMaterial({ color: 0x94a3b8, roughness: 0.72, metalness: 0.08 });
    const productMaterial = new THREE.MeshStandardMaterial({ color: 0x2563eb, roughness: 0.56 });
    const selectedMaterial = new THREE.MeshStandardMaterial({ color: 0xf59e0b, roughness: 0.5 });

    const frameThickness = Math.max(0.025, width * 0.01);
    const sideGeometry = new THREE.BoxGeometry(frameThickness, height, depth);
    const leftSide = new THREE.Mesh(sideGeometry, frameMaterial);
    leftSide.position.set(-width / 2, height / 2, 0);
    const rightSide = new THREE.Mesh(sideGeometry.clone(), frameMaterial.clone());
    rightSide.position.set(width / 2, height / 2, 0);
    scene.add(leftSide, rightSide);

    module.shelves.forEach((shelf) => {
      const shelfDepth = shelf.depthCm * scale;
      const shelfWidth = shelf.widthCm * scale;
      const shelfY = shelf.yCm * scale;
      const boardThickness = Math.max(0.025, height * 0.007);
      const board = new THREE.Mesh(
        new THREE.BoxGeometry(shelfWidth, boardThickness, shelfDepth),
        shelfMaterial.clone()
      );
      board.position.set(-width / 2 + shelfWidth / 2, shelfY, 0);
      scene.add(board);

      shelf.products.forEach((product) => {
        const faceWidth = product.widthCm * scale;
        const productHeight = product.heightCm * scale;
        const productDepth = product.depthCm * scale;
        for (let face = 0; face < product.facing; face += 1) {
          const box = new THREE.Mesh(
            new THREE.BoxGeometry(faceWidth, productHeight, productDepth),
            (selectedProductKey === product.key ? selectedMaterial : productMaterial).clone()
          );
          box.position.set(
            -width / 2 + (product.xCm + product.widthCm * face + product.widthCm / 2) * scale,
            shelfY + boardThickness / 2 + productHeight / 2,
            -shelfDepth / 2 + productDepth / 2
          );
          scene.add(box);
        }
      });
    });

    const resize = () => {
      const bounds = host.getBoundingClientRect();
      const nextWidth = Math.max(280, bounds.width || 280);
      const nextHeight = Math.max(320, bounds.height || 320);
      renderer.setSize(nextWidth, nextHeight, false);
      camera.aspect = nextWidth / nextHeight;
      camera.updateProjectionMatrix();
      renderer.render(scene, camera);
    };
    resize();
    const observer = new ResizeObserver(resize);
    observer.observe(host);

    let frame = 0;
    const drawOnce = () => {
      controls.update();
      renderer.render(scene, camera);
    };
    const animate = () => {
      drawOnce();
      frame = window.requestAnimationFrame(animate);
    };
    const onControlChange = () => {
      if (reducedMotion) renderer.render(scene, camera);
    };

    if (reducedMotion) {
      controls.addEventListener("change", onControlChange);
      drawOnce();
    } else {
      animate();
    }

    return () => {
      if (frame) window.cancelAnimationFrame(frame);
      observer.disconnect();
      controls.removeEventListener("change", onControlChange);
      controls.dispose();
      disposeObject(scene);
      frameMaterial.dispose();
      shelfMaterial.dispose();
      productMaterial.dispose();
      selectedMaterial.dispose();
      renderer.dispose();
      host.replaceChildren();
    };
  }, [module, onUnavailable, selectedProductKey]);

  return <div ref={hostRef} className="eay-planogram-3d" aria-hidden="true" />;
}

function ProductList({ module, selectedProductKey, setSelectedProductKey, t }) {
  const products = module.shelves.flatMap((shelf) => (
    shelf.products.map((product) => ({ shelf, product }))
  ));

  return (
    <section className="eay-planogram-placement-list" aria-label={t("accessibleList")}>
      <h4>{t("accessibleList")}</h4>
      {products.length === 0 ? <p>{t("emptyModule")}</p> : (
        <ul>
          {products.map(({ shelf, product }) => (
            <li key={product.key}>
              <button
                type="button"
                className={selectedProductKey === product.key ? "is-selected" : ""}
                onClick={() => setSelectedProductKey(product.key)}
              >
                <strong>{product.productName}</strong>
                <span>{product.sku}</span>
                <span>{t("shelf")}: {shelf.shelfNo} · {t("productPosition")}: {product.positionOrder}</span>
                <span>{t("facings")}: {product.facing}</span>
                <span>{t("dimensions")}: {fmt(product.widthCm)} × {fmt(product.heightCm)} × {fmt(product.depthCm)} cm</span>
                <span>{t("dimensionSource")}: {product.dimensionSource}</span>
              </button>
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}

export default function PlanogramExperience({ result, locale }) {
  const t = useMemo(() => (key) => translatePlanogramExperience(locale, key), [locale]);
  const scene = useMemo(() => buildPlanogramScene(result), [result]);
  const firstReadyKey = scene.modules.find((module) => module.geometryReady)?.key || scene.modules[0]?.key || "";
  const [moduleKey, setModuleKey] = useState(firstReadyKey);
  const [mode, setMode] = useState("2d");
  const [selectedProductKey, setSelectedProductKey] = useState("");
  const [webglUnavailable, setWebglUnavailable] = useState(false);

  useEffect(() => {
    setModuleKey(firstReadyKey);
    setSelectedProductKey("");
    setMode("2d");
    setWebglUnavailable(false);
  }, [firstReadyKey, result]);

  const selectedModule = moduleByKey(scene, moduleKey) || scene.modules[0] || null;

  if (!scene.renderable) {
    return (
      <section className="eay-planogram-experience is-empty" role="status" aria-live="polite">
        <h3>{t("title")}</h3>
        <p>{t("noPlan")}</p>
      </section>
    );
  }

  return (
    <section className="eay-planogram-experience">
      <header className="eay-planogram-experience-head">
        <div>
          <span>{t("previewUnattested")}</span>
          <h3>{t("title")}</h3>
          <p>{t("subtitle")}</p>
        </div>
        <strong>{t("productionAuthorityBlocked")}</strong>
      </header>

      <div className="eay-planogram-experience-grid">
        <aside className="eay-planogram-module-nav" aria-label={t("topologyNavigator")}>
          <h4>{t("topologyNavigator")}</h4>
          <p>{t("schematicNavigator")}</p>
          {scene.aisles.map((aisle) => (
            <div key={aisle.aisleId} className="eay-planogram-aisle-group">
              <strong>{t("aisle")} {aisle.aisleId}</strong>
              <div>
                {aisle.modules.map((module) => (
                  <button
                    type="button"
                    key={module.key}
                    className={module.key === selectedModule?.key ? "is-selected" : ""}
                    onClick={() => {
                      setModuleKey(module.key);
                      setSelectedProductKey("");
                    }}
                    aria-pressed={module.key === selectedModule?.key}
                  >
                    <span>{t("module")} {module.moduleId} · {module.side}</span>
                    <small>{module.productCount} {t("products")} · {module.geometryReady ? t("geometryReady") : t("geometryBlocked")}</small>
                  </button>
                ))}
              </div>
            </div>
          ))}
        </aside>

        <div className="eay-planogram-viewer">
          <div className="eay-planogram-viewer-toolbar" role="group" aria-label={t("selectModule")}>
            <div>
              <strong>{t("aisle")} {selectedModule?.aisleId} · {t("module")} {selectedModule?.moduleId}</strong>
              <span>{selectedModule?.moduleType} · {selectedModule?.storageType}</span>
            </div>
            <div className="eay-planogram-mode-switch">
              <button type="button" onClick={() => setMode("2d")} aria-pressed={mode === "2d"}>{t("twoD")}</button>
              <button
                type="button"
                onClick={() => setMode("3d")}
                aria-pressed={mode === "3d"}
                disabled={!selectedModule?.geometryReady || webglUnavailable}
              >
                {t("threeD")}
              </button>
            </div>
          </div>

          {!selectedModule?.geometryReady ? (
            <div className="eay-planogram-geometry-blocked" role="alert">
              <strong>{t("geometryBlocked")}</strong>
              <p>{t("noGeometry")}</p>
            </div>
          ) : (
            <>
              <p className="eay-planogram-geometry-note">{t("exactGeometry")}</p>
              {mode === "2d" ? (
                <Module2D
                  module={selectedModule}
                  selectedProductKey={selectedProductKey}
                  setSelectedProductKey={setSelectedProductKey}
                  t={t}
                />
              ) : (
                <Module3D
                  module={selectedModule}
                  selectedProductKey={selectedProductKey}
                  onUnavailable={() => {
                    setWebglUnavailable(true);
                    setMode("2d");
                  }}
                />
              )}
            </>
          )}

          {webglUnavailable ? <p className="eay-planogram-webgl-note" role="status">{t("webglUnavailable")}</p> : null}
          {selectedModule ? (
            <ProductList
              module={selectedModule}
              selectedProductKey={selectedProductKey}
              setSelectedProductKey={setSelectedProductKey}
              t={t}
            />
          ) : null}
        </div>
      </div>
    </section>
  );
}
