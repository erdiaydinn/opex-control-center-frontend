package com.eay.mobile.core

enum class FieldMissionKind {
    SHIFT,
    PICK,
    COUNT,
    PUTAWAY,
    RECEIVING,
    TRANSFER,
    PLANOGRAM,
    AUDIT,
    ACADEMY,
    JARVIS,
}

enum class FieldMissionPriority(val weight: Int) {
    LOW(10),
    NORMAL(20),
    HIGH(30),
    URGENT(40),
}

enum class FieldMissionState {
    ASSIGNED,
    READY,
    IN_PROGRESS,
    BLOCKED,
    COMPLETED,
    CANCELLED,
}

data class FieldMission(
    val missionId: String,
    val tenantId: String,
    val assignedActorId: String,
    val locationId: String,
    val kind: FieldMissionKind,
    val operation: String,
    val title: String,
    val priority: FieldMissionPriority,
    val state: FieldMissionState,
    val runtimeProfiles: Set<MobileRuntimeProfile>,
    val createdAtEpochMs: Long,
    val dueAtEpochMs: Long? = null,
    val estimatedSeconds: Int? = null,
) {
    fun isStructurallyValid(): Boolean =
        missionId.isNotBlank() &&
            tenantId.isNotBlank() &&
            assignedActorId.isNotBlank() &&
            locationId.isNotBlank() &&
            operation.isNotBlank() &&
            title.isNotBlank() &&
            runtimeProfiles.isNotEmpty() &&
            createdAtEpochMs > 0 &&
            (dueAtEpochMs == null || dueAtEpochMs >= createdAtEpochMs) &&
            (estimatedSeconds == null || estimatedSeconds > 0)
}

enum class MissionGateCode {
    ALLOW,
    DENY_INVALID_MISSION,
    DENY_MISSION_STATE,
    DENY_MISSION_TENANT,
    DENY_MISSION_ACTOR,
    DENY_MISSION_LOCATION,
    DENY_MISSION_RUNTIME,
    DENY_OPERATION_POLICY,
}

data class MissionLaunchDecision(
    val allowed: Boolean,
    val code: MissionGateCode,
    val admissionCode: AdmissionCode? = null,
)

object MissionGate {
    private val actionableStates = setOf(
        FieldMissionState.ASSIGNED,
        FieldMissionState.READY,
        FieldMissionState.IN_PROGRESS,
    )

    fun evaluate(
        mission: FieldMission,
        context: MobileExecutionContext,
        snapshot: MobileAuthorizationSnapshot?,
        nowEpochMs: Long,
    ): MissionLaunchDecision {
        if (!mission.isStructurallyValid()) {
            return deny(MissionGateCode.DENY_INVALID_MISSION)
        }
        if (mission.state !in actionableStates) {
            return deny(MissionGateCode.DENY_MISSION_STATE)
        }
        if (mission.tenantId != context.tenantId) {
            return deny(MissionGateCode.DENY_MISSION_TENANT)
        }
        if (mission.assignedActorId != context.actorId) {
            return deny(MissionGateCode.DENY_MISSION_ACTOR)
        }
        if (mission.locationId != context.locationId) {
            return deny(MissionGateCode.DENY_MISSION_LOCATION)
        }
        if (context.runtimeProfile !in mission.runtimeProfiles) {
            return deny(MissionGateCode.DENY_MISSION_RUNTIME)
        }

        val admission = MobileOperationAdmission.evaluate(
            context = context,
            snapshot = snapshot,
            operation = mission.operation,
            nowEpochMs = nowEpochMs,
        )
        if (!admission.allowed) {
            return MissionLaunchDecision(
                allowed = false,
                code = MissionGateCode.DENY_OPERATION_POLICY,
                admissionCode = admission.code,
            )
        }
        return MissionLaunchDecision(
            allowed = true,
            code = MissionGateCode.ALLOW,
            admissionCode = AdmissionCode.ALLOW,
        )
    }

    private fun deny(code: MissionGateCode) = MissionLaunchDecision(false, code)
}

object MissionQueue {
    private val actionableStates = setOf(
        FieldMissionState.ASSIGNED,
        FieldMissionState.READY,
        FieldMissionState.IN_PROGRESS,
    )

    fun orderedFor(
        missions: Collection<FieldMission>,
        context: MobileExecutionContext,
        nowEpochMs: Long,
    ): List<FieldMission> = missions
        .asSequence()
        .filter { it.isStructurallyValid() }
        .filter { it.state in actionableStates }
        .filter { it.tenantId == context.tenantId }
        .filter { it.assignedActorId == context.actorId }
        .filter { it.locationId == context.locationId }
        .filter { context.runtimeProfile in it.runtimeProfiles }
        .sortedWith(
            compareBy<FieldMission> { if (it.state == FieldMissionState.IN_PROGRESS) 0 else 1 }
                .thenBy { if (it.dueAtEpochMs != null && it.dueAtEpochMs < nowEpochMs) 0 else 1 }
                .thenByDescending { it.priority.weight }
                .thenBy { it.dueAtEpochMs ?: Long.MAX_VALUE }
                .thenBy { it.createdAtEpochMs }
                .thenBy { it.missionId },
        )
        .toList()
}
