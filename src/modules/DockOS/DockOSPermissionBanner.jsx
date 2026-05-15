import React from "react";
import {
  Download,
  FileSpreadsheet,
  Lock,
  MapPin,
  ShieldCheck,
  Truck,
  Upload,
} from "lucide-react";
import { useAuth } from "../../auth/AuthContext.jsx";
import { getDockOSPermissionSnapshot } from "./dockosPermissions.js";
import "./dockos-permissions.css";

const featureLabels = {
  dashboard: "Dashboard",
  livePurchaseOrders: "Canlı PO",
  supplierAppointments: "Tedarikçi Randevu",
  shipmentDetails: "Sevkiyat Detayları",
  vehicleTracking: "Araç / Plaka",
  excelUpload: "Excel Upload",
  duplicateResolution: "Duplicate Karar",
};

const actionLabels = {
  view: "Görüntüle",
  create: "Oluştur",
  edit: "Düzenle",
  approve: "Onayla",
  export: "Export",
  delete: "Sil",
};

function scopeText(scope) {
  if (!scope || scope.type === "all") return "Tüm Türkiye";
  if (scope.type === "warehouse") return `Depo bazlı · ${(scope.warehouses || []).join(", ") || "seçilmedi"}`;
  if (scope.type === "supplier") return `Tedarikçi bazlı · ${(scope.suppliers || []).join(", ") || "seçilmedi"}`;
  if (scope.type === "region") return `Bölge bazlı · ${(scope.regions || []).join(", ") || "seçilmedi"}`;
  return "Kapsam yok";
}

export default function DockOSPermissionBanner() {
  const { user } = useAuth();
  const snapshot = getDockOSPermissionSnapshot();

  const activeFeatures = Object.entries(snapshot.features || {})
    .filter(([, value]) => value)
    .map(([key]) => featureLabels[key] || key);

  const activeActions = Object.entries(snapshot.actions || {})
    .filter(([, value]) => value)
    .map(([key]) => actionLabels[key] || key);

  return (
    <section className="dockos-permission-banner">
      <div className="dockos-permission-main">
        <div className="dockos-permission-icon">
          <ShieldCheck size={22} />
        </div>

        <div>
          <span>DockOS Permission Layer</span>
          <strong>{user?.email || "unknown user"}</strong>
          <p>Bu görünüm Access Control üzerinde tanımlanan grup + kullanıcı yetkilerine göre çalışır.</p>
        </div>
      </div>

      <div className="dockos-permission-grid">
        <div>
          <Truck size={16} />
          <small>Ekranlar</small>
          <strong>{activeFeatures.length ? activeFeatures.join(" · ") : "Yetki yok"}</strong>
        </div>

        <div>
          <Download size={16} />
          <small>Aksiyonlar</small>
          <strong>{activeActions.length ? activeActions.join(" · ") : "Yetki yok"}</strong>
        </div>

        <div>
          <MapPin size={16} />
          <small>Veri kapsamı</small>
          <strong>{scopeText(snapshot.scope)}</strong>
        </div>
      </div>

      <div className="dockos-permission-chips">
        <span className={snapshot.features?.excelUpload ? "on" : "off"}>
          <Upload size={14} />
          Excel Upload
        </span>

        <span className={snapshot.features?.duplicateResolution ? "on" : "off"}>
          <FileSpreadsheet size={14} />
          Duplicate Karar
        </span>

        <span className={snapshot.actions?.approve ? "on" : "off"}>
          {snapshot.actions?.approve ? <ShieldCheck size={14} /> : <Lock size={14} />}
          Onay
        </span>
      </div>
    </section>
  );
}
