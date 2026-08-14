import React from "react";
import {
  ArrowLeft,
  Database,
  Lock,
  ShieldCheck,
} from "lucide-react";
import { useNavigate } from "react-router-dom";

import {
  useAuth,
} from "../../auth/AuthContext.jsx";
import "./access-control.css";


export default function AccessControl() {
  const navigate = useNavigate();

  const {
    user,
    tenantId,
    roles,
    permissions,
    permissionAssignments,
    isSuperAdmin,
  } = useAuth();

  if (!isSuperAdmin()) {
    return (
      <main className="access-page">
        <section className="access-denied">
          <Lock size={32} />
          <h1>
            Bu alan yalnızca Super Admin için.
          </h1>

          <button
            type="button"
            onClick={() => navigate("/")}
          >
            Ana ekrana dön
          </button>
        </section>
      </main>
    );
  }

  return (
    <main className="access-page">
      <div className="access-bg-grid" />

      <section className="access-denied">
        <ShieldCheck size={36} />

        <h1>
          Veritabanı Yetki Otoritesi
        </h1>

        <p>
          Tarayıcı tabanlı kullanıcı, grup ve rol
          editörü güvenlik nedeniyle devre dışıdır.
          Yetkiler yalnızca backend ve veritabanı
          üzerinden yönetilir.
        </p>

        <p>
          <strong>Kullanıcı:</strong>{" "}
          {user?.email || user?.subject || "—"}
        </p>

        <p>
          <strong>Tenant:</strong>{" "}
          {tenantId || "—"}
        </p>

        <p>
          <Database size={16} />{" "}
          <strong>DB rolleri:</strong>{" "}
          {roles.length
            ? roles.join(", ")
            : "Yok"}
        </p>

        <p>
          <strong>Permission sayısı:</strong>{" "}
          {permissions.length}
        </p>

        <p>
          <strong>
            Scope assignment sayısı:
          </strong>{" "}
          {permissionAssignments.length}
        </p>

        <button
          type="button"
          onClick={() => navigate("/")}
        >
          <ArrowLeft size={16} />
          Ana ekrana dön
        </button>
      </section>
    </main>
  );
}
