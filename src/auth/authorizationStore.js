const EMPTY_SNAPSHOT = Object.freeze({
  user: null,
  tenantId: null,
  roles: Object.freeze([]),
  permissions: Object.freeze([]),
  permissionAssignments: Object.freeze([]),
});

let authorizationSnapshot = EMPTY_SNAPSHOT;


function freezeAssignments(values) {
  return Object.freeze(
    (Array.isArray(values) ? values : []).map(
      (item) =>
        Object.freeze({
          key: String(item?.key || ""),
          role_key: String(item?.role_key || ""),
          scope: Object.freeze({
            ...(item?.scope &&
            typeof item.scope === "object" &&
            !Array.isArray(item.scope)
              ? item.scope
              : {}),
          }),
        })
    )
  );
}


export function publishAuthorizationSnapshot(value) {
  if (!value || typeof value !== "object") {
    authorizationSnapshot = EMPTY_SNAPSHOT;
    return;
  }

  authorizationSnapshot = Object.freeze({
    user:
      value.user && typeof value.user === "object"
        ? Object.freeze({ ...value.user })
        : null,

    tenantId:
      typeof value.tenantId === "string"
        ? value.tenantId
        : null,

    roles: Object.freeze(
      Array.isArray(value.roles)
        ? [...value.roles]
        : []
    ),

    permissions: Object.freeze(
      Array.isArray(value.permissions)
        ? [...value.permissions]
        : []
    ),

    permissionAssignments:
      freezeAssignments(
        value.permissionAssignments
      ),
  });
}


export function clearAuthorizationSnapshot() {
  authorizationSnapshot = EMPTY_SNAPSHOT;
}


export function getAuthorizationSnapshot() {
  return authorizationSnapshot;
}
