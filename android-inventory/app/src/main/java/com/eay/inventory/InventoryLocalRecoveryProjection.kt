package com.eay.inventory

data class InventoryLocalRecoveryProjection(
    val missionTruth: Map<String, InventoryLocalCompletionState>,
    val recovery: InventoryRecoverySummary?,
)

/**
 * Reads the durable queue exactly once and derives every local presentation truth
 * from that immutable snapshot. No counter is guessed from UI/controller state.
 */
object InventoryLocalRecoveryProjectionReader {
    fun project(
        tasks: List<InventoryTerminalCountTask>,
        unsettled: List<OfflineEvent>,
    ): InventoryLocalRecoveryProjection = InventoryLocalRecoveryProjection(
        missionTruth = InventoryLocalMissionTruth.classify(tasks, unsettled),
        recovery = InventoryRecoveryContract.summarize(unsettled),
    )

    suspend fun read(
        database: InventoryDatabase,
        tasks: List<InventoryTerminalCountTask>,
    ): InventoryLocalRecoveryProjection {
        val unsettled = database.events().unsettledBefore(Long.MAX_VALUE)
        return project(tasks, unsettled)
    }
}
