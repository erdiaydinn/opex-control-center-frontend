package com.eay.mobile.core

import java.math.BigDecimal
import java.nio.charset.StandardCharsets
import java.security.MessageDigest
import java.util.Locale

/** Executable workflow contract for the four physical inventory operations. */
enum class OperationalMissionType { PICKING, PUTAWAY, RECEIVING, TRANSFER }

enum class OperationalStepKind {
    SOURCE_LOCATION,
    DESTINATION_LOCATION,
    ITEM,
    QUANTITY,
    CONDITION,
    CONTAINER,
    COMPLETE,
}

data class OperationalMissionDefinition(
    val missionId: String,
    val type: OperationalMissionType,
    val operation: String,
    val steps: List<OperationalStepKind>,
) {
    init {
        require(missionId.isNotBlank())
        require(operation.isNotBlank())
        require(steps.isNotEmpty() && steps.last() == OperationalStepKind.COMPLETE)
        require(steps.count { it == OperationalStepKind.COMPLETE } == 1)
    }

    companion object {
        fun picking(id: String) = OperationalMissionDefinition(
            id, OperationalMissionType.PICKING, "inventory.pick.capture",
            listOf(OperationalStepKind.SOURCE_LOCATION, OperationalStepKind.ITEM, OperationalStepKind.QUANTITY, OperationalStepKind.CONTAINER, OperationalStepKind.COMPLETE),
        )

        fun putaway(id: String) = OperationalMissionDefinition(
            id, OperationalMissionType.PUTAWAY, "inventory.putaway.capture",
            listOf(OperationalStepKind.ITEM, OperationalStepKind.QUANTITY, OperationalStepKind.DESTINATION_LOCATION, OperationalStepKind.COMPLETE),
        )

        fun receiving(id: String) = OperationalMissionDefinition(
            id, OperationalMissionType.RECEIVING, "inventory.receiving.capture",
            listOf(OperationalStepKind.CONTAINER, OperationalStepKind.ITEM, OperationalStepKind.QUANTITY, OperationalStepKind.CONDITION, OperationalStepKind.COMPLETE),
        )

        fun transfer(id: String) = OperationalMissionDefinition(
            id, OperationalMissionType.TRANSFER, "inventory.transfer.capture",
            listOf(OperationalStepKind.SOURCE_LOCATION, OperationalStepKind.ITEM, OperationalStepKind.QUANTITY, OperationalStepKind.DESTINATION_LOCATION, OperationalStepKind.COMPLETE),
        )
    }
}

/**
 * Canonicalizes the raw physical value before it is device-signature bound.
 * Raw ITEM values are intentionally not carried by OperationalStepEvidence:
 * the backend verifies this hash against server-frozen mission intent and
 * persists only the safe SKU projection.
 */
object OperationalValueCanonicalizer {
    private val codeSteps = setOf(
        OperationalStepKind.SOURCE_LOCATION,
        OperationalStepKind.DESTINATION_LOCATION,
        OperationalStepKind.CONDITION,
        OperationalStepKind.CONTAINER,
        OperationalStepKind.COMPLETE,
    )

    fun normalize(kind: OperationalStepKind, rawValue: String): String {
        val trimmed = rawValue.trim()
        require(trimmed.isNotEmpty()) { "Operational value must not be blank" }
        return when {
            kind == OperationalStepKind.QUANTITY -> {
                val value = BigDecimal(trimmed)
                require(value >= BigDecimal.ZERO && value <= BigDecimal("1000000")) {
                    "Operational quantity is outside the accepted range"
                }
                if (value.compareTo(BigDecimal.ZERO) == 0) "0" else value.stripTrailingZeros().toPlainString()
            }
            kind in codeSteps -> {
                val normalized = trimmed.uppercase(Locale.ROOT)
                if (kind == OperationalStepKind.COMPLETE) {
                    require(normalized == "COMPLETE") { "Completion value must be COMPLETE" }
                }
                normalized
            }
            else -> trimmed
        }
    }

    fun hash(kind: OperationalStepKind, rawValue: String): String {
        val normalized = normalize(kind, rawValue)
        val material = lengthPrefix(kind.name) + lengthPrefix(normalized)
        return MessageDigest.getInstance("SHA-256")
            .digest(material.toByteArray(StandardCharsets.UTF_8))
            .joinToString("") { "%02x".format(it) }
    }

    private fun lengthPrefix(value: String): String {
        val size = value.toByteArray(StandardCharsets.UTF_8).size
        return "$size:$value"
    }
}

data class OperationalStepEvidence(
    val kind: OperationalStepKind,
    val valueHash: String,
    val eventId: String,
    val deviceSequence: Long,
) {
    init {
        require(valueHash.matches(Regex("^[a-f0-9]{64}$")))
        require(eventId.isNotBlank())
        require(deviceSequence > 0)
    }
}

data class OperationalMissionSession(
    val definition: OperationalMissionDefinition,
    val evidence: List<OperationalStepEvidence> = emptyList(),
) {
    val nextStep: OperationalStepKind?
        get() = definition.steps.getOrNull(evidence.size)
    val completed: Boolean get() = nextStep == null
}

enum class OperationalCaptureCode { ACCEPTED, EXACT_REPLAY, WRONG_STEP, SEQUENCE_COLLISION, EVENT_SUBSTITUTION, ALREADY_COMPLETED }

data class OperationalCaptureResult(val session: OperationalMissionSession, val code: OperationalCaptureCode)

object OperationalMissionReducer {
    /**
     * Composes the workflow reducer with the durable MobileEventEnvelope used by
     * MobileSyncEngine. This is the only admission path for offline operation evidence.
     */
    fun captureEnvelope(
        session: OperationalMissionSession,
        step: OperationalStepKind,
        event: MobileEventEnvelope,
    ): OperationalCaptureResult {
        if (!event.isStructurallyValid() ||
            event.missionId != session.definition.missionId ||
            event.operation != session.definition.operation
        ) {
            return OperationalCaptureResult(session, OperationalCaptureCode.EVENT_SUBSTITUTION)
        }
        return capture(
            session,
            OperationalStepEvidence(step, event.payloadHash.lowercase(), event.eventId, event.deviceSequence),
        )
    }

    fun capture(session: OperationalMissionSession, evidence: OperationalStepEvidence): OperationalCaptureResult {
        val existingEvent = session.evidence.firstOrNull { it.eventId == evidence.eventId }
        if (existingEvent != null) {
            return OperationalCaptureResult(
                session,
                if (existingEvent == evidence) OperationalCaptureCode.EXACT_REPLAY else OperationalCaptureCode.EVENT_SUBSTITUTION,
            )
        }
        val sequence = session.evidence.firstOrNull { it.deviceSequence == evidence.deviceSequence }
        if (sequence != null) return OperationalCaptureResult(session, OperationalCaptureCode.SEQUENCE_COLLISION)
        val expected = session.nextStep ?: return OperationalCaptureResult(session, OperationalCaptureCode.ALREADY_COMPLETED)
        if (evidence.kind != expected) return OperationalCaptureResult(session, OperationalCaptureCode.WRONG_STEP)
        return OperationalCaptureResult(
            session.copy(evidence = session.evidence + evidence),
            OperationalCaptureCode.ACCEPTED,
        )
    }
}
