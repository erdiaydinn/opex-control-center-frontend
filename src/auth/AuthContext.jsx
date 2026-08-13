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
const TOKEN_KEY = "opex_oidc_access_token";
const REFRESH_KEY = "opex_refresh_token";
const DEVICE_KEY = "opex_device_id";
const LOCAL_PILOT_MODE = String(import.meta.env.VITE_LOCAL_PILOT_MODE || "false").toLowerCase() === "true";
const OIDC = {
  clientId: import.meta.env.VITE_OIDC_CLIENT_ID || "",
  authorizeUrl: import.meta.env.VITE_OIDC_AUTHORIZE_URL || "",
  tokenUrl: import.meta.env.VITE_OIDC_TOKEN_URL || "",
  redirectUri: import.meta.env.VITE_OIDC_REDIRECT_URI || `${window.location.origin}/auth/callback`,
  scope: import.meta.env.VITE_OIDC_SCOPE || "openid profile email",
};

function base64Url(bytes) {
  return btoa(String.fromCharCode(...new Uint8Array(bytes))).replaceAll("+", "-").replaceAll("/", "_").replaceAll("=", "");
}

function claimsFromToken(token) {
  try {
    const payload = token.split(".")[1].replaceAll("-", "+").replaceAll("_", "/");
    return JSON.parse(decodeURIComponent(escape(atob(payload.padEnd(Math.ceil(payload.length / 4) * 4, "=")))));
  } catch {
    return null;
  }
}

function oidcUser(token) {
  const claims = claimsFromToken(token);
  if (!claims || (claims.exp && claims.exp * 1000 <= Date.now())) return null;
  const roles = Array.isArray(claims.roles) ? claims.roles : String(claims.roles || "").split(/[ ,]+/).filter(Boolean);
  const permissions = Array.isArray(claims.permissions) ? claims.permissions : String(claims.permissions || "").split(/[ ,]+/).filter(Boolean);
  return {
    email: claims.email || claims.preferred_username || claims.sub,
    name: claims.name || claims.preferred_username || claims.sub,
    subject: claims.sub,
    employeeId: claims.employee_id || null,
    roles,
    permissions,
    status: "active",
    authentication: "OIDC",
  };
}

async function beginOidc() {
  const verifier = base64Url(crypto.getRandomValues(new Uint8Array(48)));
  const challenge = base64Url(await crypto.subtle.digest("SHA-256", new TextEncoder().encode(verifier)));
  const state = base64Url(crypto.getRandomValues(new Uint8Array(24)));
  sessionStorage.setItem("opex_oidc_verifier", verifier);
  sessionStorage.setItem("opex_oidc_state", state);
  const params = new URLSearchParams({ response_type: "code", client_id: OIDC.clientId, redirect_uri: OIDC.redirectUri, scope: OIDC.scope, state, code_challenge: challenge, code_challenge_method: "S256" });
  window.location.assign(`${OIDC.authorizeUrl}?${params}`);
}

async function finishOidc() {
  const params = new URLSearchParams(window.location.search);
  if (!params.get("code")) return null;
  if (params.get("state") !== sessionStorage.getItem("opex_oidc_state")) throw new Error("SSO state doğrulaması başarısız.");
  const body = new URLSearchParams({ grant_type: "authorization_code", code: params.get("code"), client_id: OIDC.clientId, redirect_uri: OIDC.redirectUri, code_verifier: sessionStorage.getItem("opex_oidc_verifier") || "" });
  const response = await fetch(OIDC.tokenUrl, { method: "POST", headers: { "Content-Type": "application/x-www-form-urlencoded" }, body });
  if (!response.ok) throw new Error("Kurumsal SSO token değişimi başarısız.");
  const tokens = await response.json();
  sessionStorage.setItem(TOKEN_KEY, tokens.access_token);
  sessionStorage.removeItem("opex_oidc_verifier");
  sessionStorage.removeItem("opex_oidc_state");
  return oidcUser(tokens.access_token);
}

export function AuthProvider({ children }) {
  const oidcEnabled = Boolean(OIDC.clientId && OIDC.authorizeUrl && OIDC.tokenUrl);
  const [accessConfig, setAccessConfig] = useState(() => getAccessConfig());
  const [user, setUser] = useState(() => oidcUser(sessionStorage.getItem(TOKEN_KEY)) || getSessionUser());
  const [booting, setBooting] = useState(true);

  useEffect(() => {
    async function bootstrap() {
      try {
        if (oidcEnabled && window.location.pathname === "/auth/callback") {
          const next = await finishOidc();
          if (next) setUser(next);
          window.history.replaceState({}, "", "/");
        }
      } finally {
        setBooting(false);
      }
    }
    bootstrap();
  }, [oidcEnabled]);

  useEffect(() => {
    const handle = () => setAccessConfig(getAccessConfig());
    window.addEventListener("opex-access-config-updated", handle);
    window.addEventListener("storage", handle);
    return () => { window.removeEventListener("opex-access-config-updated", handle); window.removeEventListener("storage", handle); };
  }, []);

  const login = useCallback(async (email, password) => {
    if (oidcEnabled) return beginOidc();
    if (!LOCAL_PILOT_MODE || password !== "demo") {
      let deviceId = localStorage.getItem(DEVICE_KEY);
      if (!deviceId) {
        deviceId = crypto.randomUUID();
        localStorage.setItem(DEVICE_KEY, deviceId);
      }
      const response = await fetch("/api/identity/login", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ username: email, password, device_id: deviceId }),
      });
      const result = await response.json().catch(() => ({}));
      if (!response.ok) throw new Error(result.detail || "Giriş başarısız.");
      sessionStorage.setItem(TOKEN_KEY, result.access_token);
      sessionStorage.setItem(REFRESH_KEY, result.refresh_token);
      const serverUser = { ...result.user, email: result.user.username, authentication: "LOCAL_SERVER" };
      setUser(serverUser);
      return serverUser;
    }
    const sessionUser = buildUserFromEmail(email);
    if (!sessionUser || sessionUser.status !== "active") throw new Error("Geçerli ve aktif bir kullanıcı girin.");
    saveSessionUser(sessionUser); setUser(sessionUser); return sessionUser;
  }, [oidcEnabled]);

  const logout = useCallback(() => {
    sessionStorage.removeItem(TOKEN_KEY); sessionStorage.removeItem(REFRESH_KEY); clearSessionUser(); setUser(null);
  }, []);
  const changePassword = useCallback(async (currentPassword, newPassword) => {
    const token = sessionStorage.getItem(TOKEN_KEY);
    if (!token) throw new Error("Parola değişikliği için sunucu oturumu gerekli.");
    let deviceId = localStorage.getItem(DEVICE_KEY);
    if (!deviceId) {
      deviceId = crypto.randomUUID();
      localStorage.setItem(DEVICE_KEY, deviceId);
    }
    const response = await fetch("/api/identity/password/change", {
      method: "POST",
      headers: { "Content-Type": "application/json", Authorization: `Bearer ${token}` },
      body: JSON.stringify({
        current_password: currentPassword,
        new_password: newPassword,
        device_id: deviceId,
      }),
    });
    const result = await response.json().catch(() => ({}));
    if (!response.ok) throw new Error(result.detail || "Parola değiştirilemedi.");
    sessionStorage.setItem(TOKEN_KEY, result.access_token);
    sessionStorage.setItem(REFRESH_KEY, result.refresh_token);
    const serverUser = { ...result.user, email: result.user.username, authentication: "LOCAL_SERVER" };
    setUser(serverUser);
    return serverUser;
  }, []);
  const jwtAllows = useCallback((action) => user?.permissions?.includes(action) || user?.roles?.some((role) => ["admin", "super_admin"].includes(String(role).toLowerCase())), [user]);
  const can = useCallback((moduleKey, action = "view") => Boolean(user?.email && (jwtAllows(`${moduleKey}:${action}`) || canUser(user.email, moduleKey, action))), [user, jwtAllows]);
  const canFeature = useCallback((moduleKey, featureKey) => Boolean(user?.email && (jwtAllows(featureKey) || canUserFeature(user.email, moduleKey, featureKey))), [user, jwtAllows]);
  const canAction = useCallback((moduleKey, actionKey) => Boolean(user?.email && (jwtAllows(actionKey) || canUserAction(user.email, moduleKey, actionKey))), [user, jwtAllows]);
  const getModuleScope = useCallback((moduleKey) => user?.email ? getUserModuleScope(user.email, moduleKey) : { type: "none", regions: [], warehouses: [], suppliers: [], costCenters: [] }, [user]);
  const isSuperAdmin = useCallback(() => Boolean(user?.roles?.some((role) => ["admin", "super_admin"].includes(String(role).toLowerCase())) || (user?.email && isUserSuperAdmin(user.email))), [user]);
  const refreshAccess = useCallback(() => setAccessConfig(getAccessConfig()), []);
  const updateAccessConfig = useCallback((next) => { saveAccessConfig(next); setAccessConfig(getAccessConfig()); }, []);

  const value = useMemo(() => ({ user, booting, oidcEnabled, localPilotMode: LOCAL_PILOT_MODE, accessConfig, login, logout, changePassword, can, canFeature, canAction, getModuleScope, isSuperAdmin, refreshAccess, updateAccessConfig }), [user, booting, oidcEnabled, accessConfig, login, logout, changePassword, can, canFeature, canAction, getModuleScope, isSuperAdmin, refreshAccess, updateAccessConfig]);
  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth() {
  const value = useContext(AuthContext);
  if (!value) throw new Error("useAuth must be used inside AuthProvider");
  return value;
}

export function getAccessToken() {
  return sessionStorage.getItem(TOKEN_KEY) || "";
}
