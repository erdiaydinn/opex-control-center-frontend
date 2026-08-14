from types import MappingProxyType

ROUTE_MODULES = frozenset(
    {
        "admin_access",
        "budget",
        "dockos",
        "inventory",
        "planogram",
        "recruitment",
        "workforce",
    }
)


MODULE_ADMIN = frozenset(
    {
        "admin_access",
        "planogram",
    }
)


FEATURES = MappingProxyType(
    {
        "budget": frozenset(
            {
                "summary",
                "plans",
                "periods",
                "costCenters",
                "budgetLines",
                "purchaseRequests",
                "approvals",
                "purchaseOrders",
                "invoices",
                "commitments",
                "actuals",
                "forecasts",
                "variance",
                "reconciliation",
                "imports",
                "audit",
                "exports",
            }
        ),
        "dockos": frozenset(
            {
                "dashboard",
                "livePurchaseOrders",
                "supplierAppointments",
                "shipmentDetails",
                "vehicleTracking",
                "excelUpload",
                "duplicateResolution",
            }
        ),
        "planogram": frozenset(
            {
                "layoutView",
                "layoutEdit",
                "fixtureEdit",
                "ruleEdit",
                "productAssign",
                "aiRecommend",
            }
        ),
        "workforce": frozenset(
            {
                "dashboard",
                "attendance",
                "timesheet",
                "periodClose",
                "opexLab",
                "shifts",
                "approvals",
                "managerTasks",
                "communications",
                "systemConfig",
                "leaves",
                "warehouses",
                "rules",
                "devices",
                "audit",
                "pickerApp",
            }
        ),
    }
)


ACTIONS = MappingProxyType(
    {
        "ai_assistant": frozenset(
            {
                "executeOpsRead",
                "executeCatalogRead",
                "executeLegalRead",
            }
        ),
        "budget": frozenset(
            {
                "createPlan",
                "activatePlan",
                "managePeriods",
                "manageCostCenters",
                "manageBudgetLines",
                "createRequest",
                "approveRequest",
                "createPO",
                "postInvoice",
                "createForecast",
                "import",
                "resolveReconciliation",
                "closePeriod",
                "export",
                "viewAudit",
            }
        ),
        "dockos": frozenset(
            {
                "view",
                "create",
                "edit",
                "approve",
                "export",
                "delete",
            }
        ),
        "planogram": frozenset(
            {
                "view",
                "create",
                "edit",
                "approve",
                "export",
                "delete",
            }
        ),
        "recruitment": frozenset(
            {
                "approveRecruitmentRequest",
            }
        ),
        "workforce": frozenset(
            {
                "manualCorrection",
                "approveAttendance",
                "bulkApprove",
                "createShift",
                "bulkShiftUpload",
                "export",
                "printAttendance",
                "manageWarehouses",
                "manageRules",
                "manageHolidays",
                "manageLeaves",
                "manageDevices",
                "viewFullNationalId",
                "manageEmployees",
                "importTimeOff",
                "runPayrollClose",
                "importRoster",
                "overrideRoster",
                "assignRosterTask",
                "resolveManagerTasks",
                "manageAnnouncements",
                "manageNotifications",
                "manageSystemConfig",
                "manageStaffingNorms",
                "viewAuditLog",
            }
        ),
    }
)


def module_permission(module: str, action: str = "view") -> str:
    return f"module:{module}:{action}"


def feature_permission(module: str, feature: str) -> str:
    return f"feature:{module}:{feature}"


def action_permission(module: str, action: str) -> str:
    return f"action:{module}:{action}"


_permission_keys = {module_permission(module) for module in ROUTE_MODULES}
_permission_keys.update(module_permission(module, "admin") for module in MODULE_ADMIN)
for module, features in FEATURES.items():
    _permission_keys.update(feature_permission(module, feature) for feature in features)
for module, actions in ACTIONS.items():
    _permission_keys.update(action_permission(module, action) for action in actions)


ALL_PERMISSION_KEYS = frozenset(_permission_keys)


SYSTEM_ROLE_PERMISSIONS = MappingProxyType(
    {
        "super_admin": ALL_PERMISSION_KEYS,
        "platform_admin": frozenset({module_permission("admin_access", "view")}),
        "operator": frozenset(),
        "viewer": frozenset(),
    }
)


def is_known_permission(permission_key: str) -> bool:
    return permission_key in ALL_PERMISSION_KEYS
