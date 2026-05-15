import React from "react";
import { Navigate } from "react-router-dom";
import { useAuth } from "./AuthContext.jsx";

export default function ProtectedRoute({ moduleKey, action = "view", children }) {
  const { user, booting, can } = useAuth();

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
    return <Navigate to="/login" replace />;
  }

  if (moduleKey && !can(moduleKey, action)) {
    return <Navigate to="/" replace />;
  }

  return children;
}
