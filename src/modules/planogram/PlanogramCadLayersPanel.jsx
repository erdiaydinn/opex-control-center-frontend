import React from "react";
import { Eye, EyeOff, Layers3, LockKeyhole, UnlockKeyhole } from "lucide-react";

const LABEL_KEYS = Object.freeze({
  architecture: "layerArchitecture",
  equipment: "layerEquipment",
  operations: "layerOperations",
  annotations: "layerAnnotations",
});

export default function PlanogramCadLayersPanel({
  layerModel,
  t,
  canEdit,
  onToggleVisibility,
  onToggleLock,
}) {
  if (!layerModel?.layers?.length) return null;
  return (
    <section
      className="eay-cad-layers"
      data-cad-layer-contract={layerModel.contract}
      aria-label={t("layers")}
    >
      <header>
        <Layers3 size={17} aria-hidden="true" />
        <div>
          <strong>{t("layers")}</strong>
          <span>{t("layerWorkspaceLock")}</span>
        </div>
      </header>
      <div className="eay-cad-layers-list">
        {layerModel.layers.map((layer) => (
          <div
            key={layer.layerId}
            className="eay-cad-layer-row"
            data-layer-id={layer.layerId}
            data-visible={layer.visible ? "true" : "false"}
            data-locked={layer.locked ? "true" : "false"}
          >
            <span>
              <strong>{t(LABEL_KEYS[layer.layerId] || "layers")}</strong>
              <small>{layer.count}</small>
            </span>
            <button
              type="button"
              aria-pressed={layer.visible ? "true" : "false"}
              aria-label={layer.visible ? t("hideLayer") : t("showLayer")}
              onClick={() => onToggleVisibility?.(layer.layerId)}
            >
              {layer.visible
                ? <Eye size={15} aria-hidden="true" />
                : <EyeOff size={15} aria-hidden="true" />}
            </button>
            <button
              type="button"
              disabled={!canEdit}
              aria-pressed={layer.locked ? "true" : "false"}
              aria-label={layer.locked ? t("unlockLayer") : t("lockLayer")}
              onClick={() => onToggleLock?.(layer.layerId)}
            >
              {layer.locked
                ? <LockKeyhole size={15} aria-hidden="true" />
                : <UnlockKeyhole size={15} aria-hidden="true" />}
            </button>
          </div>
        ))}
      </div>
    </section>
  );
}
