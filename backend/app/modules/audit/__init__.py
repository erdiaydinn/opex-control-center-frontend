"""Business Audit domain authority.

Roadmap items 23+ live in explicit submodules. Import the required submodule
directly so historical acceptance gates do not inherit dependencies introduced
by newer roadmap items (for example offline AES-GCM support).

Examples:
- app.modules.audit.template_authority
- app.modules.audit.finding_lifecycle
- app.modules.audit.offline_schedule
"""
