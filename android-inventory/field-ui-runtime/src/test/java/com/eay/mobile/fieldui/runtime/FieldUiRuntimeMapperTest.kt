package com.eay.mobile.fieldui.runtime

import com.eay.mobile.presentation.FieldMissionCardModel
import com.eay.mobile.presentation.FieldMissionVisualKind
import com.eay.mobile.presentation.FieldMissionVisualPriority
import com.eay.mobile.presentation.FieldRuntimeSurface
import com.eay.mobile.presentation.EayOneDestination
import com.eay.mobile.presentation.EayOneNavigationModel
import com.eay.mobile.presentation.FieldShellHeader
import com.eay.mobile.presentation.FieldSyncVisualState
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertThrows
import org.junit.Assert.assertTrue
import org.junit.Test

class FieldUiRuntimeMapperTest {
    @Test
    fun `eay one mapper enforces surface and one sync truth`() {
        val header = terminalHeader(pendingCount = 2).copy(runtimeSurface = FieldRuntimeSurface.EAY_ONE)
        val result = FieldUiRuntimeMapper.eayOne(
            EayOneNavigationModel(EayOneDestination.TODAY, 2, quarantined = false),
            header,
            emptyList(),
        )
        assertEquals(EayOneDestination.TODAY, result.navigation.selected)
        assertThrows(IllegalArgumentException::class.java) {
            FieldUiRuntimeMapper.eayOne(
                EayOneNavigationModel(EayOneDestination.TODAY, 1, quarantined = false),
                header,
                emptyList(),
            )
        }
    }
    @Test
    fun `terminal mapper preserves canonical presentation-safe models`() {
        val header = terminalHeader()
        val mission = mission(enabled = true)

        val mapped = FieldUiRuntimeMapper.terminal(header, listOf(mission))

        assertEquals(header, mapped.header)
        assertEquals(listOf(mission), mapped.missions)
        assertEquals(FieldRuntimeSurface.EAY_TERMINAL, mapped.header.runtimeSurface)
        assertTrue(mapped.missions.single().enabled)
    }

    @Test
    fun `blocked mission remains non executable in runtime model`() {
        val mapped = FieldUiRuntimeMapper.terminal(
            terminalHeader(syncState = FieldSyncVisualState.QUARANTINED, pendingCount = 2),
            listOf(mission(enabled = false)),
        )

        assertFalse(mapped.missions.single().enabled)
        assertEquals(FieldSyncVisualState.QUARANTINED, mapped.header.syncState)
        assertEquals(2, mapped.header.pendingCount)
    }

    @Test
    fun `terminal runtime rejects eay one presentation surface`() {
        val eayOneHeader = terminalHeader().copy(runtimeSurface = FieldRuntimeSurface.EAY_ONE)

        assertThrows(IllegalArgumentException::class.java) {
            FieldUiRuntimeMapper.terminal(eayOneHeader, listOf(mission(enabled = true)))
        }
    }

    private fun terminalHeader(
        syncState: FieldSyncVisualState = FieldSyncVisualState.SYNCED,
        pendingCount: Int = 0,
    ) = FieldShellHeader(
        locationLabel = "Fulya",
        deviceLabel = "Zebra-001",
        runtimeSurface = FieldRuntimeSurface.EAY_TERMINAL,
        syncState = syncState,
        pendingCount = pendingCount,
    )

    private fun mission(enabled: Boolean) = FieldMissionCardModel(
        missionId = "inventory.count:abc",
        title = "Cycle count",
        subtitle = "A-04",
        kind = FieldMissionVisualKind.COUNT,
        priority = FieldMissionVisualPriority.HIGH,
        progressCurrent = 1,
        progressTotal = 4,
        primaryActionLabel = "Open",
        enabled = enabled,
    )
}
