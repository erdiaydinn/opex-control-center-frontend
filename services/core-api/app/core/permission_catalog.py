from types import MappingProxyType

ROUTE_MODULES = frozenset(
    {
        "admin_access",
        "academy",
        "audit",
        "budget",
        "dockos",
        "field_intelligence",
        "insight",
        "inventory",
        "jarvis",
        "planogram",
        "recruitment",
        "workforce",
    }
)

MODULE_ADMIN = frozenset(
    {
        "admin_access",
        "academy",
        "audit",
        "field_intelligence",
        "planogram",
    }
)

FEATURES = MappingProxyType(
    {
        "academy": frozenset(
            {
                "home",
                "catalog",
                "learningPaths",
                "player",
                "quizzes",
                "assignments",
                "certificates",
                "jarvisTutor",
                "contentStudio",
                "audiences",
                "analytics",
                "liveLearning",
                "operationalReadiness",
            }
        ),
        "audit": frozenset(
            {
                "commandCenter",
                "audits",
                "capture",
                "standards",
                "actions",
                "scheduling",
                "analytics",
                "assurance",
                "locations",
                "reports",
                "jarvis",
            }
        ),
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
        "field_intelligence": frozenset(
            {
                "commandCenter",
                "missionBuilder",
                "missions",
                "capture",
                "evidenceReview",
                "targeting",
                "templates",
                "analytics",
                "promotions",
                "governance",
            }
        ),
        "insight": frozenset(
            {"overview", "canonicalMetrics", "trends", "drilldown", "provenance", "exports"}
        ),
        "jarvis": frozenset(
            {
                "assistant",
                "operations",
                "academyTutor",
                "sources",
                "missions",
                "approvals",
                "history",
            }
        ),
        "planogram": frozenset(
            {"layoutView", "layoutEdit", "fixtureEdit", "ruleEdit", "productAssign", "aiRecommend"}
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
        "academy": frozenset(
            {
                "manageContent",
                "managePaths",
                "manageQuizzes",
                "manageEntitlements",
                "assignEnrollment",
                "ingestDocuments",
                "revokeCompletion",
                "manageLiveLearning",
                "viewAnalytics",
                "manageOperationalReadiness",
                "ingestOperationalSignals",
                "recordOperationalOutcomes",
            }
        ),
        "ai_assistant": frozenset({"executeOpsRead", "executeCatalogRead", "executeLegalRead"}),
        "audit": frozenset(
            {
                "startAudit",
                "submitEvidence",
                "decideItem",
                "createAction",
                "updateAction",
                "submitVerification",
                "verifyAction",
                "reviewDisagreement",
                "manageStandards",
                "manageScheduling",
                "manageLocations",
                "exportResults",
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
                "acceptFieldEvidence",
            }
        ),
        "dockos": frozenset({"view", "create", "edit", "approve", "export", "delete"}),
        "field_intelligence": frozenset(
            {
                "createMission",
                "activateMission",
                "cancelMission",
                "submitEvidence",
                "sendReminder",
                "reviewEvidence",
                "manageTemplates",
                "manageLocations",
                "exportResults",
                "viewEvidence",
                "proposePromotion",
                "approvePromotion",
                "viewPromotions",
                "manageRecurrence",
                "exemptTarget",
                "approveExport",
            }
        ),
        "insight": frozenset({"view", "drilldown", "export"}),
        "inventory": frozenset({"acceptFieldEvidence"}),
        "jarvis": frozenset(
            {"ask", "proposeAction", "approveAction", "viewSources", "viewHistory"}
        ),
        "planogram": frozenset(
            {"view", "create", "edit", "approve", "export", "delete", "acceptFieldEvidence"}
        ),
        "recruitment": frozenset(
            {
                "viewRecruitment",
                "createRecruitmentRequest",
                "approveRecruitmentRequest",
                "viewRecruitmentEvidence",
                "manageRecruitmentNorms",
                "manageRecruitmentActuals",
                "manageRecruitmentSettings",
                "manageRecruitmentNotifications",
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


def is_known_permission(permission_key: str) -> bool:
    """Fail closed unless a permission is present in the canonical catalog."""
    return str(permission_key or "").strip() in ALL_PERMISSION_KEYS


ACADEMY_LEARNER_PERMISSIONS = frozenset(
    {
        module_permission("academy"),
        feature_permission("academy", "home"),
        feature_permission("academy", "catalog"),
        feature_permission("academy", "learningPaths"),
        feature_permission("academy", "player"),
        feature_permission("academy", "quizzes"),
        feature_permission("academy", "assignments"),
        feature_permission("academy", "certificates"),
        feature_permission("academy", "jarvisTutor"),
        feature_permission("academy", "operationalReadiness"),
    }
)
ACADEMY_INSTRUCTOR_PERMISSIONS = frozenset(
    set(ACADEMY_LEARNER_PERMISSIONS)
    | {
        feature_permission("academy", "contentStudio"),
        feature_permission("academy", "liveLearning"),
        action_permission("academy", "manageContent"),
        action_permission("academy", "managePaths"),
        action_permission("academy", "manageQuizzes"),
        action_permission("academy", "ingestDocuments"),
        action_permission("academy", "manageLiveLearning"),
    }
)
ACADEMY_ADMIN_PERMISSIONS = frozenset(
    set(ACADEMY_INSTRUCTOR_PERMISSIONS)
    | {
        module_permission("academy", "admin"),
        feature_permission("academy", "audiences"),
        feature_permission("academy", "analytics"),
        action_permission("academy", "manageEntitlements"),
        action_permission("academy", "assignEnrollment"),
        action_permission("academy", "revokeCompletion"),
        action_permission("academy", "viewAnalytics"),
        action_permission("academy", "manageOperationalReadiness"),
    }
)

AUDIT_AUDITOR_PERMISSIONS = frozenset(
    {
        module_permission("audit"),
        feature_permission("audit", "audits"),
        feature_permission("audit", "capture"),
        feature_permission("audit", "actions"),
        action_permission("audit", "startAudit"),
        action_permission("audit", "submitEvidence"),
        action_permission("audit", "decideItem"),
        action_permission("audit", "createAction"),
        action_permission("audit", "updateAction"),
        action_permission("audit", "submitVerification"),
    }
)
AUDIT_MANAGER_PERMISSIONS = frozenset(
    set(AUDIT_AUDITOR_PERMISSIONS)
    | {
        feature_permission("audit", "commandCenter"),
        feature_permission("audit", "scheduling"),
        feature_permission("audit", "analytics"),
        feature_permission("audit", "assurance"),
        feature_permission("audit", "locations"),
        feature_permission("audit", "reports"),
        feature_permission("audit", "jarvis"),
        action_permission("audit", "verifyAction"),
        action_permission("audit", "reviewDisagreement"),
        action_permission("audit", "manageScheduling"),
        action_permission("audit", "exportResults"),
    }
)
AUDIT_STANDARDS_PERMISSIONS = frozenset(
    set(AUDIT_MANAGER_PERMISSIONS)
    | {
        module_permission("audit", "admin"),
        feature_permission("audit", "standards"),
        action_permission("audit", "manageStandards"),
        action_permission("audit", "manageLocations"),
    }
)
AUDIT_EXECUTIVE_PERMISSIONS = frozenset(
    {
        module_permission("audit"),
        feature_permission("audit", "commandCenter"),
        feature_permission("audit", "audits"),
        feature_permission("audit", "actions"),
        feature_permission("audit", "analytics"),
        feature_permission("audit", "reports"),
        feature_permission("audit", "jarvis"),
        action_permission("audit", "exportResults"),
    }
)

FIELD_WORKER_PERMISSIONS = frozenset(
    {
        module_permission("field_intelligence"),
        feature_permission("field_intelligence", "missions"),
        feature_permission("field_intelligence", "capture"),
        action_permission("field_intelligence", "submitEvidence"),
    }
)
FIELD_MANAGER_PERMISSIONS = frozenset(
    set(FIELD_WORKER_PERMISSIONS)
    | {
        module_permission("field_intelligence", "admin"),
        feature_permission("field_intelligence", "commandCenter"),
        feature_permission("field_intelligence", "missionBuilder"),
        feature_permission("field_intelligence", "evidenceReview"),
        feature_permission("field_intelligence", "targeting"),
        feature_permission("field_intelligence", "templates"),
        feature_permission("field_intelligence", "analytics"),
        feature_permission("field_intelligence", "promotions"),
        feature_permission("field_intelligence", "governance"),
        action_permission("field_intelligence", "createMission"),
        action_permission("field_intelligence", "activateMission"),
        action_permission("field_intelligence", "cancelMission"),
        action_permission("field_intelligence", "sendReminder"),
        action_permission("field_intelligence", "reviewEvidence"),
        action_permission("field_intelligence", "manageTemplates"),
        action_permission("field_intelligence", "manageLocations"),
        action_permission("field_intelligence", "exportResults"),
        action_permission("field_intelligence", "viewEvidence"),
        action_permission("field_intelligence", "proposePromotion"),
        action_permission("field_intelligence", "approvePromotion"),
        action_permission("field_intelligence", "viewPromotions"),
        action_permission("field_intelligence", "manageRecurrence"),
        action_permission("field_intelligence", "exemptTarget"),
        action_permission("field_intelligence", "approveExport"),
    }
)

PLANOGRAM_EDITOR_PERMISSIONS = frozenset(
    {
        module_permission("planogram"),
        feature_permission("planogram", "layoutView"),
        feature_permission("planogram", "layoutEdit"),
        feature_permission("planogram", "fixtureEdit"),
        action_permission("planogram", "view"),
        action_permission("planogram", "create"),
        action_permission("planogram", "edit"),
        action_permission("planogram", "export"),
    }
)
PLANOGRAM_ADMIN_PERMISSIONS = frozenset(
    set(PLANOGRAM_EDITOR_PERMISSIONS)
    | {
        module_permission("planogram", "admin"),
        feature_permission("planogram", "ruleEdit"),
        feature_permission("planogram", "productAssign"),
        feature_permission("planogram", "aiRecommend"),
        action_permission("planogram", "approve"),
        action_permission("planogram", "delete"),
        action_permission("planogram", "acceptFieldEvidence"),
    }
)

SYSTEM_ROLE_PERMISSIONS = MappingProxyType(
    {
        "super_admin": ALL_PERMISSION_KEYS,
        "platform_admin": frozenset({module_permission("admin_access", "view")}),
        "operator": frozenset(),
        "viewer": frozenset(),
        "academy_learner": ACADEMY_LEARNER_PERMISSIONS,
        "academy_instructor": ACADEMY_INSTRUCTOR_PERMISSIONS,
        "academy_admin": ACADEMY_ADMIN_PERMISSIONS,
        "field_worker": FIELD_WORKER_PERMISSIONS,
        "field_manager": FIELD_MANAGER_PERMISSIONS,
        "planogram_editor": PLANOGRAM_EDITOR_PERMISSIONS,
        "planogram_admin": PLANOGRAM_ADMIN_PERMISSIONS,
        "audit_auditor": AUDIT_AUDITOR_PERMISSIONS,
        "audit_manager": AUDIT_MANAGER_PERMISSIONS,
        "audit_standards": AUDIT_STANDARDS_PERMISSIONS,
        "audit_executive": AUDIT_EXECUTIVE_PERMISSIONS,
    }
)
