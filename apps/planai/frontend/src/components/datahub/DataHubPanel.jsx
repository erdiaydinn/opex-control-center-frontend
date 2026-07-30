import React, { useState } from "react";
import { plonagramApi } from "../../services/plonagramApi";
import "./DataHubPanel.css";

export default function DataHubPanel({ storeCode }) {
  const [active, setActive] = useState("stock");

  return (
    <div className="dh-card">
      <div className="dh-head">
        <span>DATA HUB</span>
        <h2>Yükleme ve Zeka Katmanı</h2>
        <p>Master data ve global satış içeride kalır. Kullanıcı stok listesini, opsiyonel satış/ABC dosyasını ve layout objelerini yükler.</p>
      </div>

      <div className="dh-tabs">
        <button className={active==="stock" ? "active" : ""} onClick={()=>setActive("stock")}>Ürün / Stok</button>
        <button className={active==="sales" ? "active" : ""} onClick={()=>setActive("sales")}>Satış / ABC Opsiyonel</button>
        <button className={active==="layout" ? "active" : ""} onClick={()=>setActive("layout")}>Layout Obje</button>
        <button className={active==="quality" ? "active" : ""} onClick={()=>setActive("quality")}>Veri Kalitesi</button>
      </div>

      <div className="dh-body">
        {active === "stock" && <p>Stok dosyası zorunlu katmandır. Başlıklar değişebilir; mapping engine alias ile yakalar.</p>}
        {active === "sales" && <p>Satış/ABC dosyası opsiyoneldir. Yüklenmezse iç benchmark satış zekası kullanılır.</p>}
        {active === "layout" && <p>DXF yoksa layout obje şablonu ile koridor, raf, dolap ve alanlar işlenir.</p>}
        {active === "quality" && <p>Eksik ölçü, yanlış storage, aynı SKU tekrarı ve soğuk zincir uyumsuzluğu burada gösterilir.</p>}
      </div>
    </div>
  );
}