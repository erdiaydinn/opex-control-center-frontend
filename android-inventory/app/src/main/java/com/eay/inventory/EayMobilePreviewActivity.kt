package com.eay.inventory

import android.content.Intent
import android.os.Bundle
import android.widget.Toast
import androidx.appcompat.app.AlertDialog
import androidx.appcompat.app.AppCompatActivity
import com.eay.mobile.fieldui.runtime.EayTerminalRuntimeView
import com.eay.mobile.presentation.BlindCountUiState
import com.eay.mobile.presentation.EayOneDestination
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
 * managed EAY Terminal authority boundary. The preview exists so product/UX can be
 * reviewed on a normal Android phone without manufacturing tenant, device, shift or
 * inventory authority.
 */
class EayMobilePreviewActivity : AppCompatActivity() {
    private lateinit var fieldUi: EayTerminalRuntimeView
    private var selectedDestination = EayOneDestination.TODAY
    private var countQuantity = ""
    private var operationalQuantity = ""
    private var operationalKind: FieldMissionVisualKind? = null
    private var operationalStepIndex = 0

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        if (!BuildConfig.DEBUG) {
            startActivity(Intent(this, MainActivity::class.java))
            finish()
            return
        }
        fieldUi = EayTerminalRuntimeView(this)
        setContentView(fieldUi)
        renderEayOne()
    }

    private fun renderEayOne() {
        operationalKind = null
        operationalStepIndex = 0
        operationalQuantity = ""
        val missions = listOf(
            previewCard(
                id = "preview-shift",
                title = "Vardiya / Workforce",
                subtitle = "14:00 → 23:00 · roster + device trust + geofence",
                kind = FieldMissionVisualKind.SHIFT,
                priority = FieldMissionVisualPriority.HIGH,
                action = "Vardiyayı incele",
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
                subtitle = "A-04-02 · 27 / 210 · blind count",
                kind = FieldMissionVisualKind.COUNT,
                priority = FieldMissionVisualPriority.HIGH,
                action = "Akışı test et",
            ),
            previewCard(
                id = "preview-pick",
                title = "Picking",
                subtitle = "PICK-2048 · source → SKU → quantity → container",
                kind = FieldMissionVisualKind.PICK,
                priority = FieldMissionVisualPriority.HIGH,
                action = "Akışı test et",
            ),
            previewCard(
                id = "preview-putaway",
                title = "Putaway",
                subtitle = "PUT-981 · SKU → quantity → destination",
                kind = FieldMissionVisualKind.PUTAWAY,
                priority = FieldMissionVisualPriority.NORMAL,
                action = "Akışı test et",
            ),
            previewCard(
                id = "preview-receiving",
                title = "Receiving",
                subtitle = "RCV-441 · container → SKU → quantity → condition",
                kind = FieldMissionVisualKind.RECEIVING,
                priority = FieldMissionVisualPriority.HIGH,
                action = "Akışı test et",
            ),
            previewCard(
                id = "preview-transfer",
                title = "Transfer",
                subtitle = "TRF-118 · source → SKU → quantity → destination",
                kind = FieldMissionVisualKind.TRANSFER,
                priority = FieldMissionVisualPriority.NORMAL,
                action = "Akışı test et",
            ),
            previewCard(
                id = "preview-planogram",
                title = "Planogram",
                subtitle = "Raf doğrulama · fotoğraf · görev · vision evidence",
                kind = FieldMissionVisualKind.PLANOGRAM,
                priority = FieldMissionVisualPriority.NORMAL,
                action = "Mobil yüzeyi incele",
            ),
            previewCard(
                id = "preview-audit",
                title = "Audit",
                subtitle = "Checklist · foto/video evidence · yüz gizleme · escalation",
                kind = FieldMissionVisualKind.AUDIT,
                priority = FieldMissionVisualPriority.NORMAL,
                action = "Mobil yüzeyi incele",
            ),
            previewCard(
                id = "preview-academy",
                title = "Academy",
                subtitle = "Atanmış eğitim · checkpoint · quiz · ilerleme",
                kind = FieldMissionVisualKind.ACADEMY,
                priority = FieldMissionVisualPriority.LOW,
                action = "Mobil yüzeyi incele",
            ),
        )
        val header = FieldShellHeader(
            locationLabel = "EAY Mobile Preview · DEBUG",
            deviceLabel = "Non-authoritative product preview",
            runtimeSurface = FieldRuntimeSurface.EAY_ONE,
            syncState = FieldSyncVisualState.SYNCED,
            pendingCount = 0,
        )
        fieldUi.renderEayOne(
            navigation = EayOneNavigationModel(
                selected = selectedDestination,
                pendingSyncCount = 0,
                quarantined = false,
            ),
            header = header,
            missions = missions,
            onDestinationSelected = { destination ->
                selectedDestination = destination
                renderEayOne()
            },
            onMissionOpen = ::openMission,
            onDestinationAction = ::handleDestinationAction,
        )
    }

    private fun previewCard(
        id: String,
        title: String,
        subtitle: String,
        kind: FieldMissionVisualKind,
        priority: FieldMissionVisualPriority,
        action: String,
    ) = FieldMissionCardModel(
        missionId = id,
        title = title,
        subtitle = subtitle,
        kind = kind,
        priority = priority,
        primaryActionLabel = action,
        enabled = true,
    )

    private fun openMission(missionId: String) {
        when (missionId) {
            "real-terminal" -> startActivity(Intent(this, MainActivity::class.java))
            "preview-shift" -> showInfo(
                "Vardiya / Workforce",
                "Preview: aktif roster, trusted device, geofence ve kurumsal kimlik birlikte doğrulanır. " +
                    "Gerçek check-in yetkisi bu debug preview tarafından üretilemez.",
            )
            "preview-count" -> renderCountPreview()
            "preview-pick" -> renderOperationalPreview(FieldMissionVisualKind.PICK)
            "preview-putaway" -> renderOperationalPreview(FieldMissionVisualKind.PUTAWAY)
            "preview-receiving" -> renderOperationalPreview(FieldMissionVisualKind.RECEIVING)
            "preview-transfer" -> renderOperationalPreview(FieldMissionVisualKind.TRANSFER)
            "preview-planogram" -> showInfo(
                "Planogram Mobile",
                "Native görev, raf doğrulama ve fotoğraf-evidence yüzeyi. Bu debug ekran mutation yapmaz; " +
                    "production vision/planogram authority server tarafında kalır.",
            )
            "preview-audit" -> showInfo(
                "Audit Mobile",
                "Checklist + evidence capture + escalation tasarımı. Kişi yüzü/evidence privacy kuralları " +
                    "production authority katmanında uygulanır; preview hiçbir kanıt yüklemez.",
            )
            "preview-academy" -> showInfo(
                "Academy",
                "Atanmış öğrenme, checkpoint, quiz ve ilerleme yüzeyi. Bu preview medya veya sertifika " +
                    "authority'si üretmez.",
            )
        }
    }

    private fun handleDestinationAction(destination: EayOneDestination) {
        when (destination) {
            EayOneDestination.SCAN -> renderCountPreview()
            EayOneDestination.JARVIS -> showInfo(
                "Jarvis",
                "Context preview: aktif vardiya, görev, lokasyon ve sync durumu Jarvis bağlamına girebilir. " +
                    "Bu APK debug preview'da yapay veriyle aksiyon çalıştırmaz; gerçek agent mutation'ı policy + authorization + audit ister.",
            )
            EayOneDestination.ME -> showInfo(
                "Me",
                "Profil · vardiya · cihaz güveni · dil · bildirim · performans · eğitimler. " +
                    "Production kişisel verisi debug preview'a gömülmez.",
            )
            EayOneDestination.TODAY,
            EayOneDestination.MISSIONS,
            -> Unit
        }
    }

    private fun renderCountPreview() {
        countQuantity = ""
        fieldUi.renderBlindCount(
            state = BlindCountUiState(
                missionId = "preview-count",
                locationLabel = "A-04-02 · Golden Count",
                stepLabel = "Ürün okundu · gerçek stok gizli",
                scannedItemLabel = "Coca-Cola Zero 1L",
                observedQuantityText = countQuantity,
                confirmedLines = 27,
                totalLines = 210,
                syncState = FieldSyncVisualState.SYNCED,
            ),
            onQuantityChanged = { value ->
                countQuantity = value
                fieldUi.renderBlindCount(
                    state = BlindCountUiState(
                        missionId = "preview-count",
                        locationLabel = "A-04-02 · Golden Count",
                        stepLabel = "Ürün okundu · gerçek stok gizli",
                        scannedItemLabel = "Coca-Cola Zero 1L",
                        observedQuantityText = countQuantity,
                        confirmedLines = 27,
                        totalLines = 210,
                        syncState = FieldSyncVisualState.SYNCED,
                    ),
                    onQuantityChanged = { next ->
                        countQuantity = next
                        renderCountPreviewWithDraft()
                    },
                    onConfirmQuantity = ::finishCountPreview,
                )
            },
            onConfirmQuantity = ::finishCountPreview,
        )
    }

    private fun renderCountPreviewWithDraft() {
        fieldUi.renderBlindCount(
            state = BlindCountUiState(
                missionId = "preview-count",
                locationLabel = "A-04-02 · Golden Count",
                stepLabel = "Ürün okundu · gerçek stok gizli",
                scannedItemLabel = "Coca-Cola Zero 1L",
                observedQuantityText = countQuantity,
                confirmedLines = 27,
                totalLines = 210,
                syncState = FieldSyncVisualState.SYNCED,
            ),
            onQuantityChanged = { value ->
                countQuantity = value
                renderCountPreviewWithDraft()
            },
            onConfirmQuantity = ::finishCountPreview,
        )
    }

    private fun finishCountPreview() {
        if (countQuantity.isBlank()) return
        Toast.makeText(this, "Preview: 28 / 210 · durable event gerçek modda imzalanır", Toast.LENGTH_LONG).show()
        selectedDestination = EayOneDestination.TODAY
        renderEayOne()
    }

    private fun renderOperationalPreview(kind: FieldMissionVisualKind) {
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
                progressCurrent = operationalStepIndex,
                progressTotal = steps.size,
                quantityText = operationalQuantity,
                confirmationLabel = confirmationLabel(step),
                syncState = FieldSyncVisualState.SYNCED,
                primaryActionLabel = if (step == FieldOperationalStepKind.COMPLETE) "Tamamla" else "Preview · sonraki adım",
                primaryActionEnabled = true,
            ),
            onQuantityChanged = { value ->
                operationalQuantity = value
                renderOperationalPreview(kind)
            },
            onPrimaryAction = {
                if (step == FieldOperationalStepKind.QUANTITY && operationalQuantity.isBlank()) return@renderOperationalMission
                if (operationalStepIndex == steps.lastIndex) {
                    Toast.makeText(
                        this,
                        "Preview tamamlandı · gerçek modda event imzalı ve server-authoritative",
                        Toast.LENGTH_LONG,
                    ).show()
                    selectedDestination = EayOneDestination.MISSIONS
                    renderEayOne()
                } else {
                    operationalStepIndex += 1
                    operationalQuantity = ""
                    renderOperationalPreview(kind)
                }
            },
        )
    }

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
        FieldOperationalStepKind.CONDITION -> "Durum"
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
        FieldOperationalStepKind.CONDITION -> "Preview condition: GOOD"
        FieldOperationalStepKind.COMPLETE -> "Bu yalnız DEBUG preview; stok hareketi üretmez."
        else -> "Preview physical evidence · gerçek modda scanner gerekir"
    }

    private fun showInfo(title: String, message: String) {
        AlertDialog.Builder(this)
            .setTitle(title)
            .setMessage(message)
            .setPositiveButton("Tamam", null)
            .show()
    }
}
