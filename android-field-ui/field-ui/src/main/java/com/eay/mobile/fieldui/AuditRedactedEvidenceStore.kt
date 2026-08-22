package com.eay.mobile.fieldui

import android.content.Context
import android.graphics.Bitmap
import java.io.Closeable
import java.io.File
import java.io.FileInputStream
import java.io.FileOutputStream
import java.io.InputStream
import java.security.MessageDigest
import java.util.UUID

private val SAFE_STEP = Regex("[^a-zA-Z0-9_.-]")

data class AuditRedactedEvidenceReceipt(
    val localEvidenceId: UUID,
    val stepId: String,
    val sequence: Long,
    val timestampMs: Long,
    val sha256: String,
    val byteCount: Long,
    val mimeType: String,
    val detectedFaceCount: Int,
    val detectorModelRef: String,
    val detectorModelSha256: String,
    val detectorProvenanceRef: String,
    val detectorLicenseRef: String,
)

/**
 * Opaque handle to sanitized media. The backing file is device-private and never exposed as a
 * public path. Upload code can stream it, then acknowledgeAndDelete() after server evidence ACK.
 */
class AuditRedactedEvidenceObject internal constructor(
    val receipt: AuditRedactedEvidenceReceipt,
    private val privateFile: File,
) : Closeable {
    fun <T> readForGovernedUpload(reader: (InputStream) -> T): T =
        FileInputStream(privateFile).use(reader)

    fun acknowledgeAndDelete() {
        deleteRequired()
    }

    fun existsForTest(): Boolean = privateFile.exists()

    override fun close() {
        // Sanitized evidence may need to survive a short offline queue. Close does not delete it;
        // deletion is explicit after server ACK or queue cancellation.
    }

    private fun deleteRequired() {
        if (privateFile.exists() && !privateFile.delete()) {
            throw IllegalStateException("Sanitized audit evidence could not be deleted")
        }
    }
}

class AuditRedactedEvidenceStore(
    context: Context,
    private val jpegQuality: Int = 90,
) {
    private val directory = File(context.filesDir, "eay-audit-redacted").apply {
        if (!exists() && !mkdirs()) {
            throw IllegalStateException("Could not create private redacted evidence directory")
        }
    }

    init {
        require(jpegQuality in 70..100) { "jpegQuality must be between 70 and 100" }
    }

    fun persist(frame: AuditRedactedEvidenceFrame): AuditRedactedEvidenceObject {
        val evidenceId = UUID.randomUUID()
        val stepToken = frame.stepId.replace(SAFE_STEP, "_").take(60).ifBlank { "step" }
        val target = File(directory, "$stepToken-${frame.sequence}-$evidenceId.jpg")
        val temp = File(directory, ".$evidenceId.tmp")

        try {
            FileOutputStream(temp).use { output ->
                if (!frame.bitmap.compress(Bitmap.CompressFormat.JPEG, jpegQuality, output)) {
                    throw IllegalStateException("Redacted evidence encoding failed")
                }
                output.fd.sync()
            }
            if (!temp.renameTo(target)) {
                throw IllegalStateException("Redacted evidence atomic promotion failed")
            }
            val digest = digestFile(target)
            val model = frame.detectorModelReceipt
            return AuditRedactedEvidenceObject(
                receipt = AuditRedactedEvidenceReceipt(
                    localEvidenceId = evidenceId,
                    stepId = frame.stepId,
                    sequence = frame.sequence,
                    timestampMs = frame.timestampMs,
                    sha256 = digest.sha256,
                    byteCount = digest.byteCount,
                    mimeType = "image/jpeg",
                    detectedFaceCount = frame.detectedFaceCount,
                    detectorModelRef = model.modelRef,
                    detectorModelSha256 = model.sha256,
                    detectorProvenanceRef = model.provenanceRef,
                    detectorLicenseRef = model.licenseRef,
                ),
                privateFile = target,
            )
        } catch (error: Throwable) {
            temp.delete()
            target.delete()
            throw error
        }
    }
}

private data class FileDigest(
    val sha256: String,
    val byteCount: Long,
)

private fun digestFile(file: File): FileDigest {
    val digest = MessageDigest.getInstance("SHA-256")
    var byteCount = 0L
    FileInputStream(file).use { input ->
        val buffer = ByteArray(DEFAULT_BUFFER_SIZE)
        while (true) {
            val read = input.read(buffer)
            if (read < 0) break
            if (read == 0) continue
            digest.update(buffer, 0, read)
            byteCount += read
        }
    }
    val sha256 = digest.digest().joinToString("") { byte ->
        (byte.toInt() and 0xff).toString(16).padStart(2, '0')
    }
    return FileDigest(sha256 = sha256, byteCount = byteCount)
}
