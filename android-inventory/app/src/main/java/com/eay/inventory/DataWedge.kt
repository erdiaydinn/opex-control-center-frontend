package com.eay.inventory

import android.content.Context
import android.content.Intent
import android.content.pm.PackageManager
import android.os.Build
import android.os.Bundle
import com.eay.mobile.core.BarcodeSymbology
import com.eay.mobile.core.ScannerIngress
import com.eay.mobile.core.ScannerSource
import java.security.MessageDigest
import java.security.SecureRandom
import java.util.concurrent.atomic.AtomicLong

object DataWedge {
    private const val ACTION_PREFIX = "com.eay.inventory.SCAN."
    private const val CATEGORY_PREFIX = "com.eay.inventory.CATEGORY."
    private const val DATA_STRING = "com.symbol.datawedge.data_string"
    private const val LABEL_TYPE = "com.symbol.datawedge.label_type"
    private const val SOURCE = "com.symbol.datawedge.source"

    data class Session internal constructor(
        val action: String,
        val category: String,
        private val sessionId: String,
    ) {
        private val sequence = AtomicLong(0)

        fun toScannerIngress(
            intent: Intent,
            receivedAtEpochMs: Long,
        ): ScannerIngress? {
            if (intent.action != action) return null
            if (intent.categories?.contains(category) != true) return null
            if (intent.getStringExtra(SOURCE) != "scanner") return null

            val rawValue = intent.getStringExtra(DATA_STRING) ?: return null
            val label = intent.getStringExtra(LABEL_TYPE).orEmpty()
            return ScannerIngress(
                sourceEventId = "$sessionId-${sequence.incrementAndGet()}",
                source = ScannerSource.HARDWARE_DATAWEDGE,
                symbology = mapSymbology(label),
                rawValue = rawValue,
                capturedAtEpochMs = receivedAtEpochMs,
            )
        }
    }

    fun startSession(context: Context): Session {
        TerminalFeedbackRuntime.initialize(context)
        val sessionId = randomSessionId()
        val session = Session(
            action = ACTION_PREFIX + sessionId,
            category = CATEGORY_PREFIX + sessionId,
            sessionId = sessionId,
        )
        configure(context, session)
        return session
    }

    private fun configure(context: Context, session: Session) {
        val barcodePlugin = Bundle().apply {
            putString("PLUGIN_NAME", "BARCODE")
            // Preserve device/model-specific decoder tuning while enforcing the
            // feedback and scanner-enable baseline across the managed Zebra fleet.
            putString("RESET_CONFIG", "false")
            putBundle(
                "PARAM_LIST",
                Bundle().apply {
                    putString("scanner_input_enabled", "true")
                    putString("configure_all_scanners", "true")
                    putString("decode_haptic_feedback", "1")
                    putString("decoding_led_feedback", "1")
                    putString("volume_slider_type", "3")
                },
            )
        }
        val intentPlugin = Bundle().apply {
            putString("PLUGIN_NAME", "INTENT")
            putString("RESET_CONFIG", "true")
            putBundle(
                "PARAM_LIST",
                Bundle().apply {
                    putString("intent_output_enabled", "true")
                    putString("intent_action", session.action)
                    putString("intent_category", session.category)
                    putString("intent_delivery", "2")
                    putParcelableArrayList(
                        "intent_component_info",
                        secureComponentInfo(context),
                    )
                },
            )
        }
        val profile = Bundle().apply {
            putString("PROFILE_NAME", "EAY_INVENTORY_PRODUCTION")
            putString("PROFILE_ENABLED", "true")
            putString("CONFIG_MODE", "CREATE_IF_NOT_EXIST")
            putParcelableArray(
                "APP_LIST",
                arrayOf(
                    Bundle().apply {
                        putString("PACKAGE_NAME", context.packageName)
                        putStringArray("ACTIVITY_LIST", arrayOf("*"))
                    },
                ),
            )
            putParcelableArray("PLUGIN_CONFIG", arrayOf(barcodePlugin, intentPlugin))
        }
        context.sendBroadcast(
            Intent("com.symbol.datawedge.api.ACTION").apply {
                setPackage("com.symbol.datawedge")
                putExtra("com.symbol.datawedge.api.SET_CONFIG", profile)
            },
        )
    }

    private fun secureComponentInfo(context: Context): ArrayList<Bundle> {
        val signatures = applicationSigningSha1(context)
        check(signatures.isNotEmpty()) { "Application signing identity unavailable" }
        return ArrayList<Bundle>().apply {
            signatures.forEach { digest ->
                add(
                    Bundle().apply {
                        putString("PACKAGE_NAME", context.packageName)
                        putString("SIGNATURE", digest)
                    },
                )
            }
        }
    }

    private fun applicationSigningSha1(context: Context): List<String> {
        val packageInfo = if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.P) {
            context.packageManager.getPackageInfo(
                context.packageName,
                PackageManager.GET_SIGNING_CERTIFICATES,
            )
        } else {
            @Suppress("DEPRECATION")
            context.packageManager.getPackageInfo(
                context.packageName,
                PackageManager.GET_SIGNATURES,
            )
        }

        val signatures = if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.P) {
            val signingInfo = packageInfo.signingInfo
                ?: error("Application signingInfo unavailable")
            if (signingInfo.hasMultipleSigners()) {
                signingInfo.apkContentsSigners.toList()
            } else {
                signingInfo.signingCertificateHistory.toList()
            }
        } else {
            @Suppress("DEPRECATION")
            packageInfo.signatures.orEmpty().toList()
        }

        return signatures
            .map { signature ->
                MessageDigest.getInstance("SHA-1")
                    .digest(signature.toByteArray())
                    .joinToString("") { "%02X".format(it) }
            }
            .distinct()
    }

    private fun randomSessionId(): String {
        val bytes = ByteArray(16).also { SecureRandom().nextBytes(it) }
        return bytes.joinToString("") { "%02x".format(it) }
    }

    private fun mapSymbology(label: String): BarcodeSymbology = when (
        label.trim().uppercase()
    ) {
        "LABEL-TYPE-EAN8", "EAN8" -> BarcodeSymbology.EAN8
        "LABEL-TYPE-EAN13", "EAN13" -> BarcodeSymbology.EAN13
        "LABEL-TYPE-UPCA", "UPCA" -> BarcodeSymbology.UPCA
        "LABEL-TYPE-CODE128", "CODE128" -> BarcodeSymbology.CODE128
        "LABEL-TYPE-EAN128", "EAN128", "LABEL-TYPE-GS1-128", "GS1-128" ->
            BarcodeSymbology.GS1_128
        "LABEL-TYPE-QRCODE", "QRCODE", "QR" -> BarcodeSymbology.QR
        "LABEL-TYPE-DATAMATRIX", "DATAMATRIX" -> BarcodeSymbology.DATAMATRIX
        else -> BarcodeSymbology.UNKNOWN
    }
}
