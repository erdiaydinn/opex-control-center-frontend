package com.eay.mobile.fieldui

import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test

class FieldUiContractTest {
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
                title = "Sayım",
                subtitle = "A-04",
                kind = FieldMissionVisualKind.COUNT,
                priority = FieldMissionVisualPriority.HIGH,
                progressCurrent = 12,
                progressTotal = 10,
                primaryActionLabel = "Devam et",
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
}
