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

/** Pure reducer seeding used only after durable evidence passed restart projection. */
internal object InventoryOperationalResumeSession {
    fun seed(
        task: InventoryOperationalTask,
        claim: InventoryOperationalClaim,
        resumeEvidence: List<OperationalStepEvidence>,
    ): OperationalMissionSession {
        require(claim.missionId == task.missionId)
        require(claim.activeShiftId == task.activeShiftId)
        require(claim.nextStep == task.nextStep)
        var session = OperationalMissionSession(
            definition = OperationalMissionDefinition(
                missionId = task.missionId,
                type = task.missionType,
                operation = task.operation,
                steps = task.steps.drop(task.completedSteps),
            ),
        )
        require(session.nextStep == task.nextStep)
        for (evidence in resumeEvidence) {
            val reduced = OperationalMissionReducer.capture(session, evidence)
            require(reduced.code == OperationalCaptureCode.ACCEPTED) {
                "Durable operational evidence is not a canonical resume prefix"
            }
            session = reduced.session
        }
        return session
    }
}

class InventoryOperationalController(
    private val task: InventoryOperationalTask,
    private val claim: InventoryOperationalClaim,
    private val queue: InventoryOfflineQueue,
) {
    private val progressOffset = task.completedSteps
    private val captureMutex = Mutex()
    private var session = InventoryOperationalResumeSession.seed(
        task = task,
        claim = claim,
        resumeEvidence = claim.resumeEvidence,
    )

    fun nextStep(): OperationalStepKind? = session.nextStep

    fun progressCurrent(): Int = progressOffset + session.evidence.size

    suspend fun capture(
        step: OperationalStepKind,
        rawValue: String,
        eventId: String = UUID.randomUUID().toString(),
        occurredAt: String = Instant.now().toString(),
    ): InventoryOperationalCaptureResult = captureMutex.withLock {
        val startedAt = System.nanoTime()
        val expected = session.nextStep
            ?: return@withLock feedback(
                InventoryOperationalCaptureResult(
                    OperationalCaptureCode.ALREADY_COMPLETED,
                    null,
                    progressCurrent(),
                    completed = true,
                ),
                startedAt,
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
                return@withLock feedback(
                    InventoryOperationalCaptureResult(
                        OperationalCaptureCode.EXACT_REPLAY,
                        expected,
                        progressCurrent(),
                        completed = session.completed,
                    ),
                    startedAt,
                )
            }
            return@withLock feedback(
                InventoryOperationalCaptureResult(
                    OperationalCaptureCode.WRONG_STEP,
                    expected,
                    progressCurrent(),
                    completed = false,
                ),
                startedAt,
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
        feedback(
            InventoryOperationalCaptureResult(
                code = reduced.code,
                nextStep = session.nextStep,
                progressCurrent = progressCurrent(),
                completed = session.completed,
            ),
            startedAt,
        )
    }

    private fun feedback(
        result: InventoryOperationalCaptureResult,
        startedAt: Long,
    ): InventoryOperationalCaptureResult {
        TerminalFeedbackRuntime.recordLocalDecision(startedAt)
        when (result.code) {
            OperationalCaptureCode.ACCEPTED,
            OperationalCaptureCode.EXACT_REPLAY,
            OperationalCaptureCode.ALREADY_COMPLETED,
            -> TerminalFeedbackRuntime.accepted()
            else -> TerminalFeedbackRuntime.rejected()
        }
        return result
    }
}
