import React from "react";
import { Button } from "./common";

function Icon({ children }) {
  return <span className="pe-icon" aria-hidden="true">{children}</span>;
}

export default function TopBar({
  view,
  setView,
  status,
  storeCode,
  setStoreCode,
  onUploadProducts,
  onUploadLayout,
  onLoadSample,
  onExport,
  onPrintAll
}) {
  return (
    <header className="pe-topbar">
      <div className="pe-brand">
        <div className="pe-logo">P</div>
        <div>
          <div className="pe-eyebrow">AI Retail Digital Twin</div>
          <h1>Plonagram OS</h1>
          <p>{status}</p>
        </div>
      </div>

      <div className="pe-top-controls">
        <input
          className="pe-input store"
          value={storeCode}
          onChange={(e) => setStoreCode(e.target.value.toUpperCase())}
        />

        <Button active={view === "3D"} onClick={() => setView("3D")}>
          <Icon>◉</Icon> 3D Depo
        </Button>

        <Button active={view === "2D"} onClick={() => setView("2D")}>
          <Icon>▦</Icon> 2D Saha
        </Button>

        <Button active={view === "ANALYTICS"} onClick={() => setView("ANALYTICS")}>
          <Icon>◇</Icon> Rapor
        </Button>

        <label className="pe-btn pe-btn-secondary">
          <Icon>⇧</Icon> Ürün CSV
          <input hidden type="file" accept=".csv" onChange={onUploadProducts} />
        </label>

        <label className="pe-btn pe-btn-secondary">
          <Icon>⇧</Icon> Plan JSON/DXF
          <input hidden type="file" accept=".json,.dxf,.dwg,.pdf" onChange={onUploadLayout} />
        </label>

        <Button onClick={onLoadSample}>
          <Icon>✦</Icon> Sample
        </Button>

        <Button onClick={onPrintAll}>
          <Icon>▣</Icon> Yazdır
        </Button>

        <Button onClick={onExport}>
          <Icon>↓</Icon> Export
        </Button>
      </div>
    </header>
  );
}
