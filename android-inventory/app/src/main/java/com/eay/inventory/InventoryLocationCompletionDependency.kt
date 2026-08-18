package com.eay.inventory

import org.json.JSONObject

enum class LocationCompletionDependencyDecision {
    CLEAR,
    WAIT,
    BLOCKED,
}

/**
 * Prevents a durable LOCATION_COMPLETE event from overtaking count-line evidence.
 *
 * The server remains authoritative. This client guard only preserves local device
 * ordering: a completion cannot be transmitted while an earlier count line for
 * the same document/location is still pending, retrying, or quarantined.
 */
object InventoryLocationCompletionDependency {
    fun evaluate(
        completion: OfflineEvent,
        unsettledPrior: List<OfflineEvent>,
    ): LocationCompletionDependencyDecision {
        val target = parse(completion.canonicalPayload)
            ?: return LocationCompletionDependencyDecision.BLOCKED
        if (target.eventKind != "LOCATION_COMPLETE") {
            return LocationCompletionDependencyDecision.CLEAR
        }

        var waiting = false
        for (prior in unsettledPrior) {
            if (prior.deviceSequence >= completion.deviceSequence) continue
            val parsed = parse(prior.canonicalPayload)
                ?: return LocationCompletionDependencyDecision.BLOCKED
            if (
                parsed.documentId != target.documentId ||
                parsed.locationId != target.locationId
            ) {
                continue
            }
            if (parsed.eventKind.isNotEmpty()) continue
            if (!parsed.hasBarcode) {
                return LocationCompletionDependencyDecision.BLOCKED
            }
            if (prior.state == "QUARANTINED") {
                return LocationCompletionDependencyDecision.BLOCKED
            }
            if (prior.state != "ACKED") waiting = true
        }
        return if (waiting) {
            LocationCompletionDependencyDecision.WAIT
        } else {
            LocationCompletionDependencyDecision.CLEAR
        }
    }

    private fun parse(payload: String): ParsedEvent? = runCatching {
        val json = JSONObject(payload)
        val documentId = json.getString("document_id").trim()
        val locationId = json.getString("location_id").trim().uppercase()
        require(documentId.isNotBlank())
        require(locationId.isNotBlank())
        ParsedEvent(
            documentId = documentId,
            locationId = locationId,
            eventKind = json.optString("event_kind").trim(),
            hasBarcode = json.has("barcode") && !json.isNull("barcode"),
        )
    }.getOrNull()

    private data class ParsedEvent(
        val documentId: String,
        val locationId: String,
        val eventKind: String,
        val hasBarcode: Boolean,
    )
}
