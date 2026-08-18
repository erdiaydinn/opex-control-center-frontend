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

interface BlindCountEventSink {
    suspend fun enqueueConfirmedCount(
        context: InventoryCountEventContext,
        acceptedScan: AcceptedScan,
        evidence: com.eay.mobile.core.BlindCountLineEvidence,
        eventId: String,
        occurredAt: String,
    ): OfflineEvent

    suspend fun enqueueLocationCompletion(
        context: InventoryCountEventContext,
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
 * and the sink is responsible for binding mutations to the current verified OIDC
 * session. State advances only after the relevant immutable event is durably inserted
 * into the encrypted queue.
 */
class BlindCountTerminalController(
    private val target: BlindCountTarget,
    private val eventContext: InventoryCountEventContext,
    private val eventSink: BlindCountEventSink,
    private val eventIdFactory: () -> String = { UUID.randomUUID().toString() },
    private val occurredAtFactory: () -> String = {
        OffsetDateTime.now(ZoneOffset.UTC).toString()
    },
) {
    private var state = BlindCountSession(missionId = target.missionId)
    private var pendingItemScan: AcceptedScan? = null
    private var pendingLineIdentity: PendingDurableIdentity? = null
    private var pendingCompletionIdentity: PendingDurableIdentity? = null

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
        if (!confirmation.accepted) {
            return denied(confirmation.code)
        }
        val evidence = confirmation.evidence ?: return denied(BlindCountCode.DENY_STEP)

        val durableIdentity = pendingLineIdentity ?: newDurableIdentity().also {
            pendingLineIdentity = it
        }
        val durableEvent = try {
            eventSink.enqueueConfirmedCount(
                context = eventContext,
                acceptedScan = currentScan,
                evidence = evidence,
                eventId = durableIdentity.eventId,
                occurredAt = durableIdentity.occurredAt,
            )
        } catch (_: RetryableCountPersistenceException) {
            return persistenceRetry(confirmation.code)
        }

        state = confirmation.session
        pendingItemScan = null
        pendingLineIdentity = null
        pendingCompletionIdentity = null
        return BlindCountControllerResult(
            code = BlindCountControllerCode.OK,
            session = state,
            flowCode = confirmation.code,
            durableEvent = durableEvent,
        )
    }

    suspend fun completeLocation(): BlindCountControllerResult {
        val completion = BlindCountFlow.completeLocation(state, target)
        if (!completion.accepted) return denied(completion.code)

        val durableIdentity = pendingCompletionIdentity ?: newDurableIdentity().also {
            pendingCompletionIdentity = it
        }
        val durableEvent = try {
            eventSink.enqueueLocationCompletion(
                context = eventContext,
                eventId = durableIdentity.eventId,
                occurredAt = durableIdentity.occurredAt,
            )
        } catch (_: RetryableCountPersistenceException) {
            return persistenceRetry(completion.code)
        }

        state = completion.session
        pendingCompletionIdentity = null
        return BlindCountControllerResult(
            code = BlindCountControllerCode.OK,
            session = state,
            flowCode = completion.code,
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
        pendingLineIdentity = null
        pendingCompletionIdentity = null
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

    private fun persistenceRetry(flowCode: BlindCountCode) = BlindCountControllerResult(
        code = BlindCountControllerCode.PERSIST_RETRY,
        session = state,
        flowCode = flowCode,
    )

    private fun denied(code: BlindCountCode) = BlindCountControllerResult(
        code = BlindCountControllerCode.DENY_FLOW,
        session = state,
        flowCode = code,
    )

    private fun normalizeLocation(value: String): String =
        value.trim().uppercase(Locale.ROOT)

    private fun newDurableIdentity() = PendingDurableIdentity(
        eventId = eventIdFactory(),
        occurredAt = occurredAtFactory(),
    )

    private data class PendingDurableIdentity(
        val eventId: String,
        val occurredAt: String,
    )
}
