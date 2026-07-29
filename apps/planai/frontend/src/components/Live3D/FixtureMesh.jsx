import React from "react";
import RackMesh from "./RackMesh";

export default function FixtureMesh({ aisle, module, index = 0, onSelectProduct, selectedSku }) {
  const storage = String(module?.storage_class || module?.allowed_storage_type || module?.shelves?.[0]?.allowed_storage_type || "AMBIENT").toUpperCase();
  const isCold = storage.includes("CHILLED");
  const isFrozen = storage.includes("FROZEN") || storage.includes("ICE");
  const x = index * 1.75;
  const color = isCold ? "#18C7DF" : isFrozen ? "#7B61FF" : "#DF1067";
  return (
    <group position={[x, 0, 0]}>
      {(isCold || isFrozen) && (
        <mesh castShadow receiveShadow position={[0.75, 1.08, -0.32]}>
          <boxGeometry args={[1.52, 2.16, 0.82]} />
          <meshStandardMaterial color={color} transparent opacity={0.18} roughness={0.35} metalness={0.18} />
        </mesh>
      )}
      <RackMesh aisle={aisle} module={module} onSelectProduct={onSelectProduct} selectedSku={selectedSku} />
    </group>
  );
}
