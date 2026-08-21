const en = {
  scheduledCapacity: "Scheduled capacity",
  allocatedCapacity: "Capability-fit capacity",
  deficit: "Capacity deficit",
  recommendedPeople: "Recommended people",
  rootCause: "Root cause",
  noPressure: "No pressure signal",
  skillMix: "Skill / certification mix",
  manpowerShortage: "Scheduled manpower shortage",
};
const tr = {
  scheduledCapacity: "Planlı kapasite",
  allocatedCapacity: "Yetkinliğe uygun kapasite",
  deficit: "Kapasite açığı",
  recommendedPeople: "Önerilen kişi",
  rootCause: "Kök neden",
  noPressure: "Baskı sinyali yok",
  skillMix: "Yetkinlik / sertifika karması",
  manpowerShortage: "Planlı insan gücü açığı",
};
const de = { scheduledCapacity: "Geplante Kapazität", allocatedCapacity: "Qualifikationsgerechte Kapazität", deficit: "Kapazitätslücke", recommendedPeople: "Empfohlene Personen", rootCause: "Grundursache", noPressure: "Kein Belastungssignal", skillMix: "Qualifikations-/Zertifikatsmix", manpowerShortage: "Geplanter Personalmangel" };
const ar = { scheduledCapacity: "القدرة المجدولة", allocatedCapacity: "القدرة المطابقة للمهارات", deficit: "عجز القدرة", recommendedPeople: "الأشخاص المقترحون", rootCause: "السبب الجذري", noPressure: "لا توجد إشارة ضغط", skillMix: "مزيج المهارات والشهادات", manpowerShortage: "نقص القوى العاملة المجدولة" };
const fr = { scheduledCapacity: "Capacité planifiée", allocatedCapacity: "Capacité compatible avec les compétences", deficit: "Déficit de capacité", recommendedPeople: "Personnes recommandées", rootCause: "Cause racine", noPressure: "Aucun signal de pression", skillMix: "Mix compétences / certifications", manpowerShortage: "Manque de main-d’œuvre planifiée" };
const es = { scheduledCapacity: "Capacidad programada", allocatedCapacity: "Capacidad apta por competencias", deficit: "Déficit de capacidad", recommendedPeople: "Personas recomendadas", rootCause: "Causa raíz", noPressure: "Sin señal de presión", skillMix: "Mezcla de habilidades / certificaciones", manpowerShortage: "Falta de personal programado" };
const it = { scheduledCapacity: "Capacità pianificata", allocatedCapacity: "Capacità idonea per competenze", deficit: "Deficit di capacità", recommendedPeople: "Persone consigliate", rootCause: "Causa principale", noPressure: "Nessun segnale di pressione", skillMix: "Mix competenze / certificazioni", manpowerShortage: "Carenza di personale pianificato" };
const nl = { scheduledCapacity: "Geplande capaciteit", allocatedCapacity: "Vaardigheidsgeschikte capaciteit", deficit: "Capaciteitstekort", recommendedPeople: "Aanbevolen personen", rootCause: "Hoofdoorzaak", noPressure: "Geen druksignaal", skillMix: "Mix van vaardigheden / certificaten", manpowerShortage: "Tekort aan ingepland personeel" };
const pl = { scheduledCapacity: "Zaplanowana pojemność", allocatedCapacity: "Pojemność zgodna z kompetencjami", deficit: "Niedobór pojemności", recommendedPeople: "Zalecana liczba osób", rootCause: "Przyczyna źródłowa", noPressure: "Brak sygnału presji", skillMix: "Miks umiejętności / certyfikatów", manpowerShortage: "Brak zaplanowanej siły roboczej" };
const ptBR = { scheduledCapacity: "Capacidade programada", allocatedCapacity: "Capacidade compatível com competências", deficit: "Déficit de capacidade", recommendedPeople: "Pessoas recomendadas", rootCause: "Causa raiz", noPressure: "Sem sinal de pressão", skillMix: "Mix de habilidades / certificações", manpowerShortage: "Falta de mão de obra programada" };

const MESSAGES = { tr, en, de, ar, fr, es, it, nl, pl, "pt-BR": ptBR };

export function workforceCapacityMessage(locale, key) {
  const dictionary = MESSAGES[locale] || en;
  return dictionary[key] || en[key] || key;
}
