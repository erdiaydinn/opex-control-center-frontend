package com.eay.one

import android.os.Bundle
import android.widget.Toast
import androidx.appcompat.app.AppCompatActivity
import com.eay.mobile.fieldui.runtime.EayTerminalRuntimeView
import com.eay.mobile.presentation.EayOneDestination
import com.eay.mobile.presentation.EayOneNavigationModel
import com.eay.mobile.presentation.FieldRuntimeSurface
import com.eay.mobile.presentation.FieldShellHeader
import com.eay.mobile.presentation.FieldSyncVisualState

/**
 * Separate personal/work-phone host for the canonical shared EAY One presentation surface.
 *
 * This host deliberately owns no tenant, permission, token, mission or execution authority.
 * Until the reviewed corporate-session adapter is composed, it renders a fail-closed shell
 * with no synthetic missions and no network permission.
 */
class MainActivity : AppCompatActivity() {
    private lateinit var runtimeView: EayTerminalRuntimeView
    private var destination: EayOneDestination = EayOneDestination.TODAY

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        runtimeView = EayTerminalRuntimeView(this)
        setContentView(runtimeView)
        renderShell()
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
}
