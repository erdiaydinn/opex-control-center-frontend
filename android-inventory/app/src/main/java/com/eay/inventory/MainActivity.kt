package com.eay.inventory

import android.app.PendingIntent
import android.content.BroadcastReceiver
import android.content.Context
import android.content.Intent
import android.content.IntentFilter
import android.graphics.Color
import android.net.Uri
import android.os.Bundle
import android.view.View
import android.widget.Button
import android.widget.LinearLayout
import android.widget.TextView
import androidx.appcompat.app.AlertDialog
import androidx.appcompat.app.AppCompatActivity
import androidx.core.content.ContextCompat
import com.eay.mobile.core.BarcodeSymbology
import com.eay.mobile.core.BlindCountStep
import com.eay.mobile.core.MobileRuntimeProfile
import com.eay.mobile.core.OperationalCaptureCode
import com.eay.mobile.core.OperationalMissionType
import com.eay.mobile.core.OperationalStepKind
import com.eay.mobile.core.OperationalValueCanonicalizer
import com.eay.mobile.core.ScannerIngressGuard
import com.eay.mobile.core.ScannerPolicy
import com.eay.mobile.core.ScannerSource
import com.eay.mobile.fieldui.runtime.EayTerminalRuntimeView
import com.eay.mobile.presentation.FieldMissionVisualKind
import com.eay.mobile.presentation.FieldMissionVisualPriority
import com.eay.mobile.presentation.FieldOperationalStepKind
import com.eay.mobile.presentation.FieldRecoveryActionKind
import com.eay.mobile.presentation.FieldSessionRecoveryBannerModel
import com.eay.mobile.presentation.FieldSyncVisualState
import com.eay.mobile.presentation.OperationalExecutionUiState
import com.eay.mobile.presentation.adapter.BlindCountPresentationCopy
import com.eay.mobile.presentation.adapter.FieldPresentationAdapter
import com.eay.mobile.presentation.adapter.MissionIntentPresentation
import com.eay.mobile.presentation.adapter.SyncPresentationSummary
import java.time.Instant
import java.util.UUID
import kotlinx.coroutines.runBlocking
import net.openid.appauth.AuthorizationRequest
import net.openid.appauth.AuthorizationService
import net.openid.appauth.AuthorizationServiceConfiguration
import net.openid.appauth.ResponseTypeValues

/** Production terminal shell. Credentials and stock truth are never collected by the app UI. */
class MainActivity : AppCompatActivity() {
    private lateinit var status: TextView
    private lateinit var fieldUi: EayTerminalRuntimeView
    private lateinit var finishLocation: Button
    private val auth by lazy { AuthorizationService(this) }
    private val taskClient by lazy { InventoryTerminalTaskClient(this) }
    private val missionClaimClient by lazy { InventoryTerminalMissionClaimClient(this) }
    private val operationalTaskClient by lazy { InventoryOperationalTaskClient(this) }
    private val operationalClaimClient by lazy { InventoryOperationalClaimClient(this) }
    private val offlineQueue by lazy { InventoryOfflineQueue(InventoryDatabase.get(this)) }
    private var dataWedgeSession: DataWedge.Session? = null
    private var scannerReceiverRegistered = false
    private var loadedTasks: List<InventoryTerminalCountTask> = emptyList()
    private var loadedOperationalTasks: List<InventoryOperationalTask> = emptyList()
    private var localMissionTruth: Map<String, InventoryLocalCompletionState> = emptyMap()
    private var localOperationalTruth: Map<String, InventoryLocalCompletionState> = emptyMap()
    private var localRecoverySummary: InventoryRecoverySummary? = null
    private var sessionRecoveryBanner: FieldSessionRecoveryBannerModel? = null
    private var activeTask: InventoryTerminalCountTask? = null
    private var activeController: BlindCountTerminalController? = null
    private var activeOperationalTask: InventoryOperationalTask? = null
    private var activeOperationalController: InventoryOperationalController? = null
    private var taskSelectionEnabled = true
    private var quantityDraft = ""
    private var operationalQuantityDraft = ""

    private val scannerReceiver = object : BroadcastReceiver() {
        override fun onReceive(context: Context?, intent: Intent?) {
            val session = dataWedgeSession ?: return
            val scanIntent = intent ?: return
            val receivedAt = System.currentTimeMillis()
            val ingress = session.toScannerIngress(scanIntent, receivedAt) ?: return
            val admission = ScannerIngressGuard.evaluate(ingress, TERMINAL_SCAN_POLICY, receivedAt)
            if (!admission.accepted) {
                status.text = getString(R.string.terminal_scan_blocked, admission.code.name)
                return
            }
            val scan = admission.scan ?: return
            val countController = activeController
            if (countController != null) {
                val result = countController.onAcceptedScan(scan)
                if (result.accepted) {
                    renderStep(result.session.step)
                } else {
                    status.text = getString(R.string.terminal_scan_blocked, result.code.name)
                }
                return
            }
            val operationalController = activeOperationalController
            val step = operationalController?.nextStep()
            if (operationalController == null || step == null) {
                status.text = getString(R.string.terminal_no_mission)
                return
            }
            if (step !in OPERATIONAL_SCAN_STEPS) {
                status.text = getString(R.string.terminal_scan_blocked, "WRONG_STEP")
                return
            }
            captureOperationalStep(
                step = step,
                rawValue = scan.value,
                eventId = UUID.nameUUIDFromBytes(
                    "EAY-DW:${scan.sourceEventId}".toByteArray(Charsets.UTF_8),
                ).toString(),
                occurredAt = Instant.ofEpochMilli(scan.capturedAtEpochMs).toString(),
            )
        }
    }

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        status = TextView(this).apply {
            text = getString(R.string.terminal_device_checking)
            textSize = 18f
        }
        val signIn = Button(this).apply {
            text = getString(R.string.terminal_sign_in)
            minimumHeight = dp(56)
            setOnClickListener { startOidc() }
        }
        fieldUi = EayTerminalRuntimeView(this).apply { visibility = View.GONE }
        finishLocation = Button(this).apply {
            text = getString(R.string.terminal_finish_location)
            minimumHeight = dp(64)
            visibility = View.GONE
            setOnClickListener { showLocationCompletionConfirmation() }
        }
        val content = LinearLayout(this).apply {
            orientation = LinearLayout.VERTICAL
            setPadding(dp(20), dp(32), dp(20), dp(24))
            setBackgroundColor(Color.rgb(248, 250, 252))
            addView(
                TextView(this@MainActivity).apply {
                    text = getString(R.string.app_name)
                    textSize = 28f
                    setTextColor(Color.rgb(223, 16, 103))
                },
            )
            addView(status)
            addView(signIn)
            addView(
                fieldUi,
                LinearLayout.LayoutParams(
                    LinearLayout.LayoutParams.MATCH_PARENT,
                    0,
                    1f,
                ),
            )
            addView(finishLocation)
        }
        setContentView(content)
        runCatching {
            ManagedDeviceIdentity(this).requireDeviceId()
            DeviceRequestSigner.ensureKey()
            InventoryDatabase.get(this)
            startScannerSession()
            status.text = getString(R.string.terminal_device_ready)
        }.onFailure {
            status.text = getString(R.string.terminal_contract_blocked)
        }
        if (intent?.action == ACTION_OIDC_COMPLETE) consumeOidc(intent)
    }

    override fun onResume() {
        super.onResume()
        if (
            AccessTokenMemory.freshOrNull() != null &&
            (
                loadedTasks.isNotEmpty() ||
                    loadedOperationalTasks.isNotEmpty() ||
                    localRecoverySummary != null ||
                    sessionRecoveryBanner != null
                )
        ) {
            loadTerminalTasks()
        }
    }

    private fun startScannerSession() {
        check(!scannerReceiverRegistered) { "Scanner receiver already registered" }
        val session = DataWedge.startSession(this)
        dataWedgeSession = session
        val filter = IntentFilter(session.action).apply { addCategory(session.category) }
        ContextCompat.registerReceiver(
            this,
            scannerReceiver,
            filter,
            ContextCompat.RECEIVER_EXPORTED,
        )
        scannerReceiverRegistered = true
    }

    private fun startOidc() {
        if (!BuildConfig.OIDC_ISSUER.startsWith("https://") || BuildConfig.OIDC_CLIENT_ID == "unset") {
            status.text = getString(R.string.terminal_oidc_missing)
            return
        }
        AuthorizationServiceConfiguration.fetchFromIssuer(Uri.parse(BuildConfig.OIDC_ISSUER)) { config, error ->
            if (config == null) {
                runOnUiThread {
                    status.text = getString(
                        R.string.terminal_oidc_discovery_failed,
                        error?.errorDescription.orEmpty(),
                    )
                }
                return@fetchFromIssuer
            }
            val request = AuthorizationRequest.Builder(
                config,
                BuildConfig.OIDC_CLIENT_ID,
                ResponseTypeValues.CODE,
                Uri.parse("com.eay.inventory://oauth2redirect"),
            ).setScope("openid profile email offline_access inventory").build()
            val complete = PendingIntent.getActivity(
                this,
                1001,
                Intent(this, MainActivity::class.java).setAction(ACTION_OIDC_COMPLETE),
                PendingIntent.FLAG_UPDATE_CURRENT or PendingIntent.FLAG_MUTABLE,
            )
            val cancelled = PendingIntent.getActivity(
                this,
                1002,
                Intent(this, MainActivity::class.java).setAction(ACTION_OIDC_CANCELLED),
                PendingIntent.FLAG_UPDATE_CURRENT or PendingIntent.FLAG_IMMUTABLE,
            )
            auth.performAuthorizationRequest(request, complete, cancelled)
        }
    }

    override fun onNewIntent(intent: Intent) {
        super.onNewIntent(intent)
        setIntent(intent)
        if (intent.action == ACTION_OIDC_COMPLETE) {
            consumeOidc(intent)
        } else if (intent.action == ACTION_OIDC_CANCELLED) {
            status.text = getString(R.string.terminal_sign_in_cancelled)
        }
    }

    private fun consumeOidc(intent: Intent) {
        OidcSession(this).consumeAuthorizationResponse(intent) { result ->
            result.onSuccess {
                DeviceEnrollment.enroll(this) { enrolled ->
                    runOnUiThread {
                        enrolled.onSuccess {
                            status.text = getString(R.string.terminal_session_verified)
                            loadTerminalTasks()
                        }.onFailure {
                            status.text = getString(R.string.terminal_enrollment_failed)
                        }
                    }
                }
            }.onFailure {
                runOnUiThread { status.text = getString(R.string.terminal_sso_failed) }
            }
        }
    }

    private fun loadTerminalTasks() {
        status.text = getString(R.string.terminal_task_loading)
        fieldUi.clear()
        fieldUi.visibility = View.GONE
        loadedTasks = emptyList()
        loadedOperationalTasks = emptyList()
        localMissionTruth = emptyMap()
        localOperationalTruth = emptyMap()
        localRecoverySummary = null
        sessionRecoveryBanner = null
        clearActiveExecution()
        taskSelectionEnabled = true
        hideExecutionControls()
        Thread {
            val countResult = taskClient.fetch()
            val operationalResult = operationalTaskClient.fetch()
            val localProjectionResult = runCatching {
                runBlocking {
                    val unsettled = InventoryDatabase.get(this@MainActivity)
                        .events()
                        .unsettledBefore(Long.MAX_VALUE)
                    val countTruth = if (countResult.accepted) {
                        InventoryLocalMissionTruth.classify(countResult.tasks, unsettled)
                    } else {
                        emptyMap()
                    }
                    val operationalTruth = if (operationalResult.accepted) {
                        InventoryOperationalLocalTruth.classify(operationalResult.tasks, unsettled)
                    } else {
                        emptyMap()
                    }
                    Triple(
                        countTruth,
                        operationalTruth,
                        InventoryRecoveryContract.summarize(unsettled),
                    )
                }
            }
            runOnUiThread {
                val projection = localProjectionResult.getOrElse {
                    status.text = getString(R.string.terminal_contract_blocked)
                    return@runOnUiThread
                }
                localMissionTruth = projection.first
                localOperationalTruth = projection.second
                localRecoverySummary = projection.third
                val failure = when {
                    !countResult.accepted -> countResult.code
                    !operationalResult.accepted -> operationalResult.code
                    else -> null
                }
                if (failure != null) {
                    taskSelectionEnabled = false
                    sessionRecoveryBanner = InventoryTaskFetchRecoveryPresentation.banner(this, failure)
                    status.text = getString(R.string.terminal_task_fetch_failed, failure.name)
                } else {
                    sessionRecoveryBanner = null
                }
                renderTasks(
                    if (countResult.accepted) countResult.tasks else emptyList(),
                    if (operationalResult.accepted) operationalResult.tasks else emptyList(),
                )
            }
        }.start()
    }

    private fun renderTasks(
        countTasks: List<InventoryTerminalCountTask>,
        operationalTasks: List<InventoryOperationalTask>,
    ) {
        loadedTasks = countTasks
        loadedOperationalTasks = operationalTasks
        if (
            countTasks.isEmpty() &&
            operationalTasks.isEmpty() &&
            localRecoverySummary == null &&
            sessionRecoveryBanner == null
        ) {
            fieldUi.clear()
            fieldUi.visibility = View.GONE
            status.text = getString(R.string.terminal_no_tasks)
            return
        }
        if (sessionRecoveryBanner == null) {
            status.text = if (countTasks.isEmpty() && operationalTasks.isEmpty()) {
                getString(R.string.terminal_no_tasks)
            } else {
                getString(R.string.terminal_no_mission)
            }
        }
        renderMissionSurface()
    }

    private fun renderMissionSurface() {
        val recoverySummary = localRecoverySummary
        val recoveryPolicy = recoverySummary?.let(InventoryRecoveryPresentation::policy)
        val countStates = loadedTasks.map { task ->
            localMissionTruth[task.missionId] ?: InventoryLocalCompletionState.OPEN
        }
        val operationalStates = loadedOperationalTasks.map { task ->
            localOperationalTruth[task.missionId] ?: InventoryLocalCompletionState.OPEN
        }
        val allStates = countStates + operationalStates
        val syncState = when {
            (recoverySummary?.quarantinedEventCount ?: 0) > 0 -> FieldSyncVisualState.QUARANTINED
            (recoverySummary?.pendingEventCount ?: 0) > 0 -> FieldSyncVisualState.PENDING
            allStates.any { it == InventoryLocalCompletionState.REQUIRES_REVIEW } -> FieldSyncVisualState.QUARANTINED
            allStates.any { it == InventoryLocalCompletionState.AWAITING_SERVER } -> FieldSyncVisualState.PENDING
            else -> FieldSyncVisualState.SYNCED
        }
        val pendingCount = recoverySummary?.affectedEventCount
            ?: allStates.count { it != InventoryLocalCompletionState.OPEN }
        val warehouseLabel = (
            loadedTasks.map { it.warehouseId.trim() } +
                loadedOperationalTasks.map { it.warehouseId.trim() }
            )
            .filter { it.isNotBlank() }
            .distinct()
            .joinToString(" · ")
            .ifBlank { getString(R.string.terminal_no_tasks) }
        val header = FieldPresentationAdapter.shellHeader(
            locationLabel = warehouseLabel,
            deviceLabel = getString(com.eay.mobile.fieldui.R.string.eay_terminal_brand),
            runtimeProfile = MobileRuntimeProfile.EAY_TERMINAL,
            sync = SyncPresentationSummary(syncState, pendingCount),
        )
        val globallyBlocked = recoveryPolicy?.blocksNewMissionStarts == true || !taskSelectionEnabled
        val countCards = loadedTasks.map { task ->
            val localState = localMissionTruth[task.missionId] ?: InventoryLocalCompletionState.OPEN
            val subtitle = when (localState) {
                InventoryLocalCompletionState.OPEN -> task.locationId.trim()
                InventoryLocalCompletionState.AWAITING_SERVER -> getString(
                    R.string.terminal_task_pending_server,
                    task.name,
                    task.locationId.trim(),
                )
                InventoryLocalCompletionState.REQUIRES_REVIEW -> getString(
                    R.string.terminal_task_requires_review,
                    task.name,
                    task.locationId.trim(),
                )
            }
            val actionLabel = when (localState) {
                InventoryLocalCompletionState.OPEN -> getString(R.string.terminal_scan_location, task.locationId.trim())
                InventoryLocalCompletionState.AWAITING_SERVER -> getString(R.string.terminal_location_complete_queued)
                InventoryLocalCompletionState.REQUIRES_REVIEW -> getString(R.string.terminal_contract_blocked)
            }
            FieldPresentationAdapter.missionIntentCard(
                MissionIntentPresentation(
                    missionId = task.missionId,
                    title = task.name,
                    subtitle = subtitle,
                    kind = FieldMissionVisualKind.COUNT,
                    priority = FieldMissionVisualPriority.NORMAL,
                    primaryActionLabel = actionLabel,
                    enabled = !globallyBlocked && localState == InventoryLocalCompletionState.OPEN,
                ),
            )
        }
        val operationalCards = loadedOperationalTasks.map { task ->
            val localState = localOperationalTruth[task.missionId] ?: InventoryLocalCompletionState.OPEN
            val detail = buildOperationalReference(task)
            val subtitle = when (localState) {
                InventoryLocalCompletionState.OPEN -> detail
                InventoryLocalCompletionState.AWAITING_SERVER -> getString(
                    R.string.terminal_task_pending_server,
                    task.externalReference,
                    detail,
                )
                InventoryLocalCompletionState.REQUIRES_REVIEW -> getString(
                    R.string.terminal_task_requires_review,
                    task.externalReference,
                    detail,
                )
            }
            val actionLabel = when (localState) {
                InventoryLocalCompletionState.OPEN -> operationalStepPrompt(task.nextStep, task)
                InventoryLocalCompletionState.AWAITING_SERVER -> getString(R.string.terminal_location_complete_queued)
                InventoryLocalCompletionState.REQUIRES_REVIEW -> getString(R.string.terminal_contract_blocked)
            }
            FieldPresentationAdapter.missionIntentCard(
                MissionIntentPresentation(
                    missionId = task.missionId,
                    title = task.externalReference,
                    subtitle = subtitle,
                    kind = task.visualKind(),
                    priority = FieldMissionVisualPriority.NORMAL,
                    primaryActionLabel = actionLabel,
                    enabled = !globallyBlocked && localState == InventoryLocalCompletionState.OPEN,
                ),
            )
        }
        val recoveryBanner = recoverySummary?.let { InventoryRecoveryPresentation.banner(this, it) }
        fieldUi.visibility = View.VISIBLE
        fieldUi.renderTerminal(
            header = header,
            missions = countCards + operationalCards,
            recovery = recoveryBanner,
            sessionRecovery = sessionRecoveryBanner,
            onMissionOpen = missionOpen@{ missionId ->
                if (globallyBlocked) return@missionOpen
                loadedTasks.firstOrNull { it.missionId == missionId }?.let { task ->
                    if (localMissionTruth[missionId] != InventoryLocalCompletionState.AWAITING_SERVER &&
                        localMissionTruth[missionId] != InventoryLocalCompletionState.REQUIRES_REVIEW
                    ) {
                        selectTask(task)
                    }
                    return@missionOpen
                }
                loadedOperationalTasks.firstOrNull { it.missionId == missionId }?.let { task ->
                    if (localOperationalTruth[missionId] != InventoryLocalCompletionState.AWAITING_SERVER &&
                        localOperationalTruth[missionId] != InventoryLocalCompletionState.REQUIRES_REVIEW
                    ) {
                        selectOperationalTask(task)
                    }
                }
            },
            onRecoveryAction = { action -> handleRecoveryAction(action) },
        )
    }

    private fun handleRecoveryAction(action: FieldRecoveryActionKind) {
        when (action) {
            FieldRecoveryActionKind.NONE -> Unit
            FieldRecoveryActionKind.SIGN_IN_AGAIN -> {
                AccessTokenMemory.clear()
                startOidc()
            }
            FieldRecoveryActionKind.RELOAD_MISSIONS -> loadTerminalTasks()
        }
    }

    private fun selectTask(task: InventoryTerminalCountTask) {
        setTaskSelectionEnabled(false)
        hideExecutionControls()
        clearActiveExecution()
        status.text = getString(R.string.terminal_saving)
        Thread {
            val claim = missionClaimClient.claim(task)
            runOnUiThread {
                val claimedTask = claim.task
                if (!claim.accepted || claimedTask == null) {
                    val recovery = InventoryMissionExecutionRecoveryPresentation.claimBanner(this, claim.code)
                    if (recovery != null) recoverCurrentMission(recovery, claim.code.name) else blockCurrentMission()
                    return@runOnUiThread
                }
                val controller = runCatching {
                    BlindCountTerminalController(
                        target = claimedTask.blindCountTarget(),
                        eventContext = claimedTask.eventContext(),
                        leaseValidUntil = requireNotNull(claimedTask.leaseValidUntil),
                        eventSink = offlineQueue,
                    )
                }.getOrElse {
                    setTaskSelectionEnabled(true)
                    status.text = getString(R.string.terminal_contract_blocked)
                    return@runOnUiThread
                }
                loadedTasks = loadedTasks.map { current ->
                    if (current.missionId == claimedTask.missionId) claimedTask else current
                }
                activeTask = claimedTask
                activeController = controller
                renderStep(BlindCountStep.SCAN_LOCATION)
            }
        }.start()
    }

    private fun selectOperationalTask(task: InventoryOperationalTask) {
        setTaskSelectionEnabled(false)
        hideExecutionControls()
        clearActiveExecution()
        status.text = getString(R.string.terminal_operation_saving)
        Thread {
            val claimResult = operationalClaimClient.claim(task)
            runOnUiThread {
                val claim = claimResult.claim
                if (!claimResult.accepted || claim == null) {
                    val recovery = InventoryTaskFetchRecoveryPresentation.banner(this, claimResult.code)
                    if (recovery != null) recoverCurrentMission(recovery, claimResult.code.name) else blockCurrentMission()
                    return@runOnUiThread
                }
                val controller = runCatching {
                    InventoryOperationalController(task, claim, offlineQueue)
                }.getOrElse {
                    blockCurrentMission()
                    return@runOnUiThread
                }
                activeOperationalTask = task
                activeOperationalController = controller
                operationalQuantityDraft = ""
                renderOperationalStep()
            }
        }.start()
    }

    private fun renderStep(step: BlindCountStep) {
        val task = activeTask ?: return
        when (step) {
            BlindCountStep.SCAN_LOCATION -> {
                hideBlindCountSurface(clearDraft = true)
                hideExecutionControls()
                status.text = getString(R.string.terminal_scan_location, task.locationId.trim())
            }
            BlindCountStep.SCAN_ITEM -> {
                hideBlindCountSurface(clearDraft = true)
                finishLocation.visibility = View.VISIBLE
                finishLocation.isEnabled = true
                status.text = getString(R.string.terminal_scan_item)
            }
            BlindCountStep.ENTER_QUANTITY -> {
                finishLocation.visibility = View.GONE
                status.text = getString(R.string.terminal_enter_quantity)
                renderBlindCountQuantity()
            }
            BlindCountStep.CONFIRM_ITEM -> {
                finishLocation.visibility = View.GONE
                renderBlindCountQuantity()
            }
            BlindCountStep.COMPLETE -> {
                hideBlindCountSurface(clearDraft = true)
                hideExecutionControls()
                status.text = getString(R.string.terminal_complete)
            }
        }
    }

    private fun renderBlindCountQuantity() {
        val task = activeTask ?: return
        val controller = activeController ?: return
        val session = controller.session()
        if (session.step != BlindCountStep.ENTER_QUANTITY && session.step != BlindCountStep.CONFIRM_ITEM) return
        val state = FieldPresentationAdapter.blindCount(
            session = session,
            target = task.blindCountTarget(),
            copy = BlindCountPresentationCopy(
                locationLabel = task.locationId.trim(),
                stepLabel = getString(R.string.terminal_enter_quantity),
                scannedItemLabel = task.name,
                observedQuantityText = quantityDraft,
            ),
            syncState = currentSyncState(),
        )
        fieldUi.visibility = View.VISIBLE
        fieldUi.renderBlindCount(
            state = state,
            onQuantityChanged = { draft ->
                val normalized = draft.filter { it.isDigit() }.take(6)
                if (normalized != quantityDraft) {
                    quantityDraft = normalized
                    renderBlindCountQuantity()
                }
            },
            onConfirmQuantity = { submitObservedQuantity(quantityDraft) },
        )
    }

    private fun submitObservedQuantity(quantityText: String) {
        val controller = activeController ?: run {
            status.text = getString(R.string.terminal_no_mission)
            return
        }
        if (controller.session().step == BlindCountStep.ENTER_QUANTITY) {
            val quantity = quantityText.toIntOrNull()
            if (quantity == null) {
                status.text = getString(R.string.terminal_invalid_quantity)
                return
            }
            val entered = controller.enterQuantity(quantity)
            if (!entered.accepted) {
                status.text = getString(R.string.terminal_invalid_quantity)
                return
            }
        }
        if (controller.session().step != BlindCountStep.CONFIRM_ITEM) {
            status.text = getString(R.string.terminal_contract_blocked)
            return
        }
        fieldUi.clear()
        fieldUi.visibility = View.GONE
        status.text = getString(R.string.terminal_saving)
        Thread {
            val result = runCatching { runBlocking { controller.confirmItem() } }
            runOnUiThread {
                result.onSuccess { confirmation ->
                    when (confirmation.code) {
                        BlindCountControllerCode.OK -> {
                            quantityDraft = ""
                            finishLocation.visibility = View.VISIBLE
                            finishLocation.isEnabled = true
                            InventorySyncWorker.enqueue(this)
                            status.text = getString(R.string.terminal_saved_next)
                        }
                        BlindCountControllerCode.PERSIST_RETRY -> {
                            status.text = getString(R.string.terminal_persist_retry)
                            renderBlindCountQuantity()
                        }
                        BlindCountControllerCode.DENY_LEASE_EXPIRED -> recoverCurrentMission(
                            InventoryMissionExecutionRecoveryPresentation.leaseExpiredBanner(this),
                            "LEASE_EXPIRED",
                        )
                        else -> blockCurrentMission()
                    }
                }.onFailure { blockCurrentMission() }
            }
        }.start()
    }

    private fun renderOperationalStep() {
        val task = activeOperationalTask ?: return
        val controller = activeOperationalController ?: return
        val step = controller.nextStep() ?: run {
            finishOperationalLocally(task)
            return
        }
        val prompt = operationalStepPrompt(step, task)
        val isScannerStep = step in OPERATIONAL_SCAN_STEPS
        val quantityReady = step != OperationalStepKind.QUANTITY || operationalQuantityIsValid()
        val conditionReady = step != OperationalStepKind.CONDITION || task.allowedConditions.isNotEmpty()
        val state = OperationalExecutionUiState(
            missionId = task.missionId,
            kind = task.visualKind(),
            title = task.externalReference,
            referenceLabel = buildOperationalReference(task),
            stepKind = FieldOperationalStepKind.valueOf(step.name),
            stepLabel = prompt,
            instruction = prompt,
            progressCurrent = controller.progressCurrent(),
            progressTotal = task.totalSteps,
            quantityText = operationalQuantityDraft,
            confirmationLabel = operationalConfirmation(task, step),
            syncState = currentSyncState(),
            primaryActionLabel = when (step) {
                OperationalStepKind.QUANTITY -> getString(R.string.terminal_confirm_quantity)
                OperationalStepKind.CONDITION -> getString(R.string.terminal_select_condition)
                OperationalStepKind.COMPLETE -> getString(R.string.terminal_complete_operation)
                else -> prompt
            },
            primaryActionEnabled = !isScannerStep && quantityReady && conditionReady,
        )
        finishLocation.visibility = View.GONE
        fieldUi.visibility = View.VISIBLE
        fieldUi.renderOperationalMission(
            state = state,
            onQuantityChanged = { draft ->
                val normalized = normalizeOperationalQuantityDraft(draft)
                if (normalized != operationalQuantityDraft) {
                    operationalQuantityDraft = normalized
                    renderOperationalStep()
                }
            },
            onPrimaryAction = { handleOperationalPrimaryAction() },
        )
        status.text = prompt
    }

    private fun handleOperationalPrimaryAction() {
        val task = activeOperationalTask ?: return
        val step = activeOperationalController?.nextStep() ?: return
        when (step) {
            OperationalStepKind.QUANTITY -> {
                if (!operationalQuantityIsValid()) {
                    status.text = getString(R.string.terminal_invalid_quantity)
                    return
                }
                captureOperationalStep(step, operationalQuantityDraft)
            }
            OperationalStepKind.CONDITION -> showConditionSelection(task)
            OperationalStepKind.COMPLETE -> {
                AlertDialog.Builder(this)
                    .setTitle(R.string.terminal_complete_operation)
                    .setMessage(buildOperationalReference(task))
                    .setNegativeButton(R.string.terminal_cancel, null)
                    .setPositiveButton(R.string.terminal_confirm_operation) { _, _ ->
                        captureOperationalStep(OperationalStepKind.COMPLETE, "COMPLETE")
                    }
                    .show()
            }
            else -> status.text = getString(R.string.terminal_scan_blocked, "SCAN_REQUIRED")
        }
    }

    private fun showConditionSelection(task: InventoryOperationalTask) {
        if (task.allowedConditions.isEmpty()) {
            status.text = getString(R.string.terminal_contract_blocked)
            return
        }
        AlertDialog.Builder(this)
            .setTitle(R.string.terminal_select_condition)
            .setItems(task.allowedConditions.toTypedArray()) { _, which ->
                val selected = task.allowedConditions.getOrNull(which) ?: return@setItems
                captureOperationalStep(OperationalStepKind.CONDITION, selected)
            }
            .setNegativeButton(R.string.terminal_cancel, null)
            .show()
    }

    private fun captureOperationalStep(
        step: OperationalStepKind,
        rawValue: String,
        eventId: String = UUID.randomUUID().toString(),
        occurredAt: String = Instant.now().toString(),
    ) {
        val task = activeOperationalTask ?: return
        val controller = activeOperationalController ?: return
        if (controller.nextStep() != step) {
            status.text = getString(R.string.terminal_contract_blocked)
            return
        }
        status.text = getString(R.string.terminal_operation_saving)
        Thread {
            val blockedByLocalEvidence = runCatching {
                runBlocking {
                    val unsettled = InventoryDatabase.get(this@MainActivity)
                        .events()
                        .unsettledBefore(Long.MAX_VALUE)
                    InventoryOperationalLocalTruth.stateFor(task, unsettled) ==
                        InventoryLocalCompletionState.REQUIRES_REVIEW
                }
            }.getOrDefault(true)
            if (blockedByLocalEvidence) {
                runOnUiThread { blockCurrentMission() }
                return@Thread
            }
            val capture = runCatching {
                runBlocking { controller.capture(step, rawValue, eventId, occurredAt) }
            }
            runOnUiThread {
                capture.onSuccess { result ->
                    when (result.code) {
                        OperationalCaptureCode.ACCEPTED,
                        OperationalCaptureCode.EXACT_REPLAY,
                        -> {
                            operationalQuantityDraft = ""
                            recordLocalPendingEvidence()
                            InventorySyncWorker.enqueue(this)
                            if (result.completed) {
                                finishOperationalLocally(task)
                            } else {
                                status.text = getString(R.string.terminal_operation_saved)
                                renderOperationalStep()
                            }
                        }
                        else -> blockCurrentMission()
                    }
                }.onFailure { blockCurrentMission() }
            }
        }.start()
    }

    private fun finishOperationalLocally(task: InventoryOperationalTask) {
        activeOperationalTask = null
        activeOperationalController = null
        operationalQuantityDraft = ""
        taskSelectionEnabled = true
        localOperationalTruth = localOperationalTruth + (
            task.missionId to InventoryLocalCompletionState.AWAITING_SERVER
        )
        hideExecutionControls()
        renderTasks(loadedTasks, loadedOperationalTasks)
        status.text = getString(R.string.terminal_location_complete_queued)
    }

    private fun showLocationCompletionConfirmation() {
        val task = activeTask ?: return
        val controller = activeController ?: return
        if (controller.session().step != BlindCountStep.SCAN_ITEM) {
            status.text = getString(R.string.terminal_contract_blocked)
            return
        }
        AlertDialog.Builder(this)
            .setTitle(R.string.terminal_finish_location_title)
            .setMessage(
                getString(
                    R.string.terminal_finish_location_message,
                    task.locationId.trim(),
                    controller.session().confirmedLineCount,
                ),
            )
            .setNegativeButton(R.string.terminal_cancel, null)
            .setPositiveButton(R.string.terminal_finish_location_confirm) { _, _ ->
                completeLocationDurably(controller, task)
            }
            .show()
    }

    private fun completeLocationDurably(
        controller: BlindCountTerminalController,
        task: InventoryTerminalCountTask,
    ) {
        finishLocation.isEnabled = false
        status.text = getString(R.string.terminal_saving)
        Thread {
            val result = runCatching { runBlocking { controller.completeLocation() } }
            runOnUiThread {
                result.onSuccess { completion ->
                    when (completion.code) {
                        BlindCountControllerCode.OK -> {
                            InventorySyncWorker.enqueue(this)
                            activeTask = null
                            activeController = null
                            taskSelectionEnabled = true
                            quantityDraft = ""
                            hideExecutionControls()
                            localMissionTruth = localMissionTruth + (
                                task.missionId to InventoryLocalCompletionState.AWAITING_SERVER
                            )
                            recordLocalPendingEvidence()
                            renderTasks(loadedTasks, loadedOperationalTasks)
                            status.text = getString(R.string.terminal_location_complete_queued)
                        }
                        BlindCountControllerCode.PERSIST_RETRY -> {
                            finishLocation.isEnabled = true
                            status.text = getString(R.string.terminal_completion_retry)
                        }
                        BlindCountControllerCode.DENY_LEASE_EXPIRED -> recoverCurrentMission(
                            InventoryMissionExecutionRecoveryPresentation.leaseExpiredBanner(this),
                            "LEASE_EXPIRED",
                        )
                        else -> blockCurrentMission()
                    }
                }.onFailure { blockCurrentMission() }
            }
        }.start()
    }

    private fun recoverCurrentMission(
        recovery: FieldSessionRecoveryBannerModel,
        statusCode: String,
    ) {
        clearActiveExecution()
        taskSelectionEnabled = false
        sessionRecoveryBanner = recovery
        hideExecutionControls()
        renderTasks(loadedTasks, loadedOperationalTasks)
        status.text = getString(R.string.terminal_task_fetch_failed, statusCode)
    }

    private fun blockCurrentMission() {
        clearActiveExecution()
        taskSelectionEnabled = true
        hideExecutionControls()
        renderTasks(loadedTasks, loadedOperationalTasks)
        status.text = getString(R.string.terminal_contract_blocked)
    }

    private fun clearActiveExecution() {
        activeTask = null
        activeController = null
        activeOperationalTask = null
        activeOperationalController = null
        quantityDraft = ""
        operationalQuantityDraft = ""
    }

    private fun setTaskSelectionEnabled(enabled: Boolean) {
        taskSelectionEnabled = enabled
        if (
            (
                loadedTasks.isNotEmpty() ||
                    loadedOperationalTasks.isNotEmpty() ||
                    localRecoverySummary != null ||
                    sessionRecoveryBanner != null
                ) &&
            activeController == null &&
            activeOperationalController == null
        ) {
            renderMissionSurface()
        }
    }

    private fun recordLocalPendingEvidence() {
        val current = localRecoverySummary
        localRecoverySummary = if (current == null) {
            InventoryRecoverySummary(
                severity = InventoryRecoverySeverity.INFO,
                primaryIntent = InventoryRecoveryIntent.WAIT_FOR_AUTO_RETRY,
                affectedEventCount = 1,
                quarantinedEventCount = 0,
                pendingEventCount = 1,
            )
        } else {
            current.copy(
                affectedEventCount = current.affectedEventCount + 1,
                pendingEventCount = current.pendingEventCount + 1,
            )
        }
    }

    private fun currentSyncState(): FieldSyncVisualState = when {
        (localRecoverySummary?.quarantinedEventCount ?: 0) > 0 -> FieldSyncVisualState.QUARANTINED
        (localRecoverySummary?.pendingEventCount ?: 0) > 0 -> FieldSyncVisualState.PENDING
        else -> FieldSyncVisualState.SYNCED
    }

    private fun operationalStepPrompt(
        step: OperationalStepKind,
        task: InventoryOperationalTask,
    ): String = when (step) {
        OperationalStepKind.SOURCE_LOCATION -> getString(
            R.string.terminal_scan_location,
            task.sourceLocationId.orEmpty(),
        )
        OperationalStepKind.DESTINATION_LOCATION -> getString(
            R.string.terminal_scan_location,
            task.destinationLocationId.orEmpty(),
        )
        OperationalStepKind.ITEM -> getString(R.string.terminal_scan_item)
        OperationalStepKind.QUANTITY -> getString(R.string.terminal_enter_quantity)
        OperationalStepKind.CONDITION -> getString(R.string.terminal_select_condition)
        OperationalStepKind.CONTAINER -> getString(R.string.terminal_scan_container)
        OperationalStepKind.COMPLETE -> getString(R.string.terminal_complete_operation)
    }

    private fun operationalConfirmation(
        task: InventoryOperationalTask,
        step: OperationalStepKind,
    ): String? = when (step) {
        OperationalStepKind.SOURCE_LOCATION -> task.sourceLocationId
        OperationalStepKind.DESTINATION_LOCATION -> task.destinationLocationId
        OperationalStepKind.CONTAINER -> task.containerId
        OperationalStepKind.ITEM -> task.skuId
        OperationalStepKind.QUANTITY -> task.plannedQuantity
        OperationalStepKind.CONDITION -> task.allowedConditions.joinToString(" · ")
        OperationalStepKind.COMPLETE -> buildOperationalReference(task)
    }?.takeIf { it.isNotBlank() }

    private fun buildOperationalReference(task: InventoryOperationalTask): String = buildList {
        add(task.skuId.trim())
        add(task.plannedQuantity.trim())
        task.sourceLocationId?.trim()?.takeIf { it.isNotBlank() }?.let(::add)
        task.destinationLocationId?.trim()?.takeIf { it.isNotBlank() }?.let(::add)
        task.containerId?.trim()?.takeIf { it.isNotBlank() }?.let(::add)
    }.joinToString(" · ")

    private fun normalizeOperationalQuantityDraft(value: String): String {
        val normalized = value.trim().replace(',', '.')
        if (normalized.length > 12) return operationalQuantityDraft
        if (!normalized.matches(Regex("^\\d{0,7}(?:\\.\\d{0,3})?$"))) return operationalQuantityDraft
        return normalized
    }

    private fun operationalQuantityIsValid(): Boolean = runCatching {
        OperationalValueCanonicalizer.normalize(
            OperationalStepKind.QUANTITY,
            operationalQuantityDraft,
        )
    }.isSuccess

    private fun InventoryOperationalTask.visualKind(): FieldMissionVisualKind = when (missionType) {
        OperationalMissionType.PICKING -> FieldMissionVisualKind.PICK
        OperationalMissionType.PUTAWAY -> FieldMissionVisualKind.PUTAWAY
        OperationalMissionType.RECEIVING -> FieldMissionVisualKind.RECEIVING
        OperationalMissionType.TRANSFER -> FieldMissionVisualKind.TRANSFER
    }

    private fun hideBlindCountSurface(clearDraft: Boolean) {
        if (clearDraft) quantityDraft = ""
        fieldUi.clear()
        fieldUi.visibility = View.GONE
    }

    private fun hideExecutionControls() {
        finishLocation.visibility = View.GONE
        finishLocation.isEnabled = true
    }

    private fun dp(value: Int): Int = (value * resources.displayMetrics.density).toInt()

    override fun onDestroy() {
        if (scannerReceiverRegistered) {
            unregisterReceiver(scannerReceiver)
            scannerReceiverRegistered = false
        }
        dataWedgeSession = null
        auth.dispose()
        super.onDestroy()
    }

    companion object {
        private const val ACTION_OIDC_COMPLETE = "com.eay.inventory.OIDC_COMPLETE"
        private const val ACTION_OIDC_CANCELLED = "com.eay.inventory.OIDC_CANCELLED"
        private val OPERATIONAL_SCAN_STEPS = setOf(
            OperationalStepKind.SOURCE_LOCATION,
            OperationalStepKind.DESTINATION_LOCATION,
            OperationalStepKind.ITEM,
            OperationalStepKind.CONTAINER,
        )
        private val TERMINAL_SCAN_POLICY = ScannerPolicy(
            allowedSources = setOf(ScannerSource.HARDWARE_DATAWEDGE),
            allowedSymbologies = setOf(
                BarcodeSymbology.EAN8,
                BarcodeSymbology.EAN13,
                BarcodeSymbology.UPCA,
                BarcodeSymbology.CODE128,
                BarcodeSymbology.GS1_128,
                BarcodeSymbology.QR,
                BarcodeSymbology.DATAMATRIX,
            ),
        )
    }
}
