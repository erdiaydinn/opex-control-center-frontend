package com.opex.inventory

import android.content.BroadcastReceiver
import android.content.Context
import android.content.Intent
import android.content.IntentFilter
import android.graphics.Color
import android.os.Bundle
import android.os.VibrationEffect
import android.os.Vibrator
import android.provider.Settings
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
            setPadding(32, 32, 32, 32)
            setBackgroundColor(Color.rgb(248, 250, 252))
        }
        fun field(hint: String, saved: String = "") = EditText(this).apply {
            this.hint = hint
            setText(saved)
            setPadding(20, 18, 20, 18)
        }.also { root.addView(it, ViewGroup.LayoutParams(-1, -2)) }
        root.addView(TextView(this).apply {
            text = "OPEX Inventory V22"
            textSize = 26f
            setTextColor(Color.rgb(223, 16, 103))
            setPadding(0, 0, 0, 24)
        })
        api = field("HTTPS API adresi", prefs.getString("api", "https://inventory.company.com").orEmpty())
        token = field("SSO erişim anahtarı", prefs.getString("token", "").orEmpty())
        document = field("Sayım belge ID", prefs.getString("document", "").orEmpty())
        location = field("Lokasyon okut / gir")
        quantity = field("Adet", "1")
        root.addView(Button(this).apply {
            text = "AYARLARI KAYDET VE SENKRONİZE ET"
            setOnClickListener {
                persist()
                syncQueue()
            }
        }, ViewGroup.LayoutParams(-1, -2))
        root.addView(Button(this).apply {
            text = "TEST BARKODU GÖNDER"
            setOnClickListener { submit("8690000000001", "EAN13") }
        }, ViewGroup.LayoutParams(-1, -2))
        status = TextView(this).apply {
            text = "DataWedge bekleniyor"
            textSize = 18f
            setPadding(0, 28, 0, 0)
        }
        root.addView(status)
        return root
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
