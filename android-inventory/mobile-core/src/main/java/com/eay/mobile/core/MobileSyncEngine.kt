package com.eay.mobile.core

enum class SyncRecordState {
    QUEUED,
    RETRY_WAIT,
    ACKED,
    QUARANTINED,
}

enum class SyncQuarantineReason {
    CORRUPT_EVENT,
    LEDGER_CHAIN_MISMATCH,
    TENANT_BINDING_CHANGED,
    DEVICE_BINDING_CHANGED,
    INSTALLATION_BINDING_CHANGED,
    AUTH_BINDING_CHANGED,
    DEVICE_REVOKED,
    POLICY_REJECTED,
    BUSINESS_CONFLICT,
    SERVER_CONTRACT_MISMATCH,
    DEPENDENCY_BLOCKED,
    PERMANENT_REJECTED,
    RETRY_EXHAUSTED,
}

data class SyncRecord(
    val event: MobileEventEnvelope,
    val state: SyncRecordState = SyncRecordState.QUEUED,
    val attempts: Int = 0,
    val nextAttemptAtEpochMs: Long = 0,
    val quarantineReason: SyncQuarantineReason? = null,
    val lastServerCode: String? = null,
) {
    init {
        require(attempts >= 0) { "attempts cannot be negative" }
        require(nextAttemptAtEpochMs >= 0) { "nextAttemptAtEpochMs cannot be negative" }
        require(
            (state == SyncRecordState.QUARANTINED) == (quarantineReason != null),
        ) { "quarantine state and reason must agree" }
    }
}

data class SyncExecutionContext(
    val tenantId: String,
    val deviceId: String,
    val installationId: String,
    val authBindingId: String,
    val deviceActive: Boolean,
    val connectivity: ConnectivityState,
    val nowEpochMs: Long,
)

enum class SyncPlanCode {
    SEND,
    WAIT_OFFLINE,
    WAIT_BACKOFF,
    NOOP_ACKED,
    NOOP_QUARANTINED,
    QUARANTINE,
}

data class SyncPlan(
    val code: SyncPlanCode,
    val quarantineReason: SyncQuarantineReason? = null,
)

enum class SyncServerOutcome {
    COMMITTED,
    EXACT_REPLAY,
    RETRYABLE_FAILURE,
    AUTH_REJECTED,
    DEVICE_REJECTED,
    POLICY_REJECTED,
    BUSINESS_CONFLICT,
    PERMANENT_REJECTED,
}

data class SyncServerVerdict(
    val outcome: SyncServerOutcome,
    val code: String,
)

data class SyncRetryPolicy(
    val maxAttempts: Int = 8,
    val initialDelayMs: Long = 5_000,
    val maxDelayMs: Long = 300_000,
) {
    init {
        require(maxAttempts in 1..50)
        require(initialDelayMs > 0)
        require(maxDelayMs >= initialDelayMs)
    }

    fun delayAfterFailure(attemptsAfterFailure: Int): Long {
        require(attemptsAfterFailure > 0)
        var delay = initialDelayMs
        repeat((attemptsAfterFailure - 1).coerceAtMost(30)) {
            if (delay >= maxDelayMs / 2) {
                delay = maxDelayMs
                return@repeat
            }
            delay *= 2
        }
        return delay.coerceAtMost(maxDelayMs)
    }
}

object MobileSyncEngine {
    fun plan(
        record: SyncRecord,
        context: SyncExecutionContext,
        expectedPreviousLedgerHash: String?,
        retryPolicy: SyncRetryPolicy = SyncRetryPolicy(),
    ): SyncPlan {
        if (record.state == SyncRecordState.ACKED) {
            return SyncPlan(SyncPlanCode.NOOP_ACKED)
        }
        if (record.state == SyncRecordState.QUARANTINED) {
            return SyncPlan(
                SyncPlanCode.NOOP_QUARANTINED,
                record.quarantineReason,
            )
        }
        if (!record.event.isStructurallyValid()) {
            return quarantine(SyncQuarantineReason.CORRUPT_EVENT)
        }
        if (
            MobileLedgerGuard.verifyChain(
                expectedPreviousLedgerHash,
                record.event,
            ) == ReplayDisposition.CHAIN_MISMATCH
        ) {
            return quarantine(SyncQuarantineReason.LEDGER_CHAIN_MISMATCH)
        }
        if (record.event.tenantId != context.tenantId) {
            return quarantine(SyncQuarantineReason.TENANT_BINDING_CHANGED)
        }
        if (record.event.deviceId != context.deviceId) {
            return quarantine(SyncQuarantineReason.DEVICE_BINDING_CHANGED)
        }
        if (record.event.installationId != context.installationId) {
            return quarantine(SyncQuarantineReason.INSTALLATION_BINDING_CHANGED)
        }
        if (record.event.authBindingId != context.authBindingId) {
            return quarantine(SyncQuarantineReason.AUTH_BINDING_CHANGED)
        }
        if (!context.deviceActive) {
            return quarantine(SyncQuarantineReason.DEVICE_REVOKED)
        }
        if (record.attempts >= retryPolicy.maxAttempts) {
            return quarantine(SyncQuarantineReason.RETRY_EXHAUSTED)
        }
        if (context.connectivity == ConnectivityState.OFFLINE) {
            return SyncPlan(SyncPlanCode.WAIT_OFFLINE)
        }
        if (record.nextAttemptAtEpochMs > context.nowEpochMs) {
            return SyncPlan(SyncPlanCode.WAIT_BACKOFF)
        }
        return SyncPlan(SyncPlanCode.SEND)
    }

    fun applyServerVerdict(
        record: SyncRecord,
        verdict: SyncServerVerdict,
        nowEpochMs: Long,
        retryPolicy: SyncRetryPolicy = SyncRetryPolicy(),
    ): SyncRecord = when (verdict.outcome) {
        SyncServerOutcome.COMMITTED,
        SyncServerOutcome.EXACT_REPLAY,
        -> record.copy(
            state = SyncRecordState.ACKED,
            quarantineReason = null,
            lastServerCode = verdict.code,
            nextAttemptAtEpochMs = 0,
        )

        SyncServerOutcome.RETRYABLE_FAILURE,
        SyncServerOutcome.AUTH_REJECTED,
        -> {
            val nextAttempts = record.attempts + 1
            if (nextAttempts >= retryPolicy.maxAttempts) {
                record.copy(
                    state = SyncRecordState.QUARANTINED,
                    attempts = nextAttempts,
                    quarantineReason = SyncQuarantineReason.RETRY_EXHAUSTED,
                    lastServerCode = verdict.code,
                    nextAttemptAtEpochMs = 0,
                )
            } else {
                record.copy(
                    state = SyncRecordState.RETRY_WAIT,
                    attempts = nextAttempts,
                    quarantineReason = null,
                    lastServerCode = verdict.code,
                    nextAttemptAtEpochMs = nowEpochMs +
                        retryPolicy.delayAfterFailure(nextAttempts),
                )
            }
        }

        SyncServerOutcome.DEVICE_REJECTED -> quarantineRecord(
            record,
            SyncQuarantineReason.DEVICE_REVOKED,
            verdict.code,
        )

        SyncServerOutcome.POLICY_REJECTED -> quarantineRecord(
            record,
            SyncQuarantineReason.POLICY_REJECTED,
            verdict.code,
        )

        SyncServerOutcome.BUSINESS_CONFLICT -> quarantineRecord(
            record,
            SyncQuarantineReason.BUSINESS_CONFLICT,
            verdict.code,
        )

        SyncServerOutcome.PERMANENT_REJECTED -> quarantineRecord(
            record,
            SyncQuarantineReason.PERMANENT_REJECTED,
            verdict.code,
        )
    }

    private fun quarantine(reason: SyncQuarantineReason) = SyncPlan(
        SyncPlanCode.QUARANTINE,
        reason,
    )

    private fun quarantineRecord(
        record: SyncRecord,
        reason: SyncQuarantineReason,
        serverCode: String,
    ) = record.copy(
        state = SyncRecordState.QUARANTINED,
        quarantineReason = reason,
        lastServerCode = serverCode,
        nextAttemptAtEpochMs = 0,
    )
}