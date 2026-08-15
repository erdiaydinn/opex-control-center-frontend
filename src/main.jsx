import React from "react";
import { createRoot } from "react-dom/client";
import { BrowserRouter } from "react-router-dom";
import App from "./App.jsx";
import { AuthProvider } from "./auth/AuthContext.jsx";
import RouteAccessibility from "./platform/accessibility/RouteAccessibility.jsx";
import SkipToMainContent from "./platform/accessibility/SkipToMainContent.jsx";
import AccessibilityControl from "./platform/preferences/AccessibilityControl.jsx";
import { PlatformPreferencesProvider } from "./platform/preferences/PlatformPreferencesContext.jsx";
import "./styles.css";

createRoot(document.getElementById("root")).render(
  <React.StrictMode>
    <PlatformPreferencesProvider>
      <BrowserRouter>
        <AuthProvider>
          <SkipToMainContent />
          <AccessibilityControl />
          <RouteAccessibility />
          <main id="eay-main-content" tabIndex="-1">
            <App />
          </main>
        </AuthProvider>
      </BrowserRouter>
    </PlatformPreferencesProvider>
  </React.StrictMode>
);
