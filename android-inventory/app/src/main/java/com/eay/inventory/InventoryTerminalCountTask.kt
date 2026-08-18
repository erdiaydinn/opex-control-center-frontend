package com.eay.inventory

import com.eay.mobile.core.BlindCountLocationToken
import com.eay.mobile.core.BlindCountTarget
import com.eay.mobile.core.MobileRuntimeProfile
import java.util.UUID

/**
 * Location-bound COUNT mission returned by the production terminal task API.
 * Expected/system stock, cost, SKU universe and variance are intentionally absent.
 * activeShiftId is server-issued provenance; it never grants authority by itself.
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
    }

    fun blindCountTarget(targetLineCount: Int? = null): BlindCountTarget = BlindCountTarget(
        missionId = missionId,
        locationTokenHash = BlindCountLocationToken.hash(locationId),
        targetLineCount = targetLineCount,
    )

    fun eventContext(): InventoryCountEventContext = InventoryCountEventContext(
        missionId = missionId,
        documentId = documentId,
        activeShiftId = activeShiftId,
        locationId = locationId,
    )
}
