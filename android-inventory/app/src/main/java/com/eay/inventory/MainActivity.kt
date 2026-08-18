package com.eay.inventory

import android.app.PendingIntent
import android.content.BroadcastReceiver
import android.content.Context
import android.content.Intent
import android.content.IntentFilter
import android.graphics.Color
import android.net.Uri
import android.os.Bundle
import android.text.InputType
import android.view.View
import android.widget.Button
import android.widget.EditText
import android.widget.LinearLayout
import android.widget.ScrollView
import android.widget.TextView
import androidx.appcompat.app.AppCompatActivity
import androidx.core.content.ContextCompat
import com.eay.mobile.core.BarcodeSymbology
import com.eay.mobile.core.BlindCountStep
import com.eay.mobile.core.ScannerIngressGuard
import com.eay.mobile.core.ScannerPolicy
import com.eay.mobile.core.ScannerSource
import kotlinx.coroutines.runBlocking
import net.openid.appauth.AuthorizationRequest
import net.openid.appauth.AuthorizationService
import net.openid.appauth.AuthorizationServiceConfiguration
import net.openid.appauth.ResponseTypeValues

/** Production terminal shell. Credentials and stock truth are never collected by the app UI. */
class MainActivity : AppCompatActivity() {
    private lateinit var status: TextView
    private lateinit var taskList: LinearLayout
    private lateinit var quantityInput: EditText
    private lateinit var confirmQuantity: Button
    private val auth by lazy { AuthorizationService(this) }
    private val taskClient by lazy { InventoryTerminalTaskClient(this) }
    private val offlineQueue by lazy { InventoryOfflineQueue(InventoryDatabase.get(this)) }
    private var dataWedgeSession: DataWedge.Session? = null
    private var scannerReceiverRegistered = false
    private var activeTask: InventoryTerminalCountTask? = null
    private var activeController: BlindCountTerminalController? = null

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
        taskList = LinearLayout(this).apply {
            orientation = LinearLayout.VERTICAL
        }
        quantityInput = EditText(this).apply {
            hint = getString(R.string.terminal_quantity_hint)
            inputType = InputType.TYPE_CLASS_NUMBER
            minimumHeight = dp(64)
            visibility = View.GONE
        }
        confirmQuantity = Button(this).apply {
            text = getString(R.string.terminal_confirm_quantity)
            minimumHeight = dp(64)
            visibility = View.GONE
            setOnClickListener { submitObservedQuantity() }
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
            addView(taskList)
            addView(quantityInput)
            addView(confirmQuantity)
        }
        setContentView(ScrollView(this).apply { addView(content) })

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
        taskList.removeAllViews()
        activeTask = null
        activeController = null
        hideQuantityEntry()
        Thread {
            val result = taskClient.fetch()
            runOnUiThread {
                if (!result.accepted) {
                    status.text = getString(R.string.terminal_task_fetch_failed, result.code.name)
                    return@runOnUiThread
                }
                renderTasks(result.tasks)
            }
        }.start()
    }

    private fun renderTasks(tasks: List<InventoryTerminalCountTask>) {
        taskList.removeAllViews()
        if (tasks.isEmpty()) {
            status.text = getString(R.string.terminal_no_tasks)
            return
        }
        status.text = getString(R.string.terminal_no_mission)
        tasks.forEach { task ->
            taskList.addView(
                Button(this).apply {
                    text = getString(R.string.terminal_task_label, task.name, task.locationId.trim())
                    minimumHeight = dp(56)
                    isAllCaps = false
                    setOnClickListener { selectTask(task) }
                },
            )
        }
    }

    private fun selectTask(task: InventoryTerminalCountTask) {
        activeTask = task
        activeController = BlindCountTerminalController(
            target = task.blindCountTarget(),
            eventContext = task.eventContext(),
            eventSink = offlineQueue,
        )
        hideQuantityEntry()
        renderStep(BlindCountStep.SCAN_LOCATION)
    }

    private fun renderStep(step: BlindCountStep) {
        val task = activeTask ?: return
        when (step) {
            BlindCountStep.SCAN_LOCATION -> {
                hideQuantityEntry()
                status.text = getString(R.string.terminal_scan_location, task.locationId.trim())
            }
            BlindCountStep.SCAN_ITEM -> {
                hideQuantityEntry()
                status.text = getString(R.string.terminal_scan_item)
            }
            BlindCountStep.ENTER_QUANTITY -> {
                quantityInput.visibility = View.VISIBLE
                confirmQuantity.visibility = View.VISIBLE
                confirmQuantity.isEnabled = true
                status.text = getString(R.string.terminal_enter_quantity)
                quantityInput.requestFocus()
            }
            BlindCountStep.CONFIRM_ITEM -> {
                quantityInput.visibility = View.VISIBLE
                confirmQuantity.visibility = View.VISIBLE
                status.text = getString(R.string.terminal_saving)
            }
            BlindCountStep.COMPLETE -> {
                hideQuantityEntry()
                status.text = getString(R.string.terminal_complete)
            }
        }
    }

    private fun submitObservedQuantity() {
        val controller = activeController ?: run {
            status.text = getString(R.string.terminal_no_mission)
            return
        }
        if (controller.session().step == BlindCountStep.ENTER_QUANTITY) {
            val quantity = quantityInput.text.toString().toIntOrNull()
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
        confirmQuantity.isEnabled = false
        status.text = getString(R.string.terminal_saving)
        Thread {
            val result = runCatching { runBlocking { controller.confirmItem() } }
            runOnUiThread {
                result.onSuccess { confirmation ->
                    when (confirmation.code) {
                        BlindCountControllerCode.OK -> {
                            quantityInput.text.clear()
                            hideQuantityEntry()
                            InventorySyncWorker.enqueue(this)
                            if (confirmation.session.step == BlindCountStep.COMPLETE) {
                                status.text = getString(R.string.terminal_complete)
                            } else {
                                status.text = getString(R.string.terminal_saved_next)
                            }
                        }
                        BlindCountControllerCode.PERSIST_RETRY -> {
                            confirmQuantity.isEnabled = true
                            status.text = getString(R.string.terminal_persist_retry)
                        }
                        else -> {
                            activeController = null
                            hideQuantityEntry()
                            status.text = getString(R.string.terminal_contract_blocked)
                        }
                    }
                }.onFailure {
                    activeController = null
                    hideQuantityEntry()
                    status.text = getString(R.string.terminal_contract_blocked)
                }
            }
        }.start()
    }

    private fun hideQuantityEntry() {
        quantityInput.visibility = View.GONE
        confirmQuantity.visibility = View.GONE
        confirmQuantity.isEnabled = true
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
