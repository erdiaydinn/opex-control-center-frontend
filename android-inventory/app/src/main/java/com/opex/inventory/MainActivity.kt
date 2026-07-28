package com.opex.inventory

import android.content.BroadcastReceiver
import android.content.Context
import android.content.Intent
import android.content.IntentFilter
import android.graphics.Color
import android.graphics.Typeface
import android.graphics.drawable.GradientDrawable
import android.os.Bundle
import android.os.VibrationEffect
import android.os.Vibrator
import android.provider.Settings
import android.text.InputType
import android.view.Gravity
import android.view.ViewGroup
import android.widget.*
import androidx.appcompat.app.AppCompatActivity
import org.json.JSONArray
import org.json.JSONObject
import java.net.HttpURLConnection
import java.net.URL
import java.util.UUID
import java.util.concurrent.Executors

class MainActivity : AppCompatActivity() {
    private val io = Executors.newSingleThreadExecutor()
    private lateinit var api: EditText
    private lateinit var token: EditText
    private lateinit var document: EditText
    private lateinit var location: EditText
    private lateinit var quantity: EditText
    private lateinit var status: TextView
    private val prefs by lazy { getSharedPreferences("opex_inventory_v22", MODE_PRIVATE) }
    private val deviceId by lazy {
        Settings.Secure.getString(contentResolver, Settings.Secure.ANDROID_ID) ?: UUID.randomUUID().toString()
    }

    private val scanner = object : BroadcastReceiver() {
        override fun onReceive(context: Context?, intent: Intent?) {
            val barcode = intent?.getStringExtra("com.symbol.datawedge.data_string")?.trim().orEmpty()
            val symbology = intent?.getStringExtra("com.symbol.datawedge.label_type").orEmpty()
            if (barcode.isNotEmpty()) submit(barcode, symbology.ifEmpty { "UNKNOWN" })
        }
    }

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        setContentView(buildUi())
        configureDataWedge()
        syncQueue()
    }

    override fun onStart() {
        super.onStart()
        registerReceiver(scanner, IntentFilter(SCAN_ACTION), RECEIVER_EXPORTED)
    }

    override fun onStop() {
        unregisterReceiver(scanner)
        super.onStop()
    }

    private fun buildUi(): LinearLayout {
        val root = LinearLayout(this).apply {
            orientation = LinearLayout.VERTICAL
            setPadding(dp(20), dp(24), dp(20), dp(24))
            setBackgroundColor(Color.rgb(248, 250, 252))
        }

        fun label(textValue: String) = TextView(this).apply {
            text = textValue
            textSize = 13f
            setTextColor(Color.rgb(71, 85, 105))
            setTypeface(typeface, Typeface.BOLD)
            setPadding(dp(2), dp(14), 0, dp(6))
        }.also { root.addView(it, ViewGroup.LayoutParams(-1, -2)) }

        fun field(
            labelText: String,
            hintText: String,
            saved: String = "",
            inputTypeValue: Int = InputType.TYPE_CLASS_TEXT
        ) = EditText(this).apply {
            label(labelText)
            hint = hintText
            setText(saved)
            inputType = inputTypeValue
            textSize = 16f
            setTextColor(Color.rgb(15, 23, 42))
            setHintTextColor(Color.rgb(148, 163, 184))
            background = roundedBackground(Color.WHITE, Color.rgb(203, 213, 225), 12f)
            setPadding(dp(14), dp(12), dp(14), dp(12))
            minHeight = dp(52)
        }.also { root.addView(it, ViewGroup.LayoutParams(-1, -2)) }

        root.addView(TextView(this).apply {
            text = "OPEX Inventory V22"
            textSize = 28f
            setTextColor(Color.rgb(223, 16, 103))
            setTypeface(typeface, Typeface.BOLD)
            setPadding(0, 0, 0, dp(4))
        })

        root.addView(TextView(this).apply {
            text = "Terminal bağlantısı ve sayım ayarları"
            textSize = 14f
            setTextColor(Color.rgb(100, 116, 139))
            setPadding(0, 0, 0, dp(8))
        })

        api = field(
            "API adresi",
            "https://inventory.company.com",
            prefs.getString("api", "https://inventory.company.com").orEmpty(),
            InputType.TYPE_CLASS_TEXT or InputType.TYPE_TEXT_VARIATION_URI
        )
        token = field(
            "SSO erişim anahtarı",
            "Erişim anahtarını girin",
            prefs.getString("token", "").orEmpty(),
            InputType.TYPE_CLASS_TEXT or InputType.TYPE_TEXT_VARIATION_PASSWORD
        )
        document = field(
            "Sayım belge ID",
            "Örn. COUNT-2026-001",
            prefs.getString("document", "").orEmpty()
        )
        location = field("Lokasyon", "Lokasyon barkodunu okutun veya girin")
        quantity = field(
            "Adet",
            "1",
            "1",
            InputType.TYPE_CLASS_NUMBER or InputType.TYPE_NUMBER_FLAG_DECIMAL
        )

        root.addView(Button(this).apply {
            text = "AYARLARI KAYDET VE SENKRONİZE ET"
            textSize = 15f
            setTextColor(Color.WHITE)
            setTypeface(typeface, Typeface.BOLD)
            background = roundedBackground(Color.rgb(223, 16, 103), Color.rgb(223, 16, 103), 12f)
            isAllCaps = false
            minHeight = dp(54)
            setOnClickListener {
                persist()
                syncQueue()
            }
        }, LinearLayout.LayoutParams(-1, -2).apply { topMargin = dp(22) })

        root.addView(Button(this).apply {
            text = "TEST BARKODU GÖNDER"
            textSize = 15f
            setTextColor(Color.rgb(15, 23, 42))
            setTypeface(typeface, Typeface.BOLD)
            background = roundedBackground(Color.WHITE, Color.rgb(148, 163, 184), 12f)
            isAllCaps = false
            minHeight = dp(54)
            setOnClickListener { submit("8690000000001", "EAN13") }
        }, LinearLayout.LayoutParams(-1, -2).apply { topMargin = dp(12) })

        status = TextView(this).apply {
            text = "DataWedge bekleniyor"
            textSize = 16f
            setTextColor(Color.rgb(71, 85, 105))
            setTypeface(typeface, Typeface.BOLD)
            gravity = Gravity.CENTER_VERTICAL
            background = roundedBackground(Color.rgb(241, 245, 249), Color.rgb(203, 213, 225), 12f)
            setPadding(dp(14), dp(14), dp(14), dp(14))
        }
        root.addView(status, LinearLayout.LayoutParams(-1, -2).apply { topMargin = dp(18) })
        return root
    }

    private fun dp(value: Int): Int =
        (value * resources.displayMetrics.density).toInt()

    private fun roundedBackground(fillColor: Int, strokeColor: Int, radiusDp: Float) =
        GradientDrawable().apply {
            shape = GradientDrawable.RECTANGLE
            setColor(fillColor)
            setStroke(dp(1), strokeColor)
            cornerRadius = radiusDp * resources.displayMetrics.density
        }

    private fun persist() {
        prefs.edit()
            .putString("api", api.text.toString().trim().trimEnd('/'))
            .putString("token", token.text.toString().trim())
            .putString("document", document.text.toString().trim())
            .apply()
    }

    private fun submit(barcode: String, symbology: String) {
        persist()
        val event = JSONObject()
            .put("client_event_id", UUID.randomUUID().toString())
            .put("device_id", deviceId)
            .put("location", location.text.toString().trim().uppercase())
            .put("barcode", barcode)
            .put("quantity", quantity.text.toString().toDoubleOrNull() ?: 1.0)
            .put("source", "TERMINAL")
            .put("symbology", symbology)
        if (event.getString("location").isEmpty() || document.text.toString().isBlank()) {
            feedback(false, "Belge ve lokasyon zorunlu")
            return
        }
        io.execute {
            if (send(event)) feedback(true, "$barcode kaydedildi")
            else {
                enqueue(event)
                feedback(false, "Çevrimdışı kuyruğa alındı")
            }
        }
    }

    private fun send(event: JSONObject): Boolean = try {
        val base = prefs.getString("api", "").orEmpty().trimEnd('/')
        val doc = prefs.getString("document", "").orEmpty()
        val connection = URL("$base/api/inventory/documents/$doc/scans").openConnection() as HttpURLConnection
        connection.requestMethod = "POST"
        connection.connectTimeout = 8_000
        connection.readTimeout = 8_000
        connection.doOutput = true
        connection.setRequestProperty("Content-Type", "application/json")
        connection.setRequestProperty("Authorization", "Bearer ${prefs.getString("token", "")}")
        connection.outputStream.use { it.write(event.toString().toByteArray()) }
        connection.responseCode in 200..299
    } catch (_: Exception) { false }

    @Synchronized private fun enqueue(event: JSONObject) {
        val queue = JSONArray(prefs.getString("queue", "[]"))
        queue.put(event)
        prefs.edit().putString("queue", queue.toString()).apply()
    }

    private fun syncQueue() = io.execute {
        val queue = JSONArray(prefs.getString("queue", "[]"))
        val remaining = JSONArray()
        for (index in 0 until queue.length()) {
            val event = queue.getJSONObject(index)
            if (!send(event)) remaining.put(event)
        }
        prefs.edit().putString("queue", remaining.toString()).apply()
        runOnUiThread { status.text = "Bekleyen çevrimdışı kayıt: ${remaining.length()}" }
    }

    private fun feedback(ok: Boolean, message: String) = runOnUiThread {
        status.text = message
        status.setTextColor(if (ok) Color.rgb(22, 163, 74) else Color.rgb(220, 38, 38))
        val vibrator = getSystemService(VIBRATOR_SERVICE) as Vibrator
        vibrator.vibrate(VibrationEffect.createOneShot(if (ok) 60 else 250, VibrationEffect.DEFAULT_AMPLITUDE))
    }

    private fun configureDataWedge() {
        val profile = Bundle().apply {
            putString("PROFILE_NAME", "OPEX_INVENTORY_V22")
            putString("PROFILE_ENABLED", "true")
            putString("CONFIG_MODE", "CREATE_IF_NOT_EXIST")
            putParcelableArray("APP_LIST", arrayOf(Bundle().apply {
                putString("PACKAGE_NAME", packageName)
                putStringArray("ACTIVITY_LIST", arrayOf("*"))
            }))
            putBundle("PLUGIN_CONFIG", Bundle().apply {
                putString("PLUGIN_NAME", "INTENT")
                putString("RESET_CONFIG", "true")
                putBundle("PARAM_LIST", Bundle().apply {
                    putString("intent_output_enabled", "true")
                    putString("intent_action", SCAN_ACTION)
                    putString("intent_delivery", "2")
                })
            })
        }
        sendBroadcast(Intent("com.symbol.datawedge.api.ACTION").apply {
            setPackage("com.symbol.datawedge")
            putExtra("com.symbol.datawedge.api.SET_CONFIG", profile)
        })
    }

    companion object {
        const val SCAN_ACTION = "com.opex.inventory.SCAN"
    }
}
