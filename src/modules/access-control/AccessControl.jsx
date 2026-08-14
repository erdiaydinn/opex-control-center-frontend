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
            Bu alan yaln?zca Super Admin i?in.
          </h1>

          <button
            type="button"
            onClick={() => navigate("/")}
          >
            Ana ekrana d?n
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
          Veritaban? Yetki Otoritesi
        </h1>

        <p>
          Taray?c? tabanl? kullan?c?, grup ve rol
          edit?r? g?venlik nedeniyle devre d???d?r.
          Yetkiler yaln?zca backend ve veritaban?
          ?zerinden y?netilir.
        </p>

        <p>
          <strong>Kullan?c?:</strong>{" "}
          {user?.email || user?.subject || "?"}
        </p>

        <p>
          <strong>Tenant:</strong>{" "}
          {tenantId || "?"}
        </p>

        <p>
          <Database size={16} />{" "}
          <strong>DB rolleri:</strong>{" "}
          {roles.length
            ? roles.join(", ")
            : "Yok"}
        </p>

        <p>
          <strong>Permission say?s?:</strong>{" "}
          {permissions.length}
        </p>

        <p>
          <strong>
            Scope assignment say?s?:
          </strong>{" "}
          {permissionAssignments.length}
        </p>

        <button
          type="button"
          onClick={() => navigate("/")}
        >
          <ArrowLeft size={16} />
          Ana ekrana d?n
        </button>
      </section>
    </main>
  );
}
