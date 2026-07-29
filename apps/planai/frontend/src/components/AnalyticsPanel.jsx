import React from "react";
import { Card, Stat } from "./common";

function fmtM3(cm3) { return `${(cm3 / 1000000).toFixed(2)} m³`; }
function pct(v) { return `${Math.round(Number(v) || 0)}%`; }
function m2(v) { return `${Number(v || 0).toFixed(1)} m²`; }
function l(v) { return `${Math.round(Number(v) || 0).toLocaleString("tr-TR")} L`; }

export default function AnalyticsPanel({ metrics = {}, logs = [], onExport }) {
  return (
    <section className="analytics-panel">
      <Card title="Kapasite Özeti" right={<button onClick={onExport}>JSON Export</button>}>
        <div className="stat-grid">
          <Stat label="Toplam Raf" value={metrics.total_shelves || 0} />
          <Stat label="Yerleşen SKU" value={metrics.total_products || 0} />
          <Stat label="Raf Genişlik Kullanımı" value={pct(metrics.width_utilization_pct)} />
          <Stat label="Raf Hacim Kullanımı" value={pct(metrics.volume_utilization_pct)} />
          <Stat label="Kapasite Hacmi" value={fmtM3(metrics.volume_capacity_cm3 || 0)} />
          <Stat label="Kullanılan Hacim" value={fmtM3(metrics.volume_used_cm3 || 0)} />
        </div>
      </Card>

      <Card title="Depo Alan Kullanımı">
        <div className="stat-grid">
          <Stat label="Brüt Alan" value={m2(metrics.gross_area_m2)} />
          <Stat label="Net Alan" value={m2(metrics.net_area_m2)} />
          <Stat label="Kullanılan Zemin" value={m2(metrics.used_floor_area_m2)} />
          <Stat label="Zemin Kullanımı" value={pct(metrics.floor_utilization_pct)} />
          <Stat label="Kolon/Duvar/Blokaj" value={m2(metrics.obstacle_area_m2)} />
          <Stat label="Operasyon Alanı" value={m2(metrics.operation_area_m2)} />
          <Stat label="Fixture Alanı" value={m2(metrics.fixture_area_m2)} />
          <Stat label="Oda/Destek Alanı" value={m2(metrics.room_area_m2)} />
        </div>
      </Card>

      <Card title="Soğuk / Donuk / Fixture Kapasitesi">
        <div className="stat-grid">
          <Stat label="Kuru Hacim Kullanımı" value={pct(metrics.ambient_volume_utilization_pct)} />
          <Stat label="+4 Hacim Kullanımı" value={pct(metrics.chilled_volume_utilization_pct)} />
          <Stat label="-18 Hacim Kullanımı" value={pct(metrics.frozen_volume_utilization_pct)} />
          <Stat label="Dolap/Oda Brüt Litre" value={l(metrics.fixture_capacity_l)} />
          <Stat label="Safety Etkin Litre" value={l(metrics.fixture_effective_capacity_l)} />
        </div>
      </Card>

      <Card title="Operasyonel Uyarı Mantığı">
        <ul className="analytics-list">
          <li>Kolon/duvar ürün hacmini değil, zemin erişimini ve ölü alanı etkiler.</li>
          <li>Dolap/oda fixture kapasitesi safety fill oranıyla ayrı takip edilir.</li>
          <li>Çift taraflı koridorlarda L/R modül ayrımı yürüyüş yolu mantığını hazırlar.</li>
          <li>Bir sonraki fazda fixture içine ürün atama ve cold/frozen safety limitleri motor seviyesine bağlanacak.</li>
        </ul>
      </Card>

      <Card title="Son İşlem Logları">
        <div className="log-list">
          {(logs || []).slice(-20).reverse().map((l, i) => (
            <div key={i} className="log-row">
              <b>{l.action}</b>
              <span>{new Date(l.ts).toLocaleString("tr-TR")}</span>
            </div>
          ))}
        </div>
      </Card>
    </section>
  );
}
