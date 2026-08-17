from pathlib import Path
from app.ai_core.substrate_contract import authorize_consumer,load_substrate_contract
ROOT=Path(__file__).resolve().parents[3]

def test_frozen_ai_core_is_shared_without_mutating_pr15():
    c=load_substrate_contract(ROOT/'docs/governance/eay_ai_core_shared_substrate.json')
    assert c.frozen_pr==15
    assert {'grounded_rag','model_registry','canary','vision_provenance','promotion_gate'} <= c.capabilities
    assert {'jarvis','budget','academy','planogram'} <= c.consumers

def test_consumer_requires_tenant_and_provenance():
    c=load_substrate_contract(ROOT/'docs/governance/eay_ai_core_shared_substrate.json')
    assert authorize_consumer(c,module='jarvis',tenant_authorized=True,provenance_bound=True)
    assert not authorize_consumer(c,module='jarvis',tenant_authorized=False,provenance_bound=True)
    assert not authorize_consumer(c,module='unknown',tenant_authorized=True,provenance_bound=True)
