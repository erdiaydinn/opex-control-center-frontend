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
import android.view.View
import android.view.ViewGroup
import android.widget.*
import androidx.appcompat.app.AppCompatActivity
import androidx.security.crypto.EncryptedSharedPreferences
import androidx.security.crypto.MasterKey
import org.json.JSONArray
import org.json.JSONObject
import java.net.HttpURLConnection
import java.net.URL
import java.util.UUID
import java.util.concurrent.Executors

class MainActivity : AppCompatActivity() {
    private val io = Executors.newSingleThreadExecutor()
    private lateinit var root: LinearLayout
    private lateinit var status: TextView
    private var stage = Stage.LANGUAGE
    private var locale = "tr"
    private var documentId = ""
    private var locationCode = ""
    private var lastBarcode = ""
    private var quantityInput: EditText? = null

    private val prefs by lazy {
        val key = MasterKey.Builder(this).setKeyScheme(MasterKey.KeyScheme.AES256_GCM).build()
        EncryptedSharedPreferences.create(
            this, "opex_inventory_v24_secure", key,
            EncryptedSharedPreferences.PrefKeyEncryptionScheme.AES256_SIV,
            EncryptedSharedPreferences.PrefValueEncryptionScheme.AES256_GCM,
        )
    }
    private val deviceId by lazy {
        Settings.Secure.getString(contentResolver, Settings.Secure.ANDROID_ID)
            ?: UUID.randomUUID().toString()
    }
    private val apiBase get() = BuildConfig.API_BASE_URL.trimEnd('/')

    private val words = mapOf(
        "tr" to mapOf(
            "choose" to "Dilini seç", "continue" to "Devam et", "welcome" to "Tekrar hoş geldin",
            "subtitle" to "Sayım görevlerine güvenli erişim", "user" to "E-posta / kullanıcı adı",
            "password" to "Parola", "login" to "Giriş yap", "tasks" to "Aktif sayım görevleri",
            "refresh" to "Yenile", "empty" to "Atanmış aktif görev bulunamadı",
            "scanLocation" to "Lokasyon barkodunu okut", "locationHelp" to "Saymaya başlamak için raf veya lokasyon etiketini okut.",
            "scanProduct" to "Ürün barkodunu okut", "quantity" to "Adet", "save" to "Kaydet",
            "next" to "Sonraki ürün", "changeLocation" to "Lokasyonu değiştir", "logout" to "Çıkış",
            "online" to "Çevrimiçi", "offline" to "Çevrimdışı", "pending" to "bekleyen kayıt",
            "locked" to "Lokasyon kilitlendi", "saved" to "Ürün kaydedildi", "loginError" to "Giriş başarısız",
            "selectTask" to "Görevi aç", "warehouse" to "Depo", "locations" to "lokasyon"
        ),
        "en" to mapOf(
            "choose" to "Choose your language", "continue" to "Continue", "welcome" to "Welcome back",
            "subtitle" to "Secure access to counting tasks", "user" to "Email / username",
            "password" to "Password", "login" to "Sign in", "tasks" to "Active count tasks",
            "refresh" to "Refresh", "empty" to "No active assigned task",
            "scanLocation" to "Scan location barcode", "locationHelp" to "Scan a shelf or location label to begin.",
            "scanProduct" to "Scan product barcode", "quantity" to "Quantity", "save" to "Save",
            "next" to "Next product", "changeLocation" to "Change location", "logout" to "Sign out",
            "online" to "Online", "offline" to "Offline", "pending" to "pending records",
            "locked" to "Location locked", "saved" to "Product saved", "loginError" to "Sign-in failed",
            "selectTask" to "Open task", "warehouse" to "Warehouse", "locations" to "locations"
        ),
        "de" to mapOf(
            "choose" to "Sprache wählen", "continue" to "Weiter", "welcome" to "Willkommen zurück",
            "subtitle" to "Sicherer Zugriff auf Zählaufgaben", "user" to "E-Mail / Benutzername",
            "password" to "Passwort", "login" to "Anmelden", "tasks" to "Aktive Zählaufgaben",
            "refresh" to "Aktualisieren", "empty" to "Keine aktive Aufgabe zugewiesen",
            "scanLocation" to "Lagerplatz scannen", "locationHelp" to "Regal- oder Lagerplatzetikett scannen.",
            "scanProduct" to "Produktbarcode scannen", "quantity" to "Menge", "save" to "Speichern",
            "next" to "Nächstes Produkt", "changeLocation" to "Lagerplatz wechseln", "logout" to "Abmelden",
            "online" to "Online", "offline" to "Offline", "pending" to "ausstehende Datensätze",
            "locked" to "Lagerplatz gesperrt", "saved" to "Produkt gespeichert", "loginError" to "Anmeldung fehlgeschlagen",
            "selectTask" to "Aufgabe öffnen", "warehouse" to "Lager", "locations" to "Lagerplätze"
        ),
        "ar" to mapOf(
            "choose" to "اختر لغتك", "continue" to "متابعة", "welcome" to "مرحباً بعودتك",
            "subtitle" to "وصول آمن إلى مهام الجرد", "user" to "البريد الإلكتروني / اسم المستخدم",
            "password" to "كلمة المرور", "login" to "تسجيل الدخول", "tasks" to "مهام الجرد النشطة",
            "refresh" to "تحديث", "empty" to "لا توجد مهمة نشطة مسندة",
            "scanLocation" to "امسح رمز الموقع", "locationHelp" to "امسح ملصق الرف أو الموقع للبدء.",
            "scanProduct" to "امسح رمز المنتج", "quantity" to "الكمية", "save" to "حفظ",
            "next" to "المنتج التالي", "changeLocation" to "تغيير الموقع", "logout" to "تسجيل الخروج",
            "online" to "متصل", "offline" to "غير متصل", "pending" to "سجلات معلقة",
            "locked" to "تم قفل الموقع", "saved" to "تم حفظ المنتج", "loginError" to "فشل تسجيل الدخول",
            "selectTask" to "فتح المهمة", "warehouse" to "المستودع", "locations" to "مواقع"
        )
    )

    private fun t(key: String) = words[locale]?.get(key) ?: words["tr"]?.get(key) ?: key

    private val scanner = object : BroadcastReceiver() {
        override fun onReceive(context: Context?, intent: Intent?) {
            val value = intent?.getStringExtra("com.symbol.datawedge.data_string")?.trim().orEmpty()
            val type = intent?.getStringExtra("com.symbol.datawedge.label_type").orEmpty().ifEmpty { "UNKNOWN" }
            if (value.isEmpty()) return
            when (stage) {
                Stage.LOCATION -> lockLocation(value)
                Stage.PRODUCT -> showQuantity(value, type)
                else -> Unit
            }
        }
    }

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        window.statusBarColor = Color.rgb(190, 8, 82)
        locale = prefs.getString("locale", "").orEmpty()
        if (locale !in words.keys) locale = "tr"
        root = LinearLayout(this).apply {
            orientation = LinearLayout.VERTICAL
            setPadding(dp(20), dp(22), dp(20), dp(22))
            setBackgroundColor(BG)
            layoutDirection = if (locale == "ar") View.LAYOUT_DIRECTION_RTL else View.LAYOUT_DIRECTION_LTR
        }
        setContentView(ScrollView(this).apply { addView(root) })
        configureDataWedge()
        showLanguage()
    }

    override fun onStart() {
        super.onStart()
        registerReceiver(scanner, IntentFilter(SCAN_ACTION), RECEIVER_EXPORTED)
    }

    override fun onStop() {
        runCatching { unregisterReceiver(scanner) }
        super.onStop()
    }

    private fun clear() {
        root.removeAllViews()
        root.layoutDirection = if (locale == "ar") View.LAYOUT_DIRECTION_RTL else View.LAYOUT_DIRECTION_LTR
        header()
    }

    private fun header() {
        root.addView(LinearLayout(this).apply {
            orientation = LinearLayout.HORIZONTAL
            gravity = Gravity.CENTER_VERTICAL
            addView(TextView(this@MainActivity).apply {
                text = "O"
                gravity = Gravity.CENTER
                textSize = 22f
                setTextColor(Color.WHITE)
                setTypeface(typeface, Typeface.BOLD)
                background = rounded(PINK, PINK, 16f)
            }, LinearLayout.LayoutParams(dp(48), dp(48)))
            addView(TextView(this@MainActivity).apply {
                text = "OPEX\nInventory"
                textSize = 18f
                setTextColor(NAVY)
                setTypeface(typeface, Typeface.BOLD)
                setPadding(dp(12), 0, 0, 0)
            })
        }, LinearLayout.LayoutParams(-1, -2).apply { bottomMargin = dp(30) })
    }

    private fun showLanguage() {
        stage = Stage.LANGUAGE
        clear()
        title(t("choose"), "OPEX Inventory V24")
        val options = listOf("tr" to "Türkçe", "en" to "English", "de" to "Deutsch", "ar" to "العربية")
        options.forEach { (code, name) ->
            root.addView(actionButton(name, code == locale) {
                locale = code
                prefs.edit().putString("locale", code).apply()
                root.layoutDirection = if (code == "ar") View.LAYOUT_DIRECTION_RTL else View.LAYOUT_DIRECTION_LTR
                showLogin()
            })
        }
    }

    private fun showLogin() {
        stage = Stage.LOGIN
        clear()
        title(t("welcome"), t("subtitle"))
        val username = input(t("user"), InputType.TYPE_CLASS_TEXT or InputType.TYPE_TEXT_VARIATION_EMAIL_ADDRESS)
        val password = input(t("password"), InputType.TYPE_CLASS_TEXT or InputType.TYPE_TEXT_VARIATION_PASSWORD)
        root.addView(primaryButton(t("login")) {
            if (username.text.isNotBlank() && password.text.isNotBlank()) login(username.text.toString(), password.text.toString())
        })
        root.addView(TextView(this).apply {
            text = "TR  ·  EN  ·  DE  ·  العربية"
            gravity = Gravity.CENTER
            setTextColor(MUTED)
            setPadding(0, dp(22), 0, dp(8))
            setOnClickListener { showLanguage() }
        })
        addStatus(t("online"))
    }

    private fun login(username: String, password: String) = io.execute {
        val body = JSONObject().put("username", username).put("password", password).put("device_id", deviceId)
        val response = request("POST", "/api/identity/login", body, false)
        if (response != null && response.optString("access_token").isNotEmpty()) {
            prefs.edit()
                .putString("access_token", response.getString("access_token"))
                .putString("refresh_token", response.optString("refresh_token"))
                .putString("user_name", response.optJSONObject("user")?.optString("name"))
                .apply()
            runOnUiThread { showTasks() }
        } else feedback(false, t("loginError"))
    }

    private fun showTasks() {
        stage = Stage.TASKS
        clear()
        title(t("tasks"), prefs.getString("user_name", "").orEmpty())
        addStatus(t("online"))
        io.execute {
            val response = authorized("GET", "/api/inventory/terminal/tasks")
            val rows = response?.optJSONArray("rows") ?: JSONArray()
            runOnUiThread {
                if (rows.length() == 0) root.addView(emptyCard(t("empty")))
                for (index in 0 until rows.length()) {
                    val task = rows.getJSONObject(index)
                    root.addView(taskCard(task))
                }
                root.addView(secondaryButton(t("refresh")) { showTasks() })
                root.addView(textButton(t("logout")) {
                    prefs.edit().remove("access_token").remove("refresh_token").apply()
                    showLogin()
                })
            }
        }
    }

    private fun taskCard(task: JSONObject) = LinearLayout(this).apply {
        orientation = LinearLayout.VERTICAL
        setPadding(dp(18), dp(18), dp(18), dp(18))
        background = rounded(Color.WHITE, BORDER, 18f)
        addView(TextView(this@MainActivity).apply {
            text = task.optString("name")
            textSize = 18f
            setTextColor(NAVY)
            setTypeface(typeface, Typeface.BOLD)
        })
        addView(TextView(this@MainActivity).apply {
            text = "${t("warehouse")}: ${task.optString("warehouse_id")}  ·  ${task.optInt("location_count")} ${t("locations")}"
            textSize = 13f
            setTextColor(MUTED)
            setPadding(0, dp(8), 0, dp(14))
        })
        addView(primaryButton(t("selectTask")) {
            documentId = task.getString("id")
            showLocation()
        })
    }.also { it.layoutParams = LinearLayout.LayoutParams(-1, -2).apply { bottomMargin = dp(12) } }

    private fun showLocation() {
        stage = Stage.LOCATION
        locationCode = ""
        clear()
        title(t("scanLocation"), t("locationHelp"))
        root.addView(scanPanel("⌁", t("scanLocation")))
        addQueueStatus()
        root.addView(secondaryButton("← ${t("tasks")}") { showTasks() })
    }

    private fun lockLocation(value: String) = io.execute {
        val code = value.trim().uppercase()
        val body = JSONObject().put("device_id", deviceId).put("ttl_seconds", 900)
        val response = authorized("POST", "/api/inventory/documents/$documentId/locations/$code/lock", body)
        if (response != null) {
            locationCode = code
            feedback(true, "${t("locked")}: $code")
            runOnUiThread { showProduct() }
        } else feedback(false, t("offline"))
    }

    private fun showProduct() {
        stage = Stage.PRODUCT
        clear()
        title(t("scanProduct"), locationCode)
        root.addView(scanPanel("▦", t("scanProduct")))
        addQueueStatus()
        root.addView(secondaryButton(t("changeLocation")) { showLocation() })
    }

    private fun showQuantity(barcode: String, symbology: String) {
        stage = Stage.QUANTITY
        lastBarcode = barcode
        clear()
        title(t("quantity"), barcode)
        quantityInput = input(t("quantity"), InputType.TYPE_CLASS_NUMBER or InputType.TYPE_NUMBER_FLAG_DECIMAL).apply {
            setText("1")
            selectAll()
            requestFocus()
        }
        root.addView(primaryButton(t("save")) {
            val value = quantityInput?.text.toString().toDoubleOrNull() ?: 1.0
            submit(barcode, symbology, value)
        })
        root.addView(secondaryButton(t("next")) { showProduct() })
        addQueueStatus()
    }

    private fun submit(barcode: String, symbology: String, quantity: Double) {
        val event = JSONObject()
            .put("client_event_id", UUID.randomUUID().toString()).put("device_id", deviceId)
            .put("location", locationCode).put("barcode", barcode).put("quantity", quantity)
            .put("source", "TERMINAL").put("symbology", symbology)
        io.execute {
            if (sendEvent(event)) {
                feedback(true, t("saved"))
                runOnUiThread { showProduct() }
            } else {
                enqueue(event)
                feedback(false, "${t("offline")} · ${queue().length()} ${t("pending")}")
                runOnUiThread { showProduct() }
            }
        }
    }

    private fun sendEvent(event: JSONObject): Boolean =
        authorized("POST", "/api/inventory/documents/$documentId/scans", event) != null

    @Synchronized private fun queue() = JSONArray(prefs.getString("queue", "[]"))
    @Synchronized private fun enqueue(event: JSONObject) {
        val items = queue().put(JSONObject(event.toString()).put("document_id", documentId))
        prefs.edit().putString("queue", items.toString()).apply()
    }

    private fun syncQueue() = io.execute {
        val pending = queue()
        val remaining = JSONArray()
        for (index in 0 until pending.length()) {
            val event = pending.getJSONObject(index)
            val doc = event.optString("document_id")
            event.remove("document_id")
            if (authorized("POST", "/api/inventory/documents/$doc/scans", event) == null) {
                event.put("document_id", doc)
                remaining.put(event)
            }
        }
        prefs.edit().putString("queue", remaining.toString()).apply()
    }

    private fun authorized(method: String, path: String, body: JSONObject? = null): JSONObject? {
        var response = request(method, path, body, true)
        if (response == null && refreshSession()) response = request(method, path, body, true)
        return response
    }

    private fun refreshSession(): Boolean {
        val refresh = prefs.getString("refresh_token", "").orEmpty()
        if (refresh.isEmpty()) return false
        val body = JSONObject().put("refresh_token", refresh).put("device_id", deviceId)
        val response = request("POST", "/api/identity/refresh", body, false) ?: return false
        prefs.edit().putString("access_token", response.optString("access_token"))
            .putString("refresh_token", response.optString("refresh_token")).apply()
        return response.optString("access_token").isNotEmpty()
    }

    private fun request(method: String, path: String, body: JSONObject? = null, auth: Boolean): JSONObject? = try {
        val connection = URL("$apiBase$path").openConnection() as HttpURLConnection
        connection.requestMethod = method
        connection.connectTimeout = 8_000
        connection.readTimeout = 8_000
        connection.setRequestProperty("Accept", "application/json")
        if (auth) connection.setRequestProperty("Authorization", "Bearer ${prefs.getString("access_token", "")}")
        if (body != null) {
            connection.doOutput = true
            connection.setRequestProperty("Content-Type", "application/json")
            connection.outputStream.use { it.write(body.toString().toByteArray()) }
        }
        if (connection.responseCode !in 200..299) null
        else JSONObject(connection.inputStream.bufferedReader().use { it.readText() })
    } catch (_: Exception) { null }

    private fun title(value: String, subtitle: String) {
        root.addView(TextView(this).apply {
            text = value
            textSize = 28f
            setTextColor(NAVY)
            setTypeface(typeface, Typeface.BOLD)
        })
        root.addView(TextView(this).apply {
            text = subtitle
            textSize = 14f
            setTextColor(MUTED)
            setPadding(0, dp(8), 0, dp(22))
        })
    }

    private fun input(hint: String, type: Int) = EditText(this).apply {
        this.hint = hint
        inputType = type
        textSize = 16f
        setTextColor(NAVY)
        setHintTextColor(MUTED)
        background = rounded(Color.WHITE, BORDER, 14f)
        setPadding(dp(16), dp(14), dp(16), dp(14))
        minHeight = dp(56)
        layoutParams = LinearLayout.LayoutParams(-1, -2).apply { bottomMargin = dp(12) }
    }.also { root.addView(it) }

    private fun primaryButton(textValue: String, action: () -> Unit) =
        button(textValue, PINK, Color.WHITE, PINK, action)
    private fun secondaryButton(textValue: String, action: () -> Unit) =
        button(textValue, Color.WHITE, NAVY, BORDER, action)
    private fun textButton(textValue: String, action: () -> Unit) =
        button(textValue, BG, MUTED, BG, action)
    private fun actionButton(textValue: String, selected: Boolean, action: () -> Unit) =
        button(textValue, if (selected) Color.rgb(255, 236, 244) else Color.WHITE, if (selected) PINK else NAVY, if (selected) PINK else BORDER, action)

    private fun button(textValue: String, fill: Int, textColor: Int, stroke: Int, action: () -> Unit) =
        Button(this).apply {
            text = textValue
            textSize = 15f
            isAllCaps = false
            setTextColor(textColor)
            setTypeface(typeface, Typeface.BOLD)
            background = rounded(fill, stroke, 14f)
            minHeight = dp(56)
            setOnClickListener { action() }
            layoutParams = LinearLayout.LayoutParams(-1, -2).apply { bottomMargin = dp(12) }
        }

    private fun scanPanel(icon: String, caption: String) = LinearLayout(this).apply {
        orientation = LinearLayout.VERTICAL
        gravity = Gravity.CENTER
        setPadding(dp(18), dp(38), dp(18), dp(38))
        background = rounded(Color.WHITE, PINK, 22f, 2)
        addView(TextView(this@MainActivity).apply {
            text = icon
            textSize = 48f
            setTextColor(PINK)
            gravity = Gravity.CENTER
        })
        addView(TextView(this@MainActivity).apply {
            text = caption
            textSize = 18f
            setTextColor(NAVY)
            setTypeface(typeface, Typeface.BOLD)
            gravity = Gravity.CENTER
            setPadding(0, dp(12), 0, 0)
        })
    }.also { it.layoutParams = LinearLayout.LayoutParams(-1, -2).apply { bottomMargin = dp(18) } }

    private fun emptyCard(value: String) = TextView(this).apply {
        text = value
        textSize = 15f
        gravity = Gravity.CENTER
        setTextColor(MUTED)
        setPadding(dp(18), dp(28), dp(18), dp(28))
        background = rounded(Color.WHITE, BORDER, 18f)
    }

    private fun addStatus(value: String) {
        status = TextView(this).apply {
            text = "●  $value"
            textSize = 13f
            setTextColor(GREEN)
            setPadding(dp(12), dp(10), dp(12), dp(10))
        }
        root.addView(status)
    }

    private fun addQueueStatus() {
        syncQueue()
        addStatus("${t("online")} · ${queue().length()} ${t("pending")}")
    }

    private fun feedback(ok: Boolean, message: String) = runOnUiThread {
        Toast.makeText(this, message, Toast.LENGTH_SHORT).show()
        if (::status.isInitialized) {
            status.text = "●  $message"
            status.setTextColor(if (ok) GREEN else RED)
        }
        val vibrator = getSystemService(VIBRATOR_SERVICE) as Vibrator
        vibrator.vibrate(VibrationEffect.createOneShot(if (ok) 60 else 220, VibrationEffect.DEFAULT_AMPLITUDE))
    }

    private fun rounded(fill: Int, stroke: Int, radius: Float, strokeWidth: Int = 1) =
        GradientDrawable().apply {
            shape = GradientDrawable.RECTANGLE
            setColor(fill)
            setStroke(dp(strokeWidth), stroke)
            cornerRadius = radius * resources.displayMetrics.density
        }

    private fun dp(value: Int) = (value * resources.displayMetrics.density).toInt()

    private fun configureDataWedge() {
        val profile = Bundle().apply {
            putString("PROFILE_NAME", "OPEX_INVENTORY_V24")
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

    private enum class Stage { LANGUAGE, LOGIN, TASKS, LOCATION, PRODUCT, QUANTITY }

    companion object {
        const val SCAN_ACTION = "com.opex.inventory.SCAN"
        val PINK = Color.rgb(223, 16, 103)
        val NAVY = Color.rgb(18, 28, 45)
        val MUTED = Color.rgb(100, 116, 139)
        val BORDER = Color.rgb(220, 226, 235)
        val BG = Color.rgb(247, 249, 252)
        val GREEN = Color.rgb(22, 163, 74)
        val RED = Color.rgb(220, 38, 38)
    }
}
