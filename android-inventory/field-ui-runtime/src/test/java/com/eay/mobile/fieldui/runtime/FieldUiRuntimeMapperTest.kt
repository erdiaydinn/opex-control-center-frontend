package com.eay.mobile.fieldui.runtime

import com.eay.mobile.presentation.FieldPresentationNetworkState
import com.eay.mobile.presentation.MissionCardPresentationModel
import com.eay.mobile.presentation.MobileRuntimeProfile
import com.eay.mobile.presentation.TerminalScreenModel
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Test

class FieldUiRuntimeMapperTest {
    @Test
    fun `terminal mapper preserves only presentation mission data`() {
        val mapped = FieldUiRuntimeMapper.terminal(
            TerminalScreenModel(
                runtimeProfile = MobileRuntimeProfile.EAY_TERMINAL,
                offline = false,
                queueDepth = 0,
                syncIndicator = "Synced",
                missions = listOf(
                    MissionCardPresentationModel(
                        missionId = "inventory.count:abc",
                        missionType = "COUNT",
                        title = "Cycle count",
                        subtitle = "A-04",
                        progressLabel = "1 / 4",
                        etaLabel = "~8 min",
                        enabled = true,
                        blockedReason = null,
                    ),
                ),
            ),
        )

        assertEquals("Synced", mapped.header.syncIndicator)
        assertEquals("", mapped.header.locationLabel)
        assertEquals("", mapped.header.deviceLabel)
        assertEquals(1, mapped.missions.size)
        val mission = mapped.missions.single()
        assertEquals("inventory.count:abc", mission.missionId)
        assertEquals("Cycle count", mission.kind)
        assertEquals("A-04", mission.locationLabel)
        assertEquals("1 / 4", mission.progressLabel)
        assertNull(mission.statusLabel)
        assertTrue(mission.enabled)
    }

    @Test
    fun `blocked mission remains non executable in Compose model`() {
        val mapped = FieldUiRuntimeMapper.terminal(
            TerminalScreenModel(
                runtimeProfile = MobileRuntimeProfile.EAY_TERMINAL,
                offline = true,
                queueDepth = 2,
                syncIndicator = FieldPresentationNetworkState.QUARANTINED.name,
                missions = listOf(
                    MissionCardPresentationModel(
                        missionId = "inventory.count:blocked",
                        missionType = "COUNT",
                        title = "Cycle count",
                        subtitle = "B-02",
                        progressLabel = null,
                        etaLabel = null,
                        enabled = false,
                        blockedReason = "Review required",
                    ),
                ),
            ),
        )

        assertFalse(mapped.missions.single().enabled)
        assertEquals("Review required", mapped.missions.single().statusLabel)
    }
}
