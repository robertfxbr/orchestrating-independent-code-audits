from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import subprocess
from dataclasses import dataclass, replace
from pathlib import Path

from jsonschema import ValidationError, validate

from scripts.bindings import (
    DEFAULT_BINDINGS_PATH,
    Bindings,
    BindingsInvalid,
    BindingsRequired,
    load_bindings,
)
from scripts.preflight import all_auditors, check_auditors, run_check

ARCHITECTURE_STOP = "ARCHITECTURE_STOP"


class AuditorFailure(Exception):
    def __init__(self, message: str, status: str = "AUDITOR_FAILURE") -> None:
        super().__init__(message)
        self.status = status


class AuditProvenanceInvalid(Exception):
    def __init__(self, message: str) -> None:
        super().__init__(message)
        self.status = "AUDIT_PROVENANCE_INVALID"


MAX_AUDITOR_RETRIES = 2
AURUM_V16_BASE_SHA = "7804af0896d686a3376c2a6d3c3bc3bcb8be7f9d"

PROVENANCE_FILES = (
    "manifest.json",
    "git-status.txt",
    "git-log.txt",
    "files-changed.json",
    "diff.patch",
    "production_diff.patch",
    "test_diff.patch",
    "contract_diff.patch",
    "test-summary.json",
    "test-output.txt",
    "tdd-evidence.md",
    "agy-prompt.txt",
    "agy-raw-output.txt",
)


class AttemptAlreadyExistsError(Exception):
    def __init__(self, attempt_dir: Path) -> None:
        super().__init__(f"audit attempt already exists and is immutable: {attempt_dir}")
        self.status = "REPOSITORY_SAFETY_STOP"


class RepositorySafetyStop(Exception):
    def __init__(self, message: str) -> None:
        super().__init__(message)
        self.status = "REPOSITORY_SAFETY_STOP"


class ArchitectureStop(Exception):
    def __init__(self, message: str) -> None:
        super().__init__(message)
        self.status = ARCHITECTURE_STOP


@dataclass(frozen=True)
class BridgeConfig:
    runtime_root: Path
    agy_command: list[str]
    task_model: str
    high_model: str
    final_model: str
    protected_contract_files: tuple[str, ...] = ()
    agy_runner: object | None = None
    git_runner: object | None = None
    gh_runner: object | None = None
    bindings: Bindings | None = None
    check_runner: object | None = None
    which: object | None = None

    @classmethod
    def from_env(cls) -> "BridgeConfig":
        local_app_data = Path(os.environ.get("LOCALAPPDATA", Path.home() / "AppData" / "Local"))
        return cls(
            runtime_root=local_app_data / "AurumAuditRuntime",
            agy_command=["agy"],
            task_model="Gemini 3.8 Flash Medium",
            high_model="Gemini 3.8 Flash High",
            final_model="Gemini 3.8 Flash High",
            agy_runner=None,
            git_runner=None,
            gh_runner=None,
        )

    def with_runtime_root(self, runtime_root: Path) -> "BridgeConfig":
        return replace(self, runtime_root=runtime_root)

    def with_protected_contract_files(self, protected_contract_files: tuple[str, ...]) -> "BridgeConfig":
        return replace(self, protected_contract_files=protected_contract_files)

    def with_agy_runner(self, agy_runner: object) -> "BridgeConfig":
        return replace(self, agy_runner=agy_runner)

    def with_git_runner(self, git_runner: object) -> "BridgeConfig":
        return replace(self, git_runner=git_runner)

    def with_gh_runner(self, gh_runner: object) -> "BridgeConfig":
        return replace(self, gh_runner=gh_runner)

    def with_bindings(self, bindings: Bindings) -> "BridgeConfig":
        return replace(self, bindings=bindings)

    def with_check_tools(self, check_runner: object, which: object) -> "BridgeConfig":
        return replace(self, check_runner=check_runner, which=which)


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


def _normalize_repo_path(path: str) -> str:
    return path.replace("\\", "/")


def classify_changed_file(path: str, status: str, protected_contract_files: tuple[str, ...]) -> str:
    normalized = _normalize_repo_path(path)
    protected = {_normalize_repo_path(item) for item in protected_contract_files}
    if normalized in protected or normalized.startswith("docs/superpowers/specs/"):
        return "PROTECTED_CONTRACT"
    if normalized.startswith("tests/"):
        if status == "A":
            return "NEW_TEST"
        if status in {"M", "R"}:
            return "MODIFIED_EXISTING_TEST"
        if status == "D":
            return "DELETED_TEST"
    return "PRODUCTION"


def _diff_for_paths(worktree: Path, base_sha: str, head_sha: str, paths: list[str]) -> str:
    return "".join(_run_git(worktree, "diff", base_sha, head_sha, "--", path) for path in paths)


def detect_repository_safety_stop(
    worktree: Path,
    base_sha: str,
    head_sha: str,
    protected_contract_files: tuple[str, ...],
    runtime_root: Path,
) -> None:
    porcelain = _run_git(worktree, "status", "--porcelain")
    if porcelain.strip():
        raise RepositorySafetyStop("unexpected dirty worktree affects audit evidence")

    try:
        _run_git(worktree, "rev-parse", f"{base_sha}^{{commit}}")
        _run_git(worktree, "rev-parse", f"{head_sha}^{{commit}}")
    except subprocess.CalledProcessError as exc:
        raise RepositorySafetyStop("invalid audit commit SHA") from exc
    current_head = _run_git(worktree, "rev-parse", "HEAD").strip()
    if current_head != head_sha:
        raise RepositorySafetyStop("current HEAD differs from requested audited HEAD")

    changed_paths = [
        line.split()[-1]
        for line in _run_git(worktree, "diff", "--name-status", base_sha, head_sha).splitlines()
        if line.strip()
    ]
    for path in changed_paths:
        if classify_changed_file(path, "M", protected_contract_files) == "PROTECTED_CONTRACT":
            raise ArchitectureStop(f"protected contract changed: {path}")

    resolved_worktree = worktree.resolve()
    resolved_runtime = runtime_root.resolve()
    if resolved_worktree == resolved_runtime or resolved_worktree in resolved_runtime.parents:
        raise RepositorySafetyStop("runtime root resolves inside audited worktree")


def build_audit_package(config: BridgeConfig, request: AuditRequest) -> BridgeResult:
    worktree = _request_worktree(request)
    detect_repository_safety_stop(
        worktree,
        request.base_sha,
        request.head_sha,
        config.protected_contract_files,
        config.runtime_root,
    )
    state = collect_git_state(worktree, request.base_sha, request.head_sha)
    attempt_dir = _attempt_dir(config, state, request)
    if attempt_dir.exists():
        raise AttemptAlreadyExistsError(attempt_dir)
    attempt_dir.mkdir(parents=True)

    changed_lines = _run_git(worktree, "diff", "--name-status", request.base_sha, request.head_sha)
    changed_files = []
    production_paths: list[str] = []
    test_paths: list[str] = []
    contract_paths: list[str] = []
    test_summary: dict[str, str] = {}
    for line in changed_lines.splitlines():
        if not line.strip():
            continue
        parts = line.split()
        status = parts[0]
        path = parts[-1]
        classification = classify_changed_file(path, status, config.protected_contract_files)
        changed_files.append({"status": status, "path": path, "classification": classification})
        if classification == "PROTECTED_CONTRACT":
            contract_paths.append(path)
        elif classification in {"NEW_TEST", "MODIFIED_EXISTING_TEST", "DELETED_TEST"}:
            test_paths.append(path)
            test_summary[path] = classification
        else:
            production_paths.append(path)

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
    (attempt_dir / "production_diff.patch").write_text(
        _diff_for_paths(worktree, request.base_sha, request.head_sha, production_paths),
        encoding="utf-8",
    )
    (attempt_dir / "test_diff.patch").write_text(
        _diff_for_paths(worktree, request.base_sha, request.head_sha, test_paths),
        encoding="utf-8",
    )
    (attempt_dir / "contract_diff.patch").write_text(
        _diff_for_paths(worktree, request.base_sha, request.head_sha, contract_paths),
        encoding="utf-8",
    )
    (attempt_dir / "test-summary.json").write_text(json.dumps(test_summary, indent=2), encoding="utf-8")
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
        if isinstance(payload, dict) and "status" in payload:
            if payload["status"] != "SUCCESS" or "structured_output" not in payload:
                raise AuditorFailure("AGY returned an error or incomplete response")
            payload = payload["structured_output"]
        elif isinstance(payload, dict) and payload.get("type") == "result":
            if (payload.get("is_error") is not False or payload.get("subtype") != "success"
                    or not isinstance(payload.get("structured_output"), dict)):
                raise AuditorFailure("Claude returned an error or no structured output")
            payload = payload["structured_output"]
        validate(instance=payload, schema=load_schema(schema_path))
    except (json.JSONDecodeError, ValidationError) as exc:
        raise AuditorFailure(f"invalid auditor verdict: {exc}") from exc

    return payload


def render_auditor_prompt(kind: str, package_dir: Path, model: str) -> str:
    template_path = Path(__file__).resolve().parent.parent / "prompts" / f"{kind}_audit.md"
    if kind not in {"task", "escalation", "final_phase"}:
        raise ValueError(f"unsupported auditor prompt kind: {kind}")
    template = template_path.read_text(encoding="utf-8")
    return template.format(package_dir=package_dir, model=model)


def run_agy_audit(config: BridgeConfig, package_dir: Path, prompt_kind: str) -> str:
    model = {
        "task": config.task_model,
        "escalation": config.high_model,
        "final_phase": config.final_model,
    }[prompt_kind]
    prompt = render_auditor_prompt(prompt_kind, package_dir, model)
    prompt_path = package_dir / "agy-prompt.txt"
    prompt_path.write_text(prompt, encoding="utf-8")
    command = [
        *config.agy_command,
        "--model",
        {"Gemini 3.8 Flash Medium": "Gemini 3.8 Flash (Medium)",
         "Gemini 3.8 Flash High": "Gemini 3.8 Flash (High)"}.get(model, model),
        "--mode",
        "plan",
        "--sandbox",
        "--add-dir",
        str(package_dir),
        "--output-format",
        "json",
        "--json-schema",
        str(package_dir / "auditor_verdict.schema.json"),
        "--print",
        prompt,
    ]
    manifest_path = package_dir / "manifest.json"
    if manifest_path.exists():
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        if manifest.get("worktree"):
            command.extend(["--add-dir", manifest["worktree"]])
    if config.agy_runner is not None:
        return config.agy_runner.run(command, package_dir)
    completed = subprocess.run(
        command,
        cwd=package_dir,
        check=False,
        capture_output=True,
        text=True,
    )
    if completed.returncode != 0:
        raise AuditorFailure(
            f"AGY exited with status {completed.returncode}: {completed.stderr.strip()}"
        )
    return completed.stdout


def build_auditor_command(command: str, model: str, package_dir: Path, prompt: str, schema_path: Path) -> list[str]:
    """Read-only invocation for each supported auditor CLI."""
    directories = [str(package_dir)]
    manifest_path = package_dir / "manifest.json"
    if manifest_path.exists():
        worktree = json.loads(manifest_path.read_text(encoding="utf-8")).get("worktree")
        if worktree:
            directories.append(worktree)
    if command == "agy":
        args = ["agy", "--model", model, "--mode", "plan", "--sandbox"]
        for directory in directories:
            args.extend(["--add-dir", directory])
        return [*args, "--output-format", "json", "--json-schema", str(schema_path), "--print", prompt]
    if command == "claude":
        args = ["claude", "--print", prompt, "--model", model, "--output-format", "json",
                "--json-schema", schema_path.read_text(encoding="utf-8"),
                "--permission-mode", "plan", "--tools", "Read,Grep,Glob"]
        for directory in directories:
            args.extend(["--add-dir", directory])
        return args
    raise AuditorFailure(f"no adapter for auditor command {command!r}")


def _invoke_auditor(config: BridgeConfig, command: list[str], package_dir: Path) -> str:
    if config.agy_runner is not None:
        return config.agy_runner.run(command, package_dir)
    completed = subprocess.run(command, cwd=package_dir, check=False, capture_output=True, text=True)
    if completed.returncode != 0:
        raise AuditorFailure(f"{command[0]} exited with status {completed.returncode}: {completed.stderr.strip()}")
    return completed.stdout


STATUS_SEVERITY = ("ARCHITECTURE_STOP", "ESCALATE_TO_HIGH_REVIEW", "FIX_REQUIRED", "TASK_APPROVED")
COMBINED_VERDICT = {
    "ARCHITECTURE_STOP": "ARCHITECTURE_STOP",
    "ESCALATE_TO_HIGH_REVIEW": "FIX_REQUIRED",
    "FIX_REQUIRED": "FIX_REQUIRED",
    "TASK_APPROVED": "TASK_APPROVED",
}


def run_bound_audits(config: BridgeConfig, package_dir: Path, prompt_kind: str, schema_path: Path) -> BridgeResult:
    """Call the auditors the user bound to this phase. Every one of them must approve the same HEAD."""
    bindings = config.bindings
    manifest = json.loads((package_dir / "manifest.json").read_text(encoding="utf-8"))
    head_sha = manifest["head_sha"]
    agents = bindings.auditors_for(prompt_kind)
    checks = check_auditors(bindings, agents, run=config.check_runner or run_check, which=config.which or shutil.which)
    (package_dir / "preflight.json").write_text(json.dumps([c.as_dict() for c in checks], indent=2), encoding="utf-8")
    blocking = [c for c in checks if c.blocks]
    if blocking:
        return BridgeResult("AUDITOR_NOT_READY", package_dir, None,
                            " | ".join(f"{c.agent}: {c.status}. {c.fix}" for c in blocking))
    verdicts: list[tuple[str, dict[str, object]]] = []
    for agent in agents:
        provider = bindings.providers[agent]
        prompt = render_auditor_prompt(prompt_kind, package_dir, provider.model or agent)
        prompt_path = package_dir / f"auditor-{agent}-prompt.txt"
        prompt_path.write_text(prompt, encoding="utf-8")
        if provider.command is None:
            return BridgeResult("MANUAL_AUDIT_REQUIRED", package_dir, head_sha,
                                f"{agent} is a manual auditor: send it {prompt_path} and the package, then record its verdict")
        command = build_auditor_command(provider.command, provider.model, package_dir, prompt, schema_path)
        verdict = None
        last_output = ""
        for attempt in range(MAX_AUDITOR_RETRIES + 1):
            try:
                last_output = _invoke_auditor(config, command, package_dir)
                (package_dir / f"auditor-{agent}-output-{attempt + 1}.txt").write_text(last_output, encoding="utf-8")
                verdict = parse_auditor_output(last_output, schema_path)
                break
            except (AuditorFailure, TimeoutError, OSError):
                continue
        (package_dir / f"auditor-{agent}-raw-output.txt").write_text(last_output, encoding="utf-8")
        if verdict is None:
            return BridgeResult("AUDITOR_INFRA_STOP", package_dir, None, f"{agent} failed after maximum retries")
        verdicts.append((agent, verdict))

    statuses = [route_verdict(verdict, fix_attempt_count=0).status for _, verdict in verdicts]
    status = min(statuses, key=STATUS_SEVERITY.index)
    gate_agent, gate_verdict = verdicts[0]
    normalized = dict(gate_verdict)
    normalized["verdict"] = COMBINED_VERDICT[status] if status != "TASK_APPROVED" else gate_verdict["verdict"]
    normalized["prompt_kind"] = prompt_kind
    normalized["auditors"] = {agent: verdict["verdict"] for agent, verdict in verdicts}
    write_normalized_verdict(package_dir, normalized, head_sha)
    agreed = "all auditors approved" if status == "TASK_APPROVED" else f"blocked by {', '.join(a for a, _ in verdicts)}"
    return BridgeResult(status, package_dir, head_sha, f"{gate_agent} gated; {agreed}")


def run_audit_with_retries(
    config: BridgeConfig,
    package_dir: Path,
    prompt_kind: str,
    schema_path: Path,
) -> BridgeResult:
    if config.bindings is not None:
        return run_bound_audits(config, package_dir, prompt_kind, schema_path)
    last_output = ""
    for attempt in range(MAX_AUDITOR_RETRIES + 1):
        try:
            last_output = run_agy_audit(config, package_dir, prompt_kind)
            (package_dir / f"agy-output-{attempt + 1}.txt").write_text(last_output, encoding="utf-8")
            (package_dir / "agy-raw-output.txt").write_text(last_output, encoding="utf-8")
            verdict = parse_auditor_output(last_output, schema_path)
            manifest = json.loads((package_dir / "manifest.json").read_text(encoding="utf-8"))
            head_sha = manifest["head_sha"]
            verdict["prompt_kind"] = prompt_kind
            write_normalized_verdict(package_dir, verdict, head_sha)
            routed = route_verdict(verdict, fix_attempt_count=0)
            return BridgeResult(
                status=routed.status,
                attempt_dir=package_dir,
                head_sha=head_sha,
                message="auditor verdict accepted",
            )
        except (AuditorFailure, TimeoutError, OSError):
            continue

    (package_dir / "agy-raw-output.txt").write_text(last_output, encoding="utf-8")
    return BridgeResult(
        status="AUDITOR_INFRA_STOP",
        attempt_dir=package_dir,
        head_sha=None,
        message="auditor failed after maximum retries",
    )


def route_verdict(verdict: dict[str, object], fix_attempt_count: int) -> BridgeResult:
    findings = verdict.get("findings", [])
    if verdict.get("architecture_stop") is True or verdict.get("verdict") == ARCHITECTURE_STOP:
        return BridgeResult("ARCHITECTURE_STOP", None, None, "architectural ruling required")
    if any(item.get("severity") == "CRITICAL" for item in findings if isinstance(item, dict)):
        return BridgeResult("ARCHITECTURE_STOP", None, None, "critical contract finding")
    if verdict.get("verdict") == "TASK_APPROVED" and verdict.get("test_evidence") == "PASS":
        return BridgeResult("TASK_APPROVED", None, None, "task approved")
    if any(item.get("severity") == "HIGH" for item in findings if isinstance(item, dict)):
        return BridgeResult("ESCALATE_TO_HIGH_REVIEW", None, None, "high-severity finding")
    if verdict.get("verdict") == "FIX_REQUIRED" and fix_attempt_count >= 3:
        return BridgeResult("ESCALATE_TO_HIGH_REVIEW", None, None, "maximum automatic fixes reached")
    return BridgeResult("FIX_REQUIRED", None, None, "auditor findings require a TDD fix")


def write_architecture_stop(package_dir: Path, request: AuditRequest, finding: dict[str, object]) -> Path:
    artifact = package_dir / f"architecture-stop-{request.task_id}.md"
    content = f"""ARCHITECTURE_STOP

TASK: {request.task_id}
BASE_SHA: {request.base_sha}
HEAD_SHA: {request.head_sha}

CONTRACT:
{finding.get('contract', '')}

OBSERVED:
{finding.get('evidence', '')}

WHY_THIS_IS_NOT_A_NORMAL_BUG:
The finding concerns a frozen contract or architecture and requires an architectural ruling.

WHY_MINIMAL_ADAPTATION_IS_INSUFFICIENT:
Changing implementation alone would silently redefine the authoritative contract.

IMPACT:
- identity
- fingerprints
- runner
- gate
- causal semantics
- legacy behavior
- other relevant contracts

OPTIONS:
A. Restore the frozen contract and continue the normal implementation task.
B. Approve an architectural contract change before implementation resumes.

RECOMMENDATION:
{finding.get('required_proof', '')}

IMPLEMENTATION_STATUS:
STOPPED
"""
    artifact.write_text(content, encoding="utf-8")
    return artifact


def calculate_audit_package_id(package_dir: Path) -> str:
    digest = hashlib.sha256()
    for filename in PROVENANCE_FILES:
        path = package_dir / filename
        digest.update(path.read_bytes() if path.exists() else b"")
    for path in sorted(package_dir.glob("auditor-*-raw-output.txt")):
        digest.update(path.name.encode("utf-8") + path.read_bytes())
    return digest.hexdigest()


def write_normalized_verdict(
    package_dir: Path,
    verdict: dict[str, object],
    audited_head_sha: str,
) -> Path:
    manifest = json.loads((package_dir / "manifest.json").read_text(encoding="utf-8"))
    if manifest.get("head_sha") != audited_head_sha:
        raise AuditProvenanceInvalid("normalized verdict HEAD does not match manifest HEAD")
    target = package_dir / "auditor-verdict.json"
    target.write_text(json.dumps(verdict, indent=2, sort_keys=True), encoding="utf-8")
    return target


def finalize_after_approval(
    config: BridgeConfig,
    package_dir: Path,
    remote: str,
    branch: str,
    pr_title: str,
    pr_body: str,
) -> BridgeResult:
    try:
        verdict = json.loads((package_dir / "auditor-verdict.json").read_text(encoding="utf-8"))
        manifest = json.loads((package_dir / "manifest.json").read_text(encoding="utf-8"))
        audited_worktree = Path(manifest["worktree"])
        current_head = _run_git(audited_worktree, "rev-parse", "HEAD").strip()
        current_tree = _run_git(audited_worktree, "rev-parse", "HEAD^{tree}").strip()
        current_branch = _run_git(audited_worktree, "branch", "--show-current").strip()
        if (current_head != manifest["head_sha"]
                or current_tree != manifest["tree_sha"]
                or current_branch != branch or manifest["branch"] != branch
                or _run_git(audited_worktree, "status", "--porcelain").strip()):
            raise RepositorySafetyStop("current Git state differs from final audited state")
    except (OSError, ValueError, KeyError, TypeError, subprocess.CalledProcessError,
            RepositorySafetyStop) as exc:
        return BridgeResult("REPOSITORY_SAFETY_STOP", package_dir, None, str(exc))
    approved = (
        verdict.get("verdict") == "TASK_APPROVED"
        and verdict.get("spec_compliance") == "APPROVED"
        and verdict.get("code_quality") == "APPROVED"
        and verdict.get("test_evidence") == "PASS"
        and verdict.get("architecture_stop") is False
        and verdict.get("confidence") == "HIGH"
        and verdict.get("prompt_kind") in {"final", "final_phase"}
        and branch not in {"main", "master"}
    )
    if not approved:
        return BridgeResult(
            "REPOSITORY_SAFETY_STOP",
            package_dir,
            None,
            "push and PR require final High approval on a feature branch",
        )

    git_command = ["git", "push", remote, branch]
    gh_command = [
        "gh",
        "pr",
        "create",
        "--base",
        "main",
        "--head",
        branch,
        "--title",
        pr_title,
        "--body",
        pr_body,
    ]
    if config.git_runner is not None:
        config.git_runner.run(git_command, audited_worktree)
    else:
        subprocess.run(git_command, cwd=audited_worktree, check=True)
    if config.gh_runner is not None:
        config.gh_runner.run(gh_command, audited_worktree)
    else:
        subprocess.run(gh_command, cwd=audited_worktree, check=True)
    return BridgeResult("PR_CREATED", package_dir, None, "branch pushed and pull request created")


def build_aurum_v16_closeout_request(worktree: Path, merge_readiness_doc: Path) -> AuditRequest:
    head_sha = _run_git(worktree, "rev-parse", "HEAD").strip()
    runtime_root = BridgeConfig.from_env().runtime_root / worktree.name / "v1.6-closeout"
    runtime_root.mkdir(parents=True, exist_ok=True)
    evidence_path = runtime_root / "aurum-v1.6-closeout-evidence.md"
    evidence_path.write_text(
        f"""AURUM V1.6 CLOSEOUT

OBJECTIVE:
Identify why the merge-readiness document does not match the audited HEAD.

MERGE_READINESS_DOCUMENT:
{merge_readiness_doc}

AUDITED_BASE_SHA:
{AURUM_V16_BASE_SHA}

CURRENT_HEAD_SHA:
{head_sha}

HARD RULE:
V1.7 must not begin until V1.6 operational closeout is resolved and merged.
""",
        encoding="utf-8",
    )
    return AuditRequest(
        phase="v1.6-closeout",
        task_id="aurum-v1.6-closeout",
        base_sha=AURUM_V16_BASE_SHA,
        head_sha=head_sha,
        spec_path=merge_readiness_doc,
        plan_path=merge_readiness_doc,
        test_output_path=None,
        tdd_evidence_path=evidence_path,
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="audit_bridge")
    subcommands = parser.add_subparsers(dest="command", required=True)
    check = subcommands.add_parser("check-bindings")
    check.add_argument("--bindings", type=Path, default=DEFAULT_BINDINGS_PATH)
    for name in ("package", "audit", "escalate", "finalize"):
        command = subcommands.add_parser(name)
        for flag in ("phase", "task-id", "base-sha", "head-sha"):
            command.add_argument(f"--{flag}", required=True)
        for flag in ("spec-path", "plan-path"):
            command.add_argument(f"--{flag}", type=Path, required=True)
        for flag in ("test-output-path", "tdd-evidence-path", "runtime-root"):
            command.add_argument(f"--{flag}", type=Path)
        if name != "package":
            command.add_argument("--bindings", type=Path)
        if name == "finalize":
            command.add_argument("--remote", default="origin")
            command.add_argument("--pr-title", required=True)
            command.add_argument("--pr-body-file", type=Path, required=True)
    return parser


def check_bindings(path: Path, run=run_check, which=shutil.which) -> int:
    """Validate a bindings file, then confirm every auditor is installed, signed in and has its model.

    Nothing is sent to a model: the checks are `claude auth status` and `agy models`.
    """
    auditors: list[dict[str, str]] = []
    try:
        bindings = load_bindings(path)
        checks = check_auditors(bindings, all_auditors(bindings), run=run, which=which)
        auditors = [c.as_dict() for c in checks]
        problems = [f"{c.agent}: {c.status}. {c.fix}" for c in checks if c.blocks]
        status = "AUDITOR_NOT_READY" if problems else "BINDINGS_VALID"
    except BindingsRequired as exc:
        status, problems = exc.status, [str(exc)]
    except BindingsInvalid as exc:
        status, problems = exc.status, exc.errors
    print(json.dumps({"status": status, "path": str(path), "auditors": auditors, "problems": problems}))
    return 0 if status == "BINDINGS_VALID" else 1


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    try:
        args = parser.parse_args(argv)
    except SystemExit as exc:
        return int(exc.code)
    if args.command == "check-bindings":
        return check_bindings(args.bindings)
    try:
        config = BridgeConfig.from_env()
        if args.runtime_root:
            config = config.with_runtime_root(args.runtime_root.resolve())
        request = AuditRequest(args.phase, args.task_id, args.base_sha, args.head_sha,
                               args.spec_path.resolve(), args.plan_path.resolve(),
                               args.test_output_path, args.tdd_evidence_path)
        result = build_audit_package(config, request)
        package = result.attempt_dir
        if args.command != "package":
            worktree = Path(json.loads((package / "manifest.json").read_text(encoding="utf-8"))["worktree"])
            config = config.with_bindings(load_bindings(args.bindings or worktree / DEFAULT_BINDINGS_PATH))
            schema = package / "auditor_verdict.schema.json"
            shutil.copyfile(Path(__file__).resolve().parent.parent / "schemas/auditor_verdict.schema.json", schema)
            prompt_kind = {"audit": "task", "escalate": "escalation", "finalize": "final_phase"}[args.command]
            result = run_audit_with_retries(config, package, prompt_kind, schema)
        if args.command == "finalize" and result.status == "TASK_APPROVED":
            manifest = json.loads((package / "manifest.json").read_text(encoding="utf-8"))
            result = finalize_after_approval(config, package, args.remote, manifest["branch"],
                                            args.pr_title, args.pr_body_file.read_text(encoding="utf-8"))
    except (RepositorySafetyStop, ArchitectureStop, AttemptAlreadyExistsError,
            AuditProvenanceInvalid, AuditorFailure, BindingsInvalid, BindingsRequired) as exc:
        result = BridgeResult(exc.status, None, None, str(exc))
    except (OSError, ValueError, KeyError, subprocess.CalledProcessError) as exc:
        result = BridgeResult("REPOSITORY_SAFETY_STOP", None, None, str(exc))
    print(json.dumps({"status": result.status, "head_sha": result.head_sha,
                      "attempt_dir": str(result.attempt_dir) if result.attempt_dir else None,
                      "message": result.message}))
    return 0 if result.status in {"PACKAGE_CREATED", "TASK_APPROVED", "PR_CREATED"} else 1


if __name__ == "__main__":
    raise SystemExit(main())
