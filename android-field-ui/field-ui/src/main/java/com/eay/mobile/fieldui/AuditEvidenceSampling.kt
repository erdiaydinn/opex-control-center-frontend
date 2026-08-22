package com.eay.mobile.fieldui

import android.graphics.Bitmap


data class AuditEvidenceSamplingPolicy(
    val minimumIntervalMs: Long = 750L,
    val maxFramesPerStep: Int = 8,
) {
    init {
        require(minimumIntervalMs >= 100L) { "minimumIntervalMs must be at least 100ms" }
        require(maxFramesPerStep > 0) { "maxFramesPerStep must be positive" }
    }
}

data class AuditEvidenceSamplingSnapshot(
    val totalAcceptedFrames: Long,
    val acceptedByStep: Map<String, Int>,
    val lastAcceptedTimestampMs: Long?,
)

/**
 * Sampling authority for derived evidence frames.
 *
 * CameraX may drop ImageAnalysis candidate frames under KEEP_ONLY_LATEST. That is acceptable:
 * dropped candidates are not canonical evidence. A frame becomes canonical evidence only after
 * this gate accepts it and local privacy redaction succeeds.
 */
class AuditEvidenceSamplingGate(
    private val policy: AuditEvidenceSamplingPolicy = AuditEvidenceSamplingPolicy(),
) {
    private val acceptedByStep = linkedMapOf<String, Int>()
    private val lastAcceptedByStep = linkedMapOf<String, Long>()
    private var lastAcceptedGlobal: Long? = null
    private var totalAccepted = 0L

    @Synchronized
    fun shouldAccept(stepId: String?, timestampMs: Long): Boolean {
        val normalizedStep = stepId?.trim().orEmpty()
        if (normalizedStep.isEmpty() || timestampMs < 0L) return false
        val global = lastAcceptedGlobal
        if (global != null && timestampMs <= global) return false
        val count = acceptedByStep[normalizedStep] ?: 0
        if (count >= policy.maxFramesPerStep) return false
        val previous = lastAcceptedByStep[normalizedStep]
        if (previous != null && timestampMs - previous < policy.minimumIntervalMs) return false
        return true
    }

    @Synchronized
    fun recordAccepted(stepId: String, timestampMs: Long) {
        check(shouldAccept(stepId, timestampMs)) {
            "Evidence frame does not satisfy the active sampling policy"
        }
        val normalizedStep = stepId.trim()
        acceptedByStep[normalizedStep] = (acceptedByStep[normalizedStep] ?: 0) + 1
        lastAcceptedByStep[normalizedStep] = timestampMs
        lastAcceptedGlobal = timestampMs
        totalAccepted += 1
    }

    @Synchronized
    fun snapshot(): AuditEvidenceSamplingSnapshot = AuditEvidenceSamplingSnapshot(
        totalAcceptedFrames = totalAccepted,
        acceptedByStep = acceptedByStep.toMap(),
        lastAcceptedTimestampMs = lastAcceptedGlobal,
    )
}

data class AuditRedactedEvidenceFrame(
    val stepId: String,
    val sequence: Long,
    val timestampMs: Long,
    val detectedFaceCount: Int,
    val bitmap: Bitmap,
    val detectorModelReceipt: AuditModelAssetReceipt,
)

/**
 * Converts selected local camera frames into privacy-redacted evidence candidates.
 * Raw bitmaps never leave this processor through its output contract.
 */
class AuditLocalRedactedFrameProcessor(
    private val detector: MediaPipeAuditFaceDetector,
    private val redactor: BitmapAuditFaceRedactor = BitmapAuditFaceRedactor(),
    private val samplingGate: AuditEvidenceSamplingGate = AuditEvidenceSamplingGate(),
) {
    private var nextSequence = 0L

    @Synchronized
    fun process(
        stepId: String?,
        source: Bitmap,
        timestampMs: Long,
    ): AuditRedactedEvidenceFrame? {
        val normalizedStep = stepId?.trim().orEmpty()
        if (!samplingGate.shouldAccept(normalizedStep, timestampMs)) return null

        val faces = detector.detectVideoFrame(source, timestampMs)
        val result = redactor.redact(
            source = source,
            regions = faces,
            frameSequence = nextSequence,
            timestampMs = timestampMs,
        )
        samplingGate.recordAccepted(normalizedStep, timestampMs)
        nextSequence += 1

        return AuditRedactedEvidenceFrame(
            stepId = normalizedStep,
            sequence = result.frameSequence,
            timestampMs = result.timestampMs,
            detectedFaceCount = result.detectedFaceCount,
            bitmap = result.redactedBitmap,
            detectorModelReceipt = detector.modelReceipt,
        )
    }

    fun coverageSnapshot(): AuditEvidenceSamplingSnapshot = samplingGate.snapshot()
}
