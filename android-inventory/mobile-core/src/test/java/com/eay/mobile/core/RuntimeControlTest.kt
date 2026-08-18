package com.eay.mobile.core

import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test

class RuntimeControlTest {
    private val now = 1_800_000_000_000L
    private val fingerprint = "a".repeat(64)

    private fun snapshot(
        rings: Set<RolloutRing> = setOf(RolloutRing.LAB),
    ) = RuntimeControlSnapshot(
        version = 1,
        policyFingerprint = fingerprint,
        issuedAtEpochMs = now - 1_000,
        expiresAtEpochMs = now + 60_000,
        controls = mapOf(
            RuntimeFeature.INVENTORY_COUNT_V2_UI to RuntimeFeatureControl(
                RuntimeFeature.INVENTORY_COUNT_V2_UI,
                rings,
            ),
        ),
    )

    @Test
    fun `optional feature defaults off without current server control`() {
        val decision = RuntimeControlGuard.evaluate(
            RuntimeFeature.INVENTORY_COUNT_V2_UI,
            null,
            fingerprint,
            RolloutRing.LAB,
            now,
        )
        assertFalse(decision.enabled)
        assertEquals(RuntimeControlCode.DISABLED_NO_SNAPSHOT, decision.code)
    }

    @Test
    fun `feature enables only for exact rollout ring and policy binding`() {
        val enabled = RuntimeControlGuard.evaluate(
            RuntimeFeature.INVENTORY_COUNT_V2_UI,
            snapshot(),
            fingerprint,
            RolloutRing.LAB,
            now,
        )
        assertTrue(enabled.enabled)

        val wrongRing = RuntimeControlGuard.evaluate(
            RuntimeFeature.INVENTORY_COUNT_V2_UI,
            snapshot(),
            fingerprint,
            RolloutRing.PILOT_1,
            now,
        )
        assertEquals(RuntimeControlCode.DISABLED_ROLLOUT_RING, wrongRing.code)
    }

    @Test
    fun `stale or policy mismatched runtime control fails closed`() {
        val mismatched = RuntimeControlGuard.evaluate(
            RuntimeFeature.INVENTORY_COUNT_V2_UI,
            snapshot(),
            "b".repeat(64),
            RolloutRing.LAB,
            now,
        )
        assertEquals(RuntimeControlCode.DISABLED_POLICY_MISMATCH, mismatched.code)

        val expired = RuntimeControlGuard.evaluate(
            RuntimeFeature.INVENTORY_COUNT_V2_UI,
            snapshot(),
            fingerprint,
            RolloutRing.LAB,
            now + 60_001,
        )
        assertEquals(RuntimeControlCode.DISABLED_EXPIRED, expired.code)
    }

    @Test
    fun `empty ring set is an immediate kill switch`() {
        val disabled = RuntimeControlGuard.evaluate(
            RuntimeFeature.INVENTORY_COUNT_V2_UI,
            snapshot(rings = emptySet()),
            fingerprint,
            RolloutRing.LAB,
            now,
        )
        assertEquals(RuntimeControlCode.DISABLED_ROLLOUT_RING, disabled.code)
    }
}
