from __future__ import annotations

import argparse
import os
from dataclasses import dataclass
from pathlib import Path


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
