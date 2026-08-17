export const PLANOGRAM_EXECUTION_MESSAGES = Object.freeze({
  tr: {
    savePlanDraft: "Optimize sonucu plan taslağına kaydet",
    approvedStoreDnaRequired: "Aynı depo için onaylı ve fiziksel geometrisi doğrulanmış Store DNA gerekli.",
    planDraftSaved: "Plan taslağı kaydedildi.",
    assign: "Mağazaya ata",
    effectiveFrom: "Başlangıç zamanı",
    dueOptional: "Son tarih (opsiyonel)",
    consumeEvidence: "Compliance kanıtını işle",
    promotionId: "Governed Field promotion ID",
    planPendingAttestation: "Harici fiziksel attestation gelmeden plan onaylanamaz.",
  },
  en: {
    savePlanDraft: "Save optimized result as plan draft",
    approvedStoreDnaRequired: "Approved Store DNA with attested physical geometry is required for the same store.",
    planDraftSaved: "Plan draft saved.",
    assign: "Assign to store",
    effectiveFrom: "Effective from",
    dueOptional: "Due date (optional)",
    consumeEvidence: "Consume compliance evidence",
    promotionId: "Governed Field promotion ID",
    planPendingAttestation: "The plan cannot be approved until external physical attestation arrives.",
  },
  de: {
    savePlanDraft: "Optimiertes Ergebnis als Planentwurf speichern",
    approvedStoreDnaRequired: "Für dieselbe Filiale ist genehmigte Store DNA mit bestätigter physischer Geometrie erforderlich.",
    planDraftSaved: "Planentwurf gespeichert.",
    assign: "Filiale zuweisen",
    effectiveFrom: "Gültig ab",
    dueOptional: "Fälligkeitsdatum (optional)",
    consumeEvidence: "Compliance-Nachweis übernehmen",
    promotionId: "Governed Field Promotion-ID",
    planPendingAttestation: "Der Plan kann erst nach externer physischer Attestierung freigegeben werden.",
  },
  ar: {
    savePlanDraft: "حفظ النتيجة المحسنة كمسودة خطة",
    approvedStoreDnaRequired: "يلزم Store DNA معتمد بهندسة مادية موثقة لنفس المتجر.",
    planDraftSaved: "تم حفظ مسودة الخطة.",
    assign: "تعيين للمتجر",
    effectiveFrom: "ساري من",
    dueOptional: "الموعد النهائي (اختياري)",
    consumeEvidence: "استهلاك دليل الامتثال",
    promotionId: "معرّف governed Field promotion",
    planPendingAttestation: "لا يمكن اعتماد الخطة قبل وصول التوثيق المادي الخارجي.",
  },
  fr: {
    savePlanDraft: "Enregistrer le résultat optimisé comme brouillon de plan",
    approvedStoreDnaRequired: "Une Store DNA approuvée avec géométrie physique attestée est requise pour le même magasin.",
    planDraftSaved: "Brouillon de plan enregistré.",
    assign: "Affecter au magasin",
    effectiveFrom: "Effectif à partir de",
    dueOptional: "Échéance (facultative)",
    consumeEvidence: "Consommer la preuve de conformité",
    promotionId: "ID governed Field promotion",
    planPendingAttestation: "Le plan ne peut pas être approuvé avant l’attestation physique externe.",
  },
  es: {
    savePlanDraft: "Guardar resultado optimizado como borrador de plan",
    approvedStoreDnaRequired: "Se requiere Store DNA aprobado con geometría física atestada para la misma tienda.",
    planDraftSaved: "Borrador de plan guardado.",
    assign: "Asignar a tienda",
    effectiveFrom: "Vigente desde",
    dueOptional: "Fecha límite (opcional)",
    consumeEvidence: "Consumir evidencia de cumplimiento",
    promotionId: "ID de governed Field promotion",
    planPendingAttestation: "El plan no puede aprobarse hasta recibir la atestación física externa.",
  },
  it: {
    savePlanDraft: "Salva il risultato ottimizzato come bozza di piano",
    approvedStoreDnaRequired: "Per lo stesso negozio è richiesto Store DNA approvato con geometria fisica attestata.",
    planDraftSaved: "Bozza di piano salvata.",
    assign: "Assegna al negozio",
    effectiveFrom: "Valido da",
    dueOptional: "Scadenza (opzionale)",
    consumeEvidence: "Acquisisci prova di conformità",
    promotionId: "ID governed Field promotion",
    planPendingAttestation: "Il piano non può essere approvato finché non arriva l’attestazione fisica esterna.",
  },
  nl: {
    savePlanDraft: "Geoptimaliseerd resultaat als planconcept opslaan",
    approvedStoreDnaRequired: "Goedgekeurde Store DNA met bevestigde fysieke geometrie is vereist voor dezelfde winkel.",
    planDraftSaved: "Planconcept opgeslagen.",
    assign: "Aan winkel toewijzen",
    effectiveFrom: "Geldig vanaf",
    dueOptional: "Vervaldatum (optioneel)",
    consumeEvidence: "Compliance-bewijs verwerken",
    promotionId: "Governed Field promotion-ID",
    planPendingAttestation: "Het plan kan pas worden goedgekeurd na externe fysieke attestatie.",
  },
  pl: {
    savePlanDraft: "Zapisz zoptymalizowany wynik jako szkic planu",
    approvedStoreDnaRequired: "Dla tego samego sklepu wymagane jest zatwierdzone Store DNA z potwierdzoną geometrią fizyczną.",
    planDraftSaved: "Szkic planu zapisany.",
    assign: "Przypisz do sklepu",
    effectiveFrom: "Obowiązuje od",
    dueOptional: "Termin (opcjonalny)",
    consumeEvidence: "Przetwórz dowód zgodności",
    promotionId: "ID governed Field promotion",
    planPendingAttestation: "Plan nie może zostać zatwierdzony bez zewnętrznej atestacji fizycznej.",
  },
  "pt-BR": {
    savePlanDraft: "Salvar resultado otimizado como rascunho de plano",
    approvedStoreDnaRequired: "É necessário Store DNA aprovado com geometria física atestada para a mesma loja.",
    planDraftSaved: "Rascunho do plano salvo.",
    assign: "Atribuir à loja",
    effectiveFrom: "Vigente a partir de",
    dueOptional: "Prazo (opcional)",
    consumeEvidence: "Consumir evidência de conformidade",
    promotionId: "ID de governed Field promotion",
    planPendingAttestation: "O plano não pode ser aprovado até a chegada da atestação física externa.",
  },
});

export function translatePlanogramExecution(locale, key) {
  return PLANOGRAM_EXECUTION_MESSAGES[locale]?.[key]
    || PLANOGRAM_EXECUTION_MESSAGES.en[key]
    || key;
}

export function planogramExecutionMessageCoverage(locales) {
  const keys = Object.keys(PLANOGRAM_EXECUTION_MESSAGES.en).sort();
  return {
    missing: Object.fromEntries(
      locales.map((locale) => [
        locale,
        keys.filter((key) => typeof PLANOGRAM_EXECUTION_MESSAGES[locale]?.[key] !== "string"),
      ])
    ),
    extra: Object.fromEntries(
      locales.map((locale) => [
        locale,
        Object.keys(PLANOGRAM_EXECUTION_MESSAGES[locale] || {})
          .filter((key) => !keys.includes(key))
          .sort(),
      ])
    ),
  };
}
