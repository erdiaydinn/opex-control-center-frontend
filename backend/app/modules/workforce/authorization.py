def is_action_allowed(role: str, permissions: str, action: str) -> bool:
    """Return whether the trusted identity context grants a Workforce action."""
    normalized_role = role.strip().lower().replace("-", "_").replace(" ", "_")
    granted = {item.strip() for item in permissions.split(",") if item.strip()}
    return normalized_role in {"super_admin", "superadmin", "admin", "administrator"} or action in granted
