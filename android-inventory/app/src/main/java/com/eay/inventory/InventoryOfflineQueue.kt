package com.eay.inventory

/**
 * Single enqueue boundary for terminal mutations.
 *
 * Offline events are deliberately bound to the current interactive OIDC grant.
 * Refresh-token rotation preserves the same binding; a new interactive login
 * receives a new binding and cannot replay mutations created by the old grant.
 *
 * Re-enqueuing the exact same immutable event is idempotent. Reusing an event ID
 * for a different sequence, payload, hash or auth binding fails closed instead
 * of mutating the already-durable event or resurrecting an ACKED event.
 */
class InventoryOfflineQueue(private val database: InventoryDatabase) {
    suspend fun enqueue(event: OfflineEvent) {
        val binding = database.sessions().get()?.authBindingId.orEmpty()
        require(binding.isNotBlank()) { "Verified interactive inventory session is required" }
        require(event.authBindingId.isBlank() || event.authBindingId == binding) {
            "Offline event is bound to a different inventory session"
        }

        val boundEvent = event.copy(authBindingId = binding)
        val existing = database.events().byEventId(event.eventId)
        if (existing != null) {
            require(OfflineEventIdentity.sameImmutableIdentity(existing, boundEvent)) {
                "Offline event ID collision"
            }
            return
        }

        database.events().insert(boundEvent)
    }
}

object OfflineEventIdentity {
    fun sameImmutableIdentity(existing: OfflineEvent, incoming: OfflineEvent): Boolean =
        existing.eventId == incoming.eventId &&
            existing.deviceSequence == incoming.deviceSequence &&
            existing.canonicalPayload == incoming.canonicalPayload &&
            existing.payloadHash == incoming.payloadHash &&
            existing.authBindingId.isNotBlank() &&
            existing.authBindingId == incoming.authBindingId
}
