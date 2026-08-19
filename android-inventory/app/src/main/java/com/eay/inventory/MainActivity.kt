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
import com.eay.mobile.core.ScannerIngressGuard
import com.eay.mobile.core.ScannerPolicy
import com.eay.mobile.core.ScannerSource
import com.eay.mobile.fieldui.runtime.EayTerminalRuntimeView
import com.eay.mobile.presentation.FieldMissionVisualKind
import com.eay.mobile.presentation.FieldMissionVisualPriority
import com.eay.mobile.presentation.FieldRecoveryActionKind
import com.eay.mobile.presentation.FieldSessionRecoveryBannerModel
import com.eay.mobile.presentation.FieldSyncVisualState
import com.eay.mobile.presentation.adapter.BlindCountPresentationCopy
import com.eay.mobile.presentation.adapter.FieldPresentationAdapter
import com.eay.mobile.presentation.adapter.MissionIntentPresentation
import com.eay.mobile.presentation.adapter.SyncPresentationSummary
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
    private val offlineQueue by lazy { InventoryOfflineQueue(InventoryDatabase.get(this)) }
    private var dataWedgeSession: DataWedge.Session? = null
    private var scannerReceiverRegistered = false
    private var loadedTasks: List<InventoryTerminalCountTask> = emptyList()
    private var localMissionTruth: Map<String, InventoryLocalCompletionState> = emptyMap()
    private var localRecoverySummary: InventoryRecoverySummary? = null
    private var sessionRecoveryBanner: FieldSessionRecoveryBannerModel? = null
    private var activeTask: InventoryTerminalCountTask? = null
    private var activeController: BlindCountTerminalController? = null
    private var taskSelectionEnabled = true
    private var quantityDraft = ""

    private val scannerReceiver = object : BroadcastReceiver() {
        override fun onReceive(context: Context?, intent: Intent?) {
            val session = dataWedgeSession ?: return
            val scanIntent = intent ?: return
            val receivedAt = System.currentTimeMillis()
            val ingress = session.toScannerIngress(scanIntent, receivedAt) ?: return
            val admission = ScannerIngressGuard.evaluate(
                ingress,
                TERMINAL_SCAN_POLICY,
                receivedAt,
            )
            if (!admission.accepted) {
                status.text = getString(R.string.terminal_scan_blocked, admission.code.name)
                return
            }
            val scan = admission.scan ?: return
            val controller = activeController
            if (controller == null) {
                status.text = getString(R.string.terminal_no_mission)
                return
            }
            val result = controller.onAcceptedScan(scan)
            if (result.accepted) {
                renderStep(result.session.step)
            } else {
                status.text = getString(R.string.terminal_scan_blocked, result.code.name)
            }
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
        fieldUi = EayTerminalRuntimeView(this).apply {
            visibility = View.GONE
        }
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
            val managed = ManagedDeviceIdentity(this)
            managed.requireDeviceId()
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
        val filter = IntentFilter(session.action).apply {
            addCategory(session.category)
        }
        ContextCompat.registerReceiver(
            this,
            scannerReceiver,
            filter,
            ContextCompat.RECEIVER_EXPORTED,
        )
        scannerReceiverRegistered = true
    }

    private fun startOidc() {
        if (
            !BuildConfig.OIDC_ISSUER.startsWith("https://") ||
            BuildConfig.OIDC_CLIENT_ID == "unset"
        ) {
            status.text = getString(R.string.terminal_oidc_missing)
            return
        }
        AuthorizationServiceConfiguration.fetchFromIssuer(
            Uri.parse(BuildConfig.OIDC_ISSUER),
        ) { config, error ->
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
                runOnUiThread {
                    status.text = getString(R.string.terminal_sso_failed)
                }
            }
        }
    }

    private fun loadTerminalTasks() {
        status.text = getString(R.string.terminal_task_loading)
        fieldUi.clear()
        fieldUi.visibility = View.GONE
        loadedTasks = emptyList()
        localMissionTruth = emptyMap()
        localRecoverySummary = null
        sessionRecoveryBanner = null
        activeTask = null
        activeController = null
        taskSelectionEnabled = true
        quantityDraft = ""
        hideExecutionControls()
        Thread {
            val result = taskClient.fetch()
            val localProjectionResult = runCatching {
                runBlocking {
                    val unsettled = InventoryDatabase.get(this@MainActivity)
                        .events()
                        .unsettledBefore(Long.MAX_VALUE)
                    val missionTruth = if (result.accepted) {
                        InventoryLocalMissionTruth.classify(result.tasks, unsettled)
                    } else {
                        emptyMap()
                    }
                    missionTruth to InventoryRecoveryContract.summarize(unsettled)
                }
            }
            runOnUiThread {
                val projection = localProjectionResult.getOrElse {
                    status.text = getString(R.string.terminal_contract_blocked)
                    return@runOnUiThread
                }
                localMissionTruth = projection.first
                localRecoverySummary = projection.second
                if (!result.accepted) {
                    sessionRecoveryBanner = InventoryTaskFetchRecoveryPresentation.banner(
                        this,
                        result.code,
                    )
                    status.text = getString(R.string.terminal_task_fetch_failed, result.code.name)
                    renderTasks(emptyList())
                    return@runOnUiThread
                }
                sessionRecoveryBanner = null
                renderTasks(result.tasks)
            }
        }.start()
    }

    private fun renderTasks(tasks: List<InventoryTerminalCountTask>) {
        loadedTasks = tasks
        if (
            tasks.isEmpty() &&
            localRecoverySummary == null &&
            sessionRecoveryBanner == null
        ) {
            fieldUi.clear()
            fieldUi.visibility = View.GONE
            status.text = getString(R.string.terminal_no_tasks)
            return
        }
        status.text = if (tasks.isEmpty()) {
            getString(R.string.terminal_no_tasks)
        } else {
            getString(R.string.terminal_no_mission)
        }
        renderMissionSurface()
    }

    private fun renderMissionSurface() {
        val recoverySummary = localRecoverySummary
        val recoveryPolicy = recoverySummary?.let(InventoryRecoveryPresentation::policy)
        val localStates = loadedTasks.map { task ->
            localMissionTruth[task.missionId] ?: InventoryLocalCompletionState.OPEN
        }
        val syncState = when {
            (recoverySummary?.quarantinedEventCount ?: 0) > 0 -> {
                FieldSyncVisualState.QUARANTINED
            }
            (recoverySummary?.pendingEventCount ?: 0) > 0 -> {
                FieldSyncVisualState.PENDING
            }
            localStates.any { it == InventoryLocalCompletionState.REQUIRES_REVIEW } -> {
                FieldSyncVisualState.QUARANTINED
            }
            localStates.any { it == InventoryLocalCompletionState.AWAITING_SERVER } -> {
                FieldSyncVisualState.PENDING
            }
            else -> FieldSyncVisualState.SYNCED
        }
        val pendingCount = recoverySummary?.affectedEventCount
            ?: localStates.count { it != InventoryLocalCompletionState.OPEN }
        val warehouseLabel = loadedTasks
            .map { it.warehouseId.trim() }
            .filter { it.isNotBlank() }
            .distinct()
            .joinToString(" · ")
            .ifBlank { getString(R.string.terminal_no_tasks) }
        val header = FieldPresentationAdapter.shellHeader(
            locationLabel = warehouseLabel,
            deviceLabel = getString(com.eay.mobile.fieldui.R.string.eay_terminal_brand),
            runtimeProfile = MobileRuntimeProfile.EAY_TERMINAL,
            sync = SyncPresentationSummary(
                state = syncState,
                pendingCount = pendingCount,
            ),
        )
        val globallyBlocked = recoveryPolicy?.blocksNewMissionStarts == true
        val missions = loadedTasks.map { task ->
            val localState = localMissionTruth[task.missionId]
                ?: InventoryLocalCompletionState.OPEN
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
                InventoryLocalCompletionState.OPEN -> getString(
                    R.string.terminal_scan_location,
                    task.locationId.trim(),
                )
                InventoryLocalCompletionState.AWAITING_SERVER -> getString(
                    R.string.terminal_location_complete_queued,
                )
                InventoryLocalCompletionState.REQUIRES_REVIEW -> getString(
                    R.string.terminal_contract_blocked,
                )
            }
            FieldPresentationAdapter.missionIntentCard(
                MissionIntentPresentation(
                    missionId = task.missionId,
                    title = task.name,
                    subtitle = subtitle,
                    kind = FieldMissionVisualKind.COUNT,
                    priority = FieldMissionVisualPriority.NORMAL,
                    primaryActionLabel = actionLabel,
                    enabled = taskSelectionEnabled &&
                        !globallyBlocked &&
                        localState == InventoryLocalCompletionState.OPEN,
                ),
            )
        }
        val recoveryBanner = recoverySummary?.let {
            InventoryRecoveryPresentation.banner(this, it)
        }

        fieldUi.visibility = View.VISIBLE
        fieldUi.renderTerminal(
            header = header,
            missions = missions,
            recovery = recoveryBanner,
            sessionRecovery = sessionRecoveryBanner,
            onMissionOpen = missionOpen@{ missionId ->
                if (!taskSelectionEnabled || globallyBlocked) return@missionOpen
                val task = loadedTasks.firstOrNull { it.missionId == missionId }
                    ?: return@missionOpen
                val localState = localMissionTruth[missionId]
                    ?: InventoryLocalCompletionState.OPEN
                if (localState == InventoryLocalCompletionState.OPEN) {
                    selectTask(task)
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
        activeTask = null
        activeController = null
        quantityDraft = ""
        status.text = getString(R.string.terminal_saving)
        Thread {
            val claim = missionClaimClient.claim(task)
            runOnUiThread {
                val claimedTask = claim.task
                if (!claim.accepted || claimedTask == null) {
                    val recovery = InventoryMissionExecutionRecoveryPresentation.claimBanner(
                        this,
                        claim.code,
                    )
                    if (recovery != null) {
                        recoverCurrentMission(recovery, claim.code.name)
                    } else {
                        blockCurrentMission()
                    }
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
        if (
            session.step != BlindCountStep.ENTER_QUANTITY &&
            session.step != BlindCountStep.CONFIRM_ITEM
        ) {
            return
        }
        val state = FieldPresentationAdapter.blindCount(
            session = session,
            target = task.blindCountTarget(),
            copy = BlindCountPresentationCopy(
                locationLabel = task.locationId.trim(),
                stepLabel = getString(R.string.terminal_enter_quantity),
                scannedItemLabel = task.name,
                observedQuantityText = quantityDraft,
            ),
            syncState = FieldSyncVisualState.SYNCED,
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
            onConfirmQuantity = {
                submitObservedQuantity(quantityDraft)
            },
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
                        BlindCountControllerCode.DENY_LEASE_EXPIRED -> {
                            recoverCurrentMission(
                                InventoryMissionExecutionRecoveryPresentation.leaseExpiredBanner(this),
                                "LEASE_EXPIRED",
                            )
                        }
                        else -> blockCurrentMission()
                    }
                }.onFailure {
                    blockCurrentMission()
                }
            }
        }.start()
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
                            val currentRecovery = localRecoverySummary
                            localRecoverySummary = if (currentRecovery == null) {
                                InventoryRecoverySummary(
                                    severity = InventoryRecoverySeverity.INFO,
                                    primaryIntent = InventoryRecoveryIntent.WAIT_FOR_AUTO_RETRY,
                                    affectedEventCount = 1,
                                    quarantinedEventCount = 0,
                                    pendingEventCount = 1,
                                )
                            } else {
                                currentRecovery.copy(
                                    affectedEventCount = currentRecovery.affectedEventCount + 1,
                                    pendingEventCount = currentRecovery.pendingEventCount + 1,
                                )
                            }
                            renderTasks(loadedTasks)
                            status.text = getString(R.string.terminal_location_complete_queued)
                        }
                        BlindCountControllerCode.PERSIST_RETRY -> {
                            finishLocation.isEnabled = true
                            status.text = getString(R.string.terminal_completion_retry)
                        }
                        BlindCountControllerCode.DENY_LEASE_EXPIRED -> {
                            recoverCurrentMission(
                                InventoryMissionExecutionRecoveryPresentation.leaseExpiredBanner(this),
                                "LEASE_EXPIRED",
                            )
                        }
                        else -> blockCurrentMission()
                    }
                }.onFailure {
                    blockCurrentMission()
                }
            }
        }.start()
    }

    private fun recoverCurrentMission(
        recovery: FieldSessionRecoveryBannerModel,
        statusCode: String,
    ) {
        activeTask = null
        activeController = null
        taskSelectionEnabled = false
        quantityDraft = ""
        sessionRecoveryBanner = recovery
        hideExecutionControls()
        renderTasks(loadedTasks)
        status.text = getString(R.string.terminal_task_fetch_failed, statusCode)
    }

    private fun blockCurrentMission() {
        activeTask = null
        activeController = null
        taskSelectionEnabled = true
        quantityDraft = ""
        hideExecutionControls()
        renderTasks(loadedTasks)
        status.text = getString(R.string.terminal_contract_blocked)
    }

    private fun setTaskSelectionEnabled(enabled: Boolean) {
        taskSelectionEnabled = enabled
        if (
            (
                loadedTasks.isNotEmpty() ||
                    localRecoverySummary != null ||
                    sessionRecoveryBanner != null
                ) &&
            activeController == null
        ) {
            renderMissionSurface()
        }
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
