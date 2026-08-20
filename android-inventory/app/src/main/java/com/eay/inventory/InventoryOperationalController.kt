package com.eay.inventory

import com.eay.mobile.core.OperationalCaptureCode
import com.eay.mobile.core.OperationalMissionDefinition
import com.eay.mobile.core.OperationalMissionReducer
import com.eay.mobile.core.OperationalMissionSession
import com.eay.mobile.core.OperationalStepEvidence
import com.eay.mobile.core.OperationalStepKind
import com.eay.mobile.core.OperationalValueCanonicalizer
import java.time.Instant
import java.util.UUID
import kotlinx.coroutines.sync.Mutex
import kotlinx.coroutines.sync.withLock

data class InventoryOperationalCaptureResult(
    val code: OperationalCaptureCode,
    val nextStep: OperationalStepKind?,
    val progressCurrent: Int,
    val completed: Boolean,
)

class InventoryOperationalController(
    private val task: InventoryOperationalTask,
    private val claim: InventoryOperationalClaim,
    private val queue: InventoryOfflineQueue,
) {
    private val progressOffset = task.completedSteps
    private val captureMutex = Mutex()
    private var session = OperationalMissionSession(
        definition = OperationalMissionDefinition(
            missionId = task.missionId,
            type = task.missionType,
            operation = task.operation,
            steps = task.steps.drop(task.completedSteps),
        ),
    )

    init {
        require(claim.missionId == task.missionId)
        require(claim.activeShiftId == task.activeShiftId)
        require(session.nextStep == task.nextStep)
    }

    fun nextStep(): OperationalStepKind? = session.nextStep

    fun progressCurrent(): Int = progressOffset + session.evidence.size

    suspend fun capture(
        step: OperationalStepKind,
        rawValue: String,
        eventId: String = UUID.randomUUID().toString(),
        occurredAt: String = Instant.now().toString(),
    ): InventoryOperationalCaptureResult = captureMutex.withLock {
        val expected = session.nextStep
            ?: return@withLock InventoryOperationalCaptureResult(
                OperationalCaptureCode.ALREADY_COMPLETED,
                null,
                progressCurrent(),
                completed = true,
            )
        if (step != expected) {
            val previous = session.evidence.lastOrNull()
            val incomingHash = runCatching {
                OperationalValueCanonicalizer.hash(step, rawValue)
            }.getOrNull()
            if (
                previous != null &&
                previous.kind == step &&
                incomingHash != null &&
                previous.valueHash == incomingHash
            ) {
                // Rapid duplicate physical ingress after the prior capture committed is
                // presentation-idempotent. No second durable event or device sequence is minted.
                return@withLock InventoryOperationalCaptureResult(
                    OperationalCaptureCode.EXACT_REPLAY,
                    expected,
                    progressCurrent(),
                    completed = session.completed,
                )
            }
            return@withLock InventoryOperationalCaptureResult(
                OperationalCaptureCode.WRONG_STEP,
                expected,
                progressCurrent(),
                completed = false,
            )
        }
        val event = queue.enqueueOperationalStep(
            context = InventoryOperationalEventContext(
                missionId = claim.missionId,
                claimId = claim.claimId,
                activeShiftId = claim.activeShiftId,
            ),
            step = step,
            rawValue = rawValue,
            eventId = eventId,
            occurredAt = occurredAt,
        )
        val evidence = OperationalStepEvidence(
            kind = step,
            valueHash = OperationalValueCanonicalizer.hash(step, rawValue),
            eventId = event.eventId,
            deviceSequence = event.deviceSequence,
        )
        val reduced = OperationalMissionReducer.capture(session, evidence)
        if (reduced.code == OperationalCaptureCode.ACCEPTED || reduced.code == OperationalCaptureCode.EXACT_REPLAY) {
            session = reduced.session
        }
        InventoryOperationalCaptureResult(
            code = reduced.code,
            nextStep = session.nextStep,
            progressCurrent = progressCurrent(),
            completed = session.completed,
        )
    }
}
