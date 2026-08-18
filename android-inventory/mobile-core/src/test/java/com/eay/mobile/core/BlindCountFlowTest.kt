package com.eay.mobile.core

import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Test

class BlindCountFlowTest {
    private val now = 1_800_000_000_000L
    private val policy = ScannerPolicy(
        allowedSources = setOf(ScannerSource.HARDWARE_DATAWEDGE),
        allowedSymbologies = setOf(BarcodeSymbology.CODE128, BarcodeSymbology.EAN13),
    )

    private fun accepted(
        id: String,
        value: String,
        symbology: BarcodeSymbology = BarcodeSymbology.CODE128,
    ): AcceptedScan = ScannerIngressGuard.evaluate(
        ScannerIngress(
            sourceEventId = id,
            source = ScannerSource.HARDWARE_DATAWEDGE,
            symbology = symbology,
            rawValue = value,
            capturedAtEpochMs = now,
        ),
        policy,
        now,
    ).scan!!

    @Test
    fun `count cannot expose or consume expected stock quantity`() {
        val target = BlindCountTarget(
            missionId = "mission-1",
            locationTokenHash = sha256("A-04-02"),
            targetLineCount = 1,
        )
        var session = BlindCountSession("mission-1")

        val location = BlindCountFlow.verifyLocation(
            session,
            target,
            accepted("location-1", "A-04-02"),
        )
        assertTrue(location.accepted)
        session = location.session

        session = BlindCountFlow.scanItem(
            session,
            accepted("item-1", "8691234567890", BarcodeSymbology.EAN13),
        ).session
        assertEquals(BlindCountStep.ENTER_QUANTITY, session.step)
        assertNull(session.currentQuantity)

        session = BlindCountFlow.enterQuantity(session, 12).session
        val confirmed = BlindCountFlow.confirmItem(session, target)
        assertTrue(confirmed.accepted)
        assertEquals(12, confirmed.evidence!!.quantity)
        assertEquals(BlindCountStep.COMPLETE, confirmed.session.step)
    }

    @Test
    fun `wrong physical location blocks count before item scan`() {
        val target = BlindCountTarget(
            missionId = "mission-1",
            locationTokenHash = sha256("A-04-02"),
        )
        val result = BlindCountFlow.verifyLocation(
            BlindCountSession("mission-1"),
            target,
            accepted("location-1", "B-09-01"),
        )
        assertFalse(result.accepted)
        assertEquals(BlindCountCode.DENY_LOCATION, result.code)
        assertEquals(BlindCountStep.SCAN_LOCATION, result.session.step)
    }

    @Test
    fun `quantity cannot be entered before a verified item scan`() {
        val session = BlindCountSession(
            missionId = "mission-1",
            step = BlindCountStep.SCAN_ITEM,
            locationVerified = true,
        )
        val result = BlindCountFlow.enterQuantity(session, 10)
        assertEquals(BlindCountCode.DENY_STEP, result.code)
    }

    @Test
    fun `negative and implausibly large quantities fail closed`() {
        val base = BlindCountSession(
            missionId = "mission-1",
            step = BlindCountStep.ENTER_QUANTITY,
            locationVerified = true,
            currentItemHash = sha256("8691234567890"),
        )
        assertEquals(
            BlindCountCode.DENY_QUANTITY,
            BlindCountFlow.enterQuantity(base, -1).code,
        )
        assertEquals(
            BlindCountCode.DENY_QUANTITY,
            BlindCountFlow.enterQuantity(base, BlindCountFlow.MAX_QUANTITY + 1).code,
        )
    }

    @Test
    fun `mission target cannot silently accept extra confirmed lines`() {
        val target = BlindCountTarget(
            missionId = "mission-1",
            locationTokenHash = sha256("A-04-02"),
            targetLineCount = 1,
        )
        val alreadyAtTarget = BlindCountSession(
            missionId = "mission-1",
            step = BlindCountStep.CONFIRM_ITEM,
            locationVerified = true,
            currentItemHash = sha256("8691234567890"),
            currentQuantity = 2,
            confirmedLineCount = 1,
        )
        val result = BlindCountFlow.confirmItem(alreadyAtTarget, target)
        assertEquals(BlindCountCode.DENY_TARGET, result.code)
    }
}
