package com.eay.inventory

import androidx.room.withTransaction
import com.eay.mobile.core.AcceptedScan
import com.eay.mobile.core.BlindCountLineEvidence
import com.eay.mobile.core.OperationalStepKind

class RetryableCountPersistenceException(
    cause: Throwable,
) : RuntimeException("Encrypted count queue is temporarily unavailable", cause)

/** Single encrypted enqueue boundary for terminal mutations. */
class InventoryOfflineQueue(
    private val database: InventoryDatabase,
) : BlindCountEventSink {
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

    override suspend fun enqueueConfirmedCount(
        context: InventoryCountEventContext,
        acceptedScan: AcceptedScan,
        evidence: BlindCountLineEvidence,
        eventId: String,
        occurredAt: String,
    ): OfflineEvent = persistWithAllocatedSequence(eventId) { sequence, binding ->
        InventoryCountEventFactory.create(
            context = context,
            acceptedScan = acceptedScan,
            evidence = evidence,
            deviceSequence = sequence,
            eventId = eventId,
            occurredAt = occurredAt,
            authBindingId = binding,
        )
    }

    override suspend fun enqueueLocationCompletion(
        context: InventoryCountEventContext,
        confirmedLineCount: Int,
        eventId: String,
        occurredAt: String,
    ): OfflineEvent = persistWithAllocatedSequence(eventId) { sequence, binding ->
        InventoryLocationCompletionEventFactory.create(
            context = context,
            confirmedLineCount = confirmedLineCount,
            deviceSequence = sequence,
            eventId = eventId,
            occurredAt = occurredAt,
            authBindingId = binding,
        )
    }

    suspend fun enqueueOperationalStep(
        context: InventoryOperationalEventContext,
        step: OperationalStepKind,
        rawValue: String,
        eventId: String,
        occurredAt: String,
    ): OfflineEvent = persistWithAllocatedSequence(eventId) { sequence, binding ->
        InventoryOperationalEventCanonical.create(
            InventoryOperationalEventInput(
                context = context,
                stepKind = step,
                rawValue = rawValue,
                eventId = eventId,
                deviceSequence = sequence,
                occurredAt = occurredAt,
            ),
            authBindingId = binding,
        )
    }

    private suspend fun persistWithAllocatedSequence(
        eventId: String,
        factory: (Long, String) -> OfflineEvent,
    ): OfflineEvent = try {
        database.withTransaction {
            val binding = requireInteractiveBinding()
            val existing = database.events().byEventId(eventId)
            if (existing != null) {
                val replayCandidate = factory(existing.deviceSequence, binding)
                require(OfflineEventIdentity.sameImmutableIdentity(existing, replayCandidate)) {
                    "Offline terminal event ID collision"
                }
                return@withTransaction existing
            }

            val nextSequence = Math.addExact(database.events().maxDeviceSequence(), 1L)
            val event = factory(nextSequence, binding)
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
