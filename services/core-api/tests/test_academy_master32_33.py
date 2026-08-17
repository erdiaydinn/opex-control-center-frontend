import asyncio
from types import SimpleNamespace
from uuid import UUID
from app.modules.academy.learning_os import SkillGap
from app.modules.academy.media_plane import MediaLoadEvidence,build_transcode_spec,production_media_capacity_accepted
from app.modules.academy.tutor import academy_tutor_answer

TENANT=UUID('11111111-1111-4111-8111-111111111111')

def principal(): return SimpleNamespace(tenant_id=TENANT,subject='learner')

async def supported(*args,**kwargs):
    return {'supported':True,'answer':'Approved SOP answer','sources':[{'source_sha256':'a'*64,'content_version_id':'v1'}]}
async def no_source(*args,**kwargs): return {'supported':False,'answer':None,'sources':[]}


def test_tutor_is_source_bound_and_can_enrich_with_skill_gap_without_requiring_workforce():
    result=asyncio.run(academy_tutor_answer(grounded_answer_fn=supported,session=object(),principal=principal(),question='How?',locale='en',skill_gaps=(SkillGap('safety',3,1,2),)))
    assert result['supported'] and result['skill_context'][0]['skill_key']=='safety'
    denied=asyncio.run(academy_tutor_answer(grounded_answer_fn=no_source,session=object(),principal=principal(),question='How?',locale='en'))
    assert not denied['supported'] and denied['answer'] is None


def test_media_plane_requires_private_source_and_real_1200_concurrency_evidence():
    spec=build_transcode_spec(private_source_key='academy/private/media/source-1.mp4',delivery_key='tenant/course/media',delivery_mode='hls')
    assert spec.renditions==(360,720,1080)
    assert not production_media_capacity_accepted(MediaLoadEvidence(1200,'ci','SYNTHETIC',True,'run:1'))
    assert production_media_capacity_accepted(MediaLoadEvidence(1200,'media-prod-shape','REAL_MEDIA_ENVIRONMENT',True,'load:approved'))
