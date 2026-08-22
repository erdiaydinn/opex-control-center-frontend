package com.eay.mobile.fieldui

import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Surface
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.unit.dp
import androidx.lifecycle.LifecycleOwner


data class AuditVideoCaptureCopy(
    val privacyLabel: String,
    val privacyPassedLabel: String,
    val privacyPendingLabel: String,
    val privacyBlockedLabel: String,
    val instructionLabel: String,
    val recordingLabel: String,
    val readyLabel: String,
    val cameraUnavailableLabel: String,
    val tapToRecordLabel: String,
    val tapToStopLabel: String,
    val rawProcessingLabel: String,
)

/**
 * Native capture-first audit experience. This screen is intentionally not the desktop Audit
 * Command Center squeezed into a phone. It exposes only field guidance and capture state; audit
 * questions remain server-owned and are not shown to the person collecting evidence.
 *
 * When a privacy frame processor is supplied, CameraX analysis candidates are converted into
 * redacted evidence frames on device. The UI callback never receives the raw candidate bitmap.
 */
@Composable
fun EayAuditVideoCaptureScreen(
    lifecycleOwner: LifecycleOwner,
    steps: List<AuditCaptureStep>,
    activeStepId: String?,
    privacyState: AuditPrivacyState,
    copy: AuditVideoCaptureCopy,
    onRawVideoCaptured: (AuditRawVideoCapture) -> Unit,
    onClose: () -> Unit,
    onCaptureError: (Throwable) -> Unit,
    modifier: Modifier = Modifier,
    frameProcessor: AuditLocalRedactedFrameProcessor? = null,
    onRedactedEvidenceFrame: (AuditRedactedEvidenceFrame) -> Unit = {},
) {
    val controller = rememberAuditCameraXController()
    var cameraReady by remember { mutableStateOf(false) }
    var recording by remember { mutableStateOf(false) }
    var localError by remember { mutableStateOf<String?>(null) }

    val activeIndex = steps.indexOfFirst { it.stepId == activeStepId }.let { index ->
        if (index >= 0) index else 0
    }
    val activeStep = steps.getOrNull(activeIndex)
    val captureAllowed = cameraReady && privacyState != AuditPrivacyState.BLOCKED && localError == null

    Box(modifier = modifier.fillMaxSize().background(Color.Black)) {
        EayAuditCameraSurface(
            controller = controller,
            lifecycleOwner = lifecycleOwner,
            modifier = Modifier.fillMaxSize(),
            frameProcessor = frameProcessor,
            activeStepId = { activeStep?.stepId },
            onRedactedEvidenceFrame = onRedactedEvidenceFrame,
            onReady = {
                cameraReady = true
                localError = null
            },
            onError = { error ->
                cameraReady = false
                localError = error.message ?: copy.cameraUnavailableLabel
                onCaptureError(error)
            },
        )

        Box(
            modifier = Modifier
                .fillMaxWidth()
                .height(180.dp)
                .background(Color.Black.copy(alpha = .38f))
                .align(Alignment.TopCenter),
        )

        Row(
            modifier = Modifier
                .fillMaxWidth()
                .padding(horizontal = 16.dp, vertical = 18.dp)
                .align(Alignment.TopCenter),
            horizontalArrangement = Arrangement.SpaceBetween,
            verticalAlignment = Alignment.CenterVertically,
        ) {
            Surface(
                color = Color.Black.copy(alpha = .62f),
                contentColor = Color.White,
                shape = RoundedCornerShape(99.dp),
            ) {
                Row(
                    modifier = Modifier.padding(horizontal = 12.dp, vertical = 8.dp),
                    horizontalArrangement = Arrangement.spacedBy(7.dp),
                    verticalAlignment = Alignment.CenterVertically,
                ) {
                    Box(
                        modifier = Modifier
                            .size(8.dp)
                            .clip(CircleShape)
                            .background(
                                when (privacyState) {
                                    AuditPrivacyState.PASSED -> Color(0xFF31D69B)
                                    AuditPrivacyState.BLOCKED -> Color(0xFFFF5B70)
                                    AuditPrivacyState.REDACTING -> Color(0xFFFFC857)
                                    AuditPrivacyState.PENDING -> Color(0xFFB4C0CF)
                                },
                            ),
                    )
                    Text(
                        text = "${copy.privacyLabel} · ${privacyStateLabel(privacyState, copy)}",
                        style = MaterialTheme.typography.labelSmall,
                        fontWeight = FontWeight.Bold,
                    )
                }
            }

            Surface(
                modifier = Modifier.size(42.dp).clickable(onClick = onClose),
                color = Color.Black.copy(alpha = .62f),
                contentColor = Color.White,
                shape = CircleShape,
            ) {
                Box(contentAlignment = Alignment.Center) {
                    Text("×", style = MaterialTheme.typography.titleLarge, fontWeight = FontWeight.Light)
                }
            }
        }

        Column(
            modifier = Modifier
                .fillMaxWidth()
                .align(Alignment.BottomCenter)
                .background(Color.Black.copy(alpha = .78f))
                .padding(horizontal = 18.dp, vertical = 18.dp),
            horizontalAlignment = Alignment.CenterHorizontally,
        ) {
            Text(
                text = copy.instructionLabel.uppercase(),
                color = Color(0xFF8DBEFF),
                style = MaterialTheme.typography.labelSmall,
                fontWeight = FontWeight.Black,
            )
            Spacer(modifier = Modifier.height(5.dp))
            Text(
                text = activeStep?.title ?: copy.readyLabel,
                color = Color.White,
                style = MaterialTheme.typography.titleLarge,
                fontWeight = FontWeight.ExtraBold,
                textAlign = TextAlign.Center,
            )
            if (!activeStep?.hint.isNullOrBlank()) {
                Spacer(modifier = Modifier.height(4.dp))
                Text(
                    text = activeStep?.hint.orEmpty(),
                    color = Color.White.copy(alpha = .72f),
                    style = MaterialTheme.typography.bodySmall,
                    textAlign = TextAlign.Center,
                )
            }

            Spacer(modifier = Modifier.height(13.dp))
            Row(
                horizontalArrangement = Arrangement.spacedBy(6.dp),
                verticalAlignment = Alignment.CenterVertically,
            ) {
                steps.forEachIndexed { index, step ->
                    val done = step.state == AuditCaptureStepState.CAPTURED || index < activeIndex
                    val active = index == activeIndex
                    Box(
                        modifier = Modifier
                            .size(width = if (active) 30.dp else 18.dp, height = 5.dp)
                            .clip(RoundedCornerShape(99.dp))
                            .background(
                                when {
                                    done -> Color(0xFF31D69B)
                                    active -> Color(0xFF66AFFF)
                                    else -> Color.White.copy(alpha = .24f)
                                },
                            ),
                    )
                }
            }

            localError?.let { message ->
                Spacer(modifier = Modifier.height(12.dp))
                Text(
                    text = message,
                    color = Color(0xFFFF8B9A),
                    style = MaterialTheme.typography.bodySmall,
                    textAlign = TextAlign.Center,
                )
            }

            Spacer(modifier = Modifier.height(16.dp))
            Box(
                modifier = Modifier
                    .size(78.dp)
                    .clip(CircleShape)
                    .border(4.dp, Color.White.copy(alpha = if (captureAllowed) 1f else .35f), CircleShape)
                    .padding(7.dp)
                    .clip(CircleShape)
                    .background(
                        if (recording) Color(0xFFFF405D)
                        else if (captureAllowed) Color.White
                        else Color.White.copy(alpha = .25f),
                    )
                    .clickable(enabled = captureAllowed) {
                        if (recording) {
                            controller.stopRecording()
                        } else {
                            controller.startPrivateVideo(
                                onStarted = {
                                    recording = true
                                    localError = null
                                },
                                onFinalized = { raw, event ->
                                    recording = false
                                    if (event.hasError()) {
                                        controller.discardRawCapture(raw)
                                        val error = IllegalStateException(
                                            "CameraX video finalize error ${event.error}",
                                        )
                                        localError = error.message
                                        onCaptureError(error)
                                    } else {
                                        try {
                                            onRawVideoCaptured(controller.handoffRawCapture(raw))
                                        } catch (error: Throwable) {
                                            raw.discardIfOpen()
                                            localError = error.message ?: copy.rawProcessingLabel
                                            onCaptureError(error)
                                        }
                                    }
                                },
                                onError = { error ->
                                    recording = false
                                    localError = error.message ?: copy.cameraUnavailableLabel
                                    onCaptureError(error)
                                },
                            )
                        }
                    },
            )
            Spacer(modifier = Modifier.height(8.dp))
            Text(
                text = when {
                    !captureAllowed -> copy.cameraUnavailableLabel
                    recording -> copy.tapToStopLabel
                    else -> copy.tapToRecordLabel
                },
                color = Color.White.copy(alpha = .78f),
                style = MaterialTheme.typography.labelSmall,
                fontWeight = FontWeight.SemiBold,
            )
            if (recording) {
                Spacer(modifier = Modifier.height(4.dp))
                Text(
                    text = copy.recordingLabel,
                    color = Color(0xFFFF8494),
                    style = MaterialTheme.typography.labelSmall,
                    fontWeight = FontWeight.Bold,
                )
            }
        }
    }
}

private fun privacyStateLabel(state: AuditPrivacyState, copy: AuditVideoCaptureCopy): String =
    when (state) {
        AuditPrivacyState.PASSED -> copy.privacyPassedLabel
        AuditPrivacyState.BLOCKED -> copy.privacyBlockedLabel
        AuditPrivacyState.REDACTING -> copy.privacyPendingLabel
        AuditPrivacyState.PENDING -> copy.privacyPendingLabel
    }
