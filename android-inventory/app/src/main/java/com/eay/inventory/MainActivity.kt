package com.eay.inventory

import android.content.Intent
import android.app.PendingIntent
import android.graphics.Color
import android.os.Bundle
import android.widget.Button
import android.widget.LinearLayout
import android.widget.TextView
import androidx.appcompat.app.AppCompatActivity
import net.openid.appauth.AuthorizationRequest
import net.openid.appauth.AuthorizationService
import net.openid.appauth.AuthorizationServiceConfiguration
import net.openid.appauth.ResponseTypeValues
import android.net.Uri

/** Production terminal shell. Credentials are never collected by the app. */
class MainActivity : AppCompatActivity() {
    private lateinit var status: TextView
    private val auth by lazy { AuthorizationService(this) }

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        status = TextView(this).apply { text = "Managed device policy doğrulanıyor…"; textSize = 18f }
        val signIn = Button(this).apply {
            text = "Kurumsal SSO ile giriş"
            setOnClickListener { startOidc() }
        }
        setContentView(LinearLayout(this).apply {
            orientation = LinearLayout.VERTICAL
            setPadding(40, 80, 40, 40)
            setBackgroundColor(Color.rgb(248, 250, 252))
            addView(TextView(this@MainActivity).apply {
                text = "EAY Inventory"; textSize = 28f; setTextColor(Color.rgb(223, 16, 103))
            })
            addView(status)
            addView(signIn)
        })
        runCatching {
            val managed = ManagedDeviceIdentity(this)
            managed.requireDeviceId()
            DeviceRequestSigner.ensureKey()
            InventoryDatabase.get(this)
            DataWedge.configure(this)
            status.text = "Cihaz hazır · kurumsal oturum gerekli"
        }.onFailure { status.text = "BLOCKED: ${it.message}" }
        if (intent?.action == ACTION_OIDC_COMPLETE) consumeOidc(intent)
    }

    private fun startOidc() {
        if (!BuildConfig.OIDC_ISSUER.startsWith("https://") || BuildConfig.OIDC_CLIENT_ID == "unset") {
            status.text = "BLOCKED: OIDC managed configuration eksik"
            return
        }
        AuthorizationServiceConfiguration.fetchFromIssuer(Uri.parse(BuildConfig.OIDC_ISSUER)) { config, error ->
            if (config == null) { runOnUiThread { status.text = "OIDC discovery başarısız: ${error?.errorDescription}" }; return@fetchFromIssuer }
            val request = AuthorizationRequest.Builder(
                config,
                BuildConfig.OIDC_CLIENT_ID,
                ResponseTypeValues.CODE,
                Uri.parse("com.eay.inventory://oauth2redirect"),
            ).setScope("openid profile email offline_access inventory").build()
            val complete = PendingIntent.getActivity(
                this,
                1001,
                Intent(this, MainActivity::class.java).setAction(ACTION_OIDC_COMPLETE),
                PendingIntent.FLAG_UPDATE_CURRENT or PendingIntent.FLAG_MUTABLE,
            )
            val cancelled = PendingIntent.getActivity(
                this,
                1002,
                Intent(this, MainActivity::class.java).setAction(ACTION_OIDC_CANCELLED),
                PendingIntent.FLAG_UPDATE_CURRENT or PendingIntent.FLAG_IMMUTABLE,
            )
            auth.performAuthorizationRequest(request, complete, cancelled)
        }
    }

    override fun onNewIntent(intent: Intent) {
        super.onNewIntent(intent)
        setIntent(intent)
        if (intent.action == ACTION_OIDC_COMPLETE) consumeOidc(intent)
        else if (intent.action == ACTION_OIDC_CANCELLED) status.text = "Kurumsal giriş iptal edildi"
    }

    private fun consumeOidc(intent: Intent) {
        // Token exchange is isolated; access tokens never enter Activity state or disk.
        OidcSession(this).consumeAuthorizationResponse(intent) { result ->
            result.onSuccess {
                DeviceEnrollment.enroll(this) { enrolled ->
                    runOnUiThread { status.text = enrolled.fold({ "Kurumsal oturum ve cihaz doğrulandı" }, { "Cihaz kaydı başarısız: ${it.message}" }) }
                }
            }.onFailure { runOnUiThread { status.text = "SSO başarısız: ${it.message}" } }
        }
    }

    override fun onDestroy() { auth.dispose(); super.onDestroy() }

    companion object {
        private const val ACTION_OIDC_COMPLETE = "com.eay.inventory.OIDC_COMPLETE"
        private const val ACTION_OIDC_CANCELLED = "com.eay.inventory.OIDC_CANCELLED"
    }
}
