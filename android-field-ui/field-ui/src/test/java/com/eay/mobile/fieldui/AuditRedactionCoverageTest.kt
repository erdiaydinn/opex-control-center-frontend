package com.eay.mobile.fieldui

import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertThrows
import org.junit.Assert.assertTrue
import org.junit.Test

class AuditRedactionCoverageTest {
    private fun result(sequence: Long, processed: Boolean = true): AuditFrameCoverageResult =
        AuditFrameCoverageResult(
            frameSequence = sequence,
            timestampMs = sequence * 33L,
            processed = processed,
        )

    @Test
    fun everyCanonicalFrameMustBeProcessedBeforePromotion() {
        val ledger = AuditRedactionCoverageLedger(expectedFrameCount = 3)
        ledger.record(result(0))
        ledger.record(result(1))

        assertFalse(ledger.isComplete())
        assertEquals(1L, ledger.missingFrameCount())
        assertThrows(IllegalStateException::class.java) { ledger.assertPromotable() }

        ledger.record(result(2))
        assertTrue(ledger.isComplete())
        ledger.assertPromotable()
    }

    @Test
    fun aDroppedOrFailedFrameBlocksTheWholeEvidenceVideo() {
        val ledger = AuditRedactionCoverageLedger(expectedFrameCount = 2)
        ledger.record(result(0))
        ledger.record(result(1, processed = false))

        assertFalse(ledger.isComplete())
        assertEquals("frame_1_was_not_processed", ledger.failureReason())
        assertThrows(IllegalStateException::class.java) { ledger.assertPromotable() }
    }

    @Test
    fun duplicateFrameReceiptDoesNotFakeCoverage() {
        val ledger = AuditRedactionCoverageLedger(expectedFrameCount = 2)
        ledger.record(result(0))
        ledger.record(result(0))

        assertFalse(ledger.isComplete())
        assertEquals(1L, ledger.missingFrameCount())
    }
}
