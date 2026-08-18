package com.eay.inventory

import androidx.room.withTransaction
import com.eay.mobile.core.AcceptedScan
import com.eay.mobile.core.BlindCountLineEvidence

class RetryableCountPersistenceException(
    cause: Throwable,
) : RuntimeException("Encrypted count queue is temporarily unavailable", cause)

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
class InventoryOfflineQueue(
    private val database: InventoryDatabase,
) : ConfirmedCountEventSink {
    suspend fun enqueue(event: OfflineEvent) = database.withTransaction {
        val binding = requireInteractiveBinding()
        require(event.authBindingId.isBlank() || event.authBindingId == binding) {
            "Offline event is bound to a different inventory session"
        }

        val boundEvent = event.copy(authBindingId = binding)
        val existing = database.events().byEventId(event.eventId)
        if (existing != null) {
            require(OfflineEventIdentity.sameImmutableIdentity(existing, boundEvent)) {
                "Offline event ID collision"
            }
            return@withTransaction
        }

        val sequenceOwner = database.events().byDeviceSequence(boundEvent.deviceSequence)
        require(sequenceOwner == null) { "Offline device sequence collision" }
        database.events().insert(boundEvent)
    }

    /**
     * Atomic count-line boundary: allocate the next durable device sequence,
     * canonicalize the accepted scan + confirmed blind-count evidence and insert
     * the immutable event under the current verified OIDC binding in one SQLCipher
     * transaction.
     *
     * Contract/security violations remain fail-closed IllegalArgumentException.
     * Storage/runtime failures are explicitly wrapped as retryable so the controller
     * can preserve the exact event identity without silently advancing the count.
     */
    override suspend fun enqueueConfirmedCount(
        context: InventoryCountEventContext,
        acceptedScan: AcceptedScan,
        evidence: BlindCountLineEvidence,
        eventId: String,
        occurredAt: String,
    ): OfflineEvent = try {
        database.withTransaction {
            val binding = requireInteractiveBinding()
            val existing = database.events().byEventId(eventId)
            if (existing != null) {
                val replayCandidate = InventoryCountEventFactory.create(
                    context = context,
                    acceptedScan = acceptedScan,
                    evidence = evidence,
                    deviceSequence = existing.deviceSequence,
                    eventId = eventId,
                    occurredAt = occurredAt,
                    authBindingId = binding,
                )
                require(OfflineEventIdentity.sameImmutableIdentity(existing, replayCandidate)) {
                    "Offline count event ID collision"
                }
                return@withTransaction existing
            }

            val nextSequence = Math.addExact(database.events().maxDeviceSequence(), 1L)
            val event = InventoryCountEventFactory.create(
                context = context,
                acceptedScan = acceptedScan,
                evidence = evidence,
                deviceSequence = nextSequence,
                eventId = eventId,
                occurredAt = occurredAt,
                authBindingId = binding,
            )
            require(database.events().byDeviceSequence(nextSequence) == null) {
                "Offline device sequence collision"
            }
            database.events().insert(event)
            event
        }
    } catch (error: IllegalArgumentException) {
        throw error
    } catch (error: Exception) {
        throw RetryableCountPersistenceException(error)
    }

    private suspend fun requireInteractiveBinding(): String {
        val binding = database.sessions().get()?.authBindingId.orEmpty()
        require(binding.isNotBlank()) { "Verified interactive inventory session is required" }
        return binding
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
