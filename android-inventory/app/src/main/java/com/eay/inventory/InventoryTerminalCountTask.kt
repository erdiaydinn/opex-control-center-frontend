package com.eay.inventory

import com.eay.mobile.core.BlindCountLocationToken
import com.eay.mobile.core.BlindCountTarget
import com.eay.mobile.core.MobileRuntimeProfile
import java.time.OffsetDateTime
import java.util.UUID

enum class InventoryMissionClaimStatus {
    AVAILABLE,
    OWNED,
}

/**
 * Location-bound COUNT mission returned by the production terminal task API.
 * Authoritative inventory truth inputs are intentionally absent from this field contract.
 * Shift/attempt/lease values are server-issued provenance; none grants authority by itself.
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
    val claimStatus: InventoryMissionClaimStatus = InventoryMissionClaimStatus.AVAILABLE,
    val attemptId: String? = null,
    val leaseId: String? = null,
    val leaseValidUntil: String? = null,
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
        require(operation == "inventory.count")
        require(runtimeProfile == MobileRuntimeProfile.EAY_TERMINAL)
        attemptId?.let { UUID.fromString(it) }
        leaseId?.let { UUID.fromString(it) }
        when (claimStatus) {
            InventoryMissionClaimStatus.AVAILABLE -> {
                require(leaseId == null) { "Available mission cannot carry live lease authority" }
                require(leaseValidUntil == null) { "Available mission cannot carry lease expiry" }
            }
            InventoryMissionClaimStatus.OWNED -> {
                require(attemptId != null) { "Owned mission requires attempt authority" }
                require(leaseId != null) { "Owned mission requires lease authority" }
                require(!leaseValidUntil.isNullOrBlank()) { "Owned mission requires lease expiry" }
                OffsetDateTime.parse(leaseValidUntil)
            }
        }
    }

    fun blindCountTarget(targetLineCount: Int? = null): BlindCountTarget = BlindCountTarget(
        missionId = missionId,
        locationTokenHash = BlindCountLocationToken.hash(locationId),
        targetLineCount = targetLineCount,
    )

    fun eventContext(): InventoryCountEventContext {
        require(claimStatus == InventoryMissionClaimStatus.OWNED) {
            "Server mission claim is required before count execution"
        }
        return InventoryCountEventContext(
            missionId = missionId,
            documentId = documentId,
            activeShiftId = activeShiftId,
            attemptId = requireNotNull(attemptId),
            leaseId = requireNotNull(leaseId),
            locationId = locationId,
        )
    }
}
