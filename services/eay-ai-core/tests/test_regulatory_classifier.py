from app.regulatory_classifier import classify_regulatory_text


def test_draft_language_is_never_binding():
    signal = classify_regulatory_text(
        "Mevzuat Taslağı hazırlanmıştır. Son Görüş Bildirme Tarihi 01.05.2026."
    )
    assert signal.classification == "draft_consultation"
    assert signal.can_auto_promote_to_binding is False


def test_resmi_gazete_publication_is_only_a_signal():
    signal = classify_regulatory_text(
        "Türk Gıda Kodeksi Yeni Gıdalar Yönetmeliği 20 Mayıs 2026 tarihli ve 33259 sayılı Resmî Gazete'de yayımlanarak yürürlüğe girdi."
    )
    assert signal.classification == "binding_publication_signal"
    assert signal.can_auto_promote_to_binding is False


def test_commission_decision_not_mistaken_for_published_law():
    signal = classify_regulatory_text(
        "Ulusal Gıda Kodeks Komisyonu toplantısında 3 mevzuatın yayımlanması kararlaştırıldı."
    )
    assert signal.classification == "committee_activity"


def test_guidance_source_role_fallback():
    signal = classify_regulatory_text("Gıda güvenilirliği hakkında açıklama", source_role="guidance")
    assert signal.classification == "guidance"
