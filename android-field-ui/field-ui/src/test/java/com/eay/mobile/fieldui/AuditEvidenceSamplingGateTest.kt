package com.eay.mobile.fieldui

import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test

class AuditEvidenceSamplingGateTest {
    @Test
    fun cadenceAndPerStepLimitAreDeterministic() {
        val gate = AuditEvidenceSamplingGate(
            AuditEvidenceSamplingPolicy(minimumIntervalMs = 500L, maxFramesPerStep = 2),
        )

        assertTrue(gate.shouldAccept("entrance", 1000L))
        gate.recordAccepted("entrance", 1000L)
        assertFalse(gate.shouldAccept("entrance", 1200L))
        assertTrue(gate.shouldAccept("entrance", 1500L))
        gate.recordAccepted("entrance", 1500L)
        assertFalse(gate.shouldAccept("entrance", 2500L))

        val snapshot = gate.snapshot()
        assertEquals(2L, snapshot.totalAcceptedFrames)
        assertEquals(2, snapshot.acceptedByStep["entrance"])
    }

    @Test
    fun missingStepAndNonMonotonicTimestampsNeverBecomeEvidence() {
        val gate = AuditEvidenceSamplingGate()
        assertFalse(gate.shouldAccept(null, 1000L))
        assertFalse(gate.shouldAccept("", 1000L))

        gate.recordAccepted("coffee", 1000L)
        assertFalse(gate.shouldAccept("shelves", 1000L))
        assertFalse(gate.shouldAccept("shelves", 999L))
        assertTrue(gate.shouldAccept("shelves", 1100L))
    }

    @Test
    fun separateStepsKeepIndependentCadenceButGlobalTimeMovesForward() {
        val gate = AuditEvidenceSamplingGate(
            AuditEvidenceSamplingPolicy(minimumIntervalMs = 1000L, maxFramesPerStep = 3),
        )
        gate.recordAccepted("entrance", 1000L)

        assertTrue(gate.shouldAccept("oven", 1200L))
        gate.recordAccepted("oven", 1200L)
        assertFalse(gate.shouldAccept("entrance", 1500L))
        assertTrue(gate.shouldAccept("entrance", 2000L))
    }
}
