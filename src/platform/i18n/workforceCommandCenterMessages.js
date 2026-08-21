const en = {
  eyebrow: "INTRADAY WORKFORCE COMMAND",
  title: "Workforce Command Center",
  detail: "One governed view of demand, capacity, schedule, attendance, pressure and approved what-if evidence.",
  worksite: "Worksite", refresh: "Refresh", loading: "Loading governed interval…", error: "Command Center authority is unavailable.", noLocations: "No authorized worksite is available.",
  current: "Current interval", past: "Past governed interval", future: "Future governed interval", intervalWidth: "{minutes}-minute authority", observedAt: "Observed {time}",
  liveTruth: "Current interval — live label permitted", staleTruth: "Not current — live label blocked", truthBoundary: "Repository evidence is not field or production proof.",
  demand: "Demand", scheduled: "Scheduled", effective: "Effective capacity", gap: "Capacity gap", scheduledPeople: "Scheduled people", present: "Present now", attendanceStarted: "Attendance started", noShow: "No-show", breaks: "Active breaks", skillDeficit: "Skill deficit", dpi: "Demand pressure index", rootCause: "Root cause", kpiPressure: "KPI pressure",
  operations: "Intraday operations", authority: "Authority lineage", actions: "Manager action queue", noActions: "No governed action is required for this interval.", humanApproval: "Human approval required", automaticOff: "Automatic schedule apply is off", replan: "Latest coherent replan", replanNone: "No replan scenario is bound to this DPI baseline.", recommendation: "Recommendation", costDelta: "Estimated cost delta", modelEvidence: "Model evidence", people: "people", manHours: "MH", count: "{count}",
  AUTHORITY_INTERVAL_NOT_CURRENT_TITLE: "Governed interval is not current", AUTHORITY_INTERVAL_NOT_CURRENT_DETAIL: "Refresh demand/capacity/DPI evidence before treating this screen as live operations.",
  SCHEDULE_SNAPSHOT_DRIFT_TITLE: "Schedule and capacity snapshot differ", SCHEDULE_SNAPSHOT_DRIFT_DETAIL: "Canonical schedule projection changed after the capacity snapshot; refresh capacity authority.",
  CAPACITY_SHORTAGE_TITLE: "Capacity shortage detected", CAPACITY_SHORTAGE_DETAIL: "Governed demand exceeds effective capacity. Review staffing options without bypassing hard rules.",
  SKILL_DEFICIT_TITLE: "Skill coverage gap", SKILL_DEFICIT_DETAIL: "The capacity authority reports skill-feasible hours below required coverage.",
  NO_SHOW_TITLE: "Scheduled attendance missing", NO_SHOW_DETAIL: "{count} scheduled shift(s) passed start time without a matching attendance start.",
  DAILY_LIMIT_BREACH_TITLE: "Daily work limit breach", DAILY_LIMIT_BREACH_DETAIL: "{count} employee schedule(s) exceed the effective canonical daily work limit.",
  REST_RULE_BREACH_TITLE: "Minimum rest breach", REST_RULE_BREACH_DETAIL: "{count} employee schedule(s) violate the effective between-shift rest rule.",
  KPI_PRESSURE_TITLE: "Operational KPI pressure", KPI_PRESSURE_DETAIL: "{count} governed KPI observation(s) are outside their approved target direction.",
  PENDING_REPLAN_TITLE: "Replan review required", PENDING_REPLAN_DETAIL: "A coherent what-if proposal exists and remains human-approved only.",
  PENDING_SHIFT_TRADE_TITLE: "Shift trade decisions waiting", PENDING_SHIFT_TRADE_DETAIL: "{count} employee-accepted trade(s) are waiting for manager approval.",
};

const tr = {
  ...en,
  eyebrow: "GÜN İÇİ WORKFORCE KOMUTA", title: "Workforce Komuta Merkezi", detail: "Talep, kapasite, vardiya, puantaj, baskı ve onaylı what-if kanıtını tek yönetişimli görünümde birleştirir.",
  worksite: "Çalışma noktası", refresh: "Yenile", loading: "Yönetişimli interval yükleniyor…", error: "Komuta Merkezi authority verisi kullanılamıyor.", noLocations: "Yetkili çalışma noktası bulunamadı.",
  current: "Güncel interval", past: "Geçmiş yönetişimli interval", future: "Gelecek yönetişimli interval", intervalWidth: "{minutes} dakikalık authority", observedAt: "Gözlem {time}",
  liveTruth: "Güncel interval — canlı etiketi kullanılabilir", staleTruth: "Güncel değil — canlı etiketi kapalı", truthBoundary: "Repository kanıtı saha veya production kanıtı değildir.",
  demand: "Talep", scheduled: "Planlanan", effective: "Efektif kapasite", gap: "Kapasite açığı", scheduledPeople: "Planlı çalışan", present: "Şu an mevcut", attendanceStarted: "Puantaj başlatan", noShow: "Gelmedi", breaks: "Aktif mola", skillDeficit: "Yetkinlik açığı", dpi: "Talep baskı endeksi", rootCause: "Kök neden", kpiPressure: "KPI baskısı",
  operations: "Gün içi operasyon", authority: "Authority lineage", actions: "Yönetici aksiyon kuyruğu", noActions: "Bu interval için yönetişimli aksiyon gerekmiyor.", humanApproval: "İnsan onayı zorunlu", automaticOff: "Otomatik vardiya uygulama kapalı", replan: "Aynı baseline'a bağlı replan", replanNone: "Bu DPI baseline'ına bağlı replan senaryosu yok.", recommendation: "Öneri", costDelta: "Tahmini maliyet farkı", modelEvidence: "Model kanıtı", people: "kişi", manHours: "KS", count: "{count}",
  AUTHORITY_INTERVAL_NOT_CURRENT_TITLE: "Yönetişimli interval güncel değil", AUTHORITY_INTERVAL_NOT_CURRENT_DETAIL: "Bu ekran canlı operasyon olarak kullanılmadan önce demand/capacity/DPI kanıtı yenilenmeli.",
  SCHEDULE_SNAPSHOT_DRIFT_TITLE: "Vardiya ile kapasite snapshot'ı farklı", SCHEDULE_SNAPSHOT_DRIFT_DETAIL: "Canonical vardiya projeksiyonu kapasite snapshot'ından sonra değişti; kapasite authority yenilenmeli.",
  CAPACITY_SHORTAGE_TITLE: "Kapasite açığı tespit edildi", CAPACITY_SHORTAGE_DETAIL: "Yönetişimli talep efektif kapasitenin üzerinde. Sert kuralları aşmadan personel seçeneklerini incele.",
  SKILL_DEFICIT_TITLE: "Yetkinlik kapsama açığı", SKILL_DEFICIT_DETAIL: "Kapasite authority, yetkinlikle karşılanabilen saatlerin gerekli kapsamın altında olduğunu gösteriyor.",
  NO_SHOW_TITLE: "Planlı çalışan puantaj başlatmadı", NO_SHOW_DETAIL: "{count} vardiyanın başlangıç saati geçti ve eşleşen puantaj başlangıcı yok.",
  DAILY_LIMIT_BREACH_TITLE: "Günlük çalışma limiti ihlali", DAILY_LIMIT_BREACH_DETAIL: "{count} çalışan planı yürürlükteki canonical günlük çalışma limitini aşıyor.",
  REST_RULE_BREACH_TITLE: "Minimum dinlenme ihlali", REST_RULE_BREACH_DETAIL: "{count} çalışan planı vardiyalar arası yürürlükteki dinlenme kuralını ihlal ediyor.",
  KPI_PRESSURE_TITLE: "Operasyon KPI baskısı", KPI_PRESSURE_DETAIL: "{count} yönetişimli KPI gözlemi onaylı hedef yönünün dışında.",
  PENDING_REPLAN_TITLE: "Replan incelemesi gerekli", PENDING_REPLAN_DETAIL: "Aynı baseline'a bağlı what-if önerisi mevcut ve yalnız insan onayıyla ilerleyebilir.",
  PENDING_SHIFT_TRADE_TITLE: "Vardiya takası kararı bekliyor", PENDING_SHIFT_TRADE_DETAIL: "{count} çalışan-kabul edilmiş takas yönetici kararını bekliyor.",
};

const deActions = {
  AUTHORITY_INTERVAL_NOT_CURRENT_TITLE: "Gesteuertes Intervall ist nicht aktuell", AUTHORITY_INTERVAL_NOT_CURRENT_DETAIL: "Bedarfs-, Kapazitäts- und DPI-Nachweise aktualisieren, bevor diese Ansicht als Live-Betrieb genutzt wird.",
  SCHEDULE_SNAPSHOT_DRIFT_TITLE: "Schichtplan und Kapazitäts-Snapshot weichen ab", SCHEDULE_SNAPSHOT_DRIFT_DETAIL: "Die kanonische Schichtprojektion wurde nach dem Kapazitäts-Snapshot geändert; die Kapazitätsautorität muss aktualisiert werden.",
  CAPACITY_SHORTAGE_TITLE: "Kapazitätsengpass erkannt", CAPACITY_SHORTAGE_DETAIL: "Der gesteuerte Bedarf übersteigt die effektive Kapazität. Personaloptionen prüfen, ohne harte Regeln zu umgehen.",
  SKILL_DEFICIT_TITLE: "Lücke in der Kompetenzabdeckung", SKILL_DEFICIT_DETAIL: "Die Kapazitätsautorität meldet weniger kompetenzgeeignete Stunden als für die erforderliche Abdeckung benötigt.",
  NO_SHOW_TITLE: "Geplante Anwesenheit fehlt", NO_SHOW_DETAIL: "Bei {count} geplanter Schicht(en) ist die Startzeit verstrichen, ohne dass ein passender Anwesenheitsbeginn vorliegt.",
  DAILY_LIMIT_BREACH_TITLE: "Tägliches Arbeitslimit überschritten", DAILY_LIMIT_BREACH_DETAIL: "{count} Mitarbeiterplan/-pläne überschreiten das aktuell gültige kanonische Tagesarbeitslimit.",
  REST_RULE_BREACH_TITLE: "Mindestpause zwischen Schichten verletzt", REST_RULE_BREACH_DETAIL: "{count} Mitarbeiterplan/-pläne verletzen die aktuell gültige Mindestruhezeit zwischen Schichten.",
  KPI_PRESSURE_TITLE: "Operativer KPI-Druck", KPI_PRESSURE_DETAIL: "{count} gesteuerte KPI-Beobachtung(en) liegen außerhalb der genehmigten Zielrichtung.",
  PENDING_REPLAN_TITLE: "Replan-Prüfung erforderlich", PENDING_REPLAN_DETAIL: "Ein kohärenter What-if-Vorschlag liegt vor und darf weiterhin nur nach menschlicher Freigabe umgesetzt werden.",
  PENDING_SHIFT_TRADE_TITLE: "Schichttausch-Entscheidungen ausstehend", PENDING_SHIFT_TRADE_DETAIL: "{count} von Mitarbeitenden akzeptierte Tauschvorgänge warten auf die Freigabe durch eine Führungskraft.",
};
const arActions = {
  AUTHORITY_INTERVAL_NOT_CURRENT_TITLE: "الفترة المحكومة ليست حالية", AUTHORITY_INTERVAL_NOT_CURRENT_DETAIL: "حدّث أدلة الطلب والسعة وDPI قبل التعامل مع هذه الشاشة كتشغيل مباشر.",
  SCHEDULE_SNAPSHOT_DRIFT_TITLE: "الجدول ولقطة السعة غير متطابقين", SCHEDULE_SNAPSHOT_DRIFT_DETAIL: "تغيّر إسقاط الجدول المعتمد بعد لقطة السعة؛ يجب تحديث سلطة السعة.",
  CAPACITY_SHORTAGE_TITLE: "تم رصد عجز في السعة", CAPACITY_SHORTAGE_DETAIL: "الطلب المحكوم يتجاوز السعة الفعلية. راجع خيارات التوظيف دون تجاوز القواعد الصارمة.",
  SKILL_DEFICIT_TITLE: "فجوة في تغطية المهارات", SKILL_DEFICIT_DETAIL: "تُظهر سلطة السعة أن الساعات الممكن تغطيتها بالمهارات أقل من التغطية المطلوبة.",
  NO_SHOW_TITLE: "الحضور المجدول مفقود", NO_SHOW_DETAIL: "مر وقت بدء {count} مناوبة مجدولة دون تسجيل بدء حضور مطابق.",
  DAILY_LIMIT_BREACH_TITLE: "تجاوز حد العمل اليومي", DAILY_LIMIT_BREACH_DETAIL: "يتجاوز {count} جدول موظف الحد اليومي المعتمد والنافذ للعمل.",
  REST_RULE_BREACH_TITLE: "مخالفة الحد الأدنى للراحة", REST_RULE_BREACH_DETAIL: "يخالف {count} جدول موظف قاعدة الراحة النافذة بين المناوبات.",
  KPI_PRESSURE_TITLE: "ضغط مؤشرات الأداء التشغيلية", KPI_PRESSURE_DETAIL: "يوجد {count} رصد KPI محكوم خارج اتجاه الهدف المعتمد.",
  PENDING_REPLAN_TITLE: "مراجعة إعادة التخطيط مطلوبة", PENDING_REPLAN_DETAIL: "يوجد اقتراح what-if متسق ولا يزال تطبيقه مشروطاً بالموافقة البشرية فقط.",
  PENDING_SHIFT_TRADE_TITLE: "قرارات تبديل المناوبات بانتظار الموافقة", PENDING_SHIFT_TRADE_DETAIL: "هناك {count} عملية تبديل وافق عليها الموظفون وتنتظر موافقة المدير.",
};
const frActions = {
  AUTHORITY_INTERVAL_NOT_CURRENT_TITLE: "L’intervalle gouverné n’est pas actuel", AUTHORITY_INTERVAL_NOT_CURRENT_DETAIL: "Actualisez les preuves de demande, capacité et DPI avant d’utiliser cet écran comme vue d’exploitation en temps réel.",
  SCHEDULE_SNAPSHOT_DRIFT_TITLE: "Le planning et le snapshot de capacité divergent", SCHEDULE_SNAPSHOT_DRIFT_DETAIL: "La projection canonique du planning a changé après le snapshot de capacité ; actualisez l’autorité de capacité.",
  CAPACITY_SHORTAGE_TITLE: "Déficit de capacité détecté", CAPACITY_SHORTAGE_DETAIL: "La demande gouvernée dépasse la capacité effective. Examinez les options de staffing sans contourner les règles strictes.",
  SKILL_DEFICIT_TITLE: "Déficit de couverture des compétences", SKILL_DEFICIT_DETAIL: "L’autorité de capacité indique que les heures réalisables avec les compétences disponibles sont inférieures à la couverture requise.",
  NO_SHOW_TITLE: "Présence planifiée manquante", NO_SHOW_DETAIL: "{count} quart(s) planifié(s) ont dépassé l’heure de début sans démarrage de présence correspondant.",
  DAILY_LIMIT_BREACH_TITLE: "Dépassement de la limite quotidienne de travail", DAILY_LIMIT_BREACH_DETAIL: "{count} planning(s) salarié dépassent la limite quotidienne canonique actuellement applicable.",
  REST_RULE_BREACH_TITLE: "Non-respect du repos minimum", REST_RULE_BREACH_DETAIL: "{count} planning(s) salarié enfreignent la règle de repos applicable entre deux quarts.",
  KPI_PRESSURE_TITLE: "Pression KPI opérationnelle", KPI_PRESSURE_DETAIL: "{count} observation(s) KPI gouvernée(s) se situent hors de la direction cible approuvée.",
  PENDING_REPLAN_TITLE: "Révision du replan requise", PENDING_REPLAN_DETAIL: "Une proposition what-if cohérente existe et reste soumise exclusivement à une approbation humaine.",
  PENDING_SHIFT_TRADE_TITLE: "Décisions d’échange de quarts en attente", PENDING_SHIFT_TRADE_DETAIL: "{count} échange(s) accepté(s) par les salariés attendent l’approbation du manager.",
};
const esActions = {
  AUTHORITY_INTERVAL_NOT_CURRENT_TITLE: "El intervalo gobernado no es actual", AUTHORITY_INTERVAL_NOT_CURRENT_DETAIL: "Actualiza la evidencia de demanda, capacidad y DPI antes de tratar esta pantalla como operación en vivo.",
  SCHEDULE_SNAPSHOT_DRIFT_TITLE: "El horario y el snapshot de capacidad difieren", SCHEDULE_SNAPSHOT_DRIFT_DETAIL: "La proyección canónica del horario cambió después del snapshot de capacidad; actualiza la autoridad de capacidad.",
  CAPACITY_SHORTAGE_TITLE: "Déficit de capacidad detectado", CAPACITY_SHORTAGE_DETAIL: "La demanda gobernada supera la capacidad efectiva. Revisa opciones de personal sin eludir las reglas estrictas.",
  SKILL_DEFICIT_TITLE: "Brecha de cobertura de habilidades", SKILL_DEFICIT_DETAIL: "La autoridad de capacidad informa que las horas factibles por habilidad están por debajo de la cobertura requerida.",
  NO_SHOW_TITLE: "Falta asistencia programada", NO_SHOW_DETAIL: "{count} turno(s) programado(s) superaron la hora de inicio sin un inicio de asistencia correspondiente.",
  DAILY_LIMIT_BREACH_TITLE: "Incumplimiento del límite diario de trabajo", DAILY_LIMIT_BREACH_DETAIL: "{count} horario(s) de empleado superan el límite diario canónico vigente.",
  REST_RULE_BREACH_TITLE: "Incumplimiento del descanso mínimo", REST_RULE_BREACH_DETAIL: "{count} horario(s) de empleado incumplen la regla vigente de descanso entre turnos.",
  KPI_PRESSURE_TITLE: "Presión operativa de KPI", KPI_PRESSURE_DETAIL: "{count} observación(es) KPI gobernada(s) están fuera de la dirección objetivo aprobada.",
  PENDING_REPLAN_TITLE: "Se requiere revisar la replanificación", PENDING_REPLAN_DETAIL: "Existe una propuesta what-if coherente y sigue requiriendo exclusivamente aprobación humana.",
  PENDING_SHIFT_TRADE_TITLE: "Decisiones de intercambio de turnos pendientes", PENDING_SHIFT_TRADE_DETAIL: "{count} intercambio(s) aceptado(s) por empleados esperan aprobación del gerente.",
};
const itActions = {
  AUTHORITY_INTERVAL_NOT_CURRENT_TITLE: "L’intervallo governato non è corrente", AUTHORITY_INTERVAL_NOT_CURRENT_DETAIL: "Aggiorna le evidenze di domanda, capacità e DPI prima di usare questa schermata come vista operativa live.",
  SCHEDULE_SNAPSHOT_DRIFT_TITLE: "Pianificazione e snapshot di capacità divergono", SCHEDULE_SNAPSHOT_DRIFT_DETAIL: "La proiezione canonica dei turni è cambiata dopo lo snapshot di capacità; aggiorna l’autorità di capacità.",
  CAPACITY_SHORTAGE_TITLE: "Carenza di capacità rilevata", CAPACITY_SHORTAGE_DETAIL: "La domanda governata supera la capacità effettiva. Valuta le opzioni di staffing senza aggirare le regole rigide.",
  SKILL_DEFICIT_TITLE: "Gap di copertura delle competenze", SKILL_DEFICIT_DETAIL: "L’autorità di capacità segnala ore compatibili con le competenze inferiori alla copertura richiesta.",
  NO_SHOW_TITLE: "Presenza pianificata mancante", NO_SHOW_DETAIL: "{count} turno/i pianificato/i hanno superato l’orario di inizio senza un corrispondente avvio della presenza.",
  DAILY_LIMIT_BREACH_TITLE: "Superamento del limite giornaliero di lavoro", DAILY_LIMIT_BREACH_DETAIL: "{count} pianificazione/i dipendente supera/no il limite giornaliero canonico attualmente in vigore.",
  REST_RULE_BREACH_TITLE: "Violazione del riposo minimo", REST_RULE_BREACH_DETAIL: "{count} pianificazione/i dipendente viola/no la regola di riposo vigente tra i turni.",
  KPI_PRESSURE_TITLE: "Pressione KPI operativa", KPI_PRESSURE_DETAIL: "{count} osservazione/i KPI governata/e è/sono fuori dalla direzione target approvata.",
  PENDING_REPLAN_TITLE: "Revisione del replan richiesta", PENDING_REPLAN_DETAIL: "Esiste una proposta what-if coerente e resta applicabile solo con approvazione umana.",
  PENDING_SHIFT_TRADE_TITLE: "Decisioni di scambio turno in attesa", PENDING_SHIFT_TRADE_DETAIL: "{count} scambio/i accettato/i dai dipendenti attende/ono l’approvazione del responsabile.",
};
const nlActions = {
  AUTHORITY_INTERVAL_NOT_CURRENT_TITLE: "Het beheerde interval is niet actueel", AUTHORITY_INTERVAL_NOT_CURRENT_DETAIL: "Vernieuw bewijs voor vraag, capaciteit en DPI voordat dit scherm als live operatie wordt gebruikt.",
  SCHEDULE_SNAPSHOT_DRIFT_TITLE: "Rooster en capaciteitssnapshot wijken af", SCHEDULE_SNAPSHOT_DRIFT_DETAIL: "De canonieke roosterprojectie is gewijzigd na de capaciteitssnapshot; vernieuw de capaciteitsautoriteit.",
  CAPACITY_SHORTAGE_TITLE: "Capaciteitstekort gedetecteerd", CAPACITY_SHORTAGE_DETAIL: "De beheerde vraag is hoger dan de effectieve capaciteit. Beoordeel personeelsopties zonder harde regels te omzeilen.",
  SKILL_DEFICIT_TITLE: "Tekort in vaardigheidsdekking", SKILL_DEFICIT_DETAIL: "De capaciteitsautoriteit meldt minder vaardigheidshaalbare uren dan de vereiste dekking.",
  NO_SHOW_TITLE: "Geplande aanwezigheid ontbreekt", NO_SHOW_DETAIL: "Bij {count} geplande dienst(en) is de starttijd verstreken zonder een overeenkomende aanwezigheidsstart.",
  DAILY_LIMIT_BREACH_TITLE: "Dagelijkse werktijdlimiet overschreden", DAILY_LIMIT_BREACH_DETAIL: "{count} medewerkersrooster(s) overschrijden de geldende canonieke dagelijkse werktijdlimiet.",
  REST_RULE_BREACH_TITLE: "Minimale rustregel overtreden", REST_RULE_BREACH_DETAIL: "{count} medewerkersrooster(s) overtreden de geldende rustregel tussen diensten.",
  KPI_PRESSURE_TITLE: "Operationele KPI-druk", KPI_PRESSURE_DETAIL: "{count} beheerde KPI-waarneming(en) vallen buiten de goedgekeurde doelrichting.",
  PENDING_REPLAN_TITLE: "Herplanning moet worden beoordeeld", PENDING_REPLAN_DETAIL: "Er is een coherente what-if-propositie en toepassing blijft uitsluitend onder menselijke goedkeuring.",
  PENDING_SHIFT_TRADE_TITLE: "Besluiten over dienstruil wachten", PENDING_SHIFT_TRADE_DETAIL: "{count} door medewerkers geaccepteerde ruil(en) wachten op goedkeuring door de manager.",
};
const plActions = {
  AUTHORITY_INTERVAL_NOT_CURRENT_TITLE: "Zarządzany interwał nie jest bieżący", AUTHORITY_INTERVAL_NOT_CURRENT_DETAIL: "Odśwież dowody popytu, pojemności i DPI przed użyciem tego ekranu jako widoku operacji na żywo.",
  SCHEDULE_SNAPSHOT_DRIFT_TITLE: "Grafik i snapshot pojemności różnią się", SCHEDULE_SNAPSHOT_DRIFT_DETAIL: "Kanoniczna projekcja grafiku zmieniła się po snapshocie pojemności; odśwież authority pojemności.",
  CAPACITY_SHORTAGE_TITLE: "Wykryto niedobór pojemności", CAPACITY_SHORTAGE_DETAIL: "Zarządzany popyt przekracza efektywną pojemność. Przejrzyj opcje obsady bez omijania twardych reguł.",
  SKILL_DEFICIT_TITLE: "Luka w pokryciu kompetencji", SKILL_DEFICIT_DETAIL: "Authority pojemności wskazuje, że godziny możliwe do pokrycia kompetencjami są niższe od wymaganego pokrycia.",
  NO_SHOW_TITLE: "Brak zaplanowanej obecności", NO_SHOW_DETAIL: "Dla {count} zaplanowanych zmian minęła godzina rozpoczęcia bez odpowiadającego rozpoczęcia obecności.",
  DAILY_LIMIT_BREACH_TITLE: "Przekroczenie dziennego limitu pracy", DAILY_LIMIT_BREACH_DETAIL: "{count} grafików pracowników przekracza obowiązujący kanoniczny dzienny limit pracy.",
  REST_RULE_BREACH_TITLE: "Naruszenie minimalnego odpoczynku", REST_RULE_BREACH_DETAIL: "{count} grafików pracowników narusza obowiązującą regułę odpoczynku między zmianami.",
  KPI_PRESSURE_TITLE: "Operacyjna presja KPI", KPI_PRESSURE_DETAIL: "{count} zarządzanych obserwacji KPI znajduje się poza zatwierdzonym kierunkiem celu.",
  PENDING_REPLAN_TITLE: "Wymagany przegląd replanu", PENDING_REPLAN_DETAIL: "Istnieje spójna propozycja what-if i nadal może zostać zastosowana wyłącznie po zatwierdzeniu przez człowieka.",
  PENDING_SHIFT_TRADE_TITLE: "Decyzje o zamianie zmian oczekują", PENDING_SHIFT_TRADE_DETAIL: "{count} zaakceptowanych przez pracowników zamian oczekuje na zatwierdzenie menedżera.",
};
const ptBRActions = {
  AUTHORITY_INTERVAL_NOT_CURRENT_TITLE: "O intervalo governado não é atual", AUTHORITY_INTERVAL_NOT_CURRENT_DETAIL: "Atualize as evidências de demanda, capacidade e DPI antes de tratar esta tela como operação ao vivo.",
  SCHEDULE_SNAPSHOT_DRIFT_TITLE: "Escala e snapshot de capacidade divergem", SCHEDULE_SNAPSHOT_DRIFT_DETAIL: "A projeção canônica da escala mudou após o snapshot de capacidade; atualize a autoridade de capacidade.",
  CAPACITY_SHORTAGE_TITLE: "Déficit de capacidade detectado", CAPACITY_SHORTAGE_DETAIL: "A demanda governada supera a capacidade efetiva. Revise opções de pessoal sem contornar regras rígidas.",
  SKILL_DEFICIT_TITLE: "Lacuna de cobertura de competências", SKILL_DEFICIT_DETAIL: "A autoridade de capacidade informa horas viáveis por competência abaixo da cobertura necessária.",
  NO_SHOW_TITLE: "Presença programada ausente", NO_SHOW_DETAIL: "{count} turno(s) programado(s) passaram do horário de início sem um início de presença correspondente.",
  DAILY_LIMIT_BREACH_TITLE: "Violação do limite diário de trabalho", DAILY_LIMIT_BREACH_DETAIL: "{count} escala(s) de colaborador excedem o limite diário canônico atualmente vigente.",
  REST_RULE_BREACH_TITLE: "Violação do descanso mínimo", REST_RULE_BREACH_DETAIL: "{count} escala(s) de colaborador violam a regra vigente de descanso entre turnos.",
  KPI_PRESSURE_TITLE: "Pressão operacional de KPI", KPI_PRESSURE_DETAIL: "{count} observação(ões) de KPI governada(s) estão fora da direção de meta aprovada.",
  PENDING_REPLAN_TITLE: "Revisão do replanejamento necessária", PENDING_REPLAN_DETAIL: "Existe uma proposta what-if coerente e sua aplicação continua condicionada exclusivamente à aprovação humana.",
  PENDING_SHIFT_TRADE_TITLE: "Decisões de troca de turno pendentes", PENDING_SHIFT_TRADE_DETAIL: "{count} troca(s) aceita(s) por colaboradores aguardam aprovação do gestor.",
};

const de = { ...en, ...deActions, eyebrow: "INTRADAY WORKFORCE COMMAND", title: "Workforce-Kommandozentrale", detail: "Eine gesteuerte Sicht auf Bedarf, Kapazität, Schichten, Anwesenheit und Druck.", worksite: "Standort", refresh: "Aktualisieren", loading: "Gesteuertes Intervall wird geladen…", error: "Die Command-Center-Autorität ist nicht verfügbar.", noLocations: "Kein berechtigter Standort verfügbar.", current: "Aktuelles Intervall", past: "Vergangenes Intervall", future: "Zukünftiges Intervall", liveTruth: "Aktuelles Intervall — Live-Kennzeichnung zulässig", staleTruth: "Nicht aktuell — Live-Kennzeichnung gesperrt", truthBoundary: "Repository-Nachweise sind kein Feld- oder Produktionsnachweis.", actions: "Aktionsliste für Führungskräfte", humanApproval: "Menschliche Freigabe erforderlich", automaticOff: "Automatische Schichtanwendung ist aus", noActions: "Für dieses Intervall ist keine gesteuerte Aktion erforderlich." };
const ar = { ...en, ...arActions, eyebrow: "قيادة القوى العاملة خلال اليوم", title: "مركز قيادة القوى العاملة", detail: "عرض محكوم يجمع الطلب والسعة والورديات والحضور والضغط.", worksite: "موقع العمل", refresh: "تحديث", loading: "جارٍ تحميل الفترة المحكومة…", error: "سلطة مركز القيادة غير متاحة.", noLocations: "لا يوجد موقع عمل مخول.", current: "الفترة الحالية", past: "فترة محكومة سابقة", future: "فترة محكومة مستقبلية", liveTruth: "الفترة الحالية — يمكن استخدام وصف مباشر", staleTruth: "ليست حالية — الوصف المباشر محجوب", truthBoundary: "دليل المستودع ليس دليلاً ميدانياً أو إنتاجياً.", actions: "قائمة إجراءات المدير", humanApproval: "موافقة بشرية مطلوبة", automaticOff: "التطبيق التلقائي للورديات متوقف", noActions: "لا يوجد إجراء محكوم مطلوب لهذه الفترة." };
const fr = { ...en, ...frActions, title: "Centre de commandement Workforce", detail: "Vue gouvernée de la demande, capacité, planning, présence et pression.", worksite: "Site", refresh: "Actualiser", loading: "Chargement de l’intervalle gouverné…", error: "L’autorité du centre de commandement est indisponible.", noLocations: "Aucun site autorisé.", current: "Intervalle actuel", past: "Intervalle gouverné passé", future: "Intervalle gouverné futur", liveTruth: "Intervalle actuel — libellé temps réel autorisé", staleTruth: "Non actuel — libellé temps réel bloqué", truthBoundary: "La preuve du dépôt n’est pas une preuve terrain ou production.", actions: "File d’actions manager", humanApproval: "Approbation humaine requise", automaticOff: "Application automatique du planning désactivée", noActions: "Aucune action gouvernée requise pour cet intervalle." };
const es = { ...en, ...esActions, title: "Centro de mando Workforce", detail: "Vista gobernada de demanda, capacidad, turnos, asistencia y presión.", worksite: "Centro", refresh: "Actualizar", loading: "Cargando intervalo gobernado…", error: "La autoridad del centro de mando no está disponible.", noLocations: "No hay centro autorizado.", current: "Intervalo actual", past: "Intervalo gobernado pasado", future: "Intervalo gobernado futuro", liveTruth: "Intervalo actual — etiqueta en vivo permitida", staleTruth: "No actual — etiqueta en vivo bloqueada", truthBoundary: "La evidencia del repositorio no es evidencia de campo ni de producción.", actions: "Cola de acciones del gerente", humanApproval: "Se requiere aprobación humana", automaticOff: "Aplicación automática de turnos desactivada", noActions: "No se requiere acción gobernada para este intervalo." };
const it = { ...en, ...itActions, title: "Centro di comando Workforce", detail: "Vista governata di domanda, capacità, turni, presenze e pressione.", worksite: "Sede", refresh: "Aggiorna", loading: "Caricamento intervallo governato…", error: "L'autorità del centro di comando non è disponibile.", noLocations: "Nessuna sede autorizzata.", current: "Intervallo corrente", past: "Intervallo governato passato", future: "Intervallo governato futuro", liveTruth: "Intervallo corrente — etichetta live consentita", staleTruth: "Non corrente — etichetta live bloccata", truthBoundary: "L'evidenza repository non è prova sul campo o di produzione.", actions: "Coda azioni manager", humanApproval: "Approvazione umana richiesta", automaticOff: "Applicazione automatica turni disattivata", noActions: "Nessuna azione governata richiesta per questo intervallo." };
const nl = { ...en, ...nlActions, title: "Workforce Command Center", detail: "Beheerde weergave van vraag, capaciteit, diensten, aanwezigheid en druk.", worksite: "Locatie", refresh: "Vernieuwen", loading: "Beheerd interval laden…", error: "Command Center-authoriteit is niet beschikbaar.", noLocations: "Geen bevoegde locatie beschikbaar.", current: "Huidig interval", past: "Voorbij beheerd interval", future: "Toekomstig beheerd interval", liveTruth: "Huidig interval — live-label toegestaan", staleTruth: "Niet huidig — live-label geblokkeerd", truthBoundary: "Repositorybewijs is geen veld- of productiebewijs.", actions: "Actiewachtrij manager", humanApproval: "Menselijke goedkeuring vereist", automaticOff: "Automatische diensttoepassing uit", noActions: "Geen beheerde actie nodig voor dit interval." };
const pl = { ...en, ...plActions, title: "Centrum dowodzenia Workforce", detail: "Zarządzany widok popytu, pojemności, zmian, obecności i presji.", worksite: "Lokalizacja", refresh: "Odśwież", loading: "Ładowanie zarządzanego interwału…", error: "Authority Command Center jest niedostępne.", noLocations: "Brak autoryzowanej lokalizacji.", current: "Bieżący interwał", past: "Przeszły interwał", future: "Przyszły interwał", liveTruth: "Bieżący interwał — etykieta live dozwolona", staleTruth: "Nieaktualny — etykieta live zablokowana", truthBoundary: "Dowód repozytorium nie jest dowodem terenowym ani produkcyjnym.", actions: "Kolejka działań menedżera", humanApproval: "Wymagana akceptacja człowieka", automaticOff: "Automatyczne stosowanie zmian wyłączone", noActions: "Brak wymaganych działań dla tego interwału." };
const ptBR = { ...en, ...ptBRActions, title: "Central de Comando Workforce", detail: "Visão governada de demanda, capacidade, turnos, presença e pressão.", worksite: "Local", refresh: "Atualizar", loading: "Carregando intervalo governado…", error: "A autoridade da Central de Comando está indisponível.", noLocations: "Nenhum local autorizado disponível.", current: "Intervalo atual", past: "Intervalo governado passado", future: "Intervalo governado futuro", liveTruth: "Intervalo atual — rótulo ao vivo permitido", staleTruth: "Não atual — rótulo ao vivo bloqueado", truthBoundary: "Evidência do repositório não é prova de campo ou produção.", actions: "Fila de ações do gestor", humanApproval: "Aprovação humana necessária", automaticOff: "Aplicação automática de turnos desligada", noActions: "Nenhuma ação governada necessária para este intervalo." };

const MESSAGES = { tr, en, de, ar, fr, es, it, nl, pl, "pt-BR": ptBR };

export function workforceCommandCenterMessage(locale, key, params = {}) {
  const dictionary = MESSAGES[locale] || MESSAGES.en;
  const template = dictionary[key] || MESSAGES.en[key] || key;
  return String(template).replace(/\{(\w+)\}/g, (_, token) => String(params[token] ?? `{${token}}`));
}
