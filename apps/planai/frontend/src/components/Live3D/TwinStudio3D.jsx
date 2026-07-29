import { useEffect, useMemo, useRef } from 'react';
import { Canvas, useThree } from '@react-three/fiber';
import { Html, OrbitControls, PerspectiveCamera } from '@react-three/drei';
import * as THREE from 'three';
import './TwinStudio3D.css';

const ZONE_COLORS = {
  AMBIENT: '#8b5cf6',
  CHILLED: '#0891b2',
  FROZEN: '#2563eb',
  PALLET: '#b45309',
  PRODUCE: '#15803d',
  DISPATCH: '#475569',
};

function number(value, fallback = 0) {
  const parsed = Number(value);
  return Number.isFinite(parsed) ? parsed : fallback;
}

function zoneOf(value) {
  const raw = String(value?.zone || value?.storage_type || value?.storage || value?.fixture_class || '').toUpperCase();
  if (raw.includes('FROZEN') || raw.includes('DONUK')) return 'FROZEN';
  if (raw.includes('CHILL') || raw.includes('COLD') || raw.includes('SOGUK')) return 'CHILLED';
  if (raw.includes('PALLET') || raw.includes('PALET') || raw.includes('HEAVY')) return 'PALLET';
  if (raw.includes('PRODUCE') || raw.includes('MANAV')) return 'PRODUCE';
  if (raw.includes('DISPATCH')) return 'DISPATCH';
  return 'AMBIENT';
}

function objectDimensions(item) {
  return {
    width: Math.max(0.4, number(item?.w ?? item?.width ?? item?.width_m, 2)),
    depth: Math.max(0.25, number(item?.d ?? item?.depth ?? item?.depth_m, 2)),
    height: Math.max(0.2, number(item?.h ?? item?.height ?? item?.height_m, 2.5)),
  };
}

function objectPosition(item, index) {
  const x = number(item?.x, 8 + (index % 3) * 36) - 55;
  const z = number(item?.y, 14 + Math.floor(index / 3) * 20) - 45;
  return [x, z];
}

function actualAisles(objects = []) {
  return objects.filter((item) => (
    item && (
      item.type === 'corridor' ||
      item.type === 'rack_module' ||
      item.type === 'steel_rack' ||
      number(item.modules, 0) > 0 ||
      number(item.shelves, 0) > 0
    )
  ));
}

function productLocation(product) {
  return {
    aisle: String(product?.aisle_id ?? product?.aisle ?? ''),
    module: String(product?.module_id ?? product?.module ?? '1'),
    shelf: String(product?.shelf_no ?? product?.shelf ?? '1'),
  };
}

function productGroups(products = []) {
  const groups = new Map();
  products.forEach((product) => {
    const location = productLocation(product);
    const key = `${location.aisle}|${location.module}|${location.shelf}`;
    if (!groups.has(key)) groups.set(key, []);
    groups.get(key).push(product);
  });
  return groups;
}

function productColor(product, index) {
  const palette = ['#f97316', '#db2777', '#16a34a', '#7c3aed', '#0f766e', '#ca8a04'];
  const text = `${product?.brand || ''}${product?.sku || ''}`;
  const seed = [...text].reduce((total, char) => total + char.charCodeAt(0), index * 17);
  return palette[Math.abs(seed) % palette.length];
}

function ProductFaces({ products, shelfWidth, shelfDepth, shelfHeight, selectedProductSku, onSelectProduct }) {
  let cursor = -shelfWidth / 2 + 0.18;
  const visible = [];

  products.forEach((product, productIndex) => {
    const facing = Math.max(1, Math.min(12, Math.round(number(product?.facing_count ?? product?.facing, 1))));
    const unitWidth = Math.max(0.18, number(product?.width_cm, 8) / 30);
    const usedWidth = Math.max(unitWidth, Math.min(shelfWidth - 0.24, number(product?.used_width_cm, unitWidth * facing) / 30));
    const faceWidth = Math.max(0.14, Math.min(0.52, usedWidth / facing));
    const height = Math.max(0.24, Math.min(shelfHeight * 0.72, number(product?.height_cm, 20) / 30));
    const depth = Math.max(0.16, Math.min(shelfDepth * 0.62, number(product?.depth_cm, 10) / 30));
    for (let face = 0; face < facing && cursor < shelfWidth / 2; face += 1) {
      const x = cursor + faceWidth / 2;
      const selected = String(product?.sku) === String(selectedProductSku);
      visible.push(
        <group
          key={`${product?.sku || productIndex}-${face}`}
          position={[x, shelfHeight / 2 + height / 2 + 0.06, -shelfDepth * 0.28]}
          onClick={(event) => { event.stopPropagation(); onSelectProduct?.(product); }}
        >
          <mesh castShadow>
            <boxGeometry args={[faceWidth * 0.9, height, depth]} />
            <meshStandardMaterial
              color={productColor(product, productIndex)}
              roughness={0.52}
              metalness={0.05}
              emissive={selected ? productColor(product, productIndex) : '#000000'}
              emissiveIntensity={selected ? 0.35 : 0}
            />
          </mesh>
          {selected && (
            <Html position={[0, height / 2 + 0.24, 0]} center distanceFactor={24} style={{ pointerEvents: 'none' }}>
              <div className="twin-product-label">
                <strong>{product?.brand || 'Marka'}</strong>
                <span>{product?.product_name || product?.name || product?.sku}</span>
                <small>{facing} facing · {product?.storage_type || product?.storage || 'AMBIENT'}</small>
              </div>
            </Html>
          )}
        </group>,
      );
      cursor += faceWidth;
    }
    cursor += 0.08;
  });

  return visible;
}

function Rack({ aisle, index, products, selectedAreaId, selectedProductSku, onSelectArea, onSelectProduct }) {
  const [x, z] = objectPosition(aisle, index);
  const dims = objectDimensions(aisle);
  const zone = zoneOf(aisle);
  const color = ZONE_COLORS[zone];
  const moduleCount = Math.max(1, Math.min(24, Math.round(number(aisle?.modules, 1))));
  const shelfCount = Math.max(1, Math.min(8, Math.round(number(aisle?.shelves, 6) / moduleCount || 6)));
  const width = Math.max(2, dims.width);
  const depth = Math.max(1, dims.depth);
  const height = Math.max(1.8, dims.height);
  const moduleWidth = width / moduleCount;
  const aisleProducts = products.filter((product) => String(productLocation(product).aisle) === String(aisle?.id || aisle?.aisle_id));
  const groups = productGroups(aisleProducts);
  const selected = String(selectedAreaId) === String(aisle?.id || aisle?.aisle_id);

  return (
    <group position={[x, 0, z]} onClick={(event) => { event.stopPropagation(); onSelectArea?.({ ...aisle, id: aisle?.id || aisle?.aisle_id, zone }); }}>
      {Array.from({ length: moduleCount }).map((_, moduleIndex) => {
        const moduleId = String(moduleIndex + 1);
        const moduleX = -width / 2 + moduleWidth / 2 + moduleIndex * moduleWidth;
        return (
          <group key={`${aisle?.id || aisle?.aisle_id}-module-${moduleId}`} position={[moduleX, height / 2, 0]}>
            {[-0.44, 0.44].map((side) => (
              <mesh key={side} position={[side * moduleWidth, 0, 0]} castShadow>
                <boxGeometry args={[0.07, height, depth * 0.88]} />
                <meshStandardMaterial color="#64748b" metalness={0.7} roughness={0.3} />
              </mesh>
            ))}
            {Array.from({ length: shelfCount }).map((_, shelfIndex) => {
              const shelfNo = String(shelfIndex + 1);
              const shelfY = -height / 2 + ((shelfIndex + 1) * height) / (shelfCount + 1);
              const key = `${aisle?.id || aisle?.aisle_id}|${moduleId}|${shelfNo}`;
              const shelfProducts = groups.get(key) || [];
              const isSelectedShelf = selected && shelfProducts.some((item) => String(item?.sku) === String(selectedProductSku));
              return (
                <group key={key} position={[0, shelfY, 0]}>
                  <mesh castShadow receiveShadow>
                    <boxGeometry args={[moduleWidth * 0.9, 0.08, depth * 0.84]} />
                    <meshStandardMaterial color={isSelectedShelf ? '#f8fafc' : '#cbd5e1'} metalness={0.5} roughness={0.32} />
                  </mesh>
                  <ProductFaces
                    products={shelfProducts}
                    shelfWidth={moduleWidth * 0.9}
                    shelfDepth={depth * 0.84}
                    shelfHeight={height / (shelfCount + 1)}
                    selectedProductSku={selectedProductSku}
                    onSelectProduct={onSelectProduct}
                  />
                </group>
              );
            })}
          </group>
        );
      })}
      {selected && <mesh position={[0, height / 2, 0]}>
        <boxGeometry args={[width + 0.18, height + 0.18, depth + 0.18]} />
        <meshBasicMaterial color={color} wireframe transparent opacity={0.65} />
      </mesh>}
      <Html position={[0, height + 0.35, 0]} center distanceFactor={32} style={{ pointerEvents: 'none' }}>
        <div className={`twin-aisle-label ${selected ? 'selected' : ''}`}>
          <b>{aisle?.id || aisle?.aisle_id || 'A'}</b><span>{zone}</span>
        </div>
      </Html>
    </group>
  );
}

function LayoutObject({ item, index, selectedAreaId, onSelectArea }) {
  if (item?.type === 'corridor' || number(item?.modules, 0) > 0) return null;
  const dims = objectDimensions(item);
  const [x, z] = objectPosition(item, index);
  const type = String(item?.type || '').toLowerCase();
  const color = type.includes('column') ? '#475569' : type.includes('wall') ? '#1e293b' : ZONE_COLORS[zoneOf(item)];
  const selected = String(selectedAreaId) === String(item?.id);
  return (
    <group position={[x, dims.height / 2, z]} rotation={[0, number(item?.rotation, 0) * Math.PI / 180, 0]} onClick={(event) => { event.stopPropagation(); onSelectArea?.({ ...item, id: item?.id }); }}>
      <mesh castShadow receiveShadow>
        <boxGeometry args={[dims.width, dims.height, dims.depth]} />
        <meshStandardMaterial color={color} roughness={0.58} metalness={type.includes('column') ? 0.42 : 0.08} />
      </mesh>
      {selected && <mesh><boxGeometry args={[dims.width + 0.12, dims.height + 0.12, dims.depth + 0.12]} /><meshBasicMaterial color="#e11d48" wireframe /></mesh>}
      {selected && <Html position={[0, dims.height / 2 + 0.3, 0]} center distanceFactor={30} style={{ pointerEvents: 'none' }}><div className="twin-aisle-label selected"><b>{item?.label || item?.id || 'Nesne'}</b><span>{zoneOf(item)}</span></div></Html>}
    </group>
  );
}

function CameraFit({ bounds, cameraPreset, controlsRef }) {
  const { camera } = useThree();
  useEffect(() => {
    if (!bounds) return undefined;
    const center = new THREE.Vector3(bounds.centerX, 0, bounds.centerZ);
    const target = new THREE.Vector3(center.x, 0, center.z);
    const preset = String(cameraPreset || 'overview').toLowerCase();
    if (preset === 'top') camera.position.set(center.x, Math.max(20, bounds.size * 1.15), center.z + 0.01);
    else if (preset === 'dispatch') camera.position.set(bounds.maxX + bounds.size * 0.55, bounds.size * 0.52, bounds.maxZ + bounds.size * 0.55);
    else if (preset === 'chilled') camera.position.set(bounds.minX - bounds.size * 0.25, bounds.size * 0.48, bounds.minZ - bounds.size * 0.28);
    else if (preset === 'frozen') camera.position.set(bounds.maxX + bounds.size * 0.25, bounds.size * 0.48, bounds.minZ - bounds.size * 0.25);
    else camera.position.set(center.x + bounds.size * 0.75, bounds.size * 0.58, center.z + bounds.size * 0.9);
    camera.lookAt(target);
    camera.updateProjectionMatrix();
    if (controlsRef.current) {
      controlsRef.current.target.copy(target);
      controlsRef.current.update();
    }
    return undefined;
  }, [bounds, cameraPreset, camera, controlsRef]);
  return null;
}

function Scene({ objects, products, cameraPreset, selectedAreaId, selectedProductSku, onSelectArea, onSelectProduct, controlsRef }) {
  const aisles = actualAisles(objects);
  const groups = useMemo(() => productGroups(products), [products]);
  const bounds = useMemo(() => {
    const items = aisles.length ? aisles : objects;
    const points = items.map((item, index) => {
      const [x, z] = objectPosition(item, index);
      const dims = objectDimensions(item);
      return { x, z, r: Math.max(dims.width, dims.depth) / 2 };
    });
    if (!points.length) return { minX: -20, maxX: 20, minZ: -20, maxZ: 20, centerX: 0, centerZ: 0, size: 40 };
    const minX = Math.min(...points.map((p) => p.x - p.r));
    const maxX = Math.max(...points.map((p) => p.x + p.r));
    const minZ = Math.min(...points.map((p) => p.z - p.r));
    const maxZ = Math.max(...points.map((p) => p.z + p.r));
    return { minX, maxX, minZ, maxZ, centerX: (minX + maxX) / 2, centerZ: (minZ + maxZ) / 2, size: Math.max(maxX - minX, maxZ - minZ, 20) };
  }, [aisles, objects]);

  return (
    <>
      <color attach="background" args={["#f8fafc"]} />
      <ambientLight intensity={1.35} />
      <directionalLight position={[20, 28, 12]} intensity={1.5} castShadow />
      <hemisphereLight intensity={0.45} groundColor="#cbd5e1" />
      <mesh rotation={[-Math.PI / 2, 0, 0]} position={[0, -0.04, 0]} receiveShadow>
        <planeGeometry args={[Math.max(80, bounds.size * 2.2), Math.max(80, bounds.size * 2.2)]} />
        <meshStandardMaterial color="#e2e8f0" roughness={0.86} />
      </mesh>
      <gridHelper args={[Math.max(80, bounds.size * 2.2), 40, '#cbd5e1', '#e2e8f0']} position={[0, 0.01, 0]} />
      {objects.map((item, index) => <LayoutObject key={item?.id || `object-${index}`} item={item} index={index} selectedAreaId={selectedAreaId} onSelectArea={onSelectArea} />)}
      {aisles.map((aisle, index) => <Rack key={aisle?.id || aisle?.aisle_id || index} aisle={aisle} index={index} products={products} selectedAreaId={selectedAreaId} selectedProductSku={selectedProductSku} onSelectArea={onSelectArea} onSelectProduct={onSelectProduct} />)}
      <PerspectiveCamera makeDefault fov={42} position={[bounds.centerX + bounds.size, bounds.size * 0.65, bounds.centerZ + bounds.size]} />
      <CameraFit bounds={bounds} cameraPreset={cameraPreset} controlsRef={controlsRef} />
      <OrbitControls ref={controlsRef} makeDefault enableDamping dampingFactor={0.12} minDistance={8} maxDistance={Math.max(80, bounds.size * 3)} maxPolarAngle={Math.PI / 2.05} />
    </>
  );
}

export default function TwinStudio3D({ objects = [], products = [], cameraPreset = 'overview', heatmap = 'sales', selectedAreaId, selectedProductSku, onSelectArea, onSelectProduct }) {
  const controlsRef = useRef(null);
  const visibleProducts = products.filter(Boolean);
  return (
    <div className="twin-studio-canvas twin-studio-canvas--foundation">
      <Canvas shadows dpr={[1, 1.5]} camera={{ position: [30, 24, 32], fov: 42 }} onContextMenu={(event) => event.preventDefault()}>
        <Scene objects={objects} products={visibleProducts} cameraPreset={cameraPreset} selectedAreaId={selectedAreaId} selectedProductSku={selectedProductSku} onSelectArea={onSelectArea} onSelectProduct={onSelectProduct} controlsRef={controlsRef} />
      </Canvas>
      <div className="twin-foundation-status">
        <span>{visibleProducts.length.toLocaleString('tr-TR')} gerçek yerleşim</span>
        <span>Katman: ürün + fixture</span>
        <span>Heatmap: {heatmap}</span>
      </div>
    </div>
  );
}

