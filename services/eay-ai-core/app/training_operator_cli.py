from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

from .training_execution import (
    TrainingExecutionRegistry,
    TrainingExecutionRequest,
)
from .training_executor import (
    execute_registered_training,
    preview_registered_training,
)
from .training_job_registry import TrainingJobRegistration, TrainingJobRegistry
from .training_manifest import TrainingManifestCreate, TrainingManifestStore


def _json_file(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError(f"training_cli_invalid_json:{path}") from exc


def _example_list(path: Path) -> list[dict[str, Any]]:
    payload = _json_file(path)
    if not isinstance(payload, list) or not all(isinstance(item, dict) for item in payload):
        raise ValueError(f"training_cli_example_list_required:{path}")
    return payload


def _print_model(model: Any) -> None:
    if hasattr(model, "model_dump_json"):
        print(model.model_dump_json(indent=2))
        return
    print(json.dumps(model, indent=2, ensure_ascii=False, sort_keys=True))


def _create_manifest(args: argparse.Namespace) -> None:
    store = TrainingManifestStore(args.db_path)
    eval_examples = _example_list(args.eval_json) if args.eval_json else []
    record = store.create(
        TrainingManifestCreate(
            examples=_example_list(args.train_json),
            eval_examples=eval_examples,
            approved_by=args.approved_by,
            approval_reference=args.approval_reference,
            parent_manifest_id=args.parent_manifest_id,
        )
    )
    _print_model(record)


def _register_job(args: argparse.Namespace) -> None:
    spec = _json_file(args.spec_json)
    if not isinstance(spec, dict):
        raise ValueError("training_cli_job_spec_object_required")
    registry = TrainingJobRegistry(args.db_path)
    record = registry.register(
        TrainingJobRegistration(
            spec=spec,
            approved_by=args.approved_by,
            approval_reference=args.approval_reference,
        )
    )
    _print_model(record)


def _create_plan(args: argparse.Namespace) -> None:
    registry = TrainingExecutionRegistry(args.db_path)
    record = registry.create_plan(
        TrainingExecutionRequest(
            training_job_fingerprint=args.training_job_fingerprint,
            base_model_path=str(args.base_model_path),
            training_dataset_path=str(args.training_dataset_path),
            eval_dataset_path=str(args.eval_dataset_path),
            output_path=str(args.output_path),
            requested_by=args.requested_by,
            execution_reference=args.execution_reference,
        )
    )
    _print_model(record)


def _preview(args: argparse.Namespace) -> None:
    _print_model(
        preview_registered_training(
            db_path=args.db_path,
            plan_fingerprint=args.plan_fingerprint,
        )
    )


def _execute(args: argparse.Namespace) -> None:
    _print_model(
        execute_registered_training(
            db_path=args.db_path,
            plan_fingerprint=args.plan_fingerprint,
            executor=args.executor,
            execution_reference=args.execution_reference,
        )
    )


def _verify_receipt(args: argparse.Namespace) -> None:
    registry = TrainingExecutionRegistry(args.db_path)
    _print_model(
        registry.require_verified_artifact(
            training_job_fingerprint=args.training_job_fingerprint,
            artifact_sha256=args.artifact_sha256,
        )
    )


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="EAY governed training operator CLI",
    )
    parser.add_argument(
        "--db-path",
        type=Path,
        required=True,
        help="Path to the EAY AI Core SQLite governance database.",
    )
    commands = parser.add_subparsers(dest="command", required=True)

    manifest = commands.add_parser(
        "create-manifest",
        help="Gate reviewed train/eval examples and create an immutable dataset manifest.",
    )
    manifest.add_argument("--train-json", type=Path, required=True)
    manifest.add_argument("--eval-json", type=Path)
    manifest.add_argument("--approved-by", required=True)
    manifest.add_argument("--approval-reference", required=True)
    manifest.add_argument("--parent-manifest-id")
    manifest.set_defaults(handler=_create_manifest)

    job = commands.add_parser(
        "register-job",
        help="Register an immutable LoRA/QLoRA job spec bound to a reviewed manifest.",
    )
    job.add_argument("--spec-json", type=Path, required=True)
    job.add_argument("--approved-by", required=True)
    job.add_argument("--approval-reference", required=True)
    job.set_defaults(handler=_register_job)

    plan = commands.add_parser(
        "create-plan",
        help="Re-hash local inputs and create an immutable offline execution plan.",
    )
    plan.add_argument("--training-job-fingerprint", required=True)
    plan.add_argument("--base-model-path", type=Path, required=True)
    plan.add_argument("--training-dataset-path", type=Path, required=True)
    plan.add_argument("--eval-dataset-path", type=Path, required=True)
    plan.add_argument("--output-path", type=Path, required=True)
    plan.add_argument("--requested-by", required=True)
    plan.add_argument("--execution-reference", required=True)
    plan.set_defaults(handler=_create_plan)

    preview = commands.add_parser(
        "preview",
        help="Fail-closed preflight without importing the heavy ML runtime.",
    )
    preview.add_argument("--plan-fingerprint", required=True)
    preview.set_defaults(handler=_preview)

    execute = commands.add_parser(
        "execute",
        help="Run the registered local LoRA/QLoRA plan and create a real artifact receipt.",
    )
    execute.add_argument("--plan-fingerprint", required=True)
    execute.add_argument("--executor", required=True)
    execute.add_argument("--execution-reference", required=True)
    execute.set_defaults(handler=_execute)

    verify = commands.add_parser(
        "verify-receipt",
        help="Re-hash the observed artifact and re-verify its immutable execution receipt.",
    )
    verify.add_argument("--training-job-fingerprint", required=True)
    verify.add_argument("--artifact-sha256", required=True)
    verify.set_defaults(handler=_verify_receipt)

    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    args.handler(args)
    return 0


if __name__ == "__main__":
    sys.exit(main())
