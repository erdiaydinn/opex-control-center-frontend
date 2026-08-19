package com.eay.mobile.fieldui

import android.content.Context
import android.os.Handler
import android.os.Looper
import androidx.camera.core.CameraSelector
import androidx.camera.core.Preview
import androidx.camera.lifecycle.ProcessCameraProvider
import androidx.camera.video.FileOutputOptions
import androidx.camera.video.Quality
import androidx.camera.video.QualitySelector
import androidx.camera.video.Recorder
import androidx.camera.video.Recording
import androidx.camera.video.VideoCapture
import androidx.camera.video.VideoRecordEvent
import androidx.camera.view.PreviewView
import androidx.compose.runtime.Composable
import androidx.compose.runtime.DisposableEffect
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.remember
import androidx.compose.ui.Modifier
import androidx.compose.ui.viewinterop.AndroidView
import androidx.lifecycle.LifecycleOwner
import java.io.Closeable
import java.io.File
import java.util.UUID
import java.util.concurrent.Executor

/**
 * Handle to raw device-private capture. It is intentionally not an evidence receipt.
 * The file must be deleted after privacy post-processing succeeds or fails.
 */
data class AuditRawVideoCapture(
    val captureId: UUID,
    val privateFile: File,
)

class AuditCameraXController(
    private val context: Context,
) : Closeable {
    private val mainExecutor: Executor = Executor { command ->
        Handler(Looper.getMainLooper()).post(command)
    }
    private var provider: ProcessCameraProvider? = null
    private var videoCapture: VideoCapture<Recorder>? = null
    private var recording: Recording? = null

    fun bind(
        lifecycleOwner: LifecycleOwner,
        previewView: PreviewView,
        lensFacing: Int = CameraSelector.LENS_FACING_BACK,
        onReady: () -> Unit = {},
        onError: (Throwable) -> Unit = {},
    ) {
        val providerFuture = ProcessCameraProvider.getInstance(context)
        providerFuture.addListener(
            {
                try {
                    val cameraProvider = providerFuture.get()
                    val preview = Preview.Builder().build().also { useCase ->
                        useCase.setSurfaceProvider(previewView.surfaceProvider)
                    }
                    val recorder = Recorder.Builder()
                        .setQualitySelector(
                            QualitySelector.from(
                                Quality.HD,
                                QualitySelector.FALLBACK_STRATEGY_HIGHER_QUALITY_OR_LOWER_THAN,
                            ),
                        )
                        .build()
                    val video = VideoCapture.withOutput(recorder)
                    val selector = CameraSelector.Builder()
                        .requireLensFacing(lensFacing)
                        .build()

                    cameraProvider.unbindAll()
                    cameraProvider.bindToLifecycle(lifecycleOwner, selector, preview, video)
                    provider = cameraProvider
                    videoCapture = video
                    onReady()
                } catch (error: Throwable) {
                    videoCapture = null
                    onError(error)
                }
            },
            mainExecutor,
        )
    }

    fun startPrivateVideo(
        onStarted: (AuditRawVideoCapture) -> Unit,
        onFinalized: (AuditRawVideoCapture, VideoRecordEvent.Finalize) -> Unit,
        onError: (Throwable) -> Unit,
    ) {
        check(recording == null) { "Audit recording is already active" }
        val video = checkNotNull(videoCapture) { "CameraX audit capture is not bound" }
        val raw = newRawCapture()

        try {
            val options = FileOutputOptions.Builder(raw.privateFile).build()
            val pending = video.output.prepareRecording(context, options)
            recording = pending.start(mainExecutor) { event ->
                when (event) {
                    is VideoRecordEvent.Start -> onStarted(raw)
                    is VideoRecordEvent.Finalize -> {
                        recording = null
                        onFinalized(raw, event)
                    }
                }
            }
        } catch (error: Throwable) {
            raw.privateFile.delete()
            recording = null
            onError(error)
        }
    }

    fun stopRecording() {
        recording?.stop()
    }

    fun cancelRecording() {
        recording?.close()
        recording = null
    }

    override fun close() {
        recording?.close()
        recording = null
        provider?.unbindAll()
        provider = null
        videoCapture = null
    }

    private fun newRawCapture(): AuditRawVideoCapture {
        val directory = File(context.cacheDir, "eay-audit-raw").apply {
            if (!exists() && !mkdirs()) {
                throw IllegalStateException("Could not create device-private audit capture directory")
            }
        }
        val captureId = UUID.randomUUID()
        return AuditRawVideoCapture(
            captureId = captureId,
            privateFile = File(directory, "$captureId.mp4"),
        )
    }
}

@Composable
fun EayAuditCameraSurface(
    lifecycleOwner: LifecycleOwner,
    modifier: Modifier = Modifier,
    lensFacing: Int = CameraSelector.LENS_FACING_BACK,
    onReady: () -> Unit = {},
    onError: (Throwable) -> Unit = {},
) {
    val context = androidx.compose.ui.platform.LocalContext.current
    val controller = remember(context) { AuditCameraXController(context.applicationContext) }

    DisposableEffect(controller) {
        onDispose { controller.close() }
    }

    AndroidView(
        modifier = modifier,
        factory = { viewContext ->
            PreviewView(viewContext).apply {
                implementationMode = PreviewView.ImplementationMode.COMPATIBLE
                scaleType = PreviewView.ScaleType.FILL_CENTER
            }
        },
        update = { previewView ->
            controller.bind(
                lifecycleOwner = lifecycleOwner,
                previewView = previewView,
                lensFacing = lensFacing,
                onReady = onReady,
                onError = onError,
            )
        },
    )
}
