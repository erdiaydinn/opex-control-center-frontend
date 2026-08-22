package com.eay.mobile.fieldui

import java.io.File
import java.util.UUID
import java.util.concurrent.atomic.AtomicBoolean

/**
 * Opaque one-shot lease for raw audit media.
 *
 * Raw media is never an evidence object. The only supported lifecycle is to consume it for
 * privacy post-processing exactly once or discard it. Both paths require physical deletion.
 */
class AuditRawVideoCapture internal constructor(
    val captureId: UUID,
    private val privateFile: File,
) {
    private val consumed = AtomicBoolean(false)

    internal fun recordingFile(): File {
        check(!consumed.get()) { "Raw audit capture lease is already consumed" }
        return privateFile
    }

    fun <T> consumeAndDelete(processor: (File) -> T): T {
        check(consumed.compareAndSet(false, true)) {
            "Raw audit capture lease may only be consumed once"
        }
        try {
            return processor(privateFile)
        } finally {
            deleteRequired()
        }
    }

    fun discard() {
        check(consumed.compareAndSet(false, true)) {
            "Raw audit capture lease may only be consumed once"
        }
        deleteRequired()
    }

    internal fun discardIfOpen() {
        if (consumed.compareAndSet(false, true)) {
            deleteRequired()
        }
    }

    fun isConsumed(): Boolean = consumed.get()

    internal fun rawExistsForTest(): Boolean = privateFile.exists()

    private fun deleteRequired() {
        if (privateFile.exists() && !privateFile.delete()) {
            throw IllegalStateException(
                "Raw audit media could not be deleted; capture remains blocked",
            )
        }
    }
}
