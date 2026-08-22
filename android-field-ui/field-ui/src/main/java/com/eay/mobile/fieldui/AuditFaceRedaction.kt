package com.eay.mobile.fieldui

import android.content.Context
import android.graphics.Bitmap
import android.graphics.Canvas
import android.graphics.Rect
import android.graphics.RectF
import com.google.mediapipe.framework.image.BitmapImageBuilder
import com.google.mediapipe.tasks.core.BaseOptions
import com.google.mediapipe.tasks.vision.core.RunningMode
import com.google.mediapipe.tasks.vision.facedetector.FaceDetector
import java.io.Closeable
import kotlin.math.ceil
import kotlin.math.floor
import kotlin.math.max

class AuditPrivacyInitializationException(message: String, cause: Throwable? = null) :
    IllegalStateException(message, cause)

data class AuditFaceRegion(
    val left: Int,
    val top: Int,
    val right: Int,
    val bottom: Int,
) {
    val width: Int get() = right - left
    val height: Int get() = bottom - top

    fun isValid(): Boolean = left >= 0 && top >= 0 && width > 0 && height > 0
}

data class AuditFrameCoverageResult(
    val frameSequence: Long,
    val timestampMs: Long,
    val processed: Boolean,
)

data class AuditFrameRedactionResult(
    val frameSequence: Long,
    val timestampMs: Long,
    val redactedBitmap: Bitmap,
    val detectedFaceCount: Int,
    val processed: Boolean,
) {
    fun coverage(): AuditFrameCoverageResult = AuditFrameCoverageResult(
        frameSequence = frameSequence,
        timestampMs = timestampMs,
        processed = processed,
    )
}

/**
 * Synchronous face detector used for canonical evidence processing.
 *
 * EAY intentionally uses VIDEO mode here instead of LIVE_STREAM. MediaPipe live-stream
 * tasks may drop input frames to reduce latency; a privacy boundary cannot treat a dropped
 * frame as anonymized. The detector cannot initialize until the packaged model asset passes
 * explicit SHA-256, byte-count, provenance and license admission.
 */
class MediaPipeAuditFaceDetector private constructor(
    private val detector: FaceDetector,
    val modelReceipt: AuditModelAssetReceipt,
) : Closeable {

    fun detectVideoFrame(bitmap: Bitmap, timestampMs: Long): List<AuditFaceRegion> {
        require(timestampMs >= 0L) { "timestampMs must be non-negative" }
        val mpImage = BitmapImageBuilder(bitmap).build()
        val result = detector.detectForVideo(mpImage, timestampMs)
        return result.detections().mapNotNull { detection ->
            detection.boundingBox().toAuditFaceRegion(bitmap.width, bitmap.height)
        }
    }

    override fun close() {
        detector.close()
    }

    companion object {
        const val DEFAULT_MIN_CONFIDENCE = 0.65f

        fun create(
            context: Context,
            modelPolicy: AuditModelAssetPolicy,
            minDetectionConfidence: Float = DEFAULT_MIN_CONFIDENCE,
        ): MediaPipeAuditFaceDetector {
            require(minDetectionConfidence in 0f..1f) {
                "minDetectionConfidence must be between 0 and 1"
            }

            try {
                val receipt = AuditModelAssetAdmission.verify(modelPolicy) {
                    context.assets.open(modelPolicy.assetPath)
                }
                val baseOptions = BaseOptions.builder()
                    .setModelAssetPath(modelPolicy.assetPath)
                    .build()
                val options = FaceDetector.FaceDetectorOptions.builder()
                    .setBaseOptions(baseOptions)
                    .setRunningMode(RunningMode.VIDEO)
                    .setMinDetectionConfidence(minDetectionConfidence)
                    .build()
                return MediaPipeAuditFaceDetector(
                    detector = FaceDetector.createFromOptions(context, options),
                    modelReceipt = receipt,
                )
            } catch (error: AuditModelAssetAdmissionException) {
                throw AuditPrivacyInitializationException(error.message ?: "Privacy model rejected", error)
            } catch (error: Exception) {
                throw AuditPrivacyInitializationException(
                    "Face-redaction detector could not initialize; audit media remains blocked",
                    error,
                )
            }
        }
    }
}

class BitmapAuditFaceRedactor(
    private val pixelBlockSize: Int = 18,
    private val expansionRatio: Float = 0.18f,
) {
    init {
        require(pixelBlockSize >= 4) { "pixelBlockSize must be at least 4" }
        require(expansionRatio in 0f..1f) { "expansionRatio must be between 0 and 1" }
    }

    fun redact(
        source: Bitmap,
        regions: List<AuditFaceRegion>,
        frameSequence: Long,
        timestampMs: Long,
    ): AuditFrameRedactionResult {
        require(frameSequence >= 0L) { "frameSequence must be non-negative" }
        require(timestampMs >= 0L) { "timestampMs must be non-negative" }

        val output = source.copy(Bitmap.Config.ARGB_8888, true)
            ?: throw IllegalStateException("Could not allocate redacted frame")
        val canvas = Canvas(output)

        regions.forEach { region ->
            val expanded = region.expandAndClamp(source.width, source.height, expansionRatio)
            if (!expanded.isValid()) return@forEach

            val crop = Bitmap.createBitmap(
                source,
                expanded.left,
                expanded.top,
                expanded.width,
                expanded.height,
            )
            val tinyWidth = max(1, expanded.width / pixelBlockSize)
            val tinyHeight = max(1, expanded.height / pixelBlockSize)
            val tiny = Bitmap.createScaledBitmap(crop, tinyWidth, tinyHeight, false)
            val pixelated = Bitmap.createScaledBitmap(tiny, expanded.width, expanded.height, false)
            canvas.drawBitmap(
                pixelated,
                null,
                Rect(expanded.left, expanded.top, expanded.right, expanded.bottom),
                null,
            )
            if (pixelated !== tiny) pixelated.recycle()
            tiny.recycle()
            crop.recycle()
        }

        return AuditFrameRedactionResult(
            frameSequence = frameSequence,
            timestampMs = timestampMs,
            redactedBitmap = output,
            detectedFaceCount = regions.size,
            processed = true,
        )
    }
}

class AuditRedactionCoverageLedger(
    expectedFrameCount: Long,
) {
    private val expected = expectedFrameCount
    private val processedSequences = linkedSetOf<Long>()
    private var blockedReason: String? = null

    init {
        require(expectedFrameCount > 0L) { "expectedFrameCount must be positive" }
    }

    fun record(result: AuditFrameRedactionResult) = record(result.coverage())

    fun record(result: AuditFrameCoverageResult) {
        if (!result.processed) {
            block("frame_${result.frameSequence}_was_not_processed")
            return
        }
        if (result.frameSequence !in 0 until expected) {
            block("frame_sequence_out_of_range")
            return
        }
        processedSequences += result.frameSequence
    }

    fun block(reason: String) {
        if (blockedReason == null) {
            blockedReason = reason.ifBlank { "privacy_redaction_failed" }
        }
    }

    fun isComplete(): Boolean = blockedReason == null && processedSequences.size.toLong() == expected

    fun missingFrameCount(): Long = expected - processedSequences.size.toLong()

    fun failureReason(): String? = blockedReason

    fun assertPromotable() {
        check(isComplete()) {
            blockedReason ?: "privacy_redaction_incomplete:${missingFrameCount()}_frames_missing"
        }
    }
}

private fun RectF.toAuditFaceRegion(imageWidth: Int, imageHeight: Int): AuditFaceRegion? {
    val region = AuditFaceRegion(
        left = floor(left).toInt().coerceIn(0, imageWidth),
        top = floor(top).toInt().coerceIn(0, imageHeight),
        right = ceil(right).toInt().coerceIn(0, imageWidth),
        bottom = ceil(bottom).toInt().coerceIn(0, imageHeight),
    )
    return region.takeIf { it.isValid() }
}

private fun AuditFaceRegion.expandAndClamp(
    imageWidth: Int,
    imageHeight: Int,
    ratio: Float,
): AuditFaceRegion {
    val xPad = width * ratio
    val yPad = height * ratio
    return AuditFaceRegion(
        left = floor(left - xPad).toInt().coerceIn(0, imageWidth),
        top = floor(top - yPad).toInt().coerceIn(0, imageHeight),
        right = ceil(right + xPad).toInt().coerceIn(0, imageWidth),
        bottom = ceil(bottom + yPad).toInt().coerceIn(0, imageHeight),
    )
}
