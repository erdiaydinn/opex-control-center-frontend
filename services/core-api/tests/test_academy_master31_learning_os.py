from pathlib import Path
from app.modules.academy.learning_os import LearningPathOutcome, SkillProficiency, SkillRequirement, compute_skill_gaps, recommend_learning_paths


def test_role_skill_gap_is_evidence_bound_and_deterministic():
    req=[SkillRequirement('inventory.count',4),SkillRequirement('safety.haccp',3)]
    prof=[SkillProficiency('inventory.count',2,'assessment:7')]
    gaps=compute_skill_gaps(req,prof)
    assert [(g.skill_key,g.current_level,g.required_level) for g in gaps] == [('inventory.count',2,4),('safety.haccp',0,3)]


def test_path_recommendation_covers_gap_without_role_database_dependency():
    gaps=compute_skill_gaps([SkillRequirement('a',3),SkillRequirement('b',2)],[])
    outcomes=[LearningPathOutcome('path-b','b',2),LearningPathOutcome('path-both','a',3),LearningPathOutcome('path-both','b',2)]
    assert recommend_learning_paths(gaps,outcomes) == ('path-both',)


def test_learning_os_migration_is_tenant_isolated_append_only_and_view_keeps_rls():
    text=(Path(__file__).resolve().parents[1]/'alembic/versions/0040_academy_learning_os.py').read_text()
    for token in ('academy_skills','academy_role_skill_requirement','academy_path_skill_outcome','academy_skill_evidence','FORCE ROW LEVEL SECURITY','REVOKE UPDATE,DELETE ON academy_skill_evidence','security_invoker = true'):
        assert token in text
