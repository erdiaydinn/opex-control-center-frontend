import React from "react";
import {
  Navigate,
  useLocation,
} from "react-router-dom";

import { useAuth } from "./AuthContext.jsx";


export default function ProtectedRoute({
  children,
  moduleKey,
  action = "view",
  roles = [],
}) {
  const {
    user,
    booting,
    can,
  } = useAuth();

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
    return (
      <Navigate
        to="/login"
        replace
        state={{ from: location }}
      />
    );
  }

  const moduleAllowed =
    !moduleKey ||
    (
      typeof can === "function" &&
      can(moduleKey, action)
    );

  const requiredRoles =
    Array.isArray(roles)
      ? roles.filter(Boolean)
      : [];

  const roleAllowed =
    requiredRoles.length === 0 ||
    requiredRoles.some((role) =>
      user.roles?.includes(role)
    );

  if (!moduleAllowed || !roleAllowed) {
    return <Navigate to="/" replace />;
  }

  return children;
}
