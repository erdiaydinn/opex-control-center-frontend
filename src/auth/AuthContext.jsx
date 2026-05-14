import React, { createContext, useContext, useEffect, useMemo, useState } from "react";
import { apiGet } from "../api/client.js";

const AuthContext = createContext(null);

export function AuthProvider({ children }) {
  const [user, setUser] = useState(null);
  const [booting, setBooting] = useState(true);

  async function loadMe() {
    try {
      const me = await apiGet("/auth/me");
      setUser(me);
      return me;
    } catch {
      const fallbackUser = {
        email: localStorage.getItem("opex_demo_email") || "admin@yemeksepeti.com",
        modules: {
          planogram: ["view"],
          budget: ["view"],
          river: ["view"],
          dockos: ["view"],
          academy: ["view"],
        },
      };

      setUser(fallbackUser);
      return fallbackUser;
    } finally {
      setBooting(false);
    }
  }

  async function login(email) {
    localStorage.setItem("opex_demo_email", email.trim().toLowerCase());
    return loadMe();
  }

  function logout() {
    localStorage.removeItem("opex_demo_email");
    setUser(null);
  }

  function hasPermission(moduleKey, action = "view") {
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