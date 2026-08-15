package com.eay.inventory

/**
 * Single enqueue boundary for terminal mutations.
 *
 * Offline events are deliberately bound to the current interactive OIDC grant.
 * Refresh-token rotation preserves the same binding; a new interactive login
 * receives a new binding and cannot replay mutations created by the old grant.
 */
class InventoryOfflineQueue(private val database: InventoryDatabase) {
    suspend fun enqueue(event: OfflineEvent) {
        val binding = database.sessions().get()?.authBindingId.orEmpty()
        require(binding.isNotBlank()) { "Verified interactive inventory session is required" }
        require(event.authBindingId.isBlank() || event.authBindingId == binding) {
            "Offline event is bound to a different inventory session"
        }
        database.events().insert(event.copy(authBindingId = binding))
    }
}
