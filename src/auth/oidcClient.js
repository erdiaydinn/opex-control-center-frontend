import {
  InMemoryWebStorage,
  UserManager,
  WebStorageStateStore,
} from "oidc-client-ts";

let manager = null;

function requireEnv(name) {
  const value = String(import.meta.env[name] || "").trim();

  if (!value) {
    throw new Error(`Missing required OIDC setting: ${name}`);
  }

  return value;
}

function buildSettings() {
  const authority = requireEnv("VITE_OIDC_AUTHORITY");
  const clientId = requireEnv("VITE_OIDC_CLIENT_ID");

  if (
    import.meta.env.PROD &&
    !authority.toLowerCase().startsWith("https://")
  ) {
    throw new Error(
      "Production OIDC authority must use HTTPS."
    );
  }

  const origin = window.location.origin;

  return {
    authority,
    client_id: clientId,

    // Authorization Code + PKCE.
    response_type: "code",

    scope:
      String(
        import.meta.env.VITE_OIDC_SCOPE ||
          "openid profile email offline_access"
      ).trim(),

    redirect_uri:
      `${origin}/auth/callback`,

    post_logout_redirect_uri:
      `${origin}/login`,

    // Tokens must not persist in localStorage/sessionStorage.
    userStore: new WebStorageStateStore({
      store: new InMemoryWebStorage(),
    }),

    // Redirect/PKCE transaction state must survive the
    // navigation to and from the identity provider.
    stateStore: new WebStorageStateStore({
      store: window.sessionStorage,
    }),

    automaticSilentRenew: true,
    revokeTokensOnSignout: true,
    loadUserInfo: false,
    monitorSession: false,
  };
}

export function getOidcManager() {
  if (!manager) {
    manager = new UserManager(buildSettings());
  }

  return manager;
}
