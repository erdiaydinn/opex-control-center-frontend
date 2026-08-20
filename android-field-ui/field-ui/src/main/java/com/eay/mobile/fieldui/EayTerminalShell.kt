package com.eay.mobile.fieldui

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.PaddingValues
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.sizeIn
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.text.KeyboardOptions
import androidx.compose.material3.Button
import androidx.compose.material3.Card
import androidx.compose.material3.CardDefaults
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.NavigationBar
import androidx.compose.material3.NavigationBarItem
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Scaffold
import androidx.compose.material3.Surface
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.res.pluralStringResource
import androidx.compose.ui.res.stringResource
import androidx.compose.ui.semantics.contentDescription
import androidx.compose.ui.semantics.semantics
import androidx.compose.ui.text.input.KeyboardType
import androidx.compose.ui.unit.dp

@Composable
fun EayTerminalShell(
    header: FieldShellHeader,
    missions: List<FieldMissionCardModel>,
    onMissionOpen: (String) -> Unit,
    modifier: Modifier = Modifier,
    recovery: FieldRecoveryBannerModel? = null,
    sessionRecovery: FieldSessionRecoveryBannerModel? = null,
    onRecoveryAction: (FieldRecoveryActionKind) -> Unit = {},
) {
    require(header.runtimeSurface == FieldRuntimeSurface.EAY_TERMINAL)
    Scaffold(modifier = modifier.fillMaxSize()) { padding ->
        LazyColumn(
            modifier = Modifier.fillMaxSize().padding(padding),
            contentPadding = PaddingValues(horizontal = 20.dp, vertical = 18.dp),
            verticalArrangement = Arrangement.spacedBy(14.dp),
        ) {
            item {
                FieldHeader(
                    brand = stringResource(R.string.eay_terminal_brand),
                    header = header,
                    pendingCount = header.pendingCount,
                )
            }
            sessionRecovery?.let { recoveryModel ->
                item {
                    SessionRecoveryBanner(
                        model = recoveryModel,
                        onAction = onRecoveryAction,
                    )
                }
            }
            recovery?.let { recoveryModel ->
                item {
                    RecoveryBanner(
                        model = recoveryModel,
                        onAction = onRecoveryAction,
                    )
                }
            }
            if (missions.isNotEmpty()) {
                item {
                    Text(
                        text = stringResource(R.string.field_next_missions),
                        style = MaterialTheme.typography.headlineMedium,
                    )
                }
            }
            items(missions, key = { it.missionId }) { mission ->
                MissionCard(mission = mission, onMissionOpen = onMissionOpen)
            }
        }
    }
}

/** Real EAY One navigation surface; callbacks remain presentation intents, never authority. */
@Composable
fun EayOneShell(
    navigation: EayOneNavigationModel,
    header: FieldShellHeader,
    missions: List<FieldMissionCardModel>,
    onDestinationSelected: (EayOneDestination) -> Unit,
    onMissionOpen: (String) -> Unit,
    modifier: Modifier = Modifier,
    onDestinationAction: (EayOneDestination) -> Unit = {},
) {
    require(header.runtimeSurface == FieldRuntimeSurface.EAY_ONE)
    Scaffold(
        modifier = modifier.fillMaxSize(),
        bottomBar = {
            NavigationBar {
                EayOneDestination.entries.forEach { destination ->
                    NavigationBarItem(
                        selected = destination == navigation.selected,
                        onClick = { onDestinationSelected(destination) },
                        icon = {},
                        label = { Text(destination.label()) },
                    )
                }
            }
        },
    ) { padding ->
        when (navigation.selected) {
            EayOneDestination.TODAY -> EayOneMissionSurface(
                title = destinationTitle(EayOneDestination.TODAY),
                header = header,
                missions = missions.take(3),
                pendingCount = navigation.pendingSyncCount,
                onMissionOpen = onMissionOpen,
                modifier = Modifier.padding(padding),
            )
            EayOneDestination.MISSIONS -> EayOneMissionSurface(
                title = destinationTitle(EayOneDestination.MISSIONS),
                header = header,
                missions = missions,
                pendingCount = navigation.pendingSyncCount,
                onMissionOpen = onMissionOpen,
                modifier = Modifier.padding(padding),
            )
            EayOneDestination.SCAN,
            EayOneDestination.JARVIS,
            EayOneDestination.ME,
            -> EayOneActionSurface(
                destination = navigation.selected,
                header = header,
                pendingCount = navigation.pendingSyncCount,
                onAction = onDestinationAction,
                modifier = Modifier.padding(padding),
            )
        }
    }
}

@Composable
private fun EayOneMissionSurface(
    title: String,
    header: FieldShellHeader,
    missions: List<FieldMissionCardModel>,
    pendingCount: Int,
    onMissionOpen: (String) -> Unit,
    modifier: Modifier = Modifier,
) {
    LazyColumn(
        modifier = modifier.fillMaxSize(),
        contentPadding = PaddingValues(horizontal = 20.dp, vertical = 18.dp),
        verticalArrangement = Arrangement.spacedBy(14.dp),
    ) {
        item {
            Column(verticalArrangement = Arrangement.spacedBy(8.dp)) {
                Text(title, style = MaterialTheme.typography.displaySmall)
                Text(header.locationLabel, style = MaterialTheme.typography.titleLarge)
                SyncStatus(header.syncState, pendingCount)
            }
        }
        if (missions.isNotEmpty()) {
            item {
                Text(
                    text = stringResource(R.string.field_next_missions),
                    style = MaterialTheme.typography.headlineMedium,
                )
            }
        }
        items(missions, key = { it.missionId }) { mission ->
            MissionCard(mission = mission, onMissionOpen = onMissionOpen)
        }
    }
}

@Composable
private fun EayOneActionSurface(
    destination: EayOneDestination,
    header: FieldShellHeader,
    pendingCount: Int,
    onAction: (EayOneDestination) -> Unit,
    modifier: Modifier = Modifier,
) {
    Column(
        modifier = modifier.fillMaxSize().padding(20.dp),
        verticalArrangement = Arrangement.spacedBy(18.dp),
    ) {
        Text(destinationTitle(destination), style = MaterialTheme.typography.displaySmall)
        Text(header.locationLabel, style = MaterialTheme.typography.titleLarge)
        SyncStatus(header.syncState, pendingCount)
        Button(
            onClick = { onAction(destination) },
            modifier = Modifier.fillMaxWidth().sizeIn(minHeight = 64.dp),
        ) {
            Text(destination.label())
        }
    }
}

@Composable
private fun FieldHeader(
    brand: String,
    header: FieldShellHeader,
    pendingCount: Int,
) {
    Column(verticalArrangement = Arrangement.spacedBy(8.dp)) {
        Text(text = brand, style = MaterialTheme.typography.displaySmall)
        Text(header.locationLabel, style = MaterialTheme.typography.titleLarge)
        Row(
            modifier = Modifier.fillMaxWidth(),
            horizontalArrangement = Arrangement.SpaceBetween,
            verticalAlignment = Alignment.CenterVertically,
        ) {
            Text(header.deviceLabel, style = MaterialTheme.typography.bodyLarge)
            SyncStatus(header.syncState, pendingCount)
        }
    }
}

@Composable
private fun MissionCard(
    mission: FieldMissionCardModel,
    onMissionOpen: (String) -> Unit,
) {
    Card(modifier = Modifier.fillMaxWidth()) {
        Column(
            modifier = Modifier.padding(18.dp),
            verticalArrangement = Arrangement.spacedBy(10.dp),
        ) {
            Text(mission.title, style = MaterialTheme.typography.titleLarge)
            if (mission.subtitle.isNotBlank()) {
                Text(mission.subtitle, style = MaterialTheme.typography.bodyLarge)
            }
            val progressCurrent = mission.progressCurrent
            val progressTotal = mission.progressTotal
            if (progressCurrent != null && progressTotal != null) {
                Text(
                    text = stringResource(
                        R.string.blind_count_progress,
                        progressCurrent,
                        progressTotal,
                    ),
                    style = MaterialTheme.typography.bodyLarge,
                )
            }
            Button(
                onClick = { onMissionOpen(mission.missionId) },
                enabled = mission.enabled,
                modifier = Modifier.fillMaxWidth().sizeIn(minHeight = 56.dp),
            ) {
                Text(mission.primaryActionLabel)
            }
        }
    }
}

@Composable
private fun EayOneDestination.label(): String = when (this) {
    EayOneDestination.TODAY -> stringResource(R.string.eay_one_today)
    EayOneDestination.MISSIONS -> stringResource(R.string.eay_one_missions)
    EayOneDestination.SCAN -> stringResource(R.string.eay_one_scan)
    EayOneDestination.JARVIS -> stringResource(R.string.eay_one_jarvis)
    EayOneDestination.ME -> stringResource(R.string.eay_one_me)
}

@Composable
private fun destinationTitle(destination: EayOneDestination) = destination.label()

@Composable
private fun RecoveryBanner(
    model: FieldRecoveryBannerModel,
    onAction: (FieldRecoveryActionKind) -> Unit,
) {
    RecoveryCard(
        severity = model.severity,
        title = model.title,
        message = model.message,
        actionKind = model.actionKind,
        actionLabel = model.actionLabel,
        onAction = onAction,
    )
}

@Composable
private fun SessionRecoveryBanner(
    model: FieldSessionRecoveryBannerModel,
    onAction: (FieldRecoveryActionKind) -> Unit,
) {
    RecoveryCard(
        severity = model.severity,
        title = model.title,
        message = model.message,
        actionKind = model.actionKind,
        actionLabel = model.actionLabel,
        onAction = onAction,
    )
}

@Composable
private fun RecoveryCard(
    severity: FieldRecoveryVisualSeverity,
    title: String,
    message: String,
    actionKind: FieldRecoveryActionKind,
    actionLabel: String?,
    onAction: (FieldRecoveryActionKind) -> Unit,
) {
    val container = when (severity) {
        FieldRecoveryVisualSeverity.INFO,
        FieldRecoveryVisualSeverity.ATTENTION,
        -> MaterialTheme.colorScheme.surfaceVariant

        FieldRecoveryVisualSeverity.BLOCKING,
        FieldRecoveryVisualSeverity.SECURITY,
        -> MaterialTheme.colorScheme.errorContainer
    }
    Card(
        modifier = Modifier.fillMaxWidth(),
        colors = CardDefaults.cardColors(containerColor = container),
    ) {
        Column(
            modifier = Modifier.padding(18.dp),
            verticalArrangement = Arrangement.spacedBy(10.dp),
        ) {
            Text(title, style = MaterialTheme.typography.titleLarge)
            Text(message, style = MaterialTheme.typography.bodyLarge)
            actionLabel?.let { label ->
                Button(
                    onClick = { onAction(actionKind) },
                    modifier = Modifier.fillMaxWidth().sizeIn(minHeight = 56.dp),
                ) {
                    Text(label)
                }
            }
        }
    }
}

@Composable
fun BlindCountScreen(
    state: BlindCountUiState,
    onQuantityChange: (String) -> Unit,
    onConfirm: () -> Unit,
    modifier: Modifier = Modifier,
) {
    Column(
        modifier = modifier.fillMaxSize().padding(20.dp),
        verticalArrangement = Arrangement.spacedBy(18.dp),
    ) {
        Text(state.locationLabel, style = MaterialTheme.typography.headlineMedium)
        Text(state.stepLabel, style = MaterialTheme.typography.titleLarge)
        state.scannedItemLabel?.let {
            Text(it, style = MaterialTheme.typography.bodyLarge)
        }
        OutlinedTextField(
            value = state.observedQuantityText,
            onValueChange = onQuantityChange,
            label = {
                Text(stringResource(R.string.blind_count_observed_quantity))
            },
            keyboardOptions = KeyboardOptions(keyboardType = KeyboardType.Number),
            singleLine = true,
            modifier = Modifier.fillMaxWidth().sizeIn(minHeight = 64.dp),
        )
        Text(
            text = state.totalLines?.let {
                stringResource(
                    R.string.blind_count_progress,
                    state.confirmedLines,
                    it,
                )
            } ?: pluralStringResource(
                R.plurals.blind_count_completed_lines,
                state.confirmedLines,
                state.confirmedLines,
            ),
            style = MaterialTheme.typography.bodyLarge,
        )
        Button(
            onClick = onConfirm,
            enabled = state.scannedItemLabel != null && state.observedQuantityText.isNotBlank(),
            modifier = Modifier.fillMaxWidth().sizeIn(minHeight = 64.dp),
        ) {
            Text(stringResource(R.string.blind_count_confirm))
        }
    }
}

/**
 * Scanner-first shared execution surface for Picking, Putaway, Receiving and Transfer.
 * The screen consumes presentation-only state; physical evidence still travels through
 * the signed MobileEventEnvelope/operational-event authority path.
 */
@Composable
fun OperationalMissionScreen(
    state: OperationalExecutionUiState,
    onQuantityChange: (String) -> Unit,
    onPrimaryAction: () -> Unit,
    modifier: Modifier = Modifier,
) {
    Column(
        modifier = modifier.fillMaxSize().padding(20.dp),
        verticalArrangement = Arrangement.spacedBy(18.dp),
    ) {
        Text(state.title, style = MaterialTheme.typography.displaySmall)
        Text(state.referenceLabel, style = MaterialTheme.typography.titleLarge)
        Row(
            modifier = Modifier.fillMaxWidth(),
            horizontalArrangement = Arrangement.SpaceBetween,
            verticalAlignment = Alignment.CenterVertically,
        ) {
            Text(state.stepLabel, style = MaterialTheme.typography.headlineMedium)
            SyncStatus(state.syncState, 0)
        }
        Text(
            text = stringResource(
                R.string.blind_count_progress,
                state.progressCurrent,
                state.progressTotal,
            ),
            style = MaterialTheme.typography.bodyLarge,
        )
        Text(state.instruction, style = MaterialTheme.typography.titleLarge)
        state.confirmationLabel?.let { confirmation ->
            Surface(
                tonalElevation = 2.dp,
                shape = RoundedCornerShape(16.dp),
            ) {
                Text(
                    confirmation,
                    modifier = Modifier.fillMaxWidth().padding(16.dp),
                    style = MaterialTheme.typography.bodyLarge,
                )
            }
        }
        if (state.stepKind == FieldOperationalStepKind.QUANTITY) {
            OutlinedTextField(
                value = state.quantityText,
                onValueChange = onQuantityChange,
                keyboardOptions = KeyboardOptions(keyboardType = KeyboardType.Decimal),
                singleLine = true,
                modifier = Modifier.fillMaxWidth().sizeIn(minHeight = 64.dp),
            )
        }
        Button(
            onClick = onPrimaryAction,
            enabled = state.primaryActionEnabled &&
                (state.stepKind != FieldOperationalStepKind.QUANTITY || state.quantityText.isNotBlank()),
            modifier = Modifier.fillMaxWidth().sizeIn(minHeight = 64.dp),
        ) {
            Text(state.primaryActionLabel)
        }
    }
}

@Composable
private fun SyncStatus(state: FieldSyncVisualState, pendingCount: Int) {
    val label = when (state) {
        FieldSyncVisualState.SYNCED -> stringResource(R.string.field_sync_synced)
        FieldSyncVisualState.OFFLINE -> stringResource(R.string.field_sync_offline)
        FieldSyncVisualState.PENDING -> pluralStringResource(
            R.plurals.field_sync_pending,
            pendingCount,
            pendingCount,
        )
        FieldSyncVisualState.QUARANTINED -> stringResource(R.string.field_sync_quarantined)
    }
    val accessibilityLabel = stringResource(R.string.field_sync_description, label)
    Surface(
        tonalElevation = 2.dp,
        shape = RoundedCornerShape(16.dp),
        modifier = Modifier.semantics {
            contentDescription = accessibilityLabel
        },
    ) {
        Text(
            text = label,
            modifier = Modifier.padding(horizontal = 12.dp, vertical = 8.dp),
            style = MaterialTheme.typography.labelLarge,
        )
    }
}
