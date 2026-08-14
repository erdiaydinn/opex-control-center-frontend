from app.regulatory_authority import assess_regulatory_authority


def assess(role, *, url, text):
    return assess_regulatory_authority(
        source_id="src-1",
        source_role=role,
        document_url=url,
        text=text,
    )


def test_gkgm_draft_never_becomes_binding():
    assessment = assess(
        "discovery",
        url="https://www.tarimorman.gov.tr/GKGM/Duyuru/684/example",
        text="Mevzuat Taslağı - Türk Gıda Kodeksi Tebliği Taslağı. Görüş bildirme tarihi 04.05.2026.",
    )
    assert assessment.document_kind == "draft"
    assert assessment.authority_level == "official_nonbinding"
    assert assessment.auto_promotable_to_binding is False
    assert assessment.exact_binding_verification_required is True


def test_ministry_announcement_of_resmi_gazete_publication_is_still_not_binding_text():
    assessment = assess(
        "discovery",
        url="https://www.tarimorman.gov.tr/GKGM/Haber/1317/example",
        text="Türk Gıda Kodeksi Yeni Gıdalar Yönetmeliği Resmî Gazete'de yayımlandı ve yürürlüğe girdi.",
    )
    assert assessment.document_kind == "announcement"
    assert assessment.authority_level == "discovery_signal"
    assert assessment.auto_promotable_to_binding is False


def test_registry_entry_requires_exact_instrument_resolution():
    assessment = assess(
        "official_registry",
        url="https://kms.kaysis.gov.tr/Home/Kurum/24308110",
        text="Türk Gıda Kodeksi Yönetmelikleri ve Tebliğleri",
    )
    assert assessment.document_kind == "registry_entry"
    assert assessment.authority_level == "official_registry"


def test_resmi_gazete_homepage_is_only_discovery_signal():
    assessment = assess(
        "binding_publication_index",
        url="https://www.resmigazete.gov.tr/",
        text="T.C. Resmî Gazete günlük fihrist yönetmelikler tebliğler",
    )
    assert assessment.document_kind == "announcement"
    assert assessment.authority_level == "discovery_signal"


def test_exact_resmi_gazete_like_text_is_candidate_but_still_requires_verification():
    assessment = assess(
        "binding_publication_index",
        url="https://www.resmigazete.gov.tr/eskiler/2026/05/20260520-1.htm",
        text="20 Mayıs 2026 Resmî Gazete Sayı : 33259 MADDE 1 Amaç ve kapsam ... MADDE 2 Dayanak ...",
    )
    assert assessment.document_kind == "binding_instrument_candidate"
    assert assessment.authority_level == "binding_candidate_unverified"
    assert assessment.auto_promotable_to_binding is False
    assert len(assessment.assessment_fingerprint) == 64


def test_guidance_cannot_override_binding_layer():
    assessment = assess(
        "guidance",
        url="https://guvenilirgida.tarimorman.gov.tr/example",
        text="Gıda etiketleme rehberi ve tüketici kılavuzu",
    )
    assert assessment.document_kind == "guidance"
    assert assessment.authority_level == "official_nonbinding"
    assert assessment.auto_promotable_to_binding is False
