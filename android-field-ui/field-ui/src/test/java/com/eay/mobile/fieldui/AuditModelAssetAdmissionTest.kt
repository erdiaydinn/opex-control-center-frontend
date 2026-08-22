package com.eay.mobile.fieldui

import java.io.ByteArrayInputStream
import org.junit.Assert.assertEquals
import org.junit.Assert.assertThrows
import org.junit.Test

class AuditModelAssetAdmissionTest {
    private val validPolicy = AuditModelAssetPolicy(
        modelRef = "mediapipe-face-detector:test-fixture",
        assetPath = "face_detection_short_range.tflite",
        expectedSha256 = "ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad",
        expectedByteCount = 3,
        provenanceRef = "github:google-ai-edge/mediapipe:test-fixture",
        licenseRef = "Apache-2.0:test-fixture",
    )

    @Test
    fun exactFingerprintProducesAdmissionReceipt() {
        val receipt = AuditModelAssetAdmission.verify(validPolicy) {
            ByteArrayInputStream("abc".toByteArray())
        }

        assertEquals(validPolicy.modelRef, receipt.modelRef)
        assertEquals(validPolicy.expectedSha256, receipt.sha256)
        assertEquals(3L, receipt.byteCount)
        assertEquals(validPolicy.provenanceRef, receipt.provenanceRef)
        assertEquals(validPolicy.licenseRef, receipt.licenseRef)
    }

    @Test
    fun shaMismatchFailsClosed() {
        val policy = validPolicy.copy(expectedSha256 = "0".repeat(64))
        assertThrows(AuditModelAssetAdmissionException::class.java) {
            AuditModelAssetAdmission.verify(policy) {
                ByteArrayInputStream("abc".toByteArray())
            }
        }
    }

    @Test
    fun byteCountMismatchFailsClosed() {
        val policy = validPolicy.copy(expectedByteCount = 4)
        assertThrows(AuditModelAssetAdmissionException::class.java) {
            AuditModelAssetAdmission.verify(policy) {
                ByteArrayInputStream("abc".toByteArray())
            }
        }
    }
}
