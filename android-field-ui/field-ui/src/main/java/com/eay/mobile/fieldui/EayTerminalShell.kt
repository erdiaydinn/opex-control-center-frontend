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
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.outlined.CloudDone
import androidx.compose.material.icons.outlined.CloudOff
import androidx.compose.material.icons.outlined.ErrorOutline
import androidx.compose.material.icons.outlined.Sync
import androidx.compose.material3.Button
import androidx.compose.material3.Card
import androidx.compose.material3.Icon
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Scaffold
import androidx.compose.material3.Surface
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.semantics.contentDescription
import androidx.compose.ui.semantics.semantics
import androidx.compose.ui.text.input.KeyboardOptions
import androidx.compose.ui.text.input.KeyboardType
import androidx.compose.ui.unit.dp

@Composable
fun EayTerminalShell(
    header: FieldShellHeader,
    missions: List<FieldMissionCardModel>,
    onMissionOpen: (String) -> Unit,
    modifier: Modifier = Modifier,
) {
    Scaffold(modifier = modifier.fillMaxSize()) { padding ->
        LazyColumn(
            modifier = Modifier.fillMaxSize().padding(padding),
            contentPadding = PaddingValues(horizontal = 20.dp, vertical = 18.dp),
            verticalArrangement = Arrangement.spacedBy(14.dp),
        ) {
            item {
                Column(verticalArrangement = Arrangement.spacedBy(8.dp)) {
                    Text("EAY Terminal", style = MaterialTheme.typography.displaySmall)
                    Text(header.locationLabel, style = MaterialTheme.typography.titleLarge)
                    Row(
                        modifier = Modifier.fillMaxWidth(),
                        horizontalArrangement = Arrangement.SpaceBetween,
                        verticalAlignment = Alignment.CenterVertically,
                    ) {
                        Text(header.deviceLabel, style = MaterialTheme.typography.bodyLarge)
                        SyncStatus(header.syncState, header.pendingCount)
                    }
                }
            }
            item { Text("Sıradaki görevler", style = MaterialTheme.typography.headlineMedium) }
            items(missions, key = { it.missionId }) { mission ->
                Card(modifier = Modifier.fillMaxWidth()) {
                    Column(
                        modifier = Modifier.padding(18.dp),
                        verticalArrangement = Arrangement.spacedBy(10.dp),
                    ) {
                        Text(mission.title, style = MaterialTheme.typography.titleLarge)
                        if (mission.subtitle.isNotBlank()) Text(mission.subtitle, style = MaterialTheme.typography.bodyLarge)
                        if (mission.progressCurrent != null && mission.progressTotal != null) {
                            Text("${mission.progressCurrent} / ${mission.progressTotal}", style = MaterialTheme.typography.bodyLarge)
                        }
                        Button(
                            onClick = { onMissionOpen(mission.missionId) },
                            enabled = mission.enabled,
                            modifier = Modifier.fillMaxWidth().sizeIn(minHeight = 56.dp),
                        ) { Text(mission.primaryActionLabel) }
                    }
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
        state.scannedItemLabel?.let { Text(it, style = MaterialTheme.typography.bodyLarge) }
        OutlinedTextField(
            value = state.observedQuantityText,
            onValueChange = onQuantityChange,
            label = { Text("Gözlenen adet") },
            keyboardOptions = KeyboardOptions(keyboardType = KeyboardType.Number),
            singleLine = true,
            modifier = Modifier.fillMaxWidth().sizeIn(minHeight = 64.dp),
        )
        Text(
            text = state.totalLines?.let { "${state.confirmedLines} / $it" }
                ?: "${state.confirmedLines} satır tamamlandı",
            style = MaterialTheme.typography.bodyLarge,
        )
        Button(
            onClick = onConfirm,
            enabled = state.scannedItemLabel != null && state.observedQuantityText.isNotBlank(),
            modifier = Modifier.fillMaxWidth().sizeIn(minHeight = 64.dp),
        ) { Text("Adedi doğrula") }
    }
}

@Composable
private fun SyncStatus(state: FieldSyncVisualState, pendingCount: Int) {
    val icon = when (state) {
        FieldSyncVisualState.SYNCED -> Icons.Outlined.CloudDone
        FieldSyncVisualState.OFFLINE -> Icons.Outlined.CloudOff
        FieldSyncVisualState.PENDING -> Icons.Outlined.Sync
        FieldSyncVisualState.QUARANTINED -> Icons.Outlined.ErrorOutline
    }
    val label = when (state) {
        FieldSyncVisualState.SYNCED -> "Senkron"
        FieldSyncVisualState.OFFLINE -> "Çevrimdışı"
        FieldSyncVisualState.PENDING -> "$pendingCount bekliyor"
        FieldSyncVisualState.QUARANTINED -> "İnceleme gerekli"
    }
    Surface(
        tonalElevation = 2.dp,
        shape = RoundedCornerShape(16.dp),
        modifier = Modifier.semantics { contentDescription = "Senkron durumu: $label" },
    ) {
        Row(
            modifier = Modifier.padding(horizontal = 12.dp, vertical = 8.dp),
            horizontalArrangement = Arrangement.spacedBy(8.dp),
            verticalAlignment = Alignment.CenterVertically,
        ) {
            Icon(icon, contentDescription = null)
            Text(label, style = MaterialTheme.typography.labelLarge)
        }
    }
}
