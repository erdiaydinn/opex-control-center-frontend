package com.eay.inventory

import com.eay.mobile.core.SyncQuarantineReason

enum class InventoryRecoverySeverity {
    INFO,
    ATTENTION,
    BLOCKING,
    SECURITY,
}

enum class InventoryRecoveryIntent {
    NONE,
    WAIT_FOR_AUTO_RETRY,
    WAIT_FOR_SUPERVISOR_REVIEW,
    SIGN_IN_AGAIN,
    RELOAD_MISSIONS,
    RECOVER_MANAGED_DEVICE,
    REQUEST_SUPERVISOR_REVIEW,
    REQUEST_SECURITY_REVIEW,
    REQUEST_INTEGRITY_REVIEW,
}

data class InventoryRecoveryItem(
    val eventId: String,
    val severity: InventoryRecoverySeverity,
    val intent: InventoryRecoveryIntent,
    val reason: SyncQuarantineReason?,
    val serverCode: String?,
) {
    init {
        require(eventId.isNotBlank())
        if (reason == null) {
            require(intent == InventoryRecoveryIntent.WAIT_FOR_AUTO_RETRY) {
                "Non-quarantined recovery may only wait for the existing sync engine"
            }
        } else {
            require(intent != InventoryRecoveryIntent.WAIT_FOR_AUTO_RETRY) {
                "Quarantined evidence must never be exposed as a client retry action"
            }
        }
    }
}

data class InventoryRecoverySummary(
    val severity: InventoryRecoverySeverity,
    val primaryIntent: InventoryRecoveryIntent,
    val affectedEventCount: Int,
    val quarantinedEventCount: Int,
    val pendingEventCount: Int,
) {
    init {
        require(affectedEventCount >= 0)
        require(quarantinedEventCount >= 0)
        require(pendingEventCount >= 0)
        require(quarantinedEventCount + pendingEventCount == affectedEventCount)
    }
}

/**
 * Presentation-safe recovery classifier for durable Inventory evidence.
 *
 * It never retries, deletes, rewrites, rebinds or reassigns an event. It only
 * explains the safest next user intent. The sync worker, server mission authority,
 * supervisor APIs and managed-device lifecycle remain the only mutation paths.
 */
object InventoryRecoveryContract {
    fun classify(event: OfflineEvent): InventoryRecoveryItem? {
        val state = event.state.trim().uppercase()
        if (state == "ACKED") return null
        if (state == "PENDING" || state == "RETRY_WAIT") {
            return InventoryRecoveryItem(
                eventId = event.eventId,
                severity = InventoryRecoverySeverity.INFO,
                intent = InventoryRecoveryIntent.WAIT_FOR_AUTO_RETRY,
                reason = null,
                serverCode = event.lastServerCode,
            )
        }
        if (state != "QUARANTINED") {
            return InventoryRecoveryItem(
                eventId = event.eventId,
                severity = InventoryRecoverySeverity.SECURITY,
                intent = InventoryRecoveryIntent.REQUEST_INTEGRITY_REVIEW,
                reason = SyncQuarantineReason.CORRUPT_EVENT,
                serverCode = "UNKNOWN_LOCAL_STATE",
            )
        }

        val reason = runCatching {
            SyncQuarantineReason.valueOf(event.quarantineReason.orEmpty())
        }.getOrElse {
            SyncQuarantineReason.CORRUPT_EVENT
        }
        val (severity, intent) = when (reason) {
            SyncQuarantineReason.CORRUPT_EVENT,
            SyncQuarantineReason.LEDGER_CHAIN_MISMATCH,
            SyncQuarantineReason.SERVER_CONTRACT_MISMATCH,
            SyncQuarantineReason.PERMANENT_REJECTED,
            -> InventoryRecoverySeverity.SECURITY to
                InventoryRecoveryIntent.REQUEST_INTEGRITY_REVIEW

            SyncQuarantineReason.TENANT_BINDING_CHANGED,
            SyncQuarantineReason.AUTH_BINDING_CHANGED,
            SyncQuarantineReason.POLICY_REJECTED,
            -> InventoryRecoverySeverity.SECURITY to
                InventoryRecoveryIntent.REQUEST_SECURITY_REVIEW

            SyncQuarantineReason.DEVICE_BINDING_CHANGED,
            SyncQuarantineReason.INSTALLATION_BINDING_CHANGED,
            SyncQuarantineReason.DEVICE_REVOKED,
            -> InventoryRecoverySeverity.BLOCKING to
                InventoryRecoveryIntent.RECOVER_MANAGED_DEVICE

            SyncQuarantineReason.BUSINESS_CONFLICT,
            SyncQuarantineReason.DEPENDENCY_BLOCKED,
            SyncQuarantineReason.RETRY_EXHAUSTED,
            -> if (
                event.recoveryState == "REQUESTED" &&
                !event.recoveryCaseId.isNullOrBlank()
            ) {
                InventoryRecoverySeverity.ATTENTION to
                    InventoryRecoveryIntent.WAIT_FOR_SUPERVISOR_REVIEW
            } else {
                InventoryRecoverySeverity.BLOCKING to
                    InventoryRecoveryIntent.REQUEST_SUPERVISOR_REVIEW
            }
        }
        return InventoryRecoveryItem(
            eventId = event.eventId,
            severity = severity,
            intent = intent,
            reason = reason,
            serverCode = event.lastServerCode,
        )
    }

    fun summarize(events: Collection<OfflineEvent>): InventoryRecoverySummary? {
        val items = events.mapNotNull(::classify)
        if (items.isEmpty()) return null
        val primary = items.maxWithOrNull(
            compareBy<InventoryRecoveryItem> { severityRank(it.severity) }
                .thenBy { intentRank(it.intent) },
        ) ?: return null
        val quarantined = items.count { it.reason != null }
        return InventoryRecoverySummary(
            severity = primary.severity,
            primaryIntent = primary.intent,
            affectedEventCount = items.size,
            quarantinedEventCount = quarantined,
            pendingEventCount = items.size - quarantined,
        )
    }

    private fun severityRank(severity: InventoryRecoverySeverity): Int = when (severity) {
        InventoryRecoverySeverity.INFO -> 0
        InventoryRecoverySeverity.ATTENTION -> 1
        InventoryRecoverySeverity.BLOCKING -> 2
        InventoryRecoverySeverity.SECURITY -> 3
    }

    private fun intentRank(intent: InventoryRecoveryIntent): Int = when (intent) {
        InventoryRecoveryIntent.NONE -> 0
        InventoryRecoveryIntent.WAIT_FOR_AUTO_RETRY -> 1
        InventoryRecoveryIntent.WAIT_FOR_SUPERVISOR_REVIEW -> 2
        InventoryRecoveryIntent.RELOAD_MISSIONS -> 3
        InventoryRecoveryIntent.SIGN_IN_AGAIN -> 4
        InventoryRecoveryIntent.REQUEST_SUPERVISOR_REVIEW -> 5
        InventoryRecoveryIntent.RECOVER_MANAGED_DEVICE -> 6
        InventoryRecoveryIntent.REQUEST_INTEGRITY_REVIEW -> 7
        InventoryRecoveryIntent.REQUEST_SECURITY_REVIEW -> 8
    }
}
