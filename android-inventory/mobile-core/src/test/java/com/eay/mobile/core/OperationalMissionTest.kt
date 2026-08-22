package com.eay.mobile.core

import org.junit.Assert.assertEquals
import org.junit.Assert.assertNotEquals
import org.junit.Assert.assertTrue
import org.junit.Test

class OperationalMissionTest {
    private fun evidence(kind: OperationalStepKind, id: String, sequence: Long, hash: Char = 'a') =
        OperationalStepEvidence(kind, hash.toString().repeat(64), id, sequence)

    @Test fun `all operational workflows execute their governed order`() {
        val definitions = listOf(
            OperationalMissionDefinition.picking("pick-1"),
            OperationalMissionDefinition.putaway("put-1"),
            OperationalMissionDefinition.receiving("receive-1"),
            OperationalMissionDefinition.transfer("transfer-1"),
        )
        definitions.forEach { definition ->
            var session = OperationalMissionSession(definition)
            definition.steps.forEachIndexed { index, step ->
                val result = OperationalMissionReducer.capture(session, evidence(step, "${definition.missionId}-$index", index + 1L))
                assertEquals(OperationalCaptureCode.ACCEPTED, result.code)
                session = result.session
            }
            assertTrue(session.completed)
        }
    }

    @Test fun `out of order physical evidence fails closed`() {
        val session = OperationalMissionSession(OperationalMissionDefinition.transfer("transfer-1"))
        val result = OperationalMissionReducer.capture(session, evidence(OperationalStepKind.DESTINATION_LOCATION, "event-1", 1))
        assertEquals(OperationalCaptureCode.WRONG_STEP, result.code)
        assertTrue(result.session.evidence.isEmpty())
    }

    @Test fun `exact replay is idempotent and substitutions collide`() {
        val initial = OperationalMissionSession(OperationalMissionDefinition.picking("pick-1"))
        val event = evidence(OperationalStepKind.SOURCE_LOCATION, "event-1", 1)
        val accepted = OperationalMissionReducer.capture(initial, event).session
        assertEquals(OperationalCaptureCode.EXACT_REPLAY, OperationalMissionReducer.capture(accepted, event).code)
        assertEquals(OperationalCaptureCode.EVENT_SUBSTITUTION, OperationalMissionReducer.capture(accepted, event.copy(valueHash = "b".repeat(64))).code)
        assertEquals(OperationalCaptureCode.SEQUENCE_COLLISION, OperationalMissionReducer.capture(accepted, evidence(OperationalStepKind.ITEM, "event-2", 1)).code)
        assertEquals(1, accepted.evidence.size)
    }

    @Test fun `offline envelope cannot be rebound to another mission or operation`() {
        val definition = OperationalMissionDefinition.putaway("put-1")
        val session = OperationalMissionSession(definition)
        val event = MobileEventEnvelope(
            eventId = "event-1", tenantId = "tenant-a", actorId = "actor-a",
            deviceId = "device-a", installationId = "install-a", authBindingId = "auth-a",
            missionId = "put-1", operation = definition.operation, deviceSequence = 1,
            occurredAt = "2026-08-20T10:00:00Z", payloadHash = "a".repeat(64),
            previousLedgerHash = null, policyFingerprint = "b".repeat(64), appVersion = "1.0.0",
        )
        val accepted = OperationalMissionReducer.captureEnvelope(session, OperationalStepKind.ITEM, event)
        assertEquals(OperationalCaptureCode.ACCEPTED, accepted.code)
        assertEquals(
            OperationalCaptureCode.EVENT_SUBSTITUTION,
            OperationalMissionReducer.captureEnvelope(session, OperationalStepKind.ITEM, event.copy(missionId = "put-2")).code,
        )
        assertEquals(
            OperationalCaptureCode.EVENT_SUBSTITUTION,
            OperationalMissionReducer.captureEnvelope(session, OperationalStepKind.ITEM, event.copy(operation = "inventory.pick.capture")).code,
        )
    }

    @Test fun `typed values canonicalize identically before signing`() {
        assertEquals("A-04-02", OperationalValueCanonicalizer.normalize(OperationalStepKind.SOURCE_LOCATION, " a-04-02 "))
        assertEquals("12", OperationalValueCanonicalizer.normalize(OperationalStepKind.QUANTITY, "12.000"))
        assertEquals("0", OperationalValueCanonicalizer.normalize(OperationalStepKind.QUANTITY, "0.000"))
        assertEquals("GOOD", OperationalValueCanonicalizer.normalize(OperationalStepKind.CONDITION, "good"))
        assertEquals(64, OperationalValueCanonicalizer.hash(OperationalStepKind.ITEM, "8690000000001").length)
        assertNotEquals(
            OperationalValueCanonicalizer.hash(OperationalStepKind.ITEM, "8690000000001"),
            OperationalValueCanonicalizer.hash(OperationalStepKind.ITEM, "8690000000002"),
        )
    }
}
