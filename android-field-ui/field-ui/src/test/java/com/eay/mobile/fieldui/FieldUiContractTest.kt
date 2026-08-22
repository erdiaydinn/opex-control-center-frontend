package com.eay.mobile.fieldui

import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test

class FieldUiContractTest {
    @Test
    fun `eay one navigation exposes all five canonical destinations`() {
        assertEquals(
            listOf("TODAY", "MISSIONS", "SCAN", "JARVIS", "ME"),
            EayOneDestination.entries.map { it.name },
        )
        val model = EayOneNavigationModel(EayOneDestination.MISSIONS, 3, quarantined = false)
        assertEquals(3, model.pendingSyncCount)
    }

    @Test
    fun `blind count ui exposes observation not system stock`() {
        val fields = BlindCountUiState::class.java.declaredFields.map { it.name.lowercase() }
        assertTrue(fields.any { it.contains("observedquantity") })
        assertFalse(fields.any { it.contains("expected") || it.contains("systemstock") })
    }

    @Test
    fun `mission progress cannot exceed total`() {
        val result = runCatching {
            FieldMissionCardModel(
                missionId = "m-1",
                title = "Count",
                subtitle = "A-04",
                kind = FieldMissionVisualKind.COUNT,
                priority = FieldMissionVisualPriority.HIGH,
                progressCurrent = 12,
                progressTotal = 10,
                primaryActionLabel = "Continue",
                enabled = true,
            )
        }
        assertTrue(result.isFailure)
    }

    @Test
    fun `terminal header rejects negative pending count`() {
        val result = runCatching {
            FieldShellHeader(
                locationLabel = "Fulya",
                deviceLabel = "TC57-041",
                runtimeSurface = FieldRuntimeSurface.EAY_TERMINAL,
                syncState = FieldSyncVisualState.PENDING,
                pendingCount = -1,
            )
        }
        assertTrue(result.isFailure)
    }

    @Test
    fun `visual kinds preserve canonical mission families`() {
        assertEquals(
            setOf("SHIFT", "PICK", "COUNT", "PUTAWAY", "RECEIVING", "TRANSFER", "PLANOGRAM", "AUDIT", "ACADEMY", "JARVIS"),
            FieldMissionVisualKind.entries.map { it.name }.toSet(),
        )
    }

    @Test
    fun `operational execution is restricted to the four physical workflows`() {
        val valid = OperationalExecutionUiState(
            missionId = "pick-1",
            kind = FieldMissionVisualKind.PICK,
            title = "Pick",
            referenceLabel = "Order 42",
            stepKind = FieldOperationalStepKind.SOURCE_LOCATION,
            stepLabel = "1 / 5",
            instruction = "Scan source location",
            progressCurrent = 0,
            progressTotal = 5,
            syncState = FieldSyncVisualState.SYNCED,
            primaryActionLabel = "Scan",
            primaryActionEnabled = true,
        )
        assertEquals(FieldMissionVisualKind.PICK, valid.kind)

        val invalid = runCatching { valid.copy(kind = FieldMissionVisualKind.COUNT) }
        assertTrue(invalid.isFailure)
    }

    @Test
    fun `operational presentation cannot own authority or raw scan fields`() {
        val fields = OperationalExecutionUiState::class.java.declaredFields.map { it.name.lowercase() }
        val forbidden = listOf(
            "tenant",
            "employee",
            "deviceid",
            "shiftid",
            "claimid",
            "token",
            "signature",
            "barcode",
            "valuehash",
            "expectedstock",
            "systemstock",
        )
        forbidden.forEach { needle -> assertFalse(fields.any { it.contains(needle) }) }
    }

    @Test
    fun `home summary rejects impossible progress`() {
        val invalid = runCatching {
            EayOneHomeSummaryUiState(
                title = "Today",
                supportingText = "Work surface",
                shiftLabel = "Shift",
                shiftValue = "14-23",
                missionLabel = "Missions",
                missionValue = "5",
                attentionLabel = "Attention",
                attentionValue = "1",
                progressCurrent = 10,
                progressTotal = 9,
            )
        }
        assertTrue(invalid.isFailure)
    }

    @Test
    fun `module workspace is restricted to non inventory execution families`() {
        val valid = EayModuleDetailUiState(
            moduleId = "audit-preview",
            kind = FieldMissionVisualKind.AUDIT,
            eyebrow = "AUDIT",
            title = "Audit workspace",
            summary = "Evidence review",
            health = EayModuleHealthVisual.READY,
            statusLabel = "Ready",
            metrics = listOf(EayModuleMetricUiModel("Checks", "8")),
            sections = listOf(EayModuleDetailSectionUiModel("Evidence", "Review evidence")),
            syncState = FieldSyncVisualState.SYNCED,
            backActionLabel = "Back",
            primaryActionLabel = "Open",
        )
        assertEquals(FieldMissionVisualKind.AUDIT, valid.kind)

        val invalid = runCatching { valid.copy(kind = FieldMissionVisualKind.COUNT) }
        assertTrue(invalid.isFailure)
    }

    @Test
    fun `module workspace cannot represent sensitive authority or stock truth`() {
        val fields = EayModuleDetailUiState::class.java.declaredFields.map { it.name.lowercase() }
        val forbidden = listOf(
            "tenant",
            "employee",
            "deviceid",
            "shiftid",
            "claimid",
            "token",
            "signature",
            "barcode",
            "valuehash",
            "expectedstock",
            "systemstock",
            "latitude",
            "longitude",
        )
        forbidden.forEach { needle -> assertFalse(fields.any { it.contains(needle) }) }
    }
}
