package com.eay.mobile.presentation.adapter

import com.eay.mobile.core.BlindCountSession
import com.eay.mobile.core.BlindCountStep
import com.eay.mobile.core.BlindCountTarget
import com.eay.mobile.presentation.FieldMissionVisualKind
import com.eay.mobile.presentation.FieldMissionVisualPriority
import com.eay.mobile.presentation.FieldSyncVisualState
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test

class MissionIntentPresentationTest {
    @Test
    fun `pre-claim intent can enable callback without carrying execution authority`() {
        val card = FieldPresentationAdapter.missionIntentCard(
            MissionIntentPresentation(
                missionId = "count-doc-1-a04",
                title = "Inventory count",
                subtitle = "A-04",
                kind = FieldMissionVisualKind.COUNT,
                priority = FieldMissionVisualPriority.NORMAL,
                primaryActionLabel = "Open mission",
                enabled = true,
            ),
        )

        assertTrue(card.enabled)
        assertEquals(FieldMissionVisualKind.COUNT, card.kind)
        val fields = card::class.java.declaredFields.map { it.name.lowercase() }
        assertFalse(
            fields.any {
                it.contains("tenant") ||
                    it.contains("actor") ||
                    it.contains("employee") ||
                    it.contains("device") ||
                    it.contains("token") ||
                    it.contains("shift") ||
                    it.contains("lease") ||
                    it.contains("attempt") ||
                    it.contains("policy")
            },
        )
    }

    @Test
    fun `pre-claim intent preserves fail-closed local disablement`() {
        val card = FieldPresentationAdapter.missionIntentCard(
            MissionIntentPresentation(
                missionId = "count-doc-1-a04",
                title = "Inventory count",
                kind = FieldMissionVisualKind.COUNT,
                priority = FieldMissionVisualPriority.NORMAL,
                primaryActionLabel = "Open mission",
                enabled = false,
            ),
        )

        assertFalse(card.enabled)
    }

    @Test
    fun `blind count draft text stays presentation only until controller confirmation`() {
        val session = BlindCountSession(
            missionId = "mission-1",
            step = BlindCountStep.ENTER_QUANTITY,
            locationVerified = true,
            currentItemHash = "a".repeat(64),
            confirmedLineCount = 4,
        )
        val state = FieldPresentationAdapter.blindCount(
            session = session,
            target = BlindCountTarget(
                missionId = "mission-1",
                locationTokenHash = "b".repeat(64),
            ),
            copy = BlindCountPresentationCopy(
                locationLabel = "A-04",
                stepLabel = "Enter quantity",
                scannedItemLabel = "Count item",
                observedQuantityText = "27",
            ),
            syncState = FieldSyncVisualState.SYNCED,
        )

        assertEquals("27", state.observedQuantityText)
        assertEquals(4, state.confirmedLines)
        val fields = state::class.java.declaredFields.map { it.name.lowercase() }
        assertFalse(fields.any { it.contains("hash") || it.contains("expected") || it.contains("systemstock") })
    }
}
