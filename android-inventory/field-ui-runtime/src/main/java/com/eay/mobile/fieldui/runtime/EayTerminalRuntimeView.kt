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
import com.eay.mobile.presentation.FieldMissionCardModel
import com.eay.mobile.presentation.FieldRuntimeSurface
import com.eay.mobile.presentation.FieldShellHeader

/**
 * View-system boundary around the shared Compose field UI.
 *
 * The executable Inventory app passes only canonical presentation-safe models plus
 * bounded user-intent callbacks. Authentication, tenant, device, scanner, lease,
 * offline queue and mutation authority stay in the proven Inventory runtime and
 * never become Compose-owned state.
 */
class EayTerminalRuntimeView @JvmOverloads constructor(
    context: Context,
    attrs: AttributeSet? = null,
) : AbstractComposeView(context, attrs) {
    private var surface by mutableStateOf<RuntimeSurface>(RuntimeSurface.Empty)
    private var onMissionOpenCallback: (String) -> Unit = {}
    private var onQuantityChangedCallback: (String) -> Unit = {}
    private var onConfirmQuantityCallback: () -> Unit = {}

    init {
        setViewCompositionStrategy(ViewCompositionStrategy.DisposeOnViewTreeLifecycleDestroyed)
    }

    fun renderTerminal(
        header: FieldShellHeader,
        missions: List<FieldMissionCardModel>,
        onMissionOpen: (String) -> Unit,
    ) {
        onMissionOpenCallback = onMissionOpen
        surface = RuntimeSurface.Terminal(FieldUiRuntimeMapper.terminal(header, missions))
    }

    fun renderBlindCount(
        state: BlindCountUiState,
        onQuantityChanged: (String) -> Unit,
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
                    onQuantityChange = { value -> onQuantityChangedCallback(value) },
                    onConfirm = { onConfirmQuantityCallback() },
                )
            }
        }
    }
}

internal data class RuntimeTerminalModel(
    val header: FieldShellHeader,
    val missions: List<FieldMissionCardModel>,
)

internal sealed interface RuntimeSurface {
    data object Empty : RuntimeSurface
    data class Terminal(val model: RuntimeTerminalModel) : RuntimeSurface
    data class BlindCount(val state: BlindCountUiState) : RuntimeSurface
}

/**
 * Compatibility guard, not a second presentation/authorization mapper.
 *
 * The canonical FieldPresentationAdapter already produces the safe header and mission
 * models. This boundary only prevents an EAY One surface from being rendered by the
 * rugged-terminal view and snapshots the presentation list for Compose rendering.
 */
internal object FieldUiRuntimeMapper {
    fun terminal(
        header: FieldShellHeader,
        missions: List<FieldMissionCardModel>,
    ): RuntimeTerminalModel {
        require(header.runtimeSurface == FieldRuntimeSurface.EAY_TERMINAL) {
            "EAY Terminal runtime requires an EAY_TERMINAL presentation surface"
        }
        return RuntimeTerminalModel(
            header = header,
            missions = missions.toList(),
        )
    }
}
