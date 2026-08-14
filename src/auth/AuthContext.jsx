import React, {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useRef,
  useState,
} from "react";

import { apiGet } from "../api/client.js";
import { getOidcManager } from "./oidcClient.js";
import {
  clearAccessToken,
  getAccessToken as readAccessToken,
  setAccessToken,
} from "./tokenStore.js";

import {
  clearAuthorizationSnapshot,
  publishAuthorizationSnapshot,
} from "./authorizationStore.js";


const AuthContext = createContext(null);

const ROLE_PRIORITY = [
  "super_admin",
  "platform_admin",
  "operator",
  "viewer",
];

const EMPTY_LEGACY_ACCESS_CONFIG = Object.freeze({
  users: {},
  groups: {},
  modules: {},
});


function emptyScope() {
  return {
    type: "none",
    regions: [],
    warehouses: [],
    suppliers: [],
    costCenters: [],
  };
}


function safeReturnTo(value) {
  const candidate = String(value || "").trim();

  if (
    !candidate.startsWith("/") ||
    candidate.startsWith("//") ||
    candidate.startsWith("/auth/callback")
  ) {
    return "/";
  }

  return candidate;
}


function normalizeContext(payload) {
  if (!payload || typeof payload !== "object") {
    throw new Error("Invalid authorization context.");
  }

  const roles = Array.isArray(payload.roles)
    ? payload.roles
        .map((value) => String(value || "").trim())
        .filter(Boolean)
    : [];

  const permissions = Array.isArray(payload.permissions)
    ? payload.permissions
        .map((value) => String(value || "").trim())
        .filter(Boolean)
    : [];

  const permissionAssignments =
    Array.isArray(payload.permission_assignments)
      ? payload.permission_assignments
          .filter(
            (item) =>
              item &&
              typeof item === "object" &&
              typeof item.key === "string" &&
              typeof item.role_key === "string" &&
              item.scope &&
              typeof item.scope === "object" &&
              !Array.isArray(item.scope)
          )
          .map((item) => ({
            key: item.key,
            role_key: item.role_key,
            scope: item.scope,
          }))
      : [];

  return {
    requestId: payload.request_id || null,
    actor: String(payload.actor || ""),
    tenantId: String(payload.tenant_id || ""),
    authMode: String(payload.auth_mode || ""),
    roles: [...new Set(roles)].sort(),
    permissions: [...new Set(permissions)].sort(),
    permissionAssignments,
  };
}


function buildDisplayUser(context, oidcUser) {
  const profile = oidcUser?.profile || {};

  const primaryRole =
    ROLE_PRIORITY.find((role) =>
      context.roles.includes(role)
    ) ||
    context.roles[0] ||
    "";

  const email =
    String(profile.email || "").trim() ||
    String(profile.preferred_username || "").trim() ||
    context.actor;

  const name =
    String(profile.name || "").trim() ||
    String(profile.given_name || "").trim() ||
    email;

  return {
    subject: context.actor,
    email,
    name,
    role: primaryRole,
    roles: context.roles,
    tenantId: context.tenantId,
    permissions: context.permissions,

    // Display/profile information only. Never authorization authority.
    employeeId:
      profile.employee_id ||
      profile.employeeId ||
      profile.employee_number ||
      null,
  };
}


function permissionBelongsToModule(permissionKey, moduleKey) {
  return (
    permissionKey.startsWith(`module:${moduleKey}:`) ||
    permissionKey.startsWith(`feature:${moduleKey}:`) ||
    permissionKey.startsWith(`action:${moduleKey}:`)
  );
}


export function AuthProvider({ children }) {
  const [user, setUser] = useState(null);
  const [authorization, setAuthorization] = useState(null);
  const [booting, setBooting] = useState(true);
  const [authError, setAuthError] = useState("");

  const callbackPromiseRef = useRef(null);

  const clearLocalSession = useCallback(() => {
    clearAccessToken();
    clearAuthorizationSnapshot();
    setUser(null);
    setAuthorization(null);
  }, []);

  const establishSession = useCallback(
    async (oidcUser) => {
      if (
        !oidcUser ||
        oidcUser.expired ||
        typeof oidcUser.access_token !== "string" ||
        !oidcUser.access_token.trim()
      ) {
        clearLocalSession();
        throw new Error("OIDC access token is missing or expired.");
      }

      setAccessToken(oidcUser.access_token);

      try {
        const payload = await apiGet("/v1/context");
        const context = normalizeContext(payload);

        if (!context.actor || !context.tenantId) {
          throw new Error("Authorization context is incomplete.");
        }

        setAuthorization(context);
        setUser(buildDisplayUser(context, oidcUser));
        setAuthError("");

        return context;
      } catch (error) {
        clearLocalSession();
        throw error;
      }
    },
    [clearLocalSession]
  );

  useEffect(() => {
    let active = true;
    let manager;

    function expireSession() {
      if (!active) return;

      clearLocalSession();
      setAuthError("Oturum s?resi doldu. Yeniden giri? yap?n.");
      setBooting(false);
    }

    function unloadSession() {
      if (!active) return;

      clearLocalSession();
      setBooting(false);
    }

    function handleUserLoaded(oidcUser) {
      establishSession(oidcUser)
        .catch(() => {
          if (!active) return;

          clearLocalSession();
          setAuthError(
            "Kimlik do?ruland? ancak uygulama yetkisi do?rulanamad?."
          );
        })
        .finally(() => {
          if (active) setBooting(false);
        });
    }

    async function initialize() {
      try {
        manager = getOidcManager();

        manager.events.addUserLoaded(handleUserLoaded);
        manager.events.addUserUnloaded(unloadSession);
        manager.events.addAccessTokenExpired(expireSession);

        // Callback route owns signinRedirectCallback().
        if (window.location.pathname === "/auth/callback") {
          return;
        }

        const existingUser = await manager.getUser();

        if (!active) return;

        if (
          existingUser &&
          !existingUser.expired &&
          existingUser.access_token
        ) {
          await establishSession(existingUser);
        } else {
          clearLocalSession();
        }
      } catch (error) {
        if (!active) return;

        clearLocalSession();
        setAuthError(
          error?.message ||
            "Kimlik do?rulama yap?land?rmas? kullan?lam?yor."
        );
      } finally {
        if (active) {
          setBooting(false);
        }
      }
    }

    initialize();

    return () => {
      active = false;

      if (manager) {
        manager.events.removeUserLoaded(handleUserLoaded);
        manager.events.removeUserUnloaded(unloadSession);
        manager.events.removeAccessTokenExpired(expireSession);
      }
    };
  }, [clearLocalSession, establishSession]);

  const login = useCallback(async ({ returnTo = "/" } = {}) => {
    const manager = getOidcManager();

    clearAccessToken();

    await manager.signinRedirect({
      state: {
        returnTo: safeReturnTo(returnTo),
      },
    });
  }, []);

  const completeLogin = useCallback(() => {
    if (callbackPromiseRef.current) {
      return callbackPromiseRef.current;
    }

    callbackPromiseRef.current = (async () => {
      setBooting(true);
      setAuthError("");

      const manager = getOidcManager();

      try {
        let oidcUser;

        try {
          oidcUser = await manager.signinRedirectCallback();
        } catch (callbackError) {
          // React StrictMode may cause a callback effect to be observed
          // more than once during development. A successfully stored
          // in-memory user is acceptable; otherwise fail closed.
          const existingUser = await manager.getUser();

          if (
            !existingUser ||
            existingUser.expired ||
            !existingUser.access_token
          ) {
            throw callbackError;
          }

          oidcUser = existingUser;
        }

        await establishSession(oidcUser);

        return safeReturnTo(
          oidcUser?.state?.returnTo
        );
      } catch (error) {
        clearLocalSession();

        try {
          await manager.removeUser();
        } catch {
          // Local state is already cleared. Do not restore it.
        }

        setAuthError(
          "Giri? do?ruland? ancak uygulama eri?imi kurulamad?."
        );

        throw error;
      } finally {
        setBooting(false);
      }
    })();

    return callbackPromiseRef.current;
  }, [clearLocalSession, establishSession]);

  const logout = useCallback(async () => {
    const manager = getOidcManager();

    // Local authorization disappears before any network redirect.
    clearLocalSession();
    setAuthError("");

    try {
      await manager.signoutRedirect();
    } catch {
      try {
        await manager.removeUser();
      } catch {
        // Already fail-closed locally.
      }

      window.location.assign("/login");
    }
  }, [clearLocalSession]);

  const refreshAccess = useCallback(async () => {
    const manager = getOidcManager();

    const renewedUser = await manager.signinSilent();

    await establishSession(renewedUser);

    return renewedUser;
  }, [establishSession]);

  const hasPermission = useCallback(
    (permissionKey) => {
      if (!authorization) return false;

      return authorization.permissions.includes(
        String(permissionKey || "")
      );
    },
    [authorization]
  );

  const can = useCallback(
    (moduleKey, action = "view") => {
      if (!moduleKey) return false;

      return hasPermission(
        `module:${moduleKey}:${action}`
      );
    },
    [hasPermission]
  );

  const canFeature = useCallback(
    (moduleKey, featureKey) => {
      if (!moduleKey || !featureKey) return false;

      return hasPermission(
        `feature:${moduleKey}:${featureKey}`
      );
    },
    [hasPermission]
  );

  const canAction = useCallback(
    (moduleKey, actionKey) => {
      if (!moduleKey || !actionKey) return false;

      return hasPermission(
        `action:${moduleKey}:${actionKey}`
      );
    },
    [hasPermission]
  );

  const isSuperAdmin = useCallback(() => {
    return Boolean(
      authorization?.roles?.includes("super_admin")
    );
  }, [authorization]);

  const getModuleScope = useCallback(
    (moduleKey) => {
      if (!authorization || !moduleKey) {
        return emptyScope();
      }

      const assignments =
        authorization.permissionAssignments.filter(
          (item) =>
            permissionBelongsToModule(
              item.key,
              moduleKey
            )
        );

      if (!assignments.length) {
        return emptyScope();
      }

      const result = emptyScope();

      for (const assignment of assignments) {
        const scope = assignment.scope;

        if (
          scope.type === "all" &&
          Object.keys(scope).every(
            (key) => key === "type"
          )
        ) {
          return {
            ...emptyScope(),
            type: "all",
          };
        }

        for (const field of [
          "regions",
          "warehouses",
          "suppliers",
          "costCenters",
        ]) {
          if (!Array.isArray(scope[field])) {
            continue;
          }

          for (const rawValue of scope[field]) {
            const value = String(rawValue || "").trim();

            if (
              value &&
              !result[field].includes(value)
            ) {
              result[field].push(value);
            }
          }
        }
      }

      const populated = [
        ["region", result.regions],
        ["warehouse", result.warehouses],
        ["supplier", result.suppliers],
        ["costCenter", result.costCenters],
      ].filter(([, values]) => values.length);

      if (populated.length === 1) {
        result.type = populated[0][0];
      } else if (populated.length > 1) {
        // Never interpret an ambiguous compound scope as unrestricted.
        result.type = "compound";
      }

      return result;
    },
    [authorization]
  );

  const getAccessToken = useCallback(() => {
    return readAccessToken();
  }, []);

  const updateAccessConfig = useCallback(() => {
    throw new Error(
      "Local Access Control authority is disabled. Permissions are database-authoritative."
    );
  }, []);

  const value = useMemo(
    () => ({
      user,
      booting,
      authError,

      roles: authorization?.roles || [],
      permissions: authorization?.permissions || [],
      permissionAssignments:
        authorization?.permissionAssignments || [],
      tenantId: authorization?.tenantId || null,

      login,
      completeLogin,
      logout,
      refreshAccess,

      can,
      canFeature,
      canAction,
      hasPermission,
      getModuleScope,
      isSuperAdmin,
      getAccessToken,

      // Temporary compatibility only. This object is never used
      // for authorization and mutations are explicitly disabled.
      accessConfig: EMPTY_LEGACY_ACCESS_CONFIG,
      updateAccessConfig,
    }),
    [
      user,
      booting,
      authError,
      authorization,
      login,
      completeLogin,
      logout,
      refreshAccess,
      can,
      canFeature,
      canAction,
      hasPermission,
      getModuleScope,
      isSuperAdmin,
      getAccessToken,
      updateAccessConfig,
    ]
  );

  return (
    <AuthContext.Provider value={value}>
      {children}
    </AuthContext.Provider>
  );
}


export function useAuth() {
  const value = useContext(AuthContext);

  if (!value) {
    throw new Error(
      "useAuth must be used inside AuthProvider"
    );
  }

  return value;
}
