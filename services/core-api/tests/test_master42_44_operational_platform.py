from app.shared_platform.contracts import IntegrationContract,SearchDocument
from app.shared_platform.search_integration import SearchPrincipal,validate_inbound_payload,visible_search_documents

def test_operational_search_never_leaks_document_without_permission_and_provenance():
    docs=(SearchDocument('inventory','sku','1','Milk','milk','module:inventory:view',{'source':'inventory'}),SearchDocument('budget','line','2','Budget','budget','module:budget:view',{'source':'budget'}))
    visible=visible_search_documents(SearchPrincipal(frozenset({'module:inventory:view'})),docs)
    assert [d.source_module for d in visible]==['inventory']

def test_integration_import_cannot_author_tenant_and_is_schema_validated():
    c=IntegrationContract('hr-roster','INBOUND',1,{}, {'required_fields':['employee_id'],'allowed_fields':['employee_id','name']})
    assert validate_inbound_payload(c,{'employee_id':'E1','name':'Ada'})==(True,())
    ok,errors=validate_inbound_payload(c,{'employee_id':'E1','tenant_id':'evil'})
    assert not ok and 'tenant_id:payload_authority_forbidden' in errors
