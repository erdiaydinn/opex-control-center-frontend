package com.eay.inventory

import android.content.Context
import android.media.AudioManager
import android.media.ToneGenerator
import android.os.Build
import android.os.VibrationEffect
import android.os.Vibrator
import android.os.VibratorManager
import java.util.concurrent.atomic.AtomicLong
import java.util.concurrent.atomic.AtomicReference

/**
 * Business-result feedback, deliberately separate from Zebra/DataWedge decode feedback.
 *
 * DataWedge owns the immediate decode haptic/LED acknowledgement. This layer is
 * emitted only after EAY's local business/controller decision: a short ACK tone
 * for accepted work, and a distinct NACK tone + haptic for rejected work.
 * No barcode, SKU, employee, mission or tenant data enters this component.
 */
object TerminalFeedbackRuntime {
    private val feedback = AtomicReference<TerminalFeedback?>(null)
    private val localDecisionCount = AtomicLong(0)
    private val localDecisionOverBudgetCount = AtomicLong(0)
    private val localDecisionMaxMs = AtomicLong(0)

    const val LOCAL_DECISION_TARGET_MS = 100L

    fun initialize(context: Context) {
        if (feedback.get() == null) {
            feedback.compareAndSet(null, TerminalFeedback(context.applicationContext))
        }
    }

    fun accepted() {
        feedback.get()?.accepted()
    }

    fun rejected() {
        feedback.get()?.rejected()
    }

    fun recordLocalDecision(startedAtNanos: Long, endedAtNanos: Long = System.nanoTime()) {
        if (startedAtNanos <= 0 || endedAtNanos < startedAtNanos) return
        val elapsedMs = (endedAtNanos - startedAtNanos) / 1_000_000L
        localDecisionCount.incrementAndGet()
        localDecisionMaxMs.accumulateAndGet(elapsedMs, ::maxOf)
        if (elapsedMs > LOCAL_DECISION_TARGET_MS) {
            localDecisionOverBudgetCount.incrementAndGet()
        }
    }

    fun performanceSnapshot(): TerminalPerformanceSnapshot = TerminalPerformanceSnapshot(
        localDecisionTargetMs = LOCAL_DECISION_TARGET_MS,
        localDecisionCount = localDecisionCount.get(),
        localDecisionOverBudgetCount = localDecisionOverBudgetCount.get(),
        localDecisionMaxMs = localDecisionMaxMs.get(),
    )

    fun close() {
        feedback.getAndSet(null)?.close()
    }
}

data class TerminalPerformanceSnapshot(
    val localDecisionTargetMs: Long,
    val localDecisionCount: Long,
    val localDecisionOverBudgetCount: Long,
    val localDecisionMaxMs: Long,
) {
    val withinBudgetRate: Double
        get() = if (localDecisionCount == 0L) 1.0 else
            (localDecisionCount - localDecisionOverBudgetCount).toDouble() / localDecisionCount.toDouble()
}

private class TerminalFeedback(context: Context) {
    private val tone = ToneGenerator(AudioManager.STREAM_NOTIFICATION, 70)
    private val vibrator: Vibrator? = if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.S) {
        context.getSystemService(VibratorManager::class.java)?.defaultVibrator
    } else {
        @Suppress("DEPRECATION")
        context.getSystemService(Context.VIBRATOR_SERVICE) as? Vibrator
    }

    fun accepted() {
        // Decode haptic already happened in DataWedge; avoid double-vibration.
        tone.startTone(ToneGenerator.TONE_PROP_ACK, 65)
    }

    fun rejected() {
        tone.startTone(ToneGenerator.TONE_PROP_NACK, 120)
        val current = vibrator ?: return
        if (!current.hasVibrator()) return
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
            current.vibrate(VibrationEffect.createOneShot(90, VibrationEffect.DEFAULT_AMPLITUDE))
        } else {
            @Suppress("DEPRECATION")
            current.vibrate(90)
        }
    }

    fun close() {
        tone.release()
    }
}
