package com.eay.mobile.core

import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test

class ScannerIngressTest {
    private val now = 1_800_000_000_000L
    private val hardwarePolicy = ScannerPolicy(
        allowedSources = setOf(ScannerSource.HARDWARE_DATAWEDGE),
        allowedSymbologies = setOf(
            BarcodeSymbology.EAN13,
            BarcodeSymbology.CODE128,
            BarcodeSymbology.GS1_128,
        ),
    )

    private fun ingress(
        id: String = "scan-1",
        value: String = "8691234567890",
        source: ScannerSource = ScannerSource.HARDWARE_DATAWEDGE,
        symbology: BarcodeSymbology = BarcodeSymbology.EAN13,
        capturedAt: Long = now,
    ) = ScannerIngress(
        sourceEventId = id,
        source = source,
        symbology = symbology,
        rawValue = value,
        capturedAtEpochMs = capturedAt,
    )

    @Test
    fun `hardware scan is admitted and only payload hash is safe correlation material`() {
        val admission = ScannerIngressGuard.evaluate(ingress(), hardwarePolicy, now)
        assertTrue(admission.accepted)
        assertEquals(64, admission.scan!!.payloadHash.length)
        assertEquals("8691234567890", admission.scan!!.value)
    }

    @Test
    fun `camera or manual input is denied when terminal policy does not allow it`() {
        assertEquals(
            ScannerAdmissionCode.DENY_SOURCE,
            ScannerIngressGuard.evaluate(
                ingress(source = ScannerSource.CAMERA),
                hardwarePolicy,
                now,
            ).code,
        )
        assertEquals(
            ScannerAdmissionCode.DENY_SOURCE,
            ScannerIngressGuard.evaluate(
                ingress(source = ScannerSource.MANUAL),
                hardwarePolicy,
                now,
            ).code,
        )
    }

    @Test
    fun `stale future oversized and control character payloads fail closed`() {
        assertEquals(
            ScannerAdmissionCode.DENY_STALE,
            ScannerIngressGuard.evaluate(
                ingress(capturedAt = now - 30_001),
                hardwarePolicy,
                now,
            ).code,
        )
        assertEquals(
            ScannerAdmissionCode.DENY_FUTURE,
            ScannerIngressGuard.evaluate(
                ingress(capturedAt = now + 2_001),
                hardwarePolicy,
                now,
            ).code,
        )
        assertEquals(
            ScannerAdmissionCode.DENY_OVERSIZE,
            ScannerIngressGuard.evaluate(
                ingress(value = "x".repeat(513)),
                hardwarePolicy,
                now,
            ).code,
        )
        assertEquals(
            ScannerAdmissionCode.DENY_CONTROL_CHARACTER,
            ScannerIngressGuard.evaluate(
                ingress(value = "869\u0000bad"),
                hardwarePolicy,
                now,
            ).code,
        )
    }

    @Test
    fun `datawedge line ending is normalized but gs1 separator is preserved`() {
        val lineEnding = ScannerIngressGuard.evaluate(
            ingress(value = "8691234567890\r\n"),
            hardwarePolicy,
            now,
        )
        assertEquals("8691234567890", lineEnding.scan!!.value)

        val gs1 = ScannerIngressGuard.evaluate(
            ingress(
                value = "0108691234567890\u001D17270101",
                symbology = BarcodeSymbology.GS1_128,
            ),
            hardwarePolicy,
            now,
        )
        assertTrue(gs1.accepted)
    }

    @Test
    fun `same source event id with changed payload is substitution not a duplicate`() {
        val first = ScannerIngressGuard.evaluate(ingress(), hardwarePolicy, now).scan!!
        val changed = ScannerIngressGuard.evaluate(
            ingress(value = "8691234567891"),
            hardwarePolicy,
            now,
        ).scan!!
        assertEquals(
            ScannerReplayDisposition.EVENT_ID_PAYLOAD_SUBSTITUTION,
            ScannerIngressGuard.compare(first, changed),
        )

        val exact = ScannerIngressGuard.evaluate(ingress(), hardwarePolicy, now).scan!!
        assertEquals(
            ScannerReplayDisposition.EXACT_REPLAY,
            ScannerIngressGuard.compare(first, exact),
        )
        assertFalse(first.payloadHash == changed.payloadHash)
    }
}
