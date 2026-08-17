from app.insight.governed_metrics import GovernedMetric,can_activate_family
from app.insight.product_experience import MetricProvenance,build_insight_card
from app.insight.proactive import action_requires_approval,auto_action_permitted,create_signal
from app.jarvis.orders_v2_production_truth import ProductionEvidence,orders_v2_production_ready

def test_synthetic_orders_v2_proof_never_activates_production():
    keys=('authorized_readonly_identity','information_schema_observation','entity_id_discriminator','cross_tenant_zero_leak','schema_attestation','human_release_deploy_promotion')
    records=tuple(ProductionEvidence(k,'SYNTHETIC',True,'ci:proof','reviewer') for k in keys)
    assert not orders_v2_production_ready(records)[0]

def test_kpi_family_expansion_requires_orders_and_metric_governance():
    m=(GovernedMetric('ops.kpi.nsfr.v1','nsfr_pfr_refund','v1','NSFR','bq:orders-v2',True),)
    assert not can_activate_family(family='nsfr_pfr_refund',orders_v2_ready=False,metrics=m)
    assert can_activate_family(family='nsfr_pfr_refund',orders_v2_ready=True,metrics=m)

def test_insight_card_and_proactive_high_risk_are_provenance_bound():
    p=MetricProvenance('otp','v3','bq:otp','OTP','2026-08-18T00:00:00Z')
    card=build_insight_card(metric_key='otp',value=94.0,trend=(95,94),explanation='Late prep increased',provenance=p,root_causes=('prep',),anomaly=True)
    assert card.anomaly
    s=create_signal(key='warehouse_pressure',module='workforce',reason='effective capacity below governed demand',evidence_refs=('demand:1','capacity:1'),risk='HIGH',proposed_action='open_shift')
    assert action_requires_approval(s) and not auto_action_permitted(s)
