# =========================
# PLANAI PERMISSION SYSTEM
# =========================

ROLE_LEVELS = {
    "USER": 1,
    "MODERATOR": 2,
    "SUPER_USER": 3,
    "ADMIN": 4,
}


PERMISSIONS = {
    # Raf / depo fiziksel yapı
    "edit_shelf_size": ["USER", "MODERATOR", "SUPER_USER", "ADMIN"],
    "edit_shelf_count": ["USER", "MODERATOR", "SUPER_USER", "ADMIN"],
    "edit_fridge_count": ["USER", "MODERATOR", "SUPER_USER", "ADMIN"],
    "edit_module_position": ["USER", "MODERATOR", "SUPER_USER", "ADMIN"],

    # Picker / rota / optimizasyon
    "edit_picking_strategy": ["MODERATOR", "SUPER_USER", "ADMIN"],
    "edit_route_priority": ["MODERATOR", "SUPER_USER", "ADMIN"],

    # Ürün kritik master verileri
    "edit_product_dimension": ["SUPER_USER", "ADMIN"],
    "edit_product_storage_type": ["SUPER_USER", "ADMIN"],

    # Hibrit model ağırlıkları
    "edit_sales_weight": ["SUPER_USER", "ADMIN"],
    "edit_category_weight": ["SUPER_USER", "ADMIN"],
    "edit_picking_weight": ["SUPER_USER", "ADMIN"],
    "edit_brand_weight": ["SUPER_USER", "ADMIN"],

    # Onay
    "approve_layout_change": ["SUPER_USER", "ADMIN"],
    "approve_product_change": ["SUPER_USER", "ADMIN"],

    # Admin panel
    "manage_users": ["ADMIN"],
    "manage_roles": ["ADMIN"],
}


APPROVAL_REQUIRED = {
    "USER": [
        "edit_product_dimension",
        "edit_product_storage_type",
        "edit_sales_weight",
        "edit_category_weight",
        "edit_picking_weight",
        "edit_brand_weight",
    ],
    "MODERATOR": [
        "edit_product_dimension",
        "edit_product_storage_type",
        "edit_sales_weight",
        "edit_category_weight",
        "edit_picking_weight",
        "edit_brand_weight",
    ],
    "SUPER_USER": [],
    "ADMIN": [],
}


def normalize_role(role):
    return str(role or "USER").strip().upper()


def can(role, action):
    role = normalize_role(role)
    allowed_roles = PERMISSIONS.get(action, [])
    return role in allowed_roles


def requires_approval(role, action):
    role = normalize_role(role)

    if can(role, action):
        return False

    return action in APPROVAL_REQUIRED.get(role, [])


def evaluate_permission(role, action):
    role = normalize_role(role)

    if can(role, action):
        return {
            "allowed": True,
            "requires_approval": False,
            "role": role,
            "action": action,
            "message": "İşlem doğrudan yapılabilir."
        }

    if requires_approval(role, action):
        return {
            "allowed": False,
            "requires_approval": True,
            "role": role,
            "action": action,
            "message": "Bu işlem onaya gönderilmelidir."
        }

    return {
        "allowed": False,
        "requires_approval": False,
        "role": role,
        "action": action,
        "message": "Bu işlem için yetkiniz yok."
    }