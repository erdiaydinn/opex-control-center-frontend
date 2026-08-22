package com.eay.inventory

import android.content.Intent
import android.os.Bundle
import androidx.activity.OnBackPressedCallback
import androidx.appcompat.app.AppCompatActivity
import com.eay.mobile.fieldui.runtime.EayTerminalRuntimeView
import com.eay.mobile.presentation.BlindCountUiState
import com.eay.mobile.presentation.EayModuleDetailSectionUiModel
import com.eay.mobile.presentation.EayModuleDetailUiState
import com.eay.mobile.presentation.EayModuleHealthVisual
import com.eay.mobile.presentation.EayModuleMetricUiModel
import com.eay.mobile.presentation.EayOneDestination
import com.eay.mobile.presentation.EayOneHomeSummaryUiState
import com.eay.mobile.presentation.EayOneNavigationModel
import com.eay.mobile.presentation.FieldMissionCardModel
import com.eay.mobile.presentation.FieldMissionVisualKind
import com.eay.mobile.presentation.FieldMissionVisualPriority
import com.eay.mobile.presentation.FieldOperationalStepKind
import com.eay.mobile.presentation.FieldRuntimeSurface
import com.eay.mobile.presentation.FieldShellHeader
import com.eay.mobile.presentation.FieldSyncVisualState
import com.eay.mobile.presentation.OperationalExecutionUiState

/**
 * Debug-only EAY Mobile product preview.
 *
 * Production builds never expose synthetic missions: they immediately enter the
 * managed EAY Terminal boundary. This activity exists for product/UX acceptance on
 * a normal Android phone without manufacturing identity, device, shift or inventory truth.
 */
class EayMobilePreviewActivity : AppCompatActivity() {
    private lateinit var fieldUi: EayTerminalRuntimeView
    private var selectedDestination = EayOneDestination.TODAY
    private var previewSurface = PreviewSurface.HOME
    private var countQuantity = ""
    private var countCompletedLines = 27
    private var operationalQuantity = ""
    private var operationalKind: FieldMissionVisualKind? = null
    private var operationalStepIndex = 0
    private val completedOperationalKinds = mutableSetOf<FieldMissionVisualKind>()
    private var activeModuleKind: FieldMissionVisualKind? = null
    private var moduleActionAcknowledged = false

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        if (!BuildConfig.DEBUG) {
            startActivity(Intent(this, MainActivity::class.java))
            finish()
            return
        }
        fieldUi = EayTerminalRuntimeView(this)
        setContentView(fieldUi)
        onBackPressedDispatcher.addCallback(this, object : OnBackPressedCallback(true) {
            override fun handleOnBackPressed() {
                if (previewSurface == PreviewSurface.HOME) {
                    finish()
                } else {
                    renderEayOne()
                }
            }
        })
        renderEayOne()
    }

    private fun renderEayOne() {
        previewSurface = PreviewSurface.HOME
        activeModuleKind = null
        moduleActionAcknowledged = false
        operationalKind = null
        operationalStepIndex = 0
        operationalQuantity = ""
        val missions = previewMissions()
        val completedFlowCount = completedOperationalKinds.size + if (countCompletedLines > 27) 1 else 0
        fieldUi.renderEayOne(
            navigation = EayOneNavigationModel(
                selected = selectedDestination,
                pendingSyncCount = 0,
                quarantined = false,
            ),
            header = FieldShellHeader(
                locationLabel = "Fulya · EAY One product preview",
                deviceLabel = "DEBUG · non-authoritative preview",
                runtimeSurface = FieldRuntimeSurface.EAY_ONE,
                syncState = FieldSyncVisualState.SYNCED,
                pendingCount = 0,
            ),
            missions = missions,
            summary = EayOneHomeSummaryUiState(
                title = "Bugünün operasyonu",
                supportingText = "Vardiya, saha görevleri ve kişisel çalışma yüzeyleri tek mobil akışta.",
                shiftLabel = "Vardiya",
                shiftValue = "14–23",
                missionLabel = "Görev",
                missionValue = "${missions.count { it.enabled }} açık",
                attentionLabel = "İnceleme",
                attentionValue = "1",
                progressCurrent = 4 + completedFlowCount,
                progressTotal = 9,
            ),
            onDestinationSelected = { destination ->
                selectedDestination = destination
                renderEayOne()
            },
            onMissionOpen = ::openMission,
            onDestinationAction = ::handleDestinationAction,
        )
    }

    private fun previewMissions(): List<FieldMissionCardModel> = listOf(
        previewCard(
            id = "preview-shift",
            title = "Vardiya / Workforce",
            subtitle = "14:00 → 23:00 · roster · trusted device · geofence",
            kind = FieldMissionVisualKind.SHIFT,
            priority = FieldMissionVisualPriority.HIGH,
            action = "Vardiya merkezini aç",
        ),
        previewCard(
            id = "real-terminal",
            title = "EAY Terminal",
            subtitle = "Managed device + SSO + gerçek server-authoritative görevler",
            kind = FieldMissionVisualKind.COUNT,
            priority = FieldMissionVisualPriority.URGENT,
            action = "Gerçek terminali aç",
        ),
        previewCard(
            id = "preview-count",
            title = "Golden Count",
            subtitle = "A-04-02 · blind count · recount-safe · duplicate-safe",
            kind = FieldMissionVisualKind.COUNT,
            priority = FieldMissionVisualPriority.HIGH,
            action = "Sayımı aç",
            progressCurrent = countCompletedLines,
            progressTotal = 210,
        ),
        operationalCard("preview-pick", "Picking", "PICK-2048 · source → SKU → quantity → container", FieldMissionVisualKind.PICK),
        operationalCard("preview-putaway", "Putaway", "PUT-981 · SKU → quantity → destination", FieldMissionVisualKind.PUTAWAY),
        operationalCard("preview-receiving", "Receiving", "RCV-441 · container → SKU → quantity → condition", FieldMissionVisualKind.RECEIVING),
        operationalCard("preview-transfer", "Transfer", "TRF-118 · source → SKU → quantity → destination", FieldMissionVisualKind.TRANSFER),
        previewCard(
            id = "preview-planogram",
            title = "Planogram Mobile",
            subtitle = "Raf doğrulama · görev · fotoğraf evidence · exception",
            kind = FieldMissionVisualKind.PLANOGRAM,
            priority = FieldMissionVisualPriority.NORMAL,
            action = "Planogram workspace",
            progressCurrent = 6,
            progressTotal = 12,
        ),
        previewCard(
            id = "preview-audit",
            title = "Audit",
            subtitle = "Checklist · evidence · privacy · escalation",
            kind = FieldMissionVisualKind.AUDIT,
            priority = FieldMissionVisualPriority.HIGH,
            action = "Audit workspace",
            progressCurrent = 3,
            progressTotal = 8,
        ),
        previewCard(
            id = "preview-academy",
            title = "Academy",
            subtitle = "Atanmış eğitim · checkpoint · quiz · ilerleme",
            kind = FieldMissionVisualKind.ACADEMY,
            priority = FieldMissionVisualPriority.LOW,
            action = "Öğrenme merkezini aç",
            progressCurrent = 2,
            progressTotal = 5,
        ),
        previewCard(
            id = "preview-jarvis",
            title = "Jarvis",
            subtitle = "Vardiya + görev + operasyon bağlamı · governed action boundary",
            kind = FieldMissionVisualKind.JARVIS,
            priority = FieldMissionVisualPriority.NORMAL,
            action = "Jarvis workspace",
        ),
    )

    private fun operationalCard(
        id: String,
        title: String,
        subtitle: String,
        kind: FieldMissionVisualKind,
    ): FieldMissionCardModel {
        val completed = kind in completedOperationalKinds
        return previewCard(
            id = id,
            title = title,
            subtitle = if (completed) "$subtitle · preview akışı tamamlandı" else subtitle,
            kind = kind,
            priority = if (completed) FieldMissionVisualPriority.LOW else FieldMissionVisualPriority.HIGH,
            action = if (completed) "Akışı tekrar aç" else "Görevi aç",
            progressCurrent = if (completed) 5 else null,
            progressTotal = if (completed) 5 else null,
        )
    }

    private fun previewCard(
        id: String,
        title: String,
        subtitle: String,
        kind: FieldMissionVisualKind,
        priority: FieldMissionVisualPriority,
        action: String,
        progressCurrent: Int? = null,
        progressTotal: Int? = null,
    ) = FieldMissionCardModel(
        missionId = id,
        title = title,
        subtitle = subtitle,
        kind = kind,
        priority = priority,
        progressCurrent = progressCurrent,
        progressTotal = progressTotal,
        primaryActionLabel = action,
        enabled = true,
    )

    private fun openMission(missionId: String) {
        when (missionId) {
            "real-terminal" -> startActivity(Intent(this, MainActivity::class.java))
            "preview-shift" -> renderModule(FieldMissionVisualKind.SHIFT)
            "preview-count" -> renderCountPreview()
            "preview-pick" -> renderOperationalPreview(FieldMissionVisualKind.PICK)
            "preview-putaway" -> renderOperationalPreview(FieldMissionVisualKind.PUTAWAY)
            "preview-receiving" -> renderOperationalPreview(FieldMissionVisualKind.RECEIVING)
            "preview-transfer" -> renderOperationalPreview(FieldMissionVisualKind.TRANSFER)
            "preview-planogram" -> renderModule(FieldMissionVisualKind.PLANOGRAM)
            "preview-audit" -> renderModule(FieldMissionVisualKind.AUDIT)
            "preview-academy" -> renderModule(FieldMissionVisualKind.ACADEMY)
            "preview-jarvis" -> renderModule(FieldMissionVisualKind.JARVIS)
        }
    }

    private fun handleDestinationAction(destination: EayOneDestination) {
        when (destination) {
            EayOneDestination.SCAN -> renderCountPreview()
            EayOneDestination.JARVIS -> renderModule(FieldMissionVisualKind.JARVIS)
            EayOneDestination.ME -> renderModule(FieldMissionVisualKind.SHIFT)
            EayOneDestination.TODAY,
            EayOneDestination.MISSIONS,
            -> Unit
        }
    }

    private fun renderCountPreview() {
        previewSurface = PreviewSurface.COUNT
        fieldUi.renderBlindCount(
            state = BlindCountUiState(
                missionId = "preview-count",
                locationLabel = "A-04-02 · Golden Count",
                stepLabel = "Ürün okundu · sistem stoğu gösterilmez",
                scannedItemLabel = "Coca-Cola Zero 1L",
                observedQuantityText = countQuantity,
                confirmedLines = countCompletedLines,
                totalLines = 210,
                syncState = FieldSyncVisualState.SYNCED,
            ),
            onQuantityChanged = { value ->
                countQuantity = value.filter { it.isDigit() }.take(6)
                renderCountPreview()
            },
            onConfirmQuantity = ::finishCountPreview,
            backActionLabel = "← EAY One",
            onBack = ::renderEayOne,
        )
    }

    private fun finishCountPreview() {
        if (countQuantity.isBlank()) return
        countCompletedLines = (countCompletedLines + 1).coerceAtMost(210)
        countQuantity = ""
        selectedDestination = EayOneDestination.TODAY
        renderEayOne()
    }

    private fun renderOperationalPreview(kind: FieldMissionVisualKind) {
        previewSurface = PreviewSurface.OPERATIONAL
        if (operationalKind != kind) {
            operationalKind = kind
            operationalStepIndex = 0
            operationalQuantity = ""
        }
        val steps = operationalSteps(kind)
        val step = steps[operationalStepIndex]
        val title = when (kind) {
            FieldMissionVisualKind.PICK -> "Picking"
            FieldMissionVisualKind.PUTAWAY -> "Putaway"
            FieldMissionVisualKind.RECEIVING -> "Receiving"
            FieldMissionVisualKind.TRANSFER -> "Transfer"
            else -> error("Unsupported operational preview kind: $kind")
        }
        fieldUi.renderOperationalMission(
            state = OperationalExecutionUiState(
                missionId = "preview-${kind.name.lowercase()}",
                kind = kind,
                title = title,
                referenceLabel = "${kind.name}-PREVIEW-001",
                stepKind = step,
                stepLabel = stepLabel(step),
                instruction = stepInstruction(step),
                progressCurrent = (operationalStepIndex + 1).coerceAtMost(steps.size),
                progressTotal = steps.size,
                quantityText = operationalQuantity,
                confirmationLabel = confirmationLabel(step),
                syncState = FieldSyncVisualState.SYNCED,
                primaryActionLabel = primaryLabel(step),
                primaryActionEnabled = true,
            ),
            onQuantityChanged = { value ->
                operationalQuantity = value.filter { it.isDigit() || it == '.' }.take(8)
                renderOperationalPreview(kind)
            },
            onPrimaryAction = {
                if (step == FieldOperationalStepKind.QUANTITY && operationalQuantity.isBlank()) return@renderOperationalMission
                if (operationalStepIndex == steps.lastIndex) {
                    completedOperationalKinds += kind
                    selectedDestination = EayOneDestination.MISSIONS
                    renderEayOne()
                } else {
                    operationalStepIndex += 1
                    operationalQuantity = ""
                    renderOperationalPreview(kind)
                }
            },
            backActionLabel = "← Görevler",
            onBack = {
                selectedDestination = EayOneDestination.MISSIONS
                renderEayOne()
            },
        )
    }

    private fun renderModule(kind: FieldMissionVisualKind, acknowledged: Boolean = false) {
        previewSurface = PreviewSurface.MODULE
        activeModuleKind = kind
        moduleActionAcknowledged = acknowledged
        val state = moduleState(kind, acknowledged)
        fieldUi.renderModuleDetail(
            state = state,
            onBack = ::renderEayOne,
            onPrimaryAction = { renderModule(kind, acknowledged = true) },
            onSecondaryAction = ::renderEayOne,
        )
    }

    private fun moduleState(kind: FieldMissionVisualKind, acknowledged: Boolean): EayModuleDetailUiState {
        val verifiedStatus = if (acknowledged) {
            "Preview aksiyonu doğrulandı · production mutation kapalı"
        } else {
            "DEBUG preview · read-only"
        }
        return when (kind) {
            FieldMissionVisualKind.SHIFT -> EayModuleDetailUiState(
                moduleId = "preview-workforce",
                kind = kind,
                eyebrow = "WORKFORCE",
                title = "Vardiya merkezi",
                summary = "Roster, check-in readiness, mola ve cihaz güveni tek mobil çalışma yüzeyinde.",
                health = if (acknowledged) EayModuleHealthVisual.READY else EayModuleHealthVisual.IN_PROGRESS,
                statusLabel = verifiedStatus,
                metrics = listOf(
                    metric("Vardiya", "14:00–23:00", "Atanmış"),
                    metric("Check-in", "Hazır", "Shift required"),
                    metric("Mola", "45 dk", "Planlı"),
                    metric("Cihaz", "Trusted", "Managed"),
                ),
                sections = listOf(
                    section("Kimlik ve cihaz", "Kurumsal oturum, tek cihaz ve managed-device trust birlikte değerlendirilir.", "Ready"),
                    section("Konum doğrulama", "Check-in sırasında geofence ve shift bağlamı server tarafında doğrulanır.", "Fail-closed"),
                    section("Vardiya kuralları", "Gece vardiyası, izin, resmi tatil, dinlenme ve günlük maksimum kuralları merkezi authority'de kalır."),
                ),
                syncState = FieldSyncVisualState.SYNCED,
                backActionLabel = "← EAY One",
                primaryActionLabel = "Check-in kontratını doğrula",
                secondaryActionLabel = "Ana ekrana dön",
            )
            FieldMissionVisualKind.PLANOGRAM -> EayModuleDetailUiState(
                moduleId = "preview-planogram",
                kind = kind,
                eyebrow = "PLANOGRAM",
                title = "Raf execution workspace",
                summary = "Atanmış raf görevi, doğrulama ve evidence capture mobilde aynı görev bağlamında ilerler.",
                health = if (acknowledged) EayModuleHealthVisual.READY else EayModuleHealthVisual.IN_PROGRESS,
                statusLabel = verifiedStatus,
                metrics = listOf(
                    metric("Görev", "12", "Bugün"),
                    metric("Tamamlanan", "6", "50%"),
                    metric("Evidence", "8", "Local queue"),
                    metric("Exception", "2", "Review"),
                ),
                sections = listOf(
                    section("Raf doğrulama", "Store DNA ve server-issued görev bağlamı korunarak ürün/raf kanıtı toplanır.", "Assigned"),
                    section("Vision evidence", "Fotoğraf kanıtı privacy/redaction politikasına göre işlenir; preview dosya yüklemez.", "Privacy"),
                    section("Offline saha", "Bağlantı kaybında evidence local durable queue'da kalır ve acceptance server ACK ile tamamlanır."),
                ),
                syncState = FieldSyncVisualState.SYNCED,
                backActionLabel = "← EAY One",
                primaryActionLabel = "Evidence kontratını doğrula",
                secondaryActionLabel = "Ana ekrana dön",
            )
            FieldMissionVisualKind.AUDIT -> EayModuleDetailUiState(
                moduleId = "preview-audit",
                kind = kind,
                eyebrow = "AUDIT",
                title = "Denetim workspace",
                summary = "Checklist, foto/video kanıtı, AI önerisi ve yönetici escalation tek denetim bağlamında.",
                health = if (acknowledged) EayModuleHealthVisual.READY else EayModuleHealthVisual.ATTENTION,
                statusLabel = verifiedStatus,
                metrics = listOf(
                    metric("Kontrol", "8", "3 tamamlandı"),
                    metric("Evidence", "4", "Privacy-safe"),
                    metric("AI review", "1", "Human decision"),
                    metric("Escalation", "1", "Manager"),
                ),
                sections = listOf(
                    section("Evidence privacy", "Kişi yüzleri ve hassas alanlar kanıt pipeline'ında policy-driven redaction'a tabidir.", "Mandatory"),
                    section("Karar ayrışması", "Denetçi AI önerisinden ayrılırsa karar gerekçesi korunur; yönetici onayı ve operasyon standardı review zinciri izlenebilir."),
                    section("Offline kanıt", "Kayıtlar durable queue ve replay-safe kimliklerle gönderilir; preview gerçek evidence üretmez."),
                ),
                syncState = FieldSyncVisualState.SYNCED,
                backActionLabel = "← EAY One",
                primaryActionLabel = "Audit güvenlik akışını doğrula",
                secondaryActionLabel = "Ana ekrana dön",
            )
            FieldMissionVisualKind.ACADEMY -> EayModuleDetailUiState(
                moduleId = "preview-academy",
                kind = kind,
                eyebrow = "ACADEMY",
                title = "Öğrenme merkezi",
                summary = "Atanmış eğitimler, video checkpoint'leri, quiz ve ilerleme mobil çalışma gününe bağlanır.",
                health = if (acknowledged) EayModuleHealthVisual.READY else EayModuleHealthVisual.IN_PROGRESS,
                statusLabel = verifiedStatus,
                metrics = listOf(
                    metric("Atanan", "5", "Bu hafta"),
                    metric("Tamamlanan", "2", "40%"),
                    metric("Quiz", "92%", "Son skor"),
                    metric("Süre", "38 dk", "Kalan"),
                ),
                sections = listOf(
                    section("Checkpoint", "Video içinde doğrulama soruları ve ilerleme checkpoint'leri server-issued eğitim bağlamını korur."),
                    section("İlerleme", "Tamamlama ve sınav sonucu merkezi öğrenme kaydına işlenir; preview sertifika üretmez."),
                    section("Mobil deneyim", "Vardiya ve görev ekranından öğrenmeye geçiş bağlam kaybetmeden yapılır."),
                ),
                syncState = FieldSyncVisualState.SYNCED,
                backActionLabel = "← EAY One",
                primaryActionLabel = "Öğrenme akışını doğrula",
                secondaryActionLabel = "Ana ekrana dön",
            )
            FieldMissionVisualKind.JARVIS -> EayModuleDetailUiState(
                moduleId = "preview-jarvis",
                kind = kind,
                eyebrow = "JARVIS",
                title = "Operasyon copilotu",
                summary = "Vardiya, görev, lokasyon ve sync bağlamını anlayan; aksiyonları policy ve audit sınırında tutan mobil yardımcı.",
                health = if (acknowledged) EayModuleHealthVisual.READY else EayModuleHealthVisual.IN_PROGRESS,
                statusLabel = verifiedStatus,
                metrics = listOf(
                    metric("Context", "4 kaynak", "Shift · mission · store · sync"),
                    metric("Risk", "Low", "Read-only preview"),
                    metric("Queue", "0", "Pending"),
                    metric("Audit", "On", "Governed"),
                ),
                sections = listOf(
                    section("Operasyon bağlamı", "Jarvis aktif görevleri ve saha durumunu açıklayabilir; mutation talebi ayrı policy kapısından geçer.", "Contextual"),
                    section("Fail-closed action", "Bu debug workspace gerçek aksiyon yürütmez ve üretim yetkisi oluşturamaz.", "Protected"),
                    section("Kaynaklı yanıt", "Kurumsal SOP, görev ve operasyon verisi bağlama göre ayrıştırılır; üretim iddiası evidence olmadan yükseltilmez."),
                ),
                syncState = FieldSyncVisualState.SYNCED,
                backActionLabel = "← EAY One",
                primaryActionLabel = "Governed action sınırını doğrula",
                secondaryActionLabel = "Ana ekrana dön",
            )
            else -> error("Unsupported module preview kind: $kind")
        }
    }

    private fun metric(label: String, value: String, supporting: String = "") =
        EayModuleMetricUiModel(label = label, value = value, supportingText = supporting)

    private fun section(title: String, body: String, status: String? = null) =
        EayModuleDetailSectionUiModel(title = title, body = body, statusLabel = status)

    private fun operationalSteps(kind: FieldMissionVisualKind): List<FieldOperationalStepKind> = when (kind) {
        FieldMissionVisualKind.PICK -> listOf(
            FieldOperationalStepKind.SOURCE_LOCATION,
            FieldOperationalStepKind.ITEM,
            FieldOperationalStepKind.QUANTITY,
            FieldOperationalStepKind.CONTAINER,
            FieldOperationalStepKind.COMPLETE,
        )
        FieldMissionVisualKind.PUTAWAY -> listOf(
            FieldOperationalStepKind.ITEM,
            FieldOperationalStepKind.QUANTITY,
            FieldOperationalStepKind.DESTINATION_LOCATION,
            FieldOperationalStepKind.COMPLETE,
        )
        FieldMissionVisualKind.RECEIVING -> listOf(
            FieldOperationalStepKind.CONTAINER,
            FieldOperationalStepKind.ITEM,
            FieldOperationalStepKind.QUANTITY,
            FieldOperationalStepKind.CONDITION,
            FieldOperationalStepKind.COMPLETE,
        )
        FieldMissionVisualKind.TRANSFER -> listOf(
            FieldOperationalStepKind.SOURCE_LOCATION,
            FieldOperationalStepKind.ITEM,
            FieldOperationalStepKind.QUANTITY,
            FieldOperationalStepKind.DESTINATION_LOCATION,
            FieldOperationalStepKind.COMPLETE,
        )
        else -> error("Unsupported operational preview kind: $kind")
    }

    private fun stepLabel(step: FieldOperationalStepKind): String = when (step) {
        FieldOperationalStepKind.SOURCE_LOCATION -> "Kaynak lokasyon"
        FieldOperationalStepKind.DESTINATION_LOCATION -> "Hedef lokasyon"
        FieldOperationalStepKind.ITEM -> "Ürün"
        FieldOperationalStepKind.QUANTITY -> "Adet"
        FieldOperationalStepKind.CONDITION -> "Ürün durumu"
        FieldOperationalStepKind.CONTAINER -> "Container / Palet"
        FieldOperationalStepKind.COMPLETE -> "Tamamlama"
    }

    private fun stepInstruction(step: FieldOperationalStepKind): String = when (step) {
        FieldOperationalStepKind.SOURCE_LOCATION -> "Kaynak lokasyonu okut · A-03-02"
        FieldOperationalStepKind.DESTINATION_LOCATION -> "Hedef lokasyonu okut · B-04-01"
        FieldOperationalStepKind.ITEM -> "Ürünü okut · SKU-10482"
        FieldOperationalStepKind.QUANTITY -> "Gerçek fiziksel adedi gir"
        FieldOperationalStepKind.CONDITION -> "Server-frozen condition listesinden seç · GOOD"
        FieldOperationalStepKind.CONTAINER -> "Container / paleti okut · C-1902"
        FieldOperationalStepKind.COMPLETE -> "Mission sonucunu tamamla"
    }

    private fun confirmationLabel(step: FieldOperationalStepKind): String? = when (step) {
        FieldOperationalStepKind.QUANTITY -> null
        FieldOperationalStepKind.CONDITION -> "Preview condition · GOOD"
        FieldOperationalStepKind.COMPLETE -> "DEBUG preview stok hareketi üretmez; real mode server reconciliation kullanır."
        else -> "Preview physical evidence · gerçek modda scanner gerekir"
    }

    private fun primaryLabel(step: FieldOperationalStepKind): String = when (step) {
        FieldOperationalStepKind.QUANTITY -> "Adedi onayla"
        FieldOperationalStepKind.COMPLETE -> "Görevi tamamla"
        else -> "Taramayı onayla"
    }

    private enum class PreviewSurface { HOME, COUNT, OPERATIONAL, MODULE }
}
