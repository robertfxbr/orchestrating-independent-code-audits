from __future__ import annotations

import argparse
import json
import os
from dataclasses import dataclass
from pathlib import Path

from jsonschema import ValidationError, validate


class AuditorFailure(Exception):
    def __init__(self, message: str, status: str = "AUDITOR_FAILURE") -> None:
        super().__init__(message)
        self.status = status


@dataclass(frozen=True)
class BridgeConfig:
    runtime_root: Path
    agy_command: list[str]
    task_model: str
    high_model: str
    final_model: str
    protected_contract_files: tuple[str, ...] = ()

    @classmethod
    def from_env(cls) -> "BridgeConfig":
        local_app_data = Path(os.environ.get("LOCALAPPDATA", Path.home() / "AppData" / "Local"))
        return cls(
            runtime_root=local_app_data / "AurumAuditRuntime",
            agy_command=["agy"],
            task_model="Gemini 3.8 Flash Medium",
            high_model="Gemini 3.8 Flash High",
            final_model="Gemini 3.8 Flash High",
        )


@dataclass(frozen=True)
class BridgeResult:
    status: str
    attempt_dir: Path | None
    head_sha: str | None
    message: str


def load_schema(schema_path: Path) -> dict[str, object]:
    return json.loads(schema_path.read_text(encoding="utf-8"))


def parse_auditor_output(raw_output: str, schema_path: Path) -> dict[str, object]:
    if not raw_output.strip():
        raise AuditorFailure("auditor produced no output")

    try:
        payload = json.loads(raw_output)
        validate(instance=payload, schema=load_schema(schema_path))
    except (json.JSONDecodeError, ValidationError) as exc:
        raise AuditorFailure(f"invalid auditor verdict: {exc}") from exc

    return payload


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="audit_bridge")
    subcommands = parser.add_subparsers(dest="command", required=True)
    subcommands.add_parser("package")
    subcommands.add_parser("audit")
    subcommands.add_parser("finalize")
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    try:
        parser.parse_args(argv)
    except SystemExit as exc:
        return int(exc.code)
    return 0
