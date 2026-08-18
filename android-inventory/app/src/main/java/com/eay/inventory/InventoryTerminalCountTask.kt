package com.eay.inventory

import com.eay.mobile.core.BlindCountLocationToken
import com.eay.mobile.core.BlindCountTarget
import com.eay.mobile.core.MobileRuntimeProfile
import java.util.Locale
import java.util.UUID

/**
 * Location-bound COUNT mission returned by the production terminal task API.
 * The task itself is not mutation authority; a server-issued attempt/lease claim
 * is mandatory before an event context can be created.
 */
data class InventoryTerminalCountTask(
    val missionId: String,
    val documentId: String,
    val activeShiftId: String,
    val warehouseId: String,
    val locationId: String,
    val name: String,
    val state: String,
    val revision: Int,
    val locationCount: Int,
    val claimRequired: Boolean = true,
    val operation: String = "inventory.count",
    val runtimeProfile: MobileRuntimeProfile = MobileRuntimeProfile.EAY_TERMINAL,
) {
    init {
        require(missionId.matches(Regex("^[A-Za-z0-9._:-]{1,128}$")))
        UUID.fromString(documentId)
        require(activeShiftId.matches(Regex("^[A-Za-z0-9._:-]{1,128}$")))
        require(warehouseId.isNotBlank())
        require(locationId.isNotBlank())
        require(name.isNotBlank())
        require(state == "COUNTING")
        require(revision > 0)
        require(locationCount > 0)
        require(claimRequired)
        require(operation == "inventory.count")
        require(runtimeProfile == MobileRuntimeProfile.EAY_TERMINAL)
    }

    fun blindCountTarget(targetLineCount: Int? = null): BlindCountTarget = BlindCountTarget(
        missionId = missionId,
        locationTokenHash = BlindCountLocationToken.hash(locationId),
        targetLineCount = targetLineCount,
    )

    fun eventContext(claim: InventoryMissionAttemptClaim): InventoryCountEventContext {
        require(claim.documentId == documentId) { "Mission claim document mismatch" }
        require(
            claim.locationId.trim().uppercase(Locale.ROOT) == locationId.trim().uppercase(Locale.ROOT),
        ) { "Mission claim location mismatch" }
        require(claim.activeShiftId == activeShiftId) { "Mission claim shift mismatch" }
        return InventoryCountEventContext(
            missionId = missionId,
            documentId = documentId,
            activeShiftId = activeShiftId,
            attemptId = claim.attemptId,
            leaseId = claim.leaseId,
            locationId = locationId,
        )
    }
}
