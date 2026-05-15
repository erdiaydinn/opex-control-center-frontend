import React, { createContext, useCallback, useContext, useEffect, useMemo, useState } from "react";
import {
  buildUserFromEmail,
  canUser,
  canUserAction,
  canUserFeature,
  clearSessionUser,
  getAccessConfig,
  getSessionUser,
  getUserModuleScope,
  isUserSuperAdmin,
  saveAccessConfig,
  saveSessionUser,
} from "./accessConfig.js";

const AuthContext = createContext(null);

export function AuthProvider({ children }) {
  const [accessConfig, setAccessConfig] = useState(() => getAccessConfig());
  const [user, setUser] = useState(() => getSessionUser());

  useEffect(() => {
    function handleAccessUpdate() {
      setAccessConfig(getAccessConfig());
    }

    window.addEventListener("opex-access-config-updated", handleAccessUpdate);
    window.addEventListener("storage", handleAccessUpdate);

    return () => {
      window.removeEventListener("opex-access-config-updated", handleAccessUpdate);
      window.removeEventListener("storage", handleAccessUpdate);
    };
  }, []);

  const login = useCallback(async (email) => {
    const sessionUser = buildUserFromEmail(email);

    if (!sessionUser) {
      throw new Error("Geçerli bir kullanıcı girin.");
    }

    if (sessionUser.status !== "active") {
      throw new Error("Bu kullanıcı pasif durumda.");
    }

    saveSessionUser(sessionUser);
    setUser(sessionUser);
    return sessionUser;
  }, []);

  const logout = useCallback(() => {
    clearSessionUser();
    setUser(null);
  }, []);

  const can = useCallback(
    (moduleKey, action = "view") => {
      if (!user?.email) return false;
      return canUser(user.email, moduleKey, action);
    },
    [user]
  );

  const canFeature = useCallback(
    (moduleKey, featureKey) => {
      if (!user?.email) return false;
      return canUserFeature(user.email, moduleKey, featureKey);
    },
    [user]
  );

  const canAction = useCallback(
    (moduleKey, actionKey) => {
      if (!user?.email) return false;
      return canUserAction(user.email, moduleKey, actionKey);
    },
    [user]
  );

  const getModuleScope = useCallback(
    (moduleKey) => {
      if (!user?.email) {
        return {
          type: "none",
          regions: [],
          warehouses: [],
          suppliers: [],
          costCenters: [],
        };
      }

      return getUserModuleScope(user.email, moduleKey);
    },
    [user]
  );

  const isSuperAdmin = useCallback(() => {
    if (!user?.email) return false;
    return isUserSuperAdmin(user.email);
  }, [user]);

  const refreshAccess = useCallback(() => {
    setAccessConfig(getAccessConfig());
  }, []);

  const updateAccessConfig = useCallback((nextConfig) => {
    saveAccessConfig(nextConfig);
    setAccessConfig(getAccessConfig());
  }, []);

  const value = useMemo(
    () => ({
      user,
      accessConfig,
      login,
      logout,
      can,
      canFeature,
      canAction,
      getModuleScope,
      isSuperAdmin,
      refreshAccess,
      updateAccessConfig,
    }),
    [
      user,
      accessConfig,
      login,
      logout,
      can,
      canFeature,
      canAction,
      getModuleScope,
      isSuperAdmin,
      refreshAccess,
      updateAccessConfig,
    ]
  );

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth() {
  const value = useContext(AuthContext);

  if (!value) {
    throw new Error("useAuth must be used inside AuthProvider");
  }

  return value;
}
