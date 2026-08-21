package com.eay.one

import android.graphics.Color
import android.os.Bundle
import android.util.TypedValue
import android.view.ViewGroup
import android.widget.LinearLayout
import android.widget.TextView
import android.widget.Toast
import androidx.appcompat.app.AppCompatActivity
import com.eay.mobile.fieldui.runtime.EayTerminalRuntimeView
import com.eay.mobile.presentation.EayOneDestination
import com.eay.mobile.presentation.EayOneNavigationModel
import com.eay.mobile.presentation.FieldRecoveryActionKind
import com.eay.mobile.presentation.FieldRecoveryVisualSeverity
import com.eay.mobile.presentation.FieldRuntimeSurface
import com.eay.mobile.presentation.FieldSessionRecoveryBannerModel
import com.eay.mobile.presentation.FieldShellHeader
import com.eay.mobile.presentation.FieldSyncVisualState
import com.google.android.material.button.MaterialButton
import com.google.android.material.card.MaterialCardView

/**
 * Separate personal/work-phone host for the canonical shared EAY One presentation surface.
 *
 * This host deliberately owns no tenant, permission, token, mission or execution authority.
 * Until the reviewed corporate-session adapter is composed, it renders an explicit security
 * recovery state, no synthetic missions and no network permission. SIGN_IN_AGAIN is a
 * presentation intent only; this host cannot manufacture a second authentication stack.
 */
class MainActivity : AppCompatActivity() {
    private lateinit var runtimeView: EayTerminalRuntimeView
    private var destination: EayOneDestination = EayOneDestination.TODAY

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        runtimeView = EayTerminalRuntimeView(this)

        val root = LinearLayout(this).apply {
            orientation = LinearLayout.VERTICAL
            setBackgroundColor(Color.parseColor("#F8FAFC"))
            setPadding(dp(16), dp(16), dp(16), 0)
        }
        root.addView(
            buildSessionRecoveryCard(),
            LinearLayout.LayoutParams(
                ViewGroup.LayoutParams.MATCH_PARENT,
                ViewGroup.LayoutParams.WRAP_CONTENT,
            ),
        )
        root.addView(
            runtimeView,
            LinearLayout.LayoutParams(
                ViewGroup.LayoutParams.MATCH_PARENT,
                0,
                1f,
            ),
        )
        setContentView(root)
        renderShell()
    }

    private fun sessionRecoveryModel() = FieldSessionRecoveryBannerModel(
        severity = FieldRecoveryVisualSeverity.SECURITY,
        title = getString(R.string.eay_one_session_required),
        message = getString(R.string.eay_one_authority_required),
        actionKind = FieldRecoveryActionKind.SIGN_IN_AGAIN,
        actionLabel = getString(R.string.eay_one_sign_in_again),
    )

    private fun buildSessionRecoveryCard(): MaterialCardView {
        val model = sessionRecoveryModel()
        val card = MaterialCardView(this).apply {
            radius = dp(20).toFloat()
            cardElevation = dp(2).toFloat()
            setCardBackgroundColor(Color.parseColor("#FDEBF3"))
            strokeColor = Color.parseColor("#D20A6D")
            strokeWidth = dp(1)
        }
        val content = LinearLayout(this).apply {
            orientation = LinearLayout.VERTICAL
            setPadding(dp(18), dp(16), dp(18), dp(16))
        }
        content.addView(TextView(this).apply {
            text = model.title
            setTextColor(Color.parseColor("#07235B"))
            setTextSize(TypedValue.COMPLEX_UNIT_SP, 19f)
            setTypeface(typeface, android.graphics.Typeface.BOLD)
        })
        content.addView(TextView(this).apply {
            text = model.message
            setTextColor(Color.parseColor("#374151"))
            setTextSize(TypedValue.COMPLEX_UNIT_SP, 15f)
            setPadding(0, dp(8), 0, dp(12))
        })
        model.actionLabel?.let { label ->
            content.addView(MaterialButton(this).apply {
                text = label
                minimumHeight = dp(52)
                setOnClickListener { handleSessionRecoveryAction(model.actionKind) }
            })
        }
        card.addView(content)
        return card
    }

    private fun handleSessionRecoveryAction(action: FieldRecoveryActionKind) {
        when (action) {
            FieldRecoveryActionKind.SIGN_IN_AGAIN -> {
                // Corporate sign-in is intentionally not implemented here. The reviewed
                // canonical session adapter must own the eventual authentication action.
                Toast.makeText(this, R.string.eay_one_authority_required, Toast.LENGTH_LONG).show()
            }
            FieldRecoveryActionKind.NONE,
            FieldRecoveryActionKind.RELOAD_MISSIONS -> {
                Toast.makeText(this, R.string.eay_one_authority_required, Toast.LENGTH_SHORT).show()
            }
        }
    }

    private fun renderShell() {
        val header = FieldShellHeader(
            locationLabel = getString(R.string.eay_one_session_required),
            deviceLabel = getString(R.string.eay_one_phone_surface),
            runtimeSurface = FieldRuntimeSurface.EAY_ONE,
            syncState = FieldSyncVisualState.OFFLINE,
            pendingCount = 0,
        )
        val navigation = EayOneNavigationModel(
            selected = destination,
            pendingSyncCount = 0,
            quarantined = false,
        )

        runtimeView.renderEayOne(
            navigation = navigation,
            header = header,
            missions = emptyList(),
            onDestinationSelected = { next ->
                destination = next
                renderShell()
            },
            onMissionOpen = {},
            onDestinationAction = {
                Toast.makeText(this, R.string.eay_one_authority_required, Toast.LENGTH_SHORT).show()
            },
        )
    }

    private fun dp(value: Int): Int =
        TypedValue.applyDimension(
            TypedValue.COMPLEX_UNIT_DIP,
            value.toFloat(),
            resources.displayMetrics,
        ).toInt()
}
