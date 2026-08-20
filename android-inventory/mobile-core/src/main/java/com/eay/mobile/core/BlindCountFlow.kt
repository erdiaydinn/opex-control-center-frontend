package com.eay.mobile.core

import java.util.Locale

enum class BlindCountStep {
    SCAN_LOCATION,
    SCAN_ITEM,
    ENTER_QUANTITY,
    CONFIRM_ITEM,
    COMPLETE,
}

enum class BlindCountCode {
    OK,
    DENY_MISSION,
    DENY_STEP,
    DENY_LOCATION,
    DENY_SCAN,
    DENY_QUANTITY,
    DENY_TARGET,
}

object BlindCountLocationToken {
    fun normalize(value: String): String = value.trim().uppercase(Locale.ROOT)

    fun hash(value: String): String {
        val normalized = normalize(value)
        require(normalized.isNotBlank())
        return sha256(normalized)
    }
}

data class BlindCountTarget(
    val missionId: String,
    val locationTokenHash: String,
    val targetLineCount: Int? = null,
) {
    init {
        require(missionId.isNotBlank())
        require(locationTokenHash.matches(Regex("^[a-f0-9]{64}$")))
        require(targetLineCount == null || targetLineCount > 0)
    }
}

data class BlindCountSession(
    val missionId: String,
    val step: BlindCountStep = BlindCountStep.SCAN_LOCATION,
    val locationVerified: Boolean = false,
    val currentItemHash: String? = null,
    val currentQuantity: Int? = null,
    val confirmedLineCount: Int = 0,
) {
    init {
        require(missionId.isNotBlank())
        require(confirmedLineCount >= 0)
        require(currentQuantity == null || currentQuantity >= 0)
    }
}

data class BlindCountLineEvidence(
    val missionId: String,
    val itemPayloadHash: String,
    val quantity: Int,
)

data class BlindCountTransition(
    val code: BlindCountCode,
    val session: BlindCountSession,
    val evidence: BlindCountLineEvidence? = null,
) {
    val accepted: Boolean get() = code == BlindCountCode.OK
}

object BlindCountFlow {
    const val MAX_QUANTITY = 999_999

    fun verifyLocation(
        session: BlindCountSession,
        target: BlindCountTarget,
        acceptedScan: AcceptedScan?,
    ): BlindCountTransition {
        if (session.missionId != target.missionId) {
            return denied(BlindCountCode.DENY_MISSION, session)
        }
        if (session.step != BlindCountStep.SCAN_LOCATION) {
            return denied(BlindCountCode.DENY_STEP, session)
        }
        val scan = acceptedScan
            ?: return denied(BlindCountCode.DENY_SCAN, session)
        if (BlindCountLocationToken.hash(scan.value) != target.locationTokenHash) {
            return denied(BlindCountCode.DENY_LOCATION, session)
        }
        return success(
            session.copy(
                step = BlindCountStep.SCAN_ITEM,
                locationVerified = true,
            ),
        )
    }

    fun scanItem(
        session: BlindCountSession,
        acceptedScan: AcceptedScan?,
    ): BlindCountTransition {
        if (!session.locationVerified || session.step != BlindCountStep.SCAN_ITEM) {
            return denied(BlindCountCode.DENY_STEP, session)
        }
        val scan = acceptedScan
            ?: return denied(BlindCountCode.DENY_SCAN, session)
        return success(
            session.copy(
                step = BlindCountStep.ENTER_QUANTITY,
                currentItemHash = scan.payloadHash,
                currentQuantity = null,
            ),
        )
    }

    fun enterQuantity(
        session: BlindCountSession,
        quantity: Int,
    ): BlindCountTransition {
        if (
            session.step != BlindCountStep.ENTER_QUANTITY ||
            session.currentItemHash == null
        ) {
            return denied(BlindCountCode.DENY_STEP, session)
        }
        if (quantity !in 0..MAX_QUANTITY) {
            return denied(BlindCountCode.DENY_QUANTITY, session)
        }
        return success(
            session.copy(
                step = BlindCountStep.CONFIRM_ITEM,
                currentQuantity = quantity,
            ),
        )
    }

    fun confirmItem(
        session: BlindCountSession,
        target: BlindCountTarget,
    ): BlindCountTransition {
        if (session.missionId != target.missionId) {
            return denied(BlindCountCode.DENY_MISSION, session)
        }
        if (
            session.step != BlindCountStep.CONFIRM_ITEM ||
            session.currentItemHash == null ||
            session.currentQuantity == null
        ) {
            return denied(BlindCountCode.DENY_STEP, session)
        }

        val nextCount = session.confirmedLineCount + 1
        if (target.targetLineCount != null && nextCount > target.targetLineCount) {
            return denied(BlindCountCode.DENY_TARGET, session)
        }
        val evidence = BlindCountLineEvidence(
            missionId = session.missionId,
            itemPayloadHash = session.currentItemHash,
            quantity = session.currentQuantity,
        )
        return BlindCountTransition(
            code = BlindCountCode.OK,
            session = session.copy(
                step = BlindCountStep.SCAN_ITEM,
                currentItemHash = null,
                currentQuantity = null,
                confirmedLineCount = nextCount,
            ),
            evidence = evidence,
        )
    }

    fun completeLocation(
        session: BlindCountSession,
        target: BlindCountTarget,
    ): BlindCountTransition {
        if (session.missionId != target.missionId) {
            return denied(BlindCountCode.DENY_MISSION, session)
        }
        if (!session.locationVerified || session.step != BlindCountStep.SCAN_ITEM) {
            return denied(BlindCountCode.DENY_STEP, session)
        }
        // A location scan alone is not evidence that the location is empty.
        // Empty-location completion requires a separate server-authorized,
        // signed evidence flow; until that contract exists, fail closed.
        if (session.confirmedLineCount == 0) {
            return denied(BlindCountCode.DENY_TARGET, session)
        }
        if (
            target.targetLineCount != null &&
            session.confirmedLineCount != target.targetLineCount
        ) {
            return denied(BlindCountCode.DENY_TARGET, session)
        }
        return success(session.copy(step = BlindCountStep.COMPLETE))
    }

    private fun success(session: BlindCountSession) = BlindCountTransition(
        code = BlindCountCode.OK,
        session = session,
    )

    private fun denied(
        code: BlindCountCode,
        session: BlindCountSession,
    ) = BlindCountTransition(code = code, session = session)
}
