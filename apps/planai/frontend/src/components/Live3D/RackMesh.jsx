import React from "react";
import ProductTile3D from "./ProductTile3D";

export default function RackMesh({ module, aisle, onSelectProduct, selectedSku }) {
  const shelves = module?.shelves || [];
  const width = Math.max(1.2, Number(module?.module_width_cm || 100) / 70);
  const depth = Math.max(0.48, Number(module?.module_depth_cm || 50) / 95);
  const height = Math.max(1.8, Number(module?.module_height_cm || 210) / 105);
  const shelfGap = height / Math.max(shelves.length || 1, 1);
  return (
    <group>
      {[0, width].map((x) => [0, -depth].map((z) => (
        <mesh key={`${x}-${z}`} castShadow receiveShadow position={[x, height / 2, z]}>
          <boxGeometry args={[0.06, height, 0.06]} />
          <meshStandardMaterial color="#2E3440" metalness={0.35} roughness={0.48} />
        </mesh>
      )))}
      {shelves.map((shelf, si) => {
        const y = 0.18 + si * shelfGap;
        const products = (shelf.products || []).slice(0, 14);
        return (
          <group key={shelf.shelf_no || si} position={[0, y, 0]}>
            <mesh receiveShadow>
              <boxGeometry args={[width + 0.08, 0.045, depth + 0.08]} />
              <meshStandardMaterial color="#E8E2D8" roughness={0.65} metalness={0.12} />
            </mesh>
            <group position={[0.12, 0.18, -0.04]}>
              {products.map((p, pi) => Array.from({ length: Math.max(1, Math.min(3, Number(p.facing_count || p.facing || 1))) }).map((_, fi) => (
                <ProductTile3D key={`${p.sku || pi}-${fi}`} product={p} index={pi} facingIndex={fi} selected={String(selectedSku || "") === String(p.sku || "")} onSelect={onSelectProduct} />
              )))}
            </group>
          </group>
        );
      })}
    </group>
  );
}
