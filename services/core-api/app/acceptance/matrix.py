from __future__ import annotations
import json
from pathlib import Path

REQUIRED_MODULES={'workforce_standalone','inventory_standalone','dockos_standalone','academy_standalone'}
REQUIRED_CROSS={'workforce_kpi','field_planogram','dock_inventory','hiring_workforce_academy','budget_operations','jarvis_all_entitled_modules'}
REQUIRED_PEN={'cross_tenant_api_rls_cache_object','ai_prompt_tool_authorization','admin_control_plane'}

def load_acceptance_matrix(path:Path)->dict[str,object]:
    d=json.loads(path.read_text(encoding='utf-8'))
    if d.get('schema_version')!=1: raise ValueError('unsupported acceptance matrix')
    if not REQUIRED_MODULES<=set(d['module_uat']): raise ValueError('standalone module UAT matrix incomplete')
    if not REQUIRED_CROSS<=set(d['cross_module_uat']): raise ValueError('cross-module UAT matrix incomplete')
    if not REQUIRED_PEN<=set(d['security_penetration']): raise ValueError('security penetration matrix incomplete')
    langs=set(d['accessibility_language'])
    if not {'tr','en','de','ar_rtl','fr','es','it','nl','pl','pt_br'}<=langs: raise ValueError('ten-language field acceptance incomplete')
    return d
