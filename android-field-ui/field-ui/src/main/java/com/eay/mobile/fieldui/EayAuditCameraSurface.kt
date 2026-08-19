package com.eay.mobile.fieldui

import android.content.Context
import android.graphics.Bitmap
import android.graphics.Matrix
import android.os.Handler
import android.os.Looper
import androidx.camera.core.CameraSelector
import androidx.camera.core.ImageAnalysis
import androidx.camera.core.Preview
import androidx.camera.lifecycle.ProcessCameraProvider
import androidx.camera.video.FallbackStrategy
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
import androidx.compose.runtime.key
import androidx.compose.runtime.remember
import androidx.compose.runtime.rememberUpdatedState
import androidx.compose.ui.Modifier
import androidx.compose.ui.viewinterop.AndroidView
import androidx.lifecycle.LifecycleOwner
import java.io.Closeable
import java.io.File
import java.util.UUID
import java.util.concurrent.Executor
import java.util.concurrent.Executors

class AuditCameraXController(
    private val context: Context,
) : Closeable {
    private val mainExecutor: Executor = Executor { command ->
        Handler(Looper.getMainLooper()).post(command)
    }
    private val analysisExecutor = Executors.newSingleThreadExecutor()
    private val rawLeases = linkedSetOf<AuditRawVideoCapture>()
    private var provider: ProcessCameraProvider? = null
    private var videoCapture: VideoCapture<Recorder>? = null
    private var imageAnalysis: ImageAnalysis? = null
    private var recording: Recording? = null

    fun bind(
        lifecycleOwner: LifecycleOwner,
        previewView: PreviewView,
        lensFacing: Int = CameraSelector.LENS_FACING_BACK,
        frameProcessor: AuditLocalRedactedFrameProcessor? = null,
        activeStepId: () -> String? = { null },
        onRedactedEvidenceFrame: (AuditRedactedEvidenceFrame) -> Unit = {},
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
                                FallbackStrategy.lowerQualityOrHigherThan(Quality.HD),
                            ),
                        )
                        .build()
                    val video = VideoCapture.withOutput(recorder)
                    val selector = CameraSelector.Builder()
                        .requireLensFacing(lensFacing)
                        .build()

                    imageAnalysis?.clearAnalyzer()
                    cameraProvider.unbindAll()

                    val analysis = frameProcessor?.let { processor ->
                        ImageAnalysis.Builder()
                            .setOutputImageFormat(ImageAnalysis.OUTPUT_IMAGE_FORMAT_RGBA_8888)
                            .setBackpressureStrategy(ImageAnalysis.STRATEGY_KEEP_ONLY_LATEST)
                            .build()
                            .also { useCase ->
                                useCase.setAnalyzer(analysisExecutor) { image ->
                                    val timestampMs = image.imageInfo.timestamp / 1_000_000L
                                    val bitmap = try {
                                        image.toBitmap()
                                    } catch (error: Throwable) {
                                        image.close()
                                        mainExecutor.execute { onError(error) }
                                        return@setAnalyzer
                                    }
                                    var orientedBitmap: Bitmap = bitmap
                                    try {
                                        orientedBitmap = bitmap.rotateForAudit(
                                            image.imageInfo.rotationDegrees,
                                        )
                                        val evidence = processor.process(
                                            stepId = activeStepId(),
                                            source = orientedBitmap,
                                            timestampMs = timestampMs,
                                        )
                                        if (evidence != null) {
                                            mainExecutor.execute {
                                                onRedactedEvidenceFrame(evidence)
                                            }
                                        }
                                    } catch (error: Throwable) {
                                        mainExecutor.execute { onError(error) }
                                    } finally {
                                        if (orientedBitmap !== bitmap) {
                                            orientedBitmap.recycle()
                                        }
                                        bitmap.recycle()
                                        image.close()
                                    }
                                }
                            }
                    }

                    if (analysis == null) {
                        cameraProvider.bindToLifecycle(lifecycleOwner, selector, preview, video)
                    } else {
                        cameraProvider.bindToLifecycle(
                            lifecycleOwner,
                            selector,
                            preview,
                            video,
                            analysis,
                        )
                    }
                    provider = cameraProvider
                    videoCapture = video
                    imageAnalysis = analysis
                    onReady()
                } catch (error: Throwable) {
                    imageAnalysis?.clearAnalyzer()
                    imageAnalysis = null
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
        rawLeases += raw

        try {
            val options = FileOutputOptions.Builder(raw.recordingFile()).build()
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
            rawLeases -= raw
            raw.discardIfOpen()
            recording = null
            onError(error)
        }
    }

    /**
     * Transfers raw-media responsibility to the caller without exposing the backing File.
     * The receiver must call consumeAndDelete() or discard() on the returned one-shot lease.
     */
    fun handoffRawCapture(raw: AuditRawVideoCapture): AuditRawVideoCapture {
        check(rawLeases.remove(raw)) { "Raw capture does not belong to this controller" }
        return raw
    }

    fun <T> consumeRawCapture(
        raw: AuditRawVideoCapture,
        processor: (File) -> T,
    ): T {
        check(rawLeases.remove(raw)) { "Raw capture does not belong to this controller" }
        return raw.consumeAndDelete(processor)
    }

    fun discardRawCapture(raw: AuditRawVideoCapture) {
        check(rawLeases.remove(raw)) { "Raw capture does not belong to this controller" }
        raw.discard()
    }

    fun stopRecording() {
        recording?.stop()
    }

    fun cancelRecording() {
        recording?.close()
        recording = null
    }

    fun isRecording(): Boolean = recording != null

    override fun close() {
        recording?.close()
        recording = null
        imageAnalysis?.clearAnalyzer()
        imageAnalysis = null
        rawLeases.toList().forEach { lease ->
            lease.discardIfOpen()
            rawLeases -= lease
        }
        provider?.unbindAll()
        provider = null
        videoCapture = null
        analysisExecutor.shutdownNow()
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
fun rememberAuditCameraXController(): AuditCameraXController {
    val context = androidx.compose.ui.platform.LocalContext.current
    val controller = remember(context) { AuditCameraXController(context.applicationContext) }
    DisposableEffect(controller) {
        onDispose { controller.close() }
    }
    return controller
}

@Composable
fun EayAuditCameraSurface(
    controller: AuditCameraXController,
    lifecycleOwner: LifecycleOwner,
    modifier: Modifier = Modifier,
    lensFacing: Int = CameraSelector.LENS_FACING_BACK,
    frameProcessor: AuditLocalRedactedFrameProcessor? = null,
    activeStepId: () -> String? = { null },
    onRedactedEvidenceFrame: (AuditRedactedEvidenceFrame) -> Unit = {},
    onReady: () -> Unit = {},
    onError: (Throwable) -> Unit = {},
) {
    val currentActiveStepId = rememberUpdatedState(activeStepId)
    val currentEvidenceCallback = rememberUpdatedState(onRedactedEvidenceFrame)
    val currentReadyCallback = rememberUpdatedState(onReady)
    val currentErrorCallback = rememberUpdatedState(onError)

    key(controller, lifecycleOwner, lensFacing, frameProcessor) {
        AndroidView(
            modifier = modifier,
            factory = { viewContext ->
                PreviewView(viewContext).apply {
                    implementationMode = PreviewView.ImplementationMode.COMPATIBLE
                    scaleType = PreviewView.ScaleType.FILL_CENTER
                    controller.bind(
                        lifecycleOwner = lifecycleOwner,
                        previewView = this,
                        lensFacing = lensFacing,
                        frameProcessor = frameProcessor,
                        activeStepId = { currentActiveStepId.value.invoke() },
                        onRedactedEvidenceFrame = { frame ->
                            currentEvidenceCallback.value.invoke(frame)
                        },
                        onReady = { currentReadyCallback.value.invoke() },
                        onError = { error -> currentErrorCallback.value.invoke(error) },
                    )
                }
            },
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
    val controller = rememberAuditCameraXController()
    EayAuditCameraSurface(
        controller = controller,
        lifecycleOwner = lifecycleOwner,
        modifier = modifier,
        lensFacing = lensFacing,
        onReady = onReady,
        onError = onError,
    )
}

private fun Bitmap.rotateForAudit(rotationDegrees: Int): Bitmap {
    val normalized = ((rotationDegrees % 360) + 360) % 360
    if (normalized == 0) return this
    val matrix = Matrix().apply { postRotate(normalized.toFloat()) }
    return Bitmap.createBitmap(this, 0, 0, width, height, matrix, true)
}
