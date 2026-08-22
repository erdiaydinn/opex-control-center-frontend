package com.eay.inventory

import org.json.JSONObject
import java.util.Locale
import java.util.UUID

enum class InventoryLocalCompletionState {
    OPEN,
    AWAITING_SERVER,
    REQUIRES_REVIEW,
}

data class InventoryLocalCompletionBinding(
    val documentId: String,
    val locationId: String,
)

/**
 * Projects encrypted offline evidence into a presentation-safe local mission state.
 *
 * This is not authorization and never marks a mission server-complete. It exists only
 * to prevent a durable-but-not-yet-accepted LOCATION_COMPLETE event from being shown
 * as a fresh executable mission after process death/restart. Server task truth remains
 * authoritative once the completion event is ACKED.
 */
object InventoryLocalMissionTruth {
    fun classify(
        tasks: List<InventoryTerminalCountTask>,
        unsettledEvents: Collection<OfflineEvent>,
    ): Map<String, InventoryLocalCompletionState> = tasks.associate { task ->
        task.missionId to stateFor(task, unsettledEvents)
    }

    fun stateFor(
        task: InventoryTerminalCountTask,
        unsettledEvents: Collection<OfflineEvent>,
    ): InventoryLocalCompletionState {
        val taskBinding = InventoryLocalCompletionBinding(
            documentId = UUID.fromString(task.documentId).toString(),
            locationId = normalizeLocation(task.locationId),
        )
        val matches = unsettledEvents.filter { event ->
            event.state != "ACKED" && binding(event.canonicalPayload) == taskBinding
        }
        if (matches.isEmpty()) return InventoryLocalCompletionState.OPEN
        if (matches.any { it.state == "QUARANTINED" }) {
            return InventoryLocalCompletionState.REQUIRES_REVIEW
        }
        if (matches.any { it.state !in setOf("PENDING", "RETRY_WAIT") }) {
            // Unknown durable states fail closed rather than reopening execution.
            return InventoryLocalCompletionState.REQUIRES_REVIEW
        }
        return InventoryLocalCompletionState.AWAITING_SERVER
    }

    fun binding(canonicalPayload: String): InventoryLocalCompletionBinding? = runCatching {
        val json = JSONObject(canonicalPayload)
        if (json.optString("event_kind") != "LOCATION_COMPLETE") return@runCatching null
        InventoryLocalCompletionBinding(
            documentId = UUID.fromString(json.getString("document_id")).toString(),
            locationId = normalizeLocation(json.getString("location_id")),
        )
    }.getOrNull()

    private fun normalizeLocation(value: String): String =
        value.trim().uppercase(Locale.ROOT)
}
