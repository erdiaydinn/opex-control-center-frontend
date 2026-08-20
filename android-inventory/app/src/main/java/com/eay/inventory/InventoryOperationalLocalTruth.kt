package com.eay.inventory

import org.json.JSONObject
import java.util.UUID

/**
 * Presentation-safe restart guard for operational missions with durable local evidence.
 *
 * It never advances workflow state. If a process restarts while operational evidence is
 * still unsettled, the mission remains locally non-executable until the signed sync path
 * settles that evidence and a fresh server projection is loaded.
 */
object InventoryOperationalLocalTruth {
    fun classify(
        tasks: List<InventoryOperationalTask>,
        unsettledEvents: Collection<OfflineEvent>,
    ): Map<String, InventoryLocalCompletionState> = tasks.associate { task ->
        task.missionId to stateFor(task, unsettledEvents)
    }

    fun stateFor(
        task: InventoryOperationalTask,
        unsettledEvents: Collection<OfflineEvent>,
    ): InventoryLocalCompletionState {
        val missionId = UUID.fromString(task.missionId).toString()
        val matches = unsettledEvents.filter { event ->
            event.state != "ACKED" && missionBinding(event.canonicalPayload) == missionId
        }
        if (matches.isEmpty()) return InventoryLocalCompletionState.OPEN
        if (matches.any { it.state == "QUARANTINED" }) {
            return InventoryLocalCompletionState.REQUIRES_REVIEW
        }
        if (matches.any { it.state !in setOf("PENDING", "RETRY_WAIT") }) {
            return InventoryLocalCompletionState.REQUIRES_REVIEW
        }
        return InventoryLocalCompletionState.AWAITING_SERVER
    }

    fun missionBinding(canonicalPayload: String): String? = runCatching {
        if (!InventoryOperationalEventCanonical.isOperationalBody(canonicalPayload)) {
            return@runCatching null
        }
        UUID.fromString(JSONObject(canonicalPayload).getString("mission_id")).toString()
    }.getOrNull()
}
