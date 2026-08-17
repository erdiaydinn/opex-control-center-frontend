from pathlib import Path
from app.acceptance.external_evidence import EvidenceRecord,evaluate_requirement,load_requirements
ROOT=Path(__file__).resolve().parents[3]

def test_repo_or_synthetic_evidence_cannot_satisfy_external_gates():
    req=load_requirements(ROOT/'docs/governance/eay_external_acceptance_requirements.json')['requirements'][0]
    records=tuple(EvidenceRecord(req['key'],key,'SYNTHETIC','PASS','ci','run:1','ci-bot') for key in req['evidence'])
    ok,blockers=evaluate_requirement(req,records)
    assert not ok and blockers and all('wrong_evidence_class' in b for b in blockers)


def test_real_identity_evidence_must_cover_every_required_proof_with_provenance():
    req=load_requirements(ROOT/'docs/governance/eay_external_acceptance_requirements.json')['requirements'][0]
    records=tuple(EvidenceRecord(req['key'],key,'REAL_ENVIRONMENT','PASS','corp-prod-readonly',f'evidence:{key}','security-owner') for key in req['evidence'])
    assert evaluate_requirement(req,records)==(True,())
