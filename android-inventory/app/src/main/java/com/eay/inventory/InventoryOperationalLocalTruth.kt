package com.eay.inventory

import com.eay.mobile.core.OperationalStepEvidence
import com.eay.mobile.core.OperationalStepKind
import com.eay.mobile.core.OperationalValueCanonicalizer
import org.json.JSONObject
import java.util.Locale
import java.util.UUID

/** Verified local prefix that may safely seed the reducer after a fresh server claim. */
data class InventoryOperationalResumeProjection(
    val state: InventoryLocalCompletionState,
    val evidence: List<OperationalStepEvidence> = emptyList(),
    val nextStep: OperationalStepKind? = null,
    val localClaimId: String? = null,
)

/**
 * Restart truth for operational missions.
 *
 * Mission discovery is allowed to present a resumable mission only when its durable
 * local evidence is a structurally valid contiguous prefix. Execution still performs
 * the stronger projection with the current auth binding and the freshly attested
 * server claim before any reducer state is restored.
 */
object InventoryOperationalLocalTruth {
    fun classify(
        tasks: List<InventoryOperationalTask>,
        unsettledEvents: Collection<OfflineEvent>,
    ): Map<String, InventoryLocalCompletionState> = tasks.associate { task ->
        task.missionId to candidateProjection(task, unsettledEvents).state
    }

    /**
     * Compatibility guard used by active execution. It deliberately does not advance
     * workflow state: any unsettled non-quarantined evidence is simply "awaiting".
     */
    fun stateFor(
        task: InventoryOperationalTask,
        unsettledEvents: Collection<OfflineEvent>,
    ): InventoryLocalCompletionState {
        val missionId = normalizeUuid(task.missionId) ?: return InventoryLocalCompletionState.REQUIRES_REVIEW
        val matches = unsettledEvents.filter { event ->
            event.state != "ACKED" && missionBinding(event.canonicalPayload) == missionId
        }
        if (matches.isEmpty()) return InventoryLocalCompletionState.OPEN
        if (matches.any { it.state == "QUARANTINED" }) {
            return InventoryLocalCompletionState.REQUIRES_REVIEW
        }
        if (matches.any { it.state !in setOf("PENDING", "RETRY_WAIT") }) {
            return InventoryLocalCompletionState.REQUIRES_REVIEW
        }
        return InventoryLocalCompletionState.AWAITING_SERVER
    }

    /**
     * Strong execution-time projection. A caller must provide the current encrypted
     * session binding and, after claim, the server-returned claim id.
     */
    fun project(
        task: InventoryOperationalTask,
        unsettledEvents: Collection<OfflineEvent>,
        currentAuthBindingId: String,
        expectedClaimId: String,
    ): InventoryOperationalResumeProjection = projectInternal(
        task = task,
        unsettledEvents = unsettledEvents,
        currentAuthBindingId = currentAuthBindingId,
        expectedClaimId = expectedClaimId,
        requireCurrentBinding = true,
    )

    fun missionBinding(canonicalPayload: String): String? = runCatching {
        if (!InventoryOperationalEventCanonical.isOperationalBody(canonicalPayload)) {
            return@runCatching null
        }
        UUID.fromString(JSONObject(canonicalPayload).getString("mission_id")).toString()
    }.getOrNull()

    private fun candidateProjection(
        task: InventoryOperationalTask,
        unsettledEvents: Collection<OfflineEvent>,
    ): InventoryOperationalResumeProjection = projectInternal(
        task = task,
        unsettledEvents = unsettledEvents,
        currentAuthBindingId = null,
        expectedClaimId = null,
        requireCurrentBinding = false,
    )

    private fun projectInternal(
        task: InventoryOperationalTask,
        unsettledEvents: Collection<OfflineEvent>,
        currentAuthBindingId: String?,
        expectedClaimId: String?,
        requireCurrentBinding: Boolean,
    ): InventoryOperationalResumeProjection {
        val missionId = normalizeUuid(task.missionId) ?: return review()
        val matches = unsettledEvents
            .filter { event -> event.state != "ACKED" && missionBinding(event.canonicalPayload) == missionId }
            .sortedBy { it.deviceSequence }

        if (matches.isEmpty()) {
            return InventoryOperationalResumeProjection(
                state = InventoryLocalCompletionState.OPEN,
                nextStep = task.nextStep,
            )
        }
        if (matches.any { it.state == "QUARANTINED" }) return review()
        if (matches.any { it.state !in setOf("PENDING", "RETRY_WAIT") }) return review()
        if (matches.zipWithNext().any { (left, right) -> left.deviceSequence >= right.deviceSequence }) {
            return review()
        }

        val localBindings = matches.map { it.authBindingId }.toSet()
        if (localBindings.size != 1 || localBindings.single().isBlank()) return review()
        if (requireCurrentBinding) {
            val binding = currentAuthBindingId?.takeIf { it.isNotBlank() } ?: return review()
            if (matches.any { InventoryQueueIntegrity.failureReason(it, binding) != null }) return review()
        } else if (matches.any { event ->
                runCatching {
                    InventoryOperationalEventCanonical.payloadHash(event.canonicalPayload) == event.payloadHash
                }.getOrDefault(false).not()
            }
        ) {
            return review()
        }

        val parsed = matches.map { event -> parseEvent(task, event) ?: return review() }
        val claimIds = parsed.map { it.claimId }.toSet()
        if (claimIds.size != 1) return review()
        val localClaimId = claimIds.single()
        val expectedClaim = expectedClaimId?.let(::normalizeUuid)
        if (expectedClaimId != null && expectedClaim == null) return review()
        if (expectedClaim != null && expectedClaim != localClaimId) return review()

        // Pending evidence attached to an OPEN/AVAILABLE projection belongs to an older
        // server view. Never execute it locally; let signed replay/recovery settle first.
        if (task.state != "CLAIMED" || task.claimStatus != "RESUMABLE") {
            return waiting(localClaimId)
        }

        val firstIndex = parsed.first().stepIndex
        if (firstIndex < task.completedSteps) {
            // The server has already advanced over at least one locally unsettled event.
            // Without server event ids in the read projection we cannot prove overlap,
            // so exact replay must settle before local execution continues.
            return waiting(localClaimId)
        }
        if (firstIndex > task.completedSteps) return review()

        parsed.forEachIndexed { offset, entry ->
            if (entry.stepIndex != task.completedSteps + offset) return review()
        }
        val advanced = task.completedSteps + parsed.size
        if (advanced > task.totalSteps) return review()
        if (advanced == task.totalSteps) return waiting(localClaimId)

        return InventoryOperationalResumeProjection(
            state = InventoryLocalCompletionState.OPEN,
            evidence = parsed.map { it.evidence },
            nextStep = task.steps[advanced],
            localClaimId = localClaimId,
        )
    }

    private data class ParsedEvent(
        val claimId: String,
        val stepIndex: Int,
        val evidence: OperationalStepEvidence,
    )

    private fun parseEvent(
        task: InventoryOperationalTask,
        event: OfflineEvent,
    ): ParsedEvent? = runCatching {
        val json = JSONObject(event.canonicalPayload)
        val missionId = UUID.fromString(json.getString("mission_id").trim()).toString()
        require(missionId == UUID.fromString(task.missionId).toString())
        val eventId = UUID.fromString(json.getString("event_id").trim()).toString()
        require(eventId == UUID.fromString(event.eventId).toString())
        require(json.getLong("device_sequence") == event.deviceSequence)
        require(event.deviceSequence > 0)
        require(json.getString("active_shift_id").trim() == task.activeShiftId)

        val claimId = UUID.fromString(json.getString("claim_id").trim()).toString()
        val step = OperationalStepKind.valueOf(
            json.getString("step_kind").trim().uppercase(Locale.ROOT),
        )
        val stepIndex = task.steps.indexOf(step)
        require(stepIndex >= 0)
        val rawValue = json.getString("value")
        val normalized = OperationalValueCanonicalizer.normalize(step, rawValue)
        val valueHash = json.getString("value_hash").trim().lowercase(Locale.ROOT)
        require(OperationalValueCanonicalizer.hash(step, rawValue) == valueHash)
        require(matchesFrozenIntent(task, step, normalized))

        ParsedEvent(
            claimId = claimId,
            stepIndex = stepIndex,
            evidence = OperationalStepEvidence(
                kind = step,
                valueHash = valueHash,
                eventId = eventId,
                deviceSequence = event.deviceSequence,
            ),
        )
    }.getOrNull()

    private fun matchesFrozenIntent(
        task: InventoryOperationalTask,
        step: OperationalStepKind,
        normalized: String,
    ): Boolean = when (step) {
        OperationalStepKind.SOURCE_LOCATION -> task.sourceLocationId?.let {
            OperationalValueCanonicalizer.normalize(step, it) == normalized
        } == true
        OperationalStepKind.DESTINATION_LOCATION -> task.destinationLocationId?.let {
            OperationalValueCanonicalizer.normalize(step, it) == normalized
        } == true
        OperationalStepKind.CONTAINER -> task.containerId?.let {
            OperationalValueCanonicalizer.normalize(step, it) == normalized
        } == true
        OperationalStepKind.CONDITION -> task.allowedConditions.any {
            OperationalValueCanonicalizer.normalize(step, it) == normalized
        }
        OperationalStepKind.COMPLETE -> normalized == "COMPLETE"
        OperationalStepKind.ITEM,
        OperationalStepKind.QUANTITY,
        -> true
    }

    private fun normalizeUuid(value: String): String? = runCatching {
        UUID.fromString(value.trim()).toString()
    }.getOrNull()

    private fun review(): InventoryOperationalResumeProjection = InventoryOperationalResumeProjection(
        state = InventoryLocalCompletionState.REQUIRES_REVIEW,
    )

    private fun waiting(localClaimId: String?): InventoryOperationalResumeProjection =
        InventoryOperationalResumeProjection(
            state = InventoryLocalCompletionState.AWAITING_SERVER,
            localClaimId = localClaimId,
        )
}
