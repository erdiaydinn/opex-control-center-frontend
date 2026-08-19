package com.eay.mobile.presentation.adapter

import com.eay.mobile.presentation.FieldMissionVisualKind
import com.eay.mobile.presentation.FieldMissionVisualPriority
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
}
