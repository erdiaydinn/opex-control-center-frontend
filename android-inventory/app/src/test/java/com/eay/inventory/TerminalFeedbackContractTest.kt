package com.eay.inventory

import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Test

class TerminalFeedbackContractTest {
    @Test
    fun `local decision budget is explicit and anonymous`() {
        assertEquals(100L, TerminalFeedbackRuntime.LOCAL_DECISION_TARGET_MS)
        val before = TerminalFeedbackRuntime.performanceSnapshot()
        TerminalFeedbackRuntime.recordLocalDecision(
            startedAtNanos = 1_000_000_000L,
            endedAtNanos = 1_050_000_000L,
        )
        TerminalFeedbackRuntime.recordLocalDecision(
            startedAtNanos = 2_000_000_000L,
            endedAtNanos = 2_150_000_000L,
        )
        val after = TerminalFeedbackRuntime.performanceSnapshot()
        assertEquals(before.localDecisionCount + 2, after.localDecisionCount)
        assertEquals(
            before.localDecisionOverBudgetCount + 1,
            after.localDecisionOverBudgetCount,
        )
        assertTrue(after.localDecisionMaxMs >= 150L)
        assertTrue(after.withinBudgetRate in 0.0..1.0)
    }
}
