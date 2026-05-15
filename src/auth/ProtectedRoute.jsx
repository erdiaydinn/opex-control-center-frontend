import React from "react";
import { Navigate, useLocation } from "react-router-dom";
import { useAuth } from "./AuthContext.jsx";

export default function ProtectedRoute({ children, moduleKey, action = "view" }) {
  const { user, booting, can, isSuperAdmin } = useAuth();
  const location = useLocation();

  if (booting) {
    return (
      <main className="auth-loading-screen">
        <div className="auth-loading-card">
          <strong>OPEX</strong>
          <span>Kontrol ediliyor...</span>
        </div>
      </main>
    );
  }

  if (!user) {
    return <Navigate to="/login" replace state={{ from: location }} />;
  }

  const superAdmin =
    typeof isSuperAdmin === "function" ? isSuperAdmin() : Boolean(isSuperAdmin);

  const allowed =
    !moduleKey ||
    superAdmin ||
    (typeof can === "function" && can(moduleKey, action));

  if (!allowed) {
    return <Navigate to="/" replace />;
  }

  return children;
}
