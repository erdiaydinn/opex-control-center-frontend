import { translateField } from "../field-intelligence/fieldMessages.js";
import { localizeAuditModule } from "../audit/auditMessages.js";

export const commandModules = [
  {
    id: "planogram", moduleKey: "planogram", titleKey: "modulePlanogramTitle", descriptionKey: "modulePlanogramDescription", route: "/planogram", enabled: true, health: "healthy", healthLabelKey: "ready", groupKey: "groupStoreIntelligence", shortcut: "P", icon: "layout", tone: "primary", metaKey: "modulePlanogramMeta", lastUsedKey: "opex_last_planogram",
  },
  {
    id: "field-intelligence", moduleKey: "field_intelligence", titleKey: null, descriptionKey: null, route: "/field-intelligence", enabled: true, health: "governed", healthLabelKey: "governed", groupKey: "groupStoreIntelligence", shortcut: "F", icon: "cycle", tone: "emerald", metaKey: null, lastUsedKey: "eay_last_field_intelligence",
    localize: (locale) => ({
      title: translateField(locale, "moduleTitle"),
      description: translateField(locale, "moduleDescription"),
      meta: translateField(locale, "capture"),
    }),
  },
  {
    id: "audit", moduleKey: "audit", titleKey: null, descriptionKey: null, route: "/audit", enabled: true, health: "governed", healthLabelKey: "governed", groupKey: "groupStoreIntelligence", shortcut: "U", icon: "ai", tone: "cyan", metaKey: null, lastUsedKey: "eay_last_audit_intelligence",
    localize: localizeAuditModule,
  },
  {
    id: "dockos", moduleKey: "dockos", titleKey: "moduleDockosTitle", descriptionKey: "moduleDockosDescription", route: "/dockos", enabled: true, health: "healthy", healthLabelKey: "ready", groupKey: "groupInboundControl", shortcut: "D", icon: "dock", tone: "cyan", metaKey: "moduleDockosMeta", lastUsedKey: "opex_last_dockos",
  },
  {
    id: "budget", moduleKey: "budget", titleKey: "moduleBudgetTitle", descriptionKey: "moduleBudgetDescription", route: "/budget", enabled: true, health: "healthy", healthLabelKey: "ready", groupKey: "groupFinanceOperations", shortcut: "B", icon: "budget", tone: "violet", metaKey: "moduleBudgetMeta", lastUsedKey: "opex_last_budget",
  },
  {
    id: "workforce", moduleKey: "workforce", titleKey: "moduleWorkforceTitle", descriptionKey: "moduleWorkforceDescription", route: "/workforce", enabled: true, health: "healthy", healthLabelKey: "ready", groupKey: "groupPeopleOperations", shortcut: "W", icon: "access", tone: "emerald", metaKey: "moduleWorkforceMeta", lastUsedKey: "opex_last_workforce",
  },
  {
    id: "recruitment", moduleKey: "recruitment", titleKey: "moduleRecruitmentTitle", descriptionKey: "moduleRecruitmentDescription", route: "/recruitment", enabled: true, health: "healthy", healthLabelKey: "ready", groupKey: "groupTalentOperations", shortcut: "R", icon: "cycle", tone: "amber", metaKey: "moduleRecruitmentMeta", lastUsedKey: "opex_last_recruitment",
  },
  {
    id: "academy", moduleKey: "academy", titleKey: "moduleAcademyTitle", descriptionKey: "moduleAcademyDescription", route: "/academy", enabled: true, health: "healthy", healthLabelKey: "ready", groupKey: "groupKnowledge", shortcut: "A", icon: "academy", tone: "amber", metaKey: "moduleAcademyMeta", lastUsedKey: "opex_last_academy",
  },
  {
    id: "jarvis", moduleKey: "jarvis", titleKey: "moduleJarvisTitle", descriptionKey: "moduleJarvisDescription", route: "/jarvis", enabled: true, health: "governed", healthLabelKey: "governed", groupKey: "groupIntelligence", shortcut: "J", icon: "ai", tone: "cyan", metaKey: "moduleJarvisMeta", lastUsedKey: "opex_last_jarvis",
  },
  {
    id: "insight", moduleKey: "insight", titleKey: "moduleInsightTitle", descriptionKey: "moduleInsightDescription", route: "/insight", enabled: true, health: "governed", healthLabelKey: "governed", groupKey: "groupIntelligence", shortcut: "I", icon: "ai", tone: "emerald", metaKey: "moduleInsightMeta", lastUsedKey: "opex_last_insight",
  },
  {
    id: "inventory", moduleKey: "inventory", titleKey: "moduleInventoryTitle", descriptionKey: "moduleInventoryDescription", route: "/inventory", enabled: true, health: "healthy", healthLabelKey: "ready", groupKey: "groupInventoryControl", shortcut: "C", icon: "inventory", tone: "rose", metaKey: "moduleInventoryMeta", lastUsedKey: "opex_last_inventory",
  },
  {
    id: "audit-log", moduleKey: "admin_access", titleKey: "moduleAuditTitle", descriptionKey: "moduleAuditDescription", route: "/audit-log", enabled: true, health: "healthy", healthLabelKey: "admin", groupKey: "groupAdministration", shortcut: "L", icon: "access", tone: "slate", metaKey: "moduleAuditMeta", lastUsedKey: "opex_last_audit_log",
  },
  {
    id: "access", moduleKey: "admin_access", titleKey: "moduleAccessTitle", descriptionKey: "moduleAccessDescription", route: "/access-control", enabled: true, health: "healthy", healthLabelKey: "admin", groupKey: "groupAdministration", shortcut: "X", icon: "access", tone: "slate", metaKey: "moduleAccessMeta", lastUsedKey: "opex_last_access",
  },
];
