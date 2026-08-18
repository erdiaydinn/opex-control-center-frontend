package com.eay.mobile.fieldui.runtime

import android.content.Context
import android.util.AttributeSet
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.setValue
import androidx.compose.ui.platform.AbstractComposeView
import androidx.compose.ui.platform.ViewCompositionStrategy
import com.eay.mobile.fieldui.BlindCountScreen
import com.eay.mobile.fieldui.BlindCountUiState
import com.eay.mobile.fieldui.EayFieldTheme
import com.eay.mobile.fieldui.EayTerminalShell
import com.eay.mobile.fieldui.TerminalHeader
import com.eay.mobile.fieldui.TerminalMissionCard
import com.eay.mobile.presentation.TerminalScreenModel

/**
 * View-system boundary around the shared Compose field UI.
 *
 * The executable Inventory app sees this as a normal Android View and passes only
 * presentation models plus bounded user-intent callbacks. Authentication, tenant,
 * device, scanner, lease, offline queue and mutation authority stay in the proven
 * Inventory runtime and never become Compose-owned state.
 */
class EayTerminalRuntimeView @JvmOverloads constructor(
    context: Context,
    attrs: AttributeSet? = null,
) : AbstractComposeView(context, attrs) {
    private var surface by mutableStateOf<RuntimeSurface>(RuntimeSurface.Empty)
    private var onMissionOpenCallback: (String) -> Unit = {}
    private var onQuantityChangedCallback: (Int?) -> Unit = {}
    private var onConfirmQuantityCallback: () -> Unit = {}

    init {
        setViewCompositionStrategy(ViewCompositionStrategy.DisposeOnViewTreeLifecycleDestroyed)
    }

    fun renderTerminal(
        model: TerminalScreenModel,
        onMissionOpen: (String) -> Unit,
    ) {
        onMissionOpenCallback = onMissionOpen
        surface = RuntimeSurface.Terminal(FieldUiRuntimeMapper.terminal(model))
    }

    fun renderBlindCount(
        state: BlindCountUiState,
        onQuantityChanged: (Int?) -> Unit,
        onConfirmQuantity: () -> Unit,
    ) {
        onQuantityChangedCallback = onQuantityChanged
        onConfirmQuantityCallback = onConfirmQuantity
        surface = RuntimeSurface.BlindCount(state)
    }

    fun clear() {
        surface = RuntimeSurface.Empty
    }

    @Composable
    override fun Content() {
        EayFieldTheme {
            when (val current = surface) {
                RuntimeSurface.Empty -> Unit
                is RuntimeSurface.Terminal -> EayTerminalShell(
                    header = current.model.header,
                    missions = current.model.missions,
                    onMissionOpen = { missionId -> onMissionOpenCallback(missionId) },
                )
                is RuntimeSurface.BlindCount -> BlindCountScreen(
                    state = current.state,
                    onQuantityChanged = { quantity -> onQuantityChangedCallback(quantity) },
                    onConfirmQuantity = { onConfirmQuantityCallback() },
                )
            }
        }
    }
}

internal data class RuntimeTerminalModel(
    val header: TerminalHeader,
    val missions: List<TerminalMissionCard>,
)

internal sealed interface RuntimeSurface {
    data object Empty : RuntimeSurface
    data class Terminal(val model: RuntimeTerminalModel) : RuntimeSurface
    data class BlindCount(val state: BlindCountUiState) : RuntimeSurface
}

internal object FieldUiRuntimeMapper {
    fun terminal(model: TerminalScreenModel): RuntimeTerminalModel = RuntimeTerminalModel(
        header = TerminalHeader(
            locationLabel = "",
            deviceLabel = "",
            syncIndicator = model.syncIndicator,
        ),
        missions = model.missions.map { mission ->
            TerminalMissionCard(
                missionId = mission.missionId,
                kind = mission.title,
                locationLabel = mission.subtitle,
                progressLabel = mission.progressLabel ?: mission.etaLabel,
                statusLabel = mission.blockedReason,
                enabled = mission.enabled,
            )
        },
    )
}
