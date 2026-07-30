import React from "react";
import { Box, Download, Eye, Grid3X3, Printer, Upload, Wand2 } from "lucide-react";
import { Button } from "./common";

export default function TopBar({ view, setView, status, storeCode, setStoreCode, onUploadProducts, onUploadLayout, onLoadSample, onExport, onPrintAll }) {
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
        <input className="pe-input store" value={storeCode} onChange={(e) => setStoreCode(e.target.value.toUpperCase())} />
        <Button active={view === "3D"} onClick={() => setView("3D")}><Eye size={16}/> 3D Depo</Button>
        <Button active={view === "2D"} onClick={() => setView("2D")}><Grid3X3 size={16}/> 2D Saha</Button>
        <Button active={view === "ANALYTICS"} onClick={() => setView("ANALYTICS")}><Box size={16}/> Rapor</Button>
        <label className="pe-btn pe-btn-secondary"><Upload size={16}/> Ürün CSV<input hidden type="file" accept=".csv" onChange={onUploadProducts}/></label>
        <label className="pe-btn pe-btn-secondary"><Upload size={16}/> Plan JSON/DXF<input hidden type="file" accept=".json,.dxf,.dwg,.pdf" onChange={onUploadLayout}/></label>
        <Button onClick={onLoadSample}><Wand2 size={16}/> Sample</Button>
        <Button onClick={onPrintAll}><Printer size={16}/> Yazdır</Button>
        <Button onClick={onExport}><Download size={16}/> Export</Button>
      </div>
    </header>
  );
}
