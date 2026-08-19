package com.eay.mobile.fieldui

import java.nio.file.Files
import java.util.UUID
import org.junit.Assert.assertFalse
import org.junit.Assert.assertThrows
import org.junit.Assert.assertTrue
import org.junit.Test

class AuditRawCaptureLeaseTest {
    @Test
    fun successfulProcessingDeletesRawFile() {
        val path = Files.createTempFile("eay-audit-raw-", ".mp4")
        path.toFile().writeBytes(byteArrayOf(1, 2, 3))
        val lease = AuditRawVideoCapture(UUID.randomUUID(), path.toFile())

        val byteCount = lease.consumeAndDelete { file -> file.length() }

        assertTrue(byteCount == 3L)
        assertTrue(lease.isConsumed())
        assertFalse(path.toFile().exists())
    }

    @Test
    fun failedProcessingStillDeletesRawFile() {
        val path = Files.createTempFile("eay-audit-raw-", ".mp4")
        val lease = AuditRawVideoCapture(UUID.randomUUID(), path.toFile())

        assertThrows(IllegalStateException::class.java) {
            lease.consumeAndDelete<Unit> { throw IllegalStateException("redaction failed") }
        }

        assertTrue(lease.isConsumed())
        assertFalse(path.toFile().exists())
    }

    @Test
    fun rawLeaseCannotBeConsumedTwice() {
        val path = Files.createTempFile("eay-audit-raw-", ".mp4")
        val lease = AuditRawVideoCapture(UUID.randomUUID(), path.toFile())
        lease.discard()

        assertThrows(IllegalStateException::class.java) {
            lease.consumeAndDelete { file -> file.length() }
        }
    }
}
