package com.eay.mobile.fieldui

import java.io.InputStream
import java.security.MessageDigest

private val MODEL_SHA256 = Regex("^[0-9a-f]{64}$")

data class AuditModelAssetPolicy(
    val modelRef: String,
    val assetPath: String,
    val expectedSha256: String,
    val expectedByteCount: Long,
    val provenanceRef: String,
    val licenseRef: String,
) {
    init {
        require(modelRef.isNotBlank()) { "modelRef must not be blank" }
        require(assetPath.isNotBlank()) { "assetPath must not be blank" }
        require(MODEL_SHA256.matches(expectedSha256)) { "expectedSha256 must be lowercase SHA-256" }
        require(expectedByteCount > 0L) { "expectedByteCount must be positive" }
        require(provenanceRef.isNotBlank()) { "provenanceRef must not be blank" }
        require(licenseRef.isNotBlank()) { "licenseRef must not be blank" }
    }
}

data class AuditModelAssetReceipt(
    val modelRef: String,
    val assetPath: String,
    val sha256: String,
    val byteCount: Long,
    val provenanceRef: String,
    val licenseRef: String,
)

class AuditModelAssetAdmissionException(message: String) : IllegalStateException(message)

object AuditModelAssetAdmission {
    fun verify(
        policy: AuditModelAssetPolicy,
        openAsset: () -> InputStream,
    ): AuditModelAssetReceipt {
        val digest = MessageDigest.getInstance("SHA-256")
        var byteCount = 0L

        openAsset().use { input ->
            val buffer = ByteArray(DEFAULT_BUFFER_SIZE)
            while (true) {
                val read = input.read(buffer)
                if (read < 0) break
                if (read == 0) continue
                digest.update(buffer, 0, read)
                byteCount += read
            }
        }

        val actualSha256 = digest.digest().joinToString("") { byte ->
            (byte.toInt() and 0xff).toString(16).padStart(2, '0')
        }
        if (byteCount != policy.expectedByteCount) {
            throw AuditModelAssetAdmissionException(
                "Privacy model byte count mismatch; audit media remains blocked",
            )
        }
        if (actualSha256 != policy.expectedSha256) {
            throw AuditModelAssetAdmissionException(
                "Privacy model SHA-256 mismatch; audit media remains blocked",
            )
        }

        return AuditModelAssetReceipt(
            modelRef = policy.modelRef,
            assetPath = policy.assetPath,
            sha256 = actualSha256,
            byteCount = byteCount,
            provenanceRef = policy.provenanceRef,
            licenseRef = policy.licenseRef,
        )
    }
}
