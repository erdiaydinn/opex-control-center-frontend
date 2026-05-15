import React, { createContext, useContext, useEffect, useMemo, useState } from "react";
import { apiGet } from "../api/client.js";

const AuthContext = createContext(null);

const DEMO_ACCESS = {
  "admin@yemeksepeti.com": {
    name: "OPEX Admin",
    roles: ["super_admin"],
    modules: {
      planogram: ["view", "admin"],
      dockos: ["view", "admin"],
      budget: ["view", "admin"],
      academy: ["view", "admin"],
      insight: ["view", "admin"],
      cycle_count: ["view", "admin"],
      admin_access: ["view", "manage"],
    },
  },
  "erdi.aydin@yemeksepeti.com": {
    name: "Erdi Aydın",
    roles: ["super_admin"],
    modules: {
      planogram: ["view", "admin"],
      dockos: ["view", "admin"],
      budget: ["view", "admin"],
      academy: ["view", "admin"],
      insight: ["view", "admin"],
      cycle_count: ["view", "admin"],
      admin_access: ["view", "manage"],
    },
  },
  "viewer@yemeksepeti.com": {
    name: "Demo Viewer",
    roles: ["viewer"],
    modules: {
      planogram: ["view"],
      dockos: ["view"],
    },
  },
  "noaccess@yemeksepeti.com": {
    name: "No Access User",
    roles: ["viewer"],
    modules: {},
  },
};

function buildDemoUser(email) {
  const normalizedEmail = String(email || "").trim().toLowerCase();
  const access = DEMO_ACCESS[normalizedEmail];

  if (!access) {
    return {
      email: normalizedEmail,
      name: normalizedEmail,
      roles: ["viewer"],
      modules: {},
    };
  }

  return {
    email: normalizedEmail,
    ...access,
  };
}

export function AuthProvider({ children }) {
  const [user, setUser] = useState(null);
  const [booting, setBooting] = useState(true);

  async function loadMe() {
    setBooting(true);

    try {
      const me = await apiGet("/auth/me");
      setUser(me);
      return me;
    } catch {
      const savedEmail = localStorage.getItem("opex_demo_email");

      if (!savedEmail) {
        setUser(null);
        return null;
      }

      const fallbackUser = buildDemoUser(savedEmail);
      setUser(fallbackUser);
      return fallbackUser;
    } finally {
      setBooting(false);
    }
  }

  async function login(email) {
    const normalizedEmail = String(email || "").trim().toLowerCase();

    if (!normalizedEmail || !normalizedEmail.includes("@")) {
      throw new Error("Geçerli bir email girin.");
    }

    localStorage.setItem("opex_demo_email", normalizedEmail);
    const demoUser = buildDemoUser(normalizedEmail);
    setUser(demoUser);
    setBooting(false);

    return demoUser;
  }

  function logout() {
    localStorage.removeItem("opex_demo_email");
    setUser(null);
  }

  function isSuperAdmin() {
    return Array.isArray(user?.roles) && user.roles.includes("super_admin");
  }

  function hasPermission(moduleKey, action = "view") {
    if (!user) return false;
    if (isSuperAdmin()) return true;

    const actions = user?.modules?.[moduleKey];
    return Array.isArray(actions) && actions.includes(action);
  }

  const value = useMemo(
    () => ({
      user,
      booting,
      login,
      logout,
      hasPermission,
      can: hasPermission,
      isSuperAdmin,
      reload: loadMe,
    }),
    [user, booting]
  );

  useEffect(() => {
    loadMe();
  }, []);

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth() {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error("useAuth must be used inside AuthProvider");
  return ctx;
}
