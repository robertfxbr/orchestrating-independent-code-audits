from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
from dataclasses import dataclass
from pathlib import Path

from jsonschema import ValidationError, validate


class AuditorFailure(Exception):
    def __init__(self, message: str, status: str = "AUDITOR_FAILURE") -> None:
        super().__init__(message)
        self.status = status


class AttemptAlreadyExistsError(Exception):
    def __init__(self, attempt_dir: Path) -> None:
        super().__init__(f"audit attempt already exists and is immutable: {attempt_dir}")
        self.status = "REPOSITORY_SAFETY_STOP"


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

    def with_runtime_root(self, runtime_root: Path) -> "BridgeConfig":
        return BridgeConfig(
            runtime_root=runtime_root,
            agy_command=self.agy_command,
            task_model=self.task_model,
            high_model=self.high_model,
            final_model=self.final_model,
            protected_contract_files=self.protected_contract_files,
        )


@dataclass(frozen=True)
class BridgeResult:
    status: str
    attempt_dir: Path | None
    head_sha: str | None
    message: str


@dataclass(frozen=True)
class AuditRequest:
    phase: str
    task_id: str
    base_sha: str
    head_sha: str
    spec_path: Path
    plan_path: Path
    test_output_path: Path | None
    tdd_evidence_path: Path | None


@dataclass(frozen=True)
class GitState:
    repository: str
    worktree: Path
    branch: str
    base_sha: str
    head_sha: str
    tree_sha: str


def _run_git(worktree: Path, *args: str) -> str:
    return subprocess.run(
        ["git", *args],
        cwd=worktree,
        check=True,
        capture_output=True,
        text=True,
    ).stdout


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def collect_git_state(worktree: Path, base_sha: str, head_sha: str) -> GitState:
    root = Path(_run_git(worktree, "rev-parse", "--show-toplevel").strip())
    branch = _run_git(root, "branch", "--show-current").strip()
    tree_sha = _run_git(root, "rev-parse", f"{head_sha}^{{tree}}").strip()
    return GitState(
        repository=root.name,
        worktree=root,
        branch=branch,
        base_sha=base_sha,
        head_sha=head_sha,
        tree_sha=tree_sha,
    )


def _request_worktree(request: AuditRequest) -> Path:
    return Path(
        subprocess.run(
            ["git", "-C", str(request.spec_path.parent), "rev-parse", "--show-toplevel"],
            check=True,
            capture_output=True,
            text=True,
        ).stdout.strip()
    )


def _attempt_dir(config: BridgeConfig, state: GitState, request: AuditRequest) -> Path:
    return config.runtime_root / state.repository / request.phase / request.task_id / "attempt-01"


def build_audit_package(config: BridgeConfig, request: AuditRequest) -> BridgeResult:
    worktree = _request_worktree(request)
    state = collect_git_state(worktree, request.base_sha, request.head_sha)
    attempt_dir = _attempt_dir(config, state, request)
    if attempt_dir.exists():
        raise AttemptAlreadyExistsError(attempt_dir)
    attempt_dir.mkdir(parents=True)

    changed_lines = _run_git(worktree, "diff", "--name-status", request.base_sha, request.head_sha)
    changed_files = []
    for line in changed_lines.splitlines():
        if not line.strip():
            continue
        parts = line.split()
        changed_files.append({"status": parts[0], "path": parts[-1]})

    manifest = {
        "phase": request.phase,
        "task_id": request.task_id,
        "attempt": attempt_dir.name,
        "repository": state.repository,
        "worktree": str(state.worktree),
        "branch": state.branch,
        "base_sha": state.base_sha,
        "head_sha": state.head_sha,
        "tree_sha": state.tree_sha,
        "spec_path": str(request.spec_path),
        "spec_sha256": _sha256(request.spec_path),
        "plan_path": str(request.plan_path),
        "plan_sha256": _sha256(request.plan_path),
    }

    (attempt_dir / "manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    (attempt_dir / "git-status.txt").write_text(_run_git(worktree, "status", "--short", "--branch"), encoding="utf-8")
    (attempt_dir / "git-log.txt").write_text(_run_git(worktree, "log", "--oneline", f"{request.base_sha}..{request.head_sha}"), encoding="utf-8")
    (attempt_dir / "commit.json").write_text(
        json.dumps(
            {
                "raw": _run_git(
                    worktree,
                    "show",
                    "--no-patch",
                    "--format=%H%n%an%n%ae%n%at%n%s",
                    request.head_sha,
                )
            },
            indent=2,
        ),
        encoding="utf-8",
    )
    (attempt_dir / "files-changed.json").write_text(json.dumps(changed_files, indent=2), encoding="utf-8")
    (attempt_dir / "diff.patch").write_text(_run_git(worktree, "diff", request.base_sha, request.head_sha), encoding="utf-8")
    (attempt_dir / "production_diff.patch").write_text("", encoding="utf-8")
    (attempt_dir / "test_diff.patch").write_text("", encoding="utf-8")
    (attempt_dir / "contract_diff.patch").write_text("", encoding="utf-8")
    (attempt_dir / "test-summary.json").write_text("{}", encoding="utf-8")
    (attempt_dir / "test-output.txt").write_text(
        request.test_output_path.read_text(encoding="utf-8") if request.test_output_path else "",
        encoding="utf-8",
    )
    (attempt_dir / "tdd-evidence.md").write_text(
        request.tdd_evidence_path.read_text(encoding="utf-8") if request.tdd_evidence_path else "",
        encoding="utf-8",
    )

    return BridgeResult("PACKAGE_CREATED", attempt_dir, request.head_sha, "audit package created")


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
