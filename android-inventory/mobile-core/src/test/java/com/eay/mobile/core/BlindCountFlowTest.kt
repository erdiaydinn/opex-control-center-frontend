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
            locationTokenHash = BlindCountLocationToken.hash("A-04-02"),
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
        assertEquals(BlindCountStep.SCAN_ITEM, confirmed.session.step)

        val completed = BlindCountFlow.completeLocation(confirmed.session, target)
        assertTrue(completed.accepted)
        assertEquals(BlindCountStep.COMPLETE, completed.session.step)
    }

    @Test
    fun `location token follows backend trim and uppercase semantics`() {
        val target = BlindCountTarget(
            missionId = "mission-1",
            locationTokenHash = BlindCountLocationToken.hash("A-04-02"),
        )
        val result = BlindCountFlow.verifyLocation(
            BlindCountSession("mission-1"),
            target,
            accepted("location-1", " a-04-02 "),
        )
        assertTrue(result.accepted)
        assertEquals(BlindCountStep.SCAN_ITEM, result.session.step)
    }

    @Test
    fun `wrong physical location blocks count before item scan`() {
        val target = BlindCountTarget(
            missionId = "mission-1",
            locationTokenHash = BlindCountLocationToken.hash("A-04-02"),
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
            locationTokenHash = BlindCountLocationToken.hash("A-04-02"),
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

    @Test
    fun `open ended location may complete only between item scans`() {
        val target = BlindCountTarget(
            missionId = "mission-1",
            locationTokenHash = BlindCountLocationToken.hash("A-04-02"),
        )
        val ready = BlindCountSession(
            missionId = "mission-1",
            step = BlindCountStep.SCAN_ITEM,
            locationVerified = true,
            confirmedLineCount = 3,
        )
        val completed = BlindCountFlow.completeLocation(ready, target)
        assertTrue(completed.accepted)
        assertEquals(BlindCountStep.COMPLETE, completed.session.step)
        assertEquals(3, completed.session.confirmedLineCount)

        val midItem = ready.copy(
            step = BlindCountStep.ENTER_QUANTITY,
            currentItemHash = sha256("8691234567890"),
        )
        assertEquals(
            BlindCountCode.DENY_STEP,
            BlindCountFlow.completeLocation(midItem, target).code,
        )
    }

    @Test
    fun `explicit target cannot be bypassed by manual location completion`() {
        val target = BlindCountTarget(
            missionId = "mission-1",
            locationTokenHash = BlindCountLocationToken.hash("A-04-02"),
            targetLineCount = 5,
        )
        val incomplete = BlindCountSession(
            missionId = "mission-1",
            step = BlindCountStep.SCAN_ITEM,
            locationVerified = true,
            confirmedLineCount = 4,
        )
        assertEquals(
            BlindCountCode.DENY_TARGET,
            BlindCountFlow.completeLocation(incomplete, target).code,
        )
    }

    @Test
    fun `location scan alone cannot assert an empty location`() {
        val target = BlindCountTarget(
            missionId = "mission-1",
            locationTokenHash = BlindCountLocationToken.hash("EMPTY-01"),
        )
        val verified = BlindCountFlow.verifyLocation(
            BlindCountSession("mission-1"),
            target,
            accepted("location-empty", "EMPTY-01"),
        ).session
        val completed = BlindCountFlow.completeLocation(verified, target)
        assertEquals(BlindCountCode.DENY_TARGET, completed.code)
        assertEquals(0, completed.session.confirmedLineCount)
        assertEquals(BlindCountStep.SCAN_ITEM, completed.session.step)
    }
}
