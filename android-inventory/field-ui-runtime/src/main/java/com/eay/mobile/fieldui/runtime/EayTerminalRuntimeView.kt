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
import com.eay.mobile.fieldui.EayOneShell
import com.eay.mobile.fieldui.EayTerminalShell
import com.eay.mobile.fieldui.OperationalMissionScreen
import com.eay.mobile.presentation.EayOneDestination
import com.eay.mobile.presentation.EayOneNavigationModel
import com.eay.mobile.presentation.FieldMissionCardModel
import com.eay.mobile.presentation.FieldRecoveryActionKind
import com.eay.mobile.presentation.FieldRecoveryBannerModel
import com.eay.mobile.presentation.FieldRuntimeSurface
import com.eay.mobile.presentation.FieldSessionRecoveryBannerModel
import com.eay.mobile.presentation.FieldShellHeader
import com.eay.mobile.presentation.OperationalExecutionUiState

/** View-system boundary around the shared Compose field UI. */
class EayTerminalRuntimeView @JvmOverloads constructor(
    context: Context,
    attrs: AttributeSet? = null,
) : AbstractComposeView(context, attrs) {
    private var surface by mutableStateOf<RuntimeSurface>(RuntimeSurface.Empty)
    private var onMissionOpenCallback: (String) -> Unit = {}
    private var onDestinationSelectedCallback: (EayOneDestination) -> Unit = {}
    private var onDestinationActionCallback: (EayOneDestination) -> Unit = {}
    private var onRecoveryActionCallback: (FieldRecoveryActionKind) -> Unit = {}
    private var onQuantityChangedCallback: (String) -> Unit = {}
    private var onConfirmQuantityCallback: () -> Unit = {}
    private var onOperationalQuantityChangedCallback: (String) -> Unit = {}
    private var onOperationalPrimaryActionCallback: () -> Unit = {}

    init {
        setViewCompositionStrategy(ViewCompositionStrategy.DisposeOnViewTreeLifecycleDestroyed)
    }

    fun renderTerminal(
        header: FieldShellHeader,
        missions: List<FieldMissionCardModel>,
        recovery: FieldRecoveryBannerModel? = null,
        sessionRecovery: FieldSessionRecoveryBannerModel? = null,
        onMissionOpen: (String) -> Unit,
        onRecoveryAction: (FieldRecoveryActionKind) -> Unit = {},
    ) {
        onMissionOpenCallback = onMissionOpen
        onRecoveryActionCallback = onRecoveryAction
        surface = RuntimeSurface.Terminal(
            FieldUiRuntimeMapper.terminal(
                header = header,
                missions = missions,
                recovery = recovery,
                sessionRecovery = sessionRecovery,
            ),
        )
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

    fun renderOperationalMission(
        state: OperationalExecutionUiState,
        onQuantityChanged: (String) -> Unit,
        onPrimaryAction: () -> Unit,
    ) {
        onOperationalQuantityChangedCallback = onQuantityChanged
        onOperationalPrimaryActionCallback = onPrimaryAction
        surface = RuntimeSurface.Operational(state)
    }

    fun renderEayOne(
        navigation: EayOneNavigationModel,
        header: FieldShellHeader,
        missions: List<FieldMissionCardModel>,
        onDestinationSelected: (EayOneDestination) -> Unit,
        onMissionOpen: (String) -> Unit,
        onDestinationAction: (EayOneDestination) -> Unit = {},
    ) {
        onDestinationSelectedCallback = onDestinationSelected
        onMissionOpenCallback = onMissionOpen
        onDestinationActionCallback = onDestinationAction
        surface = RuntimeSurface.EayOne(
            FieldUiRuntimeMapper.eayOne(navigation, header, missions),
        )
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
                    recovery = current.model.recovery,
                    sessionRecovery = current.model.sessionRecovery,
                    onMissionOpen = { missionId -> onMissionOpenCallback(missionId) },
                    onRecoveryAction = { action -> onRecoveryActionCallback(action) },
                )
                is RuntimeSurface.BlindCount -> BlindCountScreen(
                    state = current.state,
                    onQuantityChange = { value -> onQuantityChangedCallback(value) },
                    onConfirm = { onConfirmQuantityCallback() },
                )
                is RuntimeSurface.Operational -> OperationalMissionScreen(
                    state = current.state,
                    onQuantityChange = { value -> onOperationalQuantityChangedCallback(value) },
                    onPrimaryAction = { onOperationalPrimaryActionCallback() },
                )
                is RuntimeSurface.EayOne -> EayOneShell(
                    navigation = current.model.navigation,
                    header = current.model.header,
                    missions = current.model.missions,
                    onDestinationSelected = { onDestinationSelectedCallback(it) },
                    onMissionOpen = { onMissionOpenCallback(it) },
                    onDestinationAction = { onDestinationActionCallback(it) },
                )
            }
        }
    }
}

internal data class RuntimeTerminalModel(
    val header: FieldShellHeader,
    val missions: List<FieldMissionCardModel>,
    val recovery: FieldRecoveryBannerModel?,
    val sessionRecovery: FieldSessionRecoveryBannerModel?,
)

internal data class RuntimeEayOneModel(
    val navigation: EayOneNavigationModel,
    val header: FieldShellHeader,
    val missions: List<FieldMissionCardModel>,
)

internal sealed interface RuntimeSurface {
    data object Empty : RuntimeSurface
    data class Terminal(val model: RuntimeTerminalModel) : RuntimeSurface
    data class BlindCount(val state: BlindCountUiState) : RuntimeSurface
    data class Operational(val state: OperationalExecutionUiState) : RuntimeSurface
    data class EayOne(val model: RuntimeEayOneModel) : RuntimeSurface
}

internal object FieldUiRuntimeMapper {
    fun eayOne(
        navigation: EayOneNavigationModel,
        header: FieldShellHeader,
        missions: List<FieldMissionCardModel>,
    ): RuntimeEayOneModel {
        require(header.runtimeSurface == FieldRuntimeSurface.EAY_ONE) {
            "EAY One runtime requires an EAY_ONE presentation surface"
        }
        require(navigation.pendingSyncCount == header.pendingCount) {
            "EAY One navigation and canonical sync header disagree"
        }
        return RuntimeEayOneModel(navigation, header, missions.toList())
    }

    fun terminal(
        header: FieldShellHeader,
        missions: List<FieldMissionCardModel>,
        recovery: FieldRecoveryBannerModel? = null,
        sessionRecovery: FieldSessionRecoveryBannerModel? = null,
    ): RuntimeTerminalModel {
        require(header.runtimeSurface == FieldRuntimeSurface.EAY_TERMINAL) {
            "EAY Terminal runtime requires an EAY_TERMINAL presentation surface"
        }
        return RuntimeTerminalModel(
            header = header,
            missions = missions.toList(),
            recovery = recovery,
            sessionRecovery = sessionRecovery,
        )
    }
}
