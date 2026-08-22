from datetime import UTC, datetime

from app.cyber_world_championship import build_default_arena


def main() -> None:
    arena = build_default_arena(
        as_of=datetime.now(UTC),
        rotation_epoch="scheduled-current",
        sealed_ground_truth_ref="vault:cyber-world-championship:scheduled-current",
        task_count=1100,
    )
    print(f"CYBER_CHAMPIONSHIP_ARENA={arena.arena_id}")
    print(f"CYBER_CHAMPIONSHIP_TRACKS={len(arena.blind_task_manifest.tracks)}")
    print(f"CYBER_CHAMPIONSHIP_REQUIRED_BASELINES={len(arena.required_baselines)}")
    print(f"CYBER_CHAMPIONSHIP_CHALLENGE_READY={str(arena.challenge_ready).lower()}")
    print(
        "CYBER_CHAMPIONSHIP_VERIFIED_LEADER="
        f"{str(arena.verified_leader_claim_allowed).lower()}"
    )
    print(
        "CYBER_CHAMPIONSHIP_PRODUCTION_SUPERIORITY="
        f"{str(arena.production_security_superiority_claim_allowed).lower()}"
    )
    if not arena.challenge_ready:
        raise SystemExit("cyber_world_championship_not_challenge_ready")
    if arena.verified_leader_claim_allowed:
        raise SystemExit("cyber_world_championship_cannot_self_declare_leader")
    if arena.production_security_superiority_claim_allowed:
        raise SystemExit("cyber_world_championship_cannot_claim_production_superiority")


if __name__ == "__main__":
    main()
