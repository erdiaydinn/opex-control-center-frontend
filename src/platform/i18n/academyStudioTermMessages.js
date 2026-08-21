export const ACADEMY_STUDIO_TERM_MESSAGES = Object.freeze({
  tr: { scene: "Sahne", decision: "Karar", task: "Görev", evidence: "Kanıt", outcome: "Sonuç", completed: "Tamamlandı", failed: "Başarısız", remediation: "Düzeltici öğrenme", human: "İnsan çevirisi", machine_assisted: "Makine destekli", machine_draft: "Makine taslağı", defaultLabel: "Varsayılan" },
  en: { scene: "Scene", decision: "Decision", task: "Task", evidence: "Evidence", outcome: "Outcome", completed: "Completed", failed: "Failed", remediation: "Remediation", human: "Human", machine_assisted: "Machine-assisted", machine_draft: "Machine draft", defaultLabel: "Default" },
  de: { scene: "Szene", decision: "Entscheidung", task: "Aufgabe", evidence: "Nachweis", outcome: "Ergebnis", completed: "Abgeschlossen", failed: "Fehlgeschlagen", remediation: "Nachschulung", human: "Menschlich", machine_assisted: "Maschinenunterstützt", machine_draft: "Maschinenentwurf", defaultLabel: "Standard" },
  ar: { scene: "مشهد", decision: "قرار", task: "مهمة", evidence: "دليل", outcome: "نتيجة", completed: "مكتمل", failed: "فشل", remediation: "تعلم علاجي", human: "بشري", machine_assisted: "بمساعدة الآلة", machine_draft: "مسودة آلية", defaultLabel: "افتراضي" },
  fr: { scene: "Scène", decision: "Décision", task: "Tâche", evidence: "Preuve", outcome: "Résultat", completed: "Terminé", failed: "Échec", remediation: "Remédiation", human: "Humain", machine_assisted: "Assisté par machine", machine_draft: "Brouillon machine", defaultLabel: "Par défaut" },
  es: { scene: "Escena", decision: "Decisión", task: "Tarea", evidence: "Evidencia", outcome: "Resultado", completed: "Completado", failed: "Fallido", remediation: "Remediación", human: "Humana", machine_assisted: "Asistida por máquina", machine_draft: "Borrador automático", defaultLabel: "Predeterminado" },
  it: { scene: "Scena", decision: "Decisione", task: "Attività", evidence: "Evidenza", outcome: "Esito", completed: "Completato", failed: "Non riuscito", remediation: "Recupero", human: "Umana", machine_assisted: "Assistita dalla macchina", machine_draft: "Bozza automatica", defaultLabel: "Predefinito" },
  nl: { scene: "Scène", decision: "Beslissing", task: "Taak", evidence: "Bewijs", outcome: "Resultaat", completed: "Voltooid", failed: "Mislukt", remediation: "Hersteltraining", human: "Menselijk", machine_assisted: "Machine-ondersteund", machine_draft: "Machineconcept", defaultLabel: "Standaard" },
  pl: { scene: "Scena", decision: "Decyzja", task: "Zadanie", evidence: "Dowód", outcome: "Wynik", completed: "Ukończone", failed: "Niepowodzenie", remediation: "Nauka naprawcza", human: "Ludzkie", machine_assisted: "Wspomagane maszynowo", machine_draft: "Szkic maszynowy", defaultLabel: "Domyślne" },
  "pt-BR": { scene: "Cena", decision: "Decisão", task: "Tarefa", evidence: "Evidência", outcome: "Resultado", completed: "Concluído", failed: "Falhou", remediation: "Remediação", human: "Humana", machine_assisted: "Assistida por máquina", machine_draft: "Rascunho por máquina", defaultLabel: "Padrão" },
});

export function translateAcademyStudioTerm(locale, key) {
  return ACADEMY_STUDIO_TERM_MESSAGES[locale]?.[key] || ACADEMY_STUDIO_TERM_MESSAGES.en[key] || key;
}

export function academyStudioTermMessageCoverage(locales) {
  const keys = Object.keys(ACADEMY_STUDIO_TERM_MESSAGES.en).sort();
  return {
    missing: Object.fromEntries(locales.map((locale) => [locale, keys.filter((key) => typeof ACADEMY_STUDIO_TERM_MESSAGES[locale]?.[key] !== "string")])),
    extra: Object.fromEntries(locales.map((locale) => [locale, Object.keys(ACADEMY_STUDIO_TERM_MESSAGES[locale] || {}).filter((key) => !keys.includes(key)).sort()])),
  };
}
