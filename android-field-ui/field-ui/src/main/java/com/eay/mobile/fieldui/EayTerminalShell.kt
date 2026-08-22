package com.eay.mobile.fieldui

import androidx.compose.foundation.Canvas
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.PaddingValues
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.sizeIn
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.text.KeyboardOptions
import androidx.compose.material3.Button
import androidx.compose.material3.Card
import androidx.compose.material3.CardDefaults
import androidx.compose.material3.FilledTonalButton
import androidx.compose.material3.HorizontalDivider
import androidx.compose.material3.LinearProgressIndicator
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.NavigationBar
import androidx.compose.material3.NavigationBarItem
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Scaffold
import androidx.compose.material3.Surface
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.geometry.CornerRadius
import androidx.compose.ui.geometry.Offset
import androidx.compose.ui.geometry.Size
import androidx.compose.ui.graphics.drawscope.Stroke
import androidx.compose.ui.res.pluralStringResource
import androidx.compose.ui.res.stringResource
import androidx.compose.ui.semantics.contentDescription
import androidx.compose.ui.semantics.semantics
import androidx.compose.ui.text.font.FontWeight
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
                item { SectionTitle(stringResource(R.string.field_next_missions)) }
            }
            items(missions, key = { it.missionId }) { mission ->
                MissionCard(mission = mission, onMissionOpen = onMissionOpen)
            }
        }
    }
}

/** Real EAY One navigation surface; callbacks remain presentation intents, never execution truth. */
@Composable
fun EayOneShell(
    navigation: EayOneNavigationModel,
    header: FieldShellHeader,
    missions: List<FieldMissionCardModel>,
    onDestinationSelected: (EayOneDestination) -> Unit,
    onMissionOpen: (String) -> Unit,
    modifier: Modifier = Modifier,
    summary: EayOneHomeSummaryUiState? = null,
    onDestinationAction: (EayOneDestination) -> Unit = {},
) {
    require(header.runtimeSurface == FieldRuntimeSurface.EAY_ONE)
    val visibleMissions = missionsForDestination(navigation.selected, missions)
    Scaffold(
        modifier = modifier.fillMaxSize(),
        bottomBar = {
            NavigationBar {
                EayOneDestination.entries.forEach { destination ->
                    NavigationBarItem(
                        selected = destination == navigation.selected,
                        onClick = { onDestinationSelected(destination) },
                        icon = { EayNavGlyph(destination, destination == navigation.selected) },
                        label = { Text(destination.label()) },
                    )
                }
            }
        },
    ) { padding ->
        if (visibleMissions.isNotEmpty() || navigation.selected in setOf(EayOneDestination.TODAY, EayOneDestination.MISSIONS)) {
            EayOneMissionSurface(
                title = destinationTitle(navigation.selected),
                header = header,
                missions = visibleMissions,
                pendingCount = navigation.pendingSyncCount,
                summary = if (navigation.selected == EayOneDestination.TODAY) summary else null,
                onMissionOpen = onMissionOpen,
                modifier = Modifier.padding(padding),
            )
        } else {
            EayOneActionSurface(
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
private fun EayNavGlyph(destination: EayOneDestination, selected: Boolean) {
    val color = if (selected) MaterialTheme.colorScheme.primary else MaterialTheme.colorScheme.onSurfaceVariant
    Canvas(modifier = Modifier.size(24.dp)) {
        val strokeWidth = 2.2.dp.toPx()
        val stroke = Stroke(width = strokeWidth)
        when (destination) {
            EayOneDestination.TODAY -> {
                drawRoundRect(
                    color = color,
                    topLeft = Offset(3.dp.toPx(), 4.dp.toPx()),
                    size = Size(18.dp.toPx(), 16.dp.toPx()),
                    cornerRadius = CornerRadius(4.dp.toPx(), 4.dp.toPx()),
                    style = stroke,
                )
                drawLine(color, Offset(7.dp.toPx(), 8.dp.toPx()), Offset(17.dp.toPx(), 8.dp.toPx()), strokeWidth)
            }
            EayOneDestination.MISSIONS -> {
                listOf(6f, 12f, 18f).forEach { y ->
                    drawCircle(color, 1.5.dp.toPx(), Offset(4.dp.toPx(), y.dp.toPx()))
                    drawLine(color, Offset(8.dp.toPx(), y.dp.toPx()), Offset(21.dp.toPx(), y.dp.toPx()), strokeWidth)
                }
            }
            EayOneDestination.SCAN -> {
                val a = 4.dp.toPx(); val b = 9.dp.toPx(); val c = 15.dp.toPx(); val d = 20.dp.toPx()
                drawLine(color, Offset(a, b), Offset(a, a), strokeWidth); drawLine(color, Offset(a, a), Offset(b, a), strokeWidth)
                drawLine(color, Offset(c, a), Offset(d, a), strokeWidth); drawLine(color, Offset(d, a), Offset(d, b), strokeWidth)
                drawLine(color, Offset(a, c), Offset(a, d), strokeWidth); drawLine(color, Offset(a, d), Offset(b, d), strokeWidth)
                drawLine(color, Offset(d, c), Offset(d, d), strokeWidth); drawLine(color, Offset(c, d), Offset(d, d), strokeWidth)
                drawLine(color, Offset(7.dp.toPx(), 12.dp.toPx()), Offset(17.dp.toPx(), 12.dp.toPx()), strokeWidth)
            }
            EayOneDestination.JARVIS -> {
                val center = Offset(12.dp.toPx(), 12.dp.toPx())
                drawLine(color, Offset(12.dp.toPx(), 3.dp.toPx()), Offset(15.dp.toPx(), 9.dp.toPx()), strokeWidth)
                drawLine(color, Offset(15.dp.toPx(), 9.dp.toPx()), Offset(21.dp.toPx(), 12.dp.toPx()), strokeWidth)
                drawLine(color, Offset(21.dp.toPx(), 12.dp.toPx()), Offset(15.dp.toPx(), 15.dp.toPx()), strokeWidth)
                drawLine(color, Offset(15.dp.toPx(), 15.dp.toPx()), Offset(12.dp.toPx(), 21.dp.toPx()), strokeWidth)
                drawLine(color, Offset(12.dp.toPx(), 21.dp.toPx()), Offset(9.dp.toPx(), 15.dp.toPx()), strokeWidth)
                drawLine(color, Offset(9.dp.toPx(), 15.dp.toPx()), Offset(3.dp.toPx(), 12.dp.toPx()), strokeWidth)
                drawLine(color, Offset(3.dp.toPx(), 12.dp.toPx()), Offset(9.dp.toPx(), 9.dp.toPx()), strokeWidth)
                drawLine(color, Offset(9.dp.toPx(), 9.dp.toPx()), Offset(12.dp.toPx(), 3.dp.toPx()), strokeWidth)
                drawCircle(color, 2.dp.toPx(), center)
            }
            EayOneDestination.ME -> {
                drawCircle(color, 4.dp.toPx(), Offset(12.dp.toPx(), 8.dp.toPx()), style = stroke)
                drawRoundRect(
                    color = color,
                    topLeft = Offset(5.dp.toPx(), 14.dp.toPx()),
                    size = Size(14.dp.toPx(), 7.dp.toPx()),
                    cornerRadius = CornerRadius(4.dp.toPx(), 4.dp.toPx()),
                    style = stroke,
                )
            }
        }
    }
}

private fun missionsForDestination(
    destination: EayOneDestination,
    missions: List<FieldMissionCardModel>,
): List<FieldMissionCardModel> = when (destination) {
    EayOneDestination.TODAY -> missions.take(5)
    EayOneDestination.MISSIONS -> missions
    EayOneDestination.SCAN -> missions.filter {
        it.kind in setOf(
            FieldMissionVisualKind.COUNT,
            FieldMissionVisualKind.PICK,
            FieldMissionVisualKind.PUTAWAY,
            FieldMissionVisualKind.RECEIVING,
            FieldMissionVisualKind.TRANSFER,
        )
    }
    EayOneDestination.JARVIS -> missions.filter { it.kind == FieldMissionVisualKind.JARVIS }
    EayOneDestination.ME -> missions.filter {
        it.kind in setOf(FieldMissionVisualKind.SHIFT, FieldMissionVisualKind.ACADEMY)
    }
}

@Composable
private fun EayOneMissionSurface(
    title: String,
    header: FieldShellHeader,
    missions: List<FieldMissionCardModel>,
    pendingCount: Int,
    summary: EayOneHomeSummaryUiState?,
    onMissionOpen: (String) -> Unit,
    modifier: Modifier = Modifier,
) {
    LazyColumn(
        modifier = modifier.fillMaxSize(),
        contentPadding = PaddingValues(horizontal = 18.dp, vertical = 18.dp),
        verticalArrangement = Arrangement.spacedBy(14.dp),
    ) {
        item {
            Column(verticalArrangement = Arrangement.spacedBy(8.dp)) {
                Row(
                    modifier = Modifier.fillMaxWidth(),
                    horizontalArrangement = Arrangement.SpaceBetween,
                    verticalAlignment = Alignment.CenterVertically,
                ) {
                    Column(modifier = Modifier.weight(1f)) {
                        Text(title, style = MaterialTheme.typography.displaySmall)
                        Text(header.locationLabel, style = MaterialTheme.typography.bodyLarge)
                    }
                    SyncStatus(header.syncState, pendingCount)
                }
            }
        }
        summary?.let { model -> item { HomeSummaryCard(model) } }
        if (missions.isNotEmpty()) item { SectionTitle(stringResource(R.string.field_next_missions)) }
        items(missions, key = { it.missionId }) { mission -> MissionCard(mission = mission, onMissionOpen = onMissionOpen) }
    }
}

@Composable
private fun HomeSummaryCard(model: EayOneHomeSummaryUiState) {
    Card(
        modifier = Modifier.fillMaxWidth(),
        shape = RoundedCornerShape(28.dp),
        colors = CardDefaults.cardColors(containerColor = MaterialTheme.colorScheme.primaryContainer),
    ) {
        Column(modifier = Modifier.padding(20.dp), verticalArrangement = Arrangement.spacedBy(16.dp)) {
            Column(verticalArrangement = Arrangement.spacedBy(6.dp)) {
                Text(model.title, style = MaterialTheme.typography.headlineMedium, color = MaterialTheme.colorScheme.onPrimaryContainer)
                Text(model.supportingText, style = MaterialTheme.typography.bodyLarge, color = MaterialTheme.colorScheme.onPrimaryContainer)
            }
            LinearProgressIndicator(
                progress = { model.progressCurrent.toFloat() / model.progressTotal.toFloat() },
                modifier = Modifier.fillMaxWidth().height(8.dp).clip(RoundedCornerShape(999.dp)),
            )
            Row(modifier = Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.spacedBy(10.dp)) {
                SummaryMetric(model.shiftLabel, model.shiftValue, Modifier.weight(1f))
                SummaryMetric(model.missionLabel, model.missionValue, Modifier.weight(1f))
                SummaryMetric(model.attentionLabel, model.attentionValue, Modifier.weight(1f))
            }
        }
    }
}

@Composable
private fun SummaryMetric(label: String, value: String, modifier: Modifier = Modifier) {
    Surface(modifier = modifier, shape = RoundedCornerShape(18.dp), color = MaterialTheme.colorScheme.surface.copy(alpha = 0.72f)) {
        Column(modifier = Modifier.padding(horizontal = 12.dp, vertical = 12.dp), verticalArrangement = Arrangement.spacedBy(4.dp)) {
            Text(label, style = MaterialTheme.typography.labelLarge)
            Text(value, style = MaterialTheme.typography.titleLarge)
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
    Column(modifier = modifier.fillMaxSize().padding(20.dp), verticalArrangement = Arrangement.spacedBy(18.dp)) {
        Row(modifier = Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.SpaceBetween, verticalAlignment = Alignment.CenterVertically) {
            Column(modifier = Modifier.weight(1f)) {
                Text(destinationTitle(destination), style = MaterialTheme.typography.displaySmall)
                Text(header.locationLabel, style = MaterialTheme.typography.bodyLarge)
            }
            SyncStatus(header.syncState, pendingCount)
        }
        Surface(modifier = Modifier.fillMaxWidth().weight(1f), shape = RoundedCornerShape(28.dp), tonalElevation = 2.dp) {
            Column(modifier = Modifier.fillMaxSize().padding(20.dp), verticalArrangement = Arrangement.Center, horizontalAlignment = Alignment.CenterHorizontally) {
                EayNavGlyph(destination, selected = true)
                Spacer(Modifier.height(16.dp))
                Text(destination.label(), style = MaterialTheme.typography.headlineMedium)
            }
        }
        Button(onClick = { onAction(destination) }, modifier = Modifier.fillMaxWidth().sizeIn(minHeight = 64.dp)) { Text(destination.label()) }
    }
}

@Composable
private fun FieldHeader(brand: String, header: FieldShellHeader, pendingCount: Int) {
    Column(verticalArrangement = Arrangement.spacedBy(8.dp)) {
        Text(text = brand, style = MaterialTheme.typography.displaySmall)
        Text(header.locationLabel, style = MaterialTheme.typography.titleLarge)
        Row(modifier = Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.SpaceBetween, verticalAlignment = Alignment.CenterVertically) {
            Text(header.deviceLabel, style = MaterialTheme.typography.bodyLarge)
            SyncStatus(header.syncState, pendingCount)
        }
    }
}

@Composable private fun SectionTitle(title: String) { Text(text = title, style = MaterialTheme.typography.headlineMedium) }

@Composable
private fun MissionCard(mission: FieldMissionCardModel, onMissionOpen: (String) -> Unit) {
    Card(modifier = Modifier.fillMaxWidth(), shape = RoundedCornerShape(24.dp), colors = CardDefaults.cardColors(containerColor = missionContainer(mission.priority))) {
        Column(modifier = Modifier.padding(18.dp), verticalArrangement = Arrangement.spacedBy(12.dp)) {
            Row(modifier = Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.SpaceBetween, verticalAlignment = Alignment.CenterVertically) {
                KindBadge(mission.kind); PriorityDot(mission.priority)
            }
            Text(mission.title, style = MaterialTheme.typography.titleLarge)
            if (mission.subtitle.isNotBlank()) Text(mission.subtitle, style = MaterialTheme.typography.bodyLarge)
            val progressCurrent = mission.progressCurrent; val progressTotal = mission.progressTotal
            if (progressCurrent != null && progressTotal != null) {
                LinearProgressIndicator(progress = { progressCurrent.toFloat() / progressTotal.toFloat() }, modifier = Modifier.fillMaxWidth().height(7.dp).clip(RoundedCornerShape(999.dp)))
                Text(stringResource(R.string.blind_count_progress, progressCurrent, progressTotal), style = MaterialTheme.typography.bodyLarge)
            }
            FilledTonalButton(onClick = { onMissionOpen(mission.missionId) }, enabled = mission.enabled, modifier = Modifier.fillMaxWidth().sizeIn(minHeight = 56.dp)) {
                Text(mission.primaryActionLabel)
            }
        }
    }
}

@Composable
private fun KindBadge(kind: FieldMissionVisualKind) {
    Surface(shape = RoundedCornerShape(999.dp), color = MaterialTheme.colorScheme.surface.copy(alpha = 0.78f)) {
        Text(text = kind.name, modifier = Modifier.padding(horizontal = 11.dp, vertical = 6.dp), style = MaterialTheme.typography.labelLarge, fontWeight = FontWeight.Bold)
    }
}

@Composable
private fun PriorityDot(priority: FieldMissionVisualPriority) {
    Surface(
        modifier = Modifier.size(if (priority == FieldMissionVisualPriority.URGENT) 14.dp else 10.dp),
        shape = CircleShape,
        color = when (priority) {
            FieldMissionVisualPriority.LOW -> MaterialTheme.colorScheme.outline
            FieldMissionVisualPriority.NORMAL -> MaterialTheme.colorScheme.secondary
            FieldMissionVisualPriority.HIGH -> MaterialTheme.colorScheme.primary
            FieldMissionVisualPriority.URGENT -> MaterialTheme.colorScheme.error
        },
    ) {}
}

@Composable
private fun missionContainer(priority: FieldMissionVisualPriority) = when (priority) {
    FieldMissionVisualPriority.LOW, FieldMissionVisualPriority.NORMAL -> MaterialTheme.colorScheme.surfaceVariant
    FieldMissionVisualPriority.HIGH -> MaterialTheme.colorScheme.secondaryContainer
    FieldMissionVisualPriority.URGENT -> MaterialTheme.colorScheme.errorContainer
}

@Composable
private fun EayOneDestination.label(): String = when (this) {
    EayOneDestination.TODAY -> stringResource(R.string.eay_one_today)
    EayOneDestination.MISSIONS -> stringResource(R.string.eay_one_missions)
    EayOneDestination.SCAN -> stringResource(R.string.eay_one_scan)
    EayOneDestination.JARVIS -> stringResource(R.string.eay_one_jarvis)
    EayOneDestination.ME -> stringResource(R.string.eay_one_me)
}

@Composable private fun destinationTitle(destination: EayOneDestination) = destination.label()

@Composable
private fun RecoveryBanner(model: FieldRecoveryBannerModel, onAction: (FieldRecoveryActionKind) -> Unit) {
    RecoveryCard(model.severity, model.title, model.message, model.actionKind, model.actionLabel, onAction)
}

@Composable
private fun SessionRecoveryBanner(model: FieldSessionRecoveryBannerModel, onAction: (FieldRecoveryActionKind) -> Unit) {
    RecoveryCard(model.severity, model.title, model.message, model.actionKind, model.actionLabel, onAction)
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
        FieldRecoveryVisualSeverity.INFO, FieldRecoveryVisualSeverity.ATTENTION -> MaterialTheme.colorScheme.surfaceVariant
        FieldRecoveryVisualSeverity.BLOCKING, FieldRecoveryVisualSeverity.SECURITY -> MaterialTheme.colorScheme.errorContainer
    }
    Card(modifier = Modifier.fillMaxWidth(), colors = CardDefaults.cardColors(containerColor = container)) {
        Column(modifier = Modifier.padding(18.dp), verticalArrangement = Arrangement.spacedBy(10.dp)) {
            Text(title, style = MaterialTheme.typography.titleLarge); Text(message, style = MaterialTheme.typography.bodyLarge)
            actionLabel?.let { label ->
                Button(onClick = { onAction(actionKind) }, modifier = Modifier.fillMaxWidth().sizeIn(minHeight = 56.dp)) { Text(label) }
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
    backActionLabel: String? = null,
    onBack: () -> Unit = {},
) {
    Column(modifier = modifier.fillMaxSize().padding(20.dp), verticalArrangement = Arrangement.spacedBy(16.dp)) {
        Row(modifier = Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.SpaceBetween, verticalAlignment = Alignment.CenterVertically) {
            backActionLabel?.let { label -> TextButton(onClick = onBack, modifier = Modifier.sizeIn(minHeight = 56.dp)) { Text(label) } } ?: Spacer(Modifier.size(1.dp))
            SyncStatus(state.syncState, 0)
        }
        Card(modifier = Modifier.fillMaxWidth(), shape = RoundedCornerShape(26.dp), colors = CardDefaults.cardColors(containerColor = MaterialTheme.colorScheme.primaryContainer)) {
            Column(modifier = Modifier.padding(20.dp), verticalArrangement = Arrangement.spacedBy(8.dp)) {
                Text(state.locationLabel, style = MaterialTheme.typography.headlineMedium); Text(state.stepLabel, style = MaterialTheme.typography.titleLarge)
                state.scannedItemLabel?.let { Text(it, style = MaterialTheme.typography.bodyLarge) }
            }
        }
        state.totalLines?.let { total ->
            LinearProgressIndicator(progress = { state.confirmedLines.toFloat() / total.toFloat() }, modifier = Modifier.fillMaxWidth().height(8.dp).clip(RoundedCornerShape(999.dp)))
        }
        OutlinedTextField(value = state.observedQuantityText, onValueChange = onQuantityChange, label = { Text(stringResource(R.string.blind_count_observed_quantity)) }, keyboardOptions = KeyboardOptions(keyboardType = KeyboardType.Number), singleLine = true, modifier = Modifier.fillMaxWidth().sizeIn(minHeight = 64.dp))
        Text(
            text = state.totalLines?.let { stringResource(R.string.blind_count_progress, state.confirmedLines, it) }
                ?: pluralStringResource(R.plurals.blind_count_completed_lines, state.confirmedLines, state.confirmedLines),
            style = MaterialTheme.typography.bodyLarge,
        )
        Spacer(Modifier.weight(1f))
        Button(onClick = onConfirm, enabled = state.scannedItemLabel != null && state.observedQuantityText.isNotBlank(), modifier = Modifier.fillMaxWidth().sizeIn(minHeight = 64.dp)) {
            Text(stringResource(R.string.blind_count_confirm))
        }
    }
}

@Composable
fun OperationalMissionScreen(
    state: OperationalExecutionUiState,
    onQuantityChange: (String) -> Unit,
    onPrimaryAction: () -> Unit,
    modifier: Modifier = Modifier,
    backActionLabel: String? = null,
    onBack: () -> Unit = {},
) {
    Column(modifier = modifier.fillMaxSize().padding(20.dp), verticalArrangement = Arrangement.spacedBy(16.dp)) {
        Row(modifier = Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.SpaceBetween, verticalAlignment = Alignment.CenterVertically) {
            backActionLabel?.let { label -> TextButton(onClick = onBack, modifier = Modifier.sizeIn(minHeight = 56.dp)) { Text(label) } } ?: Spacer(Modifier.size(1.dp))
            SyncStatus(state.syncState, 0)
        }
        Column(verticalArrangement = Arrangement.spacedBy(6.dp)) { KindBadge(state.kind); Text(state.title, style = MaterialTheme.typography.displaySmall); Text(state.referenceLabel, style = MaterialTheme.typography.bodyLarge) }
        LinearProgressIndicator(progress = { state.progressCurrent.toFloat() / state.progressTotal.toFloat() }, modifier = Modifier.fillMaxWidth().height(8.dp).clip(RoundedCornerShape(999.dp)))
        Card(modifier = Modifier.fillMaxWidth(), shape = RoundedCornerShape(26.dp), colors = CardDefaults.cardColors(containerColor = MaterialTheme.colorScheme.surfaceVariant)) {
            Column(modifier = Modifier.padding(20.dp), verticalArrangement = Arrangement.spacedBy(10.dp)) {
                Text(state.stepLabel, style = MaterialTheme.typography.headlineMedium)
                Text(stringResource(R.string.blind_count_progress, state.progressCurrent, state.progressTotal), style = MaterialTheme.typography.bodyLarge)
                Text(state.instruction, style = MaterialTheme.typography.titleLarge)
                state.confirmationLabel?.let { confirmation ->
                    Surface(tonalElevation = 2.dp, shape = RoundedCornerShape(16.dp)) { Text(confirmation, modifier = Modifier.fillMaxWidth().padding(16.dp), style = MaterialTheme.typography.bodyLarge) }
                }
            }
        }
        if (state.stepKind == FieldOperationalStepKind.QUANTITY) {
            OutlinedTextField(value = state.quantityText, onValueChange = onQuantityChange, keyboardOptions = KeyboardOptions(keyboardType = KeyboardType.Decimal), singleLine = true, modifier = Modifier.fillMaxWidth().sizeIn(minHeight = 64.dp))
        }
        Spacer(Modifier.weight(1f))
        Button(onClick = onPrimaryAction, enabled = state.primaryActionEnabled && (state.stepKind != FieldOperationalStepKind.QUANTITY || state.quantityText.isNotBlank()), modifier = Modifier.fillMaxWidth().sizeIn(minHeight = 64.dp)) {
            Text(state.primaryActionLabel)
        }
    }
}

@Composable
fun EayModuleDetailScreen(
    state: EayModuleDetailUiState,
    onBack: () -> Unit,
    onPrimaryAction: () -> Unit,
    modifier: Modifier = Modifier,
    onSecondaryAction: () -> Unit = {},
) {
    LazyColumn(modifier = modifier.fillMaxSize(), contentPadding = PaddingValues(horizontal = 18.dp, vertical = 18.dp), verticalArrangement = Arrangement.spacedBy(14.dp)) {
        item {
            Row(modifier = Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.SpaceBetween, verticalAlignment = Alignment.CenterVertically) {
                TextButton(onClick = onBack, modifier = Modifier.sizeIn(minHeight = 56.dp)) { Text(state.backActionLabel) }
                SyncStatus(state.syncState, 0)
            }
        }
        item {
            Column(verticalArrangement = Arrangement.spacedBy(8.dp)) {
                KindBadge(state.kind); Text(state.eyebrow, style = MaterialTheme.typography.labelLarge); Text(state.title, style = MaterialTheme.typography.displaySmall)
                Text(state.summary, style = MaterialTheme.typography.bodyLarge); HealthBadge(state.health, state.statusLabel)
            }
        }
        items(state.metrics.chunked(2)) { rowMetrics ->
            Row(modifier = Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.spacedBy(10.dp)) {
                rowMetrics.forEach { metric -> MetricCard(metric, Modifier.weight(1f)) }
                if (rowMetrics.size == 1) Spacer(Modifier.weight(1f))
            }
        }
        if (state.sections.isNotEmpty()) item { HorizontalDivider() }
        items(state.sections) { section ->
            Card(modifier = Modifier.fillMaxWidth(), shape = RoundedCornerShape(22.dp), colors = CardDefaults.cardColors(containerColor = MaterialTheme.colorScheme.surfaceVariant)) {
                Column(modifier = Modifier.padding(18.dp), verticalArrangement = Arrangement.spacedBy(8.dp)) {
                    Row(modifier = Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.SpaceBetween, verticalAlignment = Alignment.CenterVertically) {
                        Text(section.title, style = MaterialTheme.typography.titleLarge)
                        section.statusLabel?.let { label ->
                            Surface(shape = RoundedCornerShape(999.dp), color = MaterialTheme.colorScheme.secondaryContainer) {
                                Text(label, modifier = Modifier.padding(horizontal = 10.dp, vertical = 6.dp), style = MaterialTheme.typography.labelLarge)
                            }
                        }
                    }
                    Text(section.body, style = MaterialTheme.typography.bodyLarge)
                }
            }
        }
        item {
            Column(verticalArrangement = Arrangement.spacedBy(10.dp)) {
                Button(onClick = onPrimaryAction, enabled = state.primaryActionEnabled, modifier = Modifier.fillMaxWidth().sizeIn(minHeight = 64.dp)) { Text(state.primaryActionLabel) }
                state.secondaryActionLabel?.let { label -> FilledTonalButton(onClick = onSecondaryAction, modifier = Modifier.fillMaxWidth().sizeIn(minHeight = 56.dp)) { Text(label) } }
            }
        }
    }
}

@Composable
private fun MetricCard(metric: EayModuleMetricUiModel, modifier: Modifier = Modifier) {
    Surface(modifier = modifier, shape = RoundedCornerShape(20.dp), tonalElevation = 2.dp) {
        Column(modifier = Modifier.padding(16.dp), verticalArrangement = Arrangement.spacedBy(4.dp)) {
            Text(metric.label, style = MaterialTheme.typography.labelLarge); Text(metric.value, style = MaterialTheme.typography.headlineMedium)
            if (metric.supportingText.isNotBlank()) Text(metric.supportingText, style = MaterialTheme.typography.bodyLarge)
        }
    }
}

@Composable
private fun HealthBadge(health: EayModuleHealthVisual, label: String) {
    Surface(
        shape = RoundedCornerShape(999.dp),
        color = when (health) {
            EayModuleHealthVisual.READY -> MaterialTheme.colorScheme.secondaryContainer
            EayModuleHealthVisual.IN_PROGRESS -> MaterialTheme.colorScheme.primaryContainer
            EayModuleHealthVisual.ATTENTION -> MaterialTheme.colorScheme.errorContainer
            EayModuleHealthVisual.LOCKED -> MaterialTheme.colorScheme.surfaceVariant
        },
    ) { Text(label, modifier = Modifier.padding(horizontal = 12.dp, vertical = 8.dp), style = MaterialTheme.typography.labelLarge) }
}

@Composable
private fun SyncStatus(state: FieldSyncVisualState, pendingCount: Int) {
    val label = when (state) {
        FieldSyncVisualState.SYNCED -> stringResource(R.string.field_sync_synced)
        FieldSyncVisualState.OFFLINE -> stringResource(R.string.field_sync_offline)
        FieldSyncVisualState.PENDING -> pluralStringResource(R.plurals.field_sync_pending, pendingCount, pendingCount)
        FieldSyncVisualState.QUARANTINED -> stringResource(R.string.field_sync_quarantined)
    }
    val accessibilityLabel = stringResource(R.string.field_sync_description, label)
    Surface(tonalElevation = 2.dp, shape = RoundedCornerShape(16.dp), modifier = Modifier.semantics { contentDescription = accessibilityLabel }) {
        Text(text = label, modifier = Modifier.padding(horizontal = 12.dp, vertical = 8.dp), style = MaterialTheme.typography.labelLarge)
    }
}
