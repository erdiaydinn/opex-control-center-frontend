package com.eay.mobile.fieldui

import androidx.compose.foundation.background
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.PaddingValues
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.Button
import androidx.compose.material3.Card
import androidx.compose.material3.CardDefaults
import androidx.compose.material3.LinearProgressIndicator
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.NavigationBar
import androidx.compose.material3.NavigationBarItem
import androidx.compose.material3.Scaffold
import androidx.compose.material3.Surface
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.semantics.contentDescription
import androidx.compose.ui.semantics.semantics
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp

@Composable
fun EayAuditMobileShell(
    state: AuditMobileHomeState,
    copy: AuditMobileCopy,
    onStartVideoAudit: () -> Unit,
    onContinueAudit: () -> Unit,
    onOpenStep: (String) -> Unit,
    onNavigation: (String) -> Unit,
    modifier: Modifier = Modifier,
) {
    Scaffold(
        modifier = modifier.fillMaxSize(),
        bottomBar = {
            AuditBottomNavigation(copy = copy, onNavigation = onNavigation)
        },
    ) { padding ->
        LazyColumn(
            modifier = Modifier.fillMaxSize().padding(padding),
            contentPadding = PaddingValues(horizontal = 18.dp, vertical = 18.dp),
            verticalArrangement = Arrangement.spacedBy(14.dp),
        ) {
            item {
                AuditMobileHeader(state = state, copy = copy)
            }
            item {
                AuditPrivacyCard(state = state.privacyState, copy = copy)
            }
            item {
                AuditCaptureHero(
                    state = state,
                    copy = copy,
                    onStartVideoAudit = onStartVideoAudit,
                    onContinueAudit = onContinueAudit,
                )
            }
            item {
                Column(verticalArrangement = Arrangement.spacedBy(4.dp)) {
                    Text(copy.guidedCaptureTitle, style = MaterialTheme.typography.headlineSmall, fontWeight = FontWeight.Bold)
                    Text(copy.guidedCaptureSubtitle, style = MaterialTheme.typography.bodyMedium, color = MaterialTheme.colorScheme.onSurfaceVariant)
                }
            }
            items(state.captureSteps, key = { it.stepId }) { step ->
                AuditCaptureStepCard(step = step, onOpen = { onOpenStep(step.stepId) })
            }
            item { Spacer(modifier = Modifier.height(8.dp)) }
        }
    }
}

@Composable
private fun AuditMobileHeader(state: AuditMobileHomeState, copy: AuditMobileCopy) {
    Row(
        modifier = Modifier.fillMaxWidth(),
        horizontalArrangement = Arrangement.SpaceBetween,
        verticalAlignment = Alignment.CenterVertically,
    ) {
        Column(modifier = Modifier.weight(1f)) {
            Text(copy.productName, style = MaterialTheme.typography.labelLarge, color = MaterialTheme.colorScheme.primary, fontWeight = FontWeight.Bold)
            Text(copy.title, style = MaterialTheme.typography.headlineMedium, fontWeight = FontWeight.ExtraBold)
            Text(state.locationLabel, style = MaterialTheme.typography.bodyMedium, color = MaterialTheme.colorScheme.onSurfaceVariant)
        }
        Surface(shape = CircleShape, color = MaterialTheme.colorScheme.surfaceVariant) {
            Box(modifier = Modifier.size(46.dp), contentAlignment = Alignment.Center) {
                Text(state.userLabel.take(2).uppercase(), style = MaterialTheme.typography.labelLarge, fontWeight = FontWeight.Bold)
            }
        }
    }
}

@Composable
private fun AuditPrivacyCard(state: AuditPrivacyState, copy: AuditMobileCopy) {
    val (label, container, content) = when (state) {
        AuditPrivacyState.PASSED -> Triple(copy.privacyPassedLabel, MaterialTheme.colorScheme.primaryContainer, MaterialTheme.colorScheme.onPrimaryContainer)
        AuditPrivacyState.BLOCKED -> Triple(copy.privacyBlockedLabel, MaterialTheme.colorScheme.errorContainer, MaterialTheme.colorScheme.onErrorContainer)
        AuditPrivacyState.REDACTING -> Triple(copy.privacyPendingLabel, MaterialTheme.colorScheme.secondaryContainer, MaterialTheme.colorScheme.onSecondaryContainer)
        AuditPrivacyState.PENDING -> Triple(copy.privacyPendingLabel, MaterialTheme.colorScheme.surfaceVariant, MaterialTheme.colorScheme.onSurfaceVariant)
    }

    Card(
        colors = CardDefaults.cardColors(containerColor = container),
        modifier = Modifier.fillMaxWidth().semantics { contentDescription = "${copy.privacyTitle}: $label" },
    ) {
        Row(
            modifier = Modifier.fillMaxWidth().padding(16.dp),
            horizontalArrangement = Arrangement.spacedBy(12.dp),
            verticalAlignment = Alignment.CenterVertically,
        ) {
            Box(
                modifier = Modifier.size(12.dp).clip(CircleShape).background(content),
            )
            Column(modifier = Modifier.weight(1f)) {
                Text(copy.privacyTitle, fontWeight = FontWeight.Bold, color = content)
                Text(label, style = MaterialTheme.typography.bodySmall, color = content)
            }
            Text("PRIVACY", style = MaterialTheme.typography.labelSmall, color = content, fontWeight = FontWeight.Black)
        }
    }
}

@Composable
private fun AuditCaptureHero(
    state: AuditMobileHomeState,
    copy: AuditMobileCopy,
    onStartVideoAudit: () -> Unit,
    onContinueAudit: () -> Unit,
) {
    Card(
        modifier = Modifier.fillMaxWidth(),
        colors = CardDefaults.cardColors(containerColor = MaterialTheme.colorScheme.inverseSurface),
        shape = RoundedCornerShape(24.dp),
    ) {
        Column(
            modifier = Modifier.padding(20.dp),
            verticalArrangement = Arrangement.spacedBy(14.dp),
        ) {
            Text(copy.subtitle, style = MaterialTheme.typography.bodyMedium, color = MaterialTheme.colorScheme.inverseOnSurface)
            state.activeAuditTitle?.let { title ->
                Text(title, style = MaterialTheme.typography.titleLarge, color = MaterialTheme.colorScheme.inverseOnSurface, fontWeight = FontWeight.Bold)
                LinearProgressIndicator(
                    progress = { state.activeAuditProgress.coerceIn(0f, 1f) },
                    modifier = Modifier.fillMaxWidth().height(6.dp).clip(RoundedCornerShape(99.dp)),
                )
            }
            Button(
                onClick = if (state.activeAuditTitle == null) onStartVideoAudit else onContinueAudit,
                modifier = Modifier.fillMaxWidth().height(58.dp),
            ) {
                Text(if (state.activeAuditTitle == null) copy.startVideoAuditLabel else copy.continueLabel, fontWeight = FontWeight.Bold)
            }
        }
    }
}

@Composable
private fun AuditCaptureStepCard(step: AuditCaptureStep, onOpen: () -> Unit) {
    val accent: Color = when (step.state) {
        AuditCaptureStepState.CAPTURED -> MaterialTheme.colorScheme.primary
        AuditCaptureStepState.REVIEW_REQUIRED -> MaterialTheme.colorScheme.error
        AuditCaptureStepState.ACTIVE -> MaterialTheme.colorScheme.tertiary
        AuditCaptureStepState.UPCOMING -> MaterialTheme.colorScheme.outline
    }

    Card(
        onClick = onOpen,
        modifier = Modifier.fillMaxWidth(),
        shape = RoundedCornerShape(18.dp),
    ) {
        Row(
            modifier = Modifier.fillMaxWidth().padding(16.dp),
            horizontalArrangement = Arrangement.spacedBy(12.dp),
            verticalAlignment = Alignment.CenterVertically,
        ) {
            Box(
                modifier = Modifier.size(40.dp).clip(RoundedCornerShape(12.dp)).background(accent.copy(alpha = .12f)),
                contentAlignment = Alignment.Center,
            ) {
                Text(
                    text = when (step.state) {
                        AuditCaptureStepState.CAPTURED -> "✓"
                        AuditCaptureStepState.REVIEW_REQUIRED -> "!"
                        AuditCaptureStepState.ACTIVE -> "●"
                        AuditCaptureStepState.UPCOMING -> "○"
                    },
                    color = accent,
                    fontWeight = FontWeight.Black,
                )
            }
            Column(modifier = Modifier.weight(1f)) {
                Text(step.title, style = MaterialTheme.typography.titleMedium, fontWeight = FontWeight.Bold)
                Text(step.hint, style = MaterialTheme.typography.bodySmall, color = MaterialTheme.colorScheme.onSurfaceVariant, maxLines = 2, overflow = TextOverflow.Ellipsis)
            }
            if (step.evidenceCount > 0) {
                Surface(shape = RoundedCornerShape(99.dp), color = MaterialTheme.colorScheme.surfaceVariant) {
                    Text("${step.evidenceCount}×", modifier = Modifier.padding(horizontal = 9.dp, vertical = 5.dp), style = MaterialTheme.typography.labelMedium)
                }
            }
        }
    }
}

@Composable
private fun AuditBottomNavigation(copy: AuditMobileCopy, onNavigation: (String) -> Unit) {
    NavigationBar {
        NavigationBarItem(selected = true, onClick = { onNavigation("home") }, icon = { Text("⌂") }, label = { Text(copy.homeLabel) })
        NavigationBarItem(selected = false, onClick = { onNavigation("audits") }, icon = { Text("✓") }, label = { Text(copy.auditsLabel) })
        NavigationBarItem(selected = false, onClick = { onNavigation("capture") }, icon = { Text("●") }, label = { Text(copy.evidenceLabel) })
        NavigationBarItem(selected = false, onClick = { onNavigation("actions") }, icon = { Text("↯") }, label = { Text(copy.actionsLabel) })
    }
}
