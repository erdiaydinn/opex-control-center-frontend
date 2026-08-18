package com.eay.inventory

import com.eay.mobile.core.AcceptedScan
import com.eay.mobile.core.BlindCountCode
import com.eay.mobile.core.BlindCountFlow
import com.eay.mobile.core.BlindCountSession
import com.eay.mobile.core.BlindCountStep
import com.eay.mobile.core.BlindCountTarget
import com.eay.mobile.core.BlindCountTransition
import java.time.OffsetDateTime
import java.time.ZoneOffset
import java.util.Locale
import java.util.UUID

fun interface ConfirmedCountEventSink {
    suspend fun enqueueConfirmedCount(
        context: InventoryCountEventContext,
        acceptedScan: AcceptedScan,
        evidence: com.eay.mobile.core.BlindCountLineEvidence,
        eventId: String,
        occurredAt: String,
    ): OfflineEvent
}

enum class BlindCountControllerCode {
    OK,
    DENY_FLOW,
    DENY_LOCATION_CONTEXT,
    DENY_PENDING_SCAN,
    PERSIST_RETRY,
}

data class BlindCountControllerResult(
    val code: BlindCountControllerCode,
    val session: BlindCountSession,
    val flowCode: BlindCountCode? = null,
    val durableEvent: OfflineEvent? = null,
) {
    val accepted: Boolean get() = code == BlindCountControllerCode.OK
}

/**
 * App-layer coordinator for the first real terminal vertical slice.
 *
 * Authority remains outside this controller: the mission/target must already come
 * from a server-authorized task, scans must already be admitted by ScannerIngressGuard,
 * and the sink is responsible for binding the mutation to the current verified OIDC
 * session. The controller advances BlindCountFlow only after the confirmed line is
 * durably inserted into the encrypted queue.
 */
class BlindCountTerminalController(
    private val target: BlindCountTarget,
    private val eventContext: InventoryCountEventContext,
    private val eventSink: ConfirmedCountEventSink,
    private val eventIdFactory: () -> String = { UUID.randomUUID().toString() },
    private val occurredAtFactory: () -> String = {
        OffsetDateTime.now(ZoneOffset.UTC).toString()
    },
) {
    private var state = BlindCountSession(missionId = target.missionId)
    private var pendingItemScan: AcceptedScan? = null
    private var pendingDurableIdentity: PendingDurableIdentity? = null

    init {
        require(eventContext.missionId == target.missionId) {
            "Event context and blind-count target must belong to the same mission"
        }
        require(eventContext.locationId.isNotBlank())
    }

    fun session(): BlindCountSession = state

    fun onAcceptedScan(scan: AcceptedScan): BlindCountControllerResult = when (state.step) {
        BlindCountStep.SCAN_LOCATION -> verifyLocation(scan)
        BlindCountStep.SCAN_ITEM -> scanItem(scan)
        else -> denied(BlindCountCode.DENY_STEP)
    }

    fun enterQuantity(quantity: Int): BlindCountControllerResult {
        val transition = BlindCountFlow.enterQuantity(state, quantity)
        return applyNonDurableTransition(transition)
    }

    suspend fun confirmItem(): BlindCountControllerResult {
        val currentScan = pendingItemScan
            ?: return BlindCountControllerResult(
                code = BlindCountControllerCode.DENY_PENDING_SCAN,
                session = state,
                flowCode = BlindCountCode.DENY_SCAN,
            )
        val confirmation = BlindCountFlow.confirmItem(state, target)
        if (!confirmation.accepted || confirmation.evidence == null) {
            return denied(confirmation.code)
        }

        val durableIdentity = pendingDurableIdentity ?: PendingDurableIdentity(
            eventId = eventIdFactory(),
            occurredAt = occurredAtFactory(),
        ).also { pendingDurableIdentity = it }

        val durableEvent = try {
            eventSink.enqueueConfirmedCount(
                context = eventContext,
                acceptedScan = currentScan,
                evidence = confirmation.evidence,
                eventId = durableIdentity.eventId,
                occurredAt = durableIdentity.occurredAt,
            )
        } catch (_: Exception) {
            // Do not advance or clear the scan. A retry uses the exact same event identity.
            return BlindCountControllerResult(
                code = BlindCountControllerCode.PERSIST_RETRY,
                session = state,
                flowCode = confirmation.code,
            )
        }

        state = confirmation.session
        pendingItemScan = null
        pendingDurableIdentity = null
        return BlindCountControllerResult(
            code = BlindCountControllerCode.OK,
            session = state,
            flowCode = confirmation.code,
            durableEvent = durableEvent,
        )
    }

    private fun verifyLocation(scan: AcceptedScan): BlindCountControllerResult {
        if (normalizeLocation(scan.value) != normalizeLocation(eventContext.locationId)) {
            return BlindCountControllerResult(
                code = BlindCountControllerCode.DENY_LOCATION_CONTEXT,
                session = state,
                flowCode = BlindCountCode.DENY_LOCATION,
            )
        }
        return applyNonDurableTransition(
            BlindCountFlow.verifyLocation(state, target, scan),
        )
    }

    private fun scanItem(scan: AcceptedScan): BlindCountControllerResult {
        val transition = BlindCountFlow.scanItem(state, scan)
        if (!transition.accepted) return denied(transition.code)
        state = transition.session
        pendingItemScan = scan
        pendingDurableIdentity = null
        return BlindCountControllerResult(
            code = BlindCountControllerCode.OK,
            session = state,
            flowCode = transition.code,
        )
    }

    private fun applyNonDurableTransition(
        transition: BlindCountTransition,
    ): BlindCountControllerResult {
        if (!transition.accepted) return denied(transition.code)
        state = transition.session
        return BlindCountControllerResult(
            code = BlindCountControllerCode.OK,
            session = state,
            flowCode = transition.code,
        )
    }

    private fun denied(code: BlindCountCode) = BlindCountControllerResult(
        code = BlindCountControllerCode.DENY_FLOW,
        session = state,
        flowCode = code,
    )

    private fun normalizeLocation(value: String): String =
        value.trim().uppercase(Locale.ROOT)

    private data class PendingDurableIdentity(
        val eventId: String,
        val occurredAt: String,
    )
}
