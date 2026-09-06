# Orchestrating Independent Code Audits Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a reusable Codex to AGY/Gemini independent-audit skill and deterministic audit bridge that automates task implementation loops while preserving human merge authority.

**Architecture:** `SKILL.md` is the policy surface, `scripts/audit_bridge.py` is the deterministic evidence and orchestration helper, `schemas/auditor_verdict.schema.json` is the normalized verdict contract, and `prompts/*.md` define read-only auditor behavior. Runtime artifacts are written outside the target worktree by default, each audit attempt is immutable and bound to exact Git state, and all approval gates fail closed.

**Tech Stack:** Python 3 standard library, `jsonschema` for schema validation, `pytest`, Git CLI read commands, AGY CLI launched headlessly from the audited worktree, Gemini 3.8 Flash Medium for default task audits, Gemini 3.8 Flash High for escalation and final-phase audits, and GitHub CLI for PR creation after final approval.

**Spec:** `docs/superpowers/specs/2026-09-06-orchestrating-independent-code-audits-design.md`

## Global Constraints

- Codex is the implementer.
- AGY / Gemini 3.8 Flash Medium is the default independent task auditor.
- AGY / Gemini 3.8 Flash High is the escalation and final-phase auditor.
- ChatGPT acts only as architectural arbiter when a frozen contract or architecture must be reconsidered.
- The human user retains merge authority.
- The system must not depend on UI interaction.
- Automatic merge is explicitly out of scope.
- Task completion requires deterministic checks to pass and an independent AGY audit to return `TASK_APPROVED`.
- Runtime evidence is created outside the target worktree by default under `%LOCALAPPDATA%\AurumAuditRuntime\`.
- `MAX_AUDITOR_RETRIES = 2`.
- `MAX_AUTOMATIC_FIX_ATTEMPTS = 3`.
- The bridge must not use `--dangerously-skip-permissions`.
- The bridge must not use `--mode=accept-edits`.
- Final phase approval permits push plus PR creation, but never merge.
- Any `ARCHITECTURE_STOP`, `AUDITOR_INFRA_STOP`, or `REPOSITORY_SAFETY_STOP` blocks push and PR creation.

---

## File Structure

- Modify: `SKILL.md`
  - Defines role authority, TDD loop, audit gates, stop taxonomy, automatic correction limits, final push/PR policy, and merge prohibition.
- Modify: `README.md`
  - Documents installation, configuration, CLI usage, runtime isolation, AGY model policy, and Aurum V1.6 closeout usage.
- Modify: `PRESSURE_TESTS.md`
  - Replaces conceptual pressure tests with spec-aligned RED/GREEN cases for immutable attempts, stop taxonomy, protected contracts, anti-gaming, and final closeout.
- Create: `pyproject.toml`
  - Declares the package, console script, and test dependencies.
- Create: `scripts/audit_bridge.py`
  - Implements the CLI, Git evidence collection, manifest construction, immutable attempt creation, prompt assembly, AGY execution, verdict parsing, stop semantics, and optional final push/PR operation.
- Create: `schemas/auditor_verdict.schema.json`
  - Defines the strict auditor verdict JSON schema.
- Create: `prompts/task_audit.md`
  - Default task audit prompt for AGY/Gemini 3.8 Flash Medium.
- Create: `prompts/escalation_audit.md`
  - Stronger independent review prompt for AGY/Gemini 3.8 Flash High.
- Create: `prompts/final_phase_audit.md`
  - Final closeout prompt for AGY/Gemini 3.8 Flash High.
- Create: `tests/test_audit_bridge.py`
  - Covers package identity, immutable attempts, Git evidence derivation, runtime isolation, protected contracts, test classification, stop routing, and final push/PR gates.
- Create: `tests/test_verdict_parser.py`
  - Covers strict JSON schema validation, verdict normalization, provenance, and fail-closed invalid output.
- Create: `tests/test_failure_semantics.py`
  - Covers AGY timeout, non-zero exit, model unavailable, retry exhaustion, dirty repository safety, HEAD drift, and architecture stop artifacts.
- Create: `tests/conftest.py`
  - Provides temporary Git repositories, fake AGY runners, fake GitHub CLI calls, and path assertions.

---

### Task 1: Project Test Harness And CLI Skeleton

**Files:**
- Create: `pyproject.toml`
- Create: `scripts/audit_bridge.py`
- Create: `tests/conftest.py`
- Create: `tests/test_audit_bridge.py`

**Interfaces:**
- Produces: `scripts.audit_bridge.main(argv: list[str] | None = None) -> int`
- Produces: `scripts.audit_bridge.BridgeConfig(runtime_root: Path, agy_command: list[str], task_model: str, high_model: str, final_model: str, protected_contract_files: tuple[str, ...])`
- Produces: `scripts.audit_bridge.BridgeResult(status: str, attempt_dir: Path | None, head_sha: str | None, message: str)`

- [ ] **Step 1: Write the failing test**

```python
from scripts.audit_bridge import BridgeConfig, BridgeResult, main


def test_cli_imports_and_returns_usage_error_for_missing_args(capsys):
    exit_code = main([])

    captured = capsys.readouterr()
    assert exit_code == 2
    assert "audit_bridge" in captured.err


def test_bridge_config_defaults_to_aurum_runtime(monkeypatch):
    monkeypatch.setenv("LOCALAPPDATA", r"C:\Users\example\AppData\Local")

    config = BridgeConfig.from_env()

    assert str(config.runtime_root).endswith(r"AurumAuditRuntime")
    assert config.task_model == "Gemini 3.8 Flash Medium"
    assert config.high_model == "Gemini 3.8 Flash High"
    assert config.final_model == "Gemini 3.8 Flash High"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_audit_bridge.py::test_cli_imports_and_returns_usage_error_for_missing_args tests/test_audit_bridge.py::test_bridge_config_defaults_to_aurum_runtime -v`

Expected: FAIL because `scripts.audit_bridge`, `BridgeConfig`, and `main` do not exist.

- [ ] **Step 3: Write minimal implementation**

```python
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
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_audit_bridge.py::test_cli_imports_and_returns_usage_error_for_missing_args tests/test_audit_bridge.py::test_bridge_config_defaults_to_aurum_runtime -v`

Expected: PASS.

- [ ] **Step 5: Run regression**

Run: `pytest -v`

Expected: PASS for the new harness tests.

- [ ] **Step 6: Commit**

```bash
git add pyproject.toml scripts/audit_bridge.py tests/conftest.py tests/test_audit_bridge.py
git commit -m "test: add audit bridge harness"
```

---

### Task 2: Strict Auditor Verdict Schema

**Files:**
- Create: `schemas/auditor_verdict.schema.json`
- Modify: `scripts/audit_bridge.py`
- Create: `tests/test_verdict_parser.py`

**Interfaces:**
- Produces: `load_schema(schema_path: Path) -> dict[str, object]`
- Produces: `parse_auditor_output(raw_output: str, schema_path: Path) -> dict[str, object]`
- Produces status string: `AUDITOR_FAILURE`

- [ ] **Step 1: Write the failing test**

```python
import json

import pytest

from scripts.audit_bridge import AuditorFailure, parse_auditor_output


def test_valid_task_approved_verdict_passes_schema(schema_path):
    raw = json.dumps({
        "verdict": "TASK_APPROVED",
        "spec_compliance": "APPROVED",
        "code_quality": "APPROVED",
        "test_evidence": "PASS",
        "architecture_stop": False,
        "findings": [],
        "confidence": "MEDIUM",
    })

    verdict = parse_auditor_output(raw, schema_path)

    assert verdict["verdict"] == "TASK_APPROVED"


@pytest.mark.parametrize("raw", ["", "not json", "{\"verdict\":\"APPROVED\"}"])
def test_invalid_output_fails_closed(schema_path, raw):
    with pytest.raises(AuditorFailure) as exc:
        parse_auditor_output(raw, schema_path)

    assert exc.value.status == "AUDITOR_FAILURE"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_verdict_parser.py -v`

Expected: FAIL because `AuditorFailure`, `parse_auditor_output`, and the schema fixture do not exist.

- [ ] **Step 3: Write minimal implementation**

```json
{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "type": "object",
  "additionalProperties": false,
  "required": [
    "verdict",
    "spec_compliance",
    "code_quality",
    "test_evidence",
    "architecture_stop",
    "findings",
    "confidence"
  ],
  "properties": {
    "verdict": { "enum": ["TASK_APPROVED", "FIX_REQUIRED", "ARCHITECTURE_STOP"] },
    "spec_compliance": { "enum": ["APPROVED", "CHANGES_REQUIRED", "ARCHITECTURE_STOP"] },
    "code_quality": { "enum": ["APPROVED", "CHANGES_REQUIRED"] },
    "test_evidence": { "enum": ["PASS", "INSUFFICIENT", "FAIL"] },
    "architecture_stop": { "type": "boolean" },
    "findings": {
      "type": "array",
      "items": {
        "type": "object",
        "additionalProperties": false,
        "required": ["id", "severity", "contract", "file", "line", "evidence", "required_proof"],
        "properties": {
          "id": { "type": "string", "minLength": 1 },
          "severity": { "enum": ["LOW", "MEDIUM", "HIGH", "CRITICAL"] },
          "contract": { "type": "string", "minLength": 1 },
          "file": { "type": "string" },
          "line": { "type": ["integer", "null"], "minimum": 1 },
          "evidence": { "type": "string", "minLength": 1 },
          "required_proof": { "type": "string", "minLength": 1 }
        }
      }
    },
    "confidence": { "enum": ["LOW", "MEDIUM", "HIGH"] }
  }
}
```

```python
import json
from jsonschema import ValidationError, validate


class AuditorFailure(Exception):
    def __init__(self, message: str, status: str = "AUDITOR_FAILURE") -> None:
        super().__init__(message)
        self.status = status


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
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_verdict_parser.py -v`

Expected: PASS.

- [ ] **Step 5: Run regression**

Run: `pytest -v`

Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add schemas/auditor_verdict.schema.json scripts/audit_bridge.py tests/test_verdict_parser.py tests/conftest.py
git commit -m "feat: validate auditor verdicts"
```

---

### Task 3: Deterministic Git Evidence Package

**Files:**
- Modify: `scripts/audit_bridge.py`
- Modify: `tests/test_audit_bridge.py`

**Interfaces:**
- Produces: `GitState(repository: str, worktree: Path, branch: str, base_sha: str, head_sha: str, tree_sha: str)`
- Produces: `collect_git_state(worktree: Path, base_sha: str, head_sha: str) -> GitState`
- Produces: `build_audit_package(config: BridgeConfig, request: AuditRequest) -> BridgeResult`
- Produces: `AuditRequest(phase: str, task_id: str, base_sha: str, head_sha: str, spec_path: Path, plan_path: Path, test_output_path: Path | None, tdd_evidence_path: Path | None)`

- [ ] **Step 1: Write the failing test**

```python
import json

from scripts.audit_bridge import AuditRequest, BridgeConfig, build_audit_package


def test_package_contains_git_derived_evidence(tmp_path, git_repo, schema_path):
    spec = git_repo.write_file("spec.md", "frozen contract\n")
    plan = git_repo.write_file("plan.md", "approved plan\n")
    git_repo.commit_all("base")
    base_sha = git_repo.head()
    git_repo.write_file("src.py", "print('changed')\n")
    git_repo.commit_all("change")
    head_sha = git_repo.head()
    runtime_root = tmp_path / "runtime"
    config = BridgeConfig.from_env().with_runtime_root(runtime_root)

    result = build_audit_package(config, AuditRequest(
        phase="v1.0",
        task_id="task-01",
        base_sha=base_sha,
        head_sha=head_sha,
        spec_path=spec,
        plan_path=plan,
        test_output_path=None,
        tdd_evidence_path=None,
    ))

    manifest = json.loads((result.attempt_dir / "manifest.json").read_text(encoding="utf-8"))
    assert result.status == "PACKAGE_CREATED"
    assert manifest["base_sha"] == base_sha
    assert manifest["head_sha"] == head_sha
    assert manifest["tree_sha"]
    assert (result.attempt_dir / "git-status.txt").exists()
    assert (result.attempt_dir / "git-log.txt").exists()
    assert (result.attempt_dir / "files-changed.json").exists()
    assert "src.py" in (result.attempt_dir / "diff.patch").read_text(encoding="utf-8")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_audit_bridge.py::test_package_contains_git_derived_evidence -v`

Expected: FAIL because package creation and Git fixtures do not exist.

- [ ] **Step 3: Write minimal implementation**

Implement Git read helpers with `subprocess.run(..., cwd=worktree, check=True, capture_output=True, text=True)`. Use these commands only: `git rev-parse --show-toplevel`, `git branch --show-current`, `git rev-parse <head_sha>^{tree}`, `git status --short --branch`, `git log --oneline <base_sha>..<head_sha>`, `git show --no-patch --format=%H%n%an%n%ae%n%at%n%s <head_sha>`, `git diff --name-status <base_sha> <head_sha>`, and `git diff <base_sha> <head_sha>`.

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_audit_bridge.py::test_package_contains_git_derived_evidence -v`

Expected: PASS.

- [ ] **Step 5: Run regression**

Run: `pytest -v`

Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add scripts/audit_bridge.py tests/test_audit_bridge.py tests/conftest.py
git commit -m "feat: build deterministic audit packages"
```

---

### Task 4: Runtime Isolation And Immutable Attempts

**Files:**
- Modify: `scripts/audit_bridge.py`
- Modify: `tests/test_audit_bridge.py`

**Interfaces:**
- Produces: `allocate_attempt_dir(config: BridgeConfig, request: AuditRequest, repository_name: str) -> Path`
- Produces: `AttemptAlreadyExistsError(status: str = "REPOSITORY_SAFETY_STOP")`

- [ ] **Step 1: Write the failing test**

```python
import pytest

from scripts.audit_bridge import AttemptAlreadyExistsError, AuditRequest, BridgeConfig, build_audit_package


def test_attempts_are_outside_worktree_and_immutable(tmp_path, git_repo):
    spec = git_repo.write_file("spec.md", "contract\n")
    plan = git_repo.write_file("plan.md", "plan\n")
    git_repo.commit_all("base")
    base_sha = git_repo.head()
    git_repo.write_file("module.py", "value = 1\n")
    git_repo.commit_all("head")
    head_sha = git_repo.head()
    config = BridgeConfig.from_env().with_runtime_root(tmp_path / "runtime")
    request = AuditRequest("v1.0", "task-01", base_sha, head_sha, spec, plan, None, None)

    first = build_audit_package(config, request)

    assert git_repo.path not in first.attempt_dir.parents
    assert first.attempt_dir.name == "attempt-01"
    with pytest.raises(AttemptAlreadyExistsError) as exc:
        build_audit_package(config, request)
    assert exc.value.status == "REPOSITORY_SAFETY_STOP"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_audit_bridge.py::test_attempts_are_outside_worktree_and_immutable -v`

Expected: FAIL because immutable attempt allocation is not enforced.

- [ ] **Step 3: Write minimal implementation**

Attempt path format:

```text
<runtime_root>/<owner_repo_or_repo_name>/<phase>/<task_id>/attempt-01
```

If `attempt-01` already exists for the same request identity, raise `AttemptAlreadyExistsError`. A later HEAD must be represented by a caller-supplied new attempt number or a future `--attempt` flag; the first implementation keeps the rule simple and fail-closed.

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_audit_bridge.py::test_attempts_are_outside_worktree_and_immutable -v`

Expected: PASS.

- [ ] **Step 5: Run regression**

Run: `pytest -v`

Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add scripts/audit_bridge.py tests/test_audit_bridge.py
git commit -m "feat: isolate immutable audit attempts"
```

---

### Task 5: Diff Classification And Test Anti-Gaming Evidence

**Files:**
- Modify: `scripts/audit_bridge.py`
- Modify: `tests/test_audit_bridge.py`

**Interfaces:**
- Produces: `classify_changed_file(path: str, status: str, protected_contract_files: tuple[str, ...]) -> str`
- Produces evidence files: `production_diff.patch`, `test_diff.patch`, `contract_diff.patch`
- Produces JSON file: `test-summary.json`

- [ ] **Step 1: Write the failing test**

```python
import json

from scripts.audit_bridge import AuditRequest, BridgeConfig, build_audit_package


def test_package_classifies_test_changes_and_contract_changes(tmp_path, git_repo):
    spec = git_repo.write_file("spec.md", "contract\n")
    plan = git_repo.write_file("plan.md", "plan\n")
    protected = git_repo.write_file("goldens/fingerprint.txt", "abc\n")
    git_repo.write_file("tests/test_old.py", "def test_old():\n    assert 1 == 1\n")
    git_repo.commit_all("base")
    base_sha = git_repo.head()
    git_repo.write_file("tests/test_old.py", "def test_old():\n    assert 2 == 2\n")
    git_repo.write_file("tests/test_new.py", "def test_new():\n    assert 'x' == 'x'\n")
    git_repo.write_file("goldens/fingerprint.txt", "def\n")
    git_repo.commit_all("head")
    head_sha = git_repo.head()
    config = BridgeConfig.from_env().with_runtime_root(tmp_path / "runtime").with_protected_contract_files((str(protected.relative_to(git_repo.path)),))

    result = build_audit_package(config, AuditRequest("v1.0", "task-02", base_sha, head_sha, spec, plan, None, None))

    summary = json.loads((result.attempt_dir / "test-summary.json").read_text(encoding="utf-8"))
    assert summary["tests/test_old.py"] == "MODIFIED_EXISTING_TEST"
    assert summary["tests/test_new.py"] == "NEW_TEST"
    assert "goldens/fingerprint.txt" in (result.attempt_dir / "contract_diff.patch").read_text(encoding="utf-8")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_audit_bridge.py::test_package_classifies_test_changes_and_contract_changes -v`

Expected: FAIL because file classification and split diffs do not exist.

- [ ] **Step 3: Write minimal implementation**

Classification rules:

```text
path starts with tests/ and git status is A -> NEW_TEST
path starts with tests/ and git status is M or R -> MODIFIED_EXISTING_TEST
path starts with tests/ and git status is D -> DELETED_TEST
path is listed in protected_contract_files -> PROTECTED_CONTRACT
path starts with docs/superpowers/specs/ -> PROTECTED_CONTRACT
otherwise -> PRODUCTION
```

Write split diffs by filtering `git diff -- <path>` per class and concatenate each group into the named patch file.

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_audit_bridge.py::test_package_classifies_test_changes_and_contract_changes -v`

Expected: PASS.

- [ ] **Step 5: Run regression**

Run: `pytest -v`

Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add scripts/audit_bridge.py tests/test_audit_bridge.py
git commit -m "feat: classify audit evidence"
```

---

### Task 6: Protected Contracts And Repository Safety Stops

**Files:**
- Modify: `scripts/audit_bridge.py`
- Modify: `tests/test_failure_semantics.py`

**Interfaces:**
- Produces: `RepositorySafetyStop(status: str = "REPOSITORY_SAFETY_STOP")`
- Produces: `detect_repository_safety_stop(worktree: Path, base_sha: str, head_sha: str, protected_contract_files: tuple[str, ...]) -> None`

- [ ] **Step 1: Write the failing test**

```python
import pytest

from scripts.audit_bridge import AuditRequest, BridgeConfig, RepositorySafetyStop, build_audit_package


def test_dirty_worktree_blocks_evidence_generation(tmp_path, git_repo):
    spec = git_repo.write_file("spec.md", "contract\n")
    plan = git_repo.write_file("plan.md", "plan\n")
    git_repo.commit_all("base")
    base_sha = git_repo.head()
    git_repo.write_file("module.py", "tracked = True\n")
    git_repo.commit_all("head")
    head_sha = git_repo.head()
    git_repo.write_file("uncommitted.txt", "dirty\n")
    config = BridgeConfig.from_env().with_runtime_root(tmp_path / "runtime")

    with pytest.raises(RepositorySafetyStop) as exc:
        build_audit_package(config, AuditRequest("v1.0", "task-03", base_sha, head_sha, spec, plan, None, None))

    assert exc.value.status == "REPOSITORY_SAFETY_STOP"


def test_protected_contract_change_blocks_normal_task(tmp_path, git_repo):
    spec = git_repo.write_file("docs/superpowers/specs/spec.md", "contract v1\n")
    plan = git_repo.write_file("plan.md", "plan\n")
    git_repo.commit_all("base")
    base_sha = git_repo.head()
    git_repo.write_file("docs/superpowers/specs/spec.md", "contract v2\n")
    git_repo.commit_all("head")
    head_sha = git_repo.head()
    config = BridgeConfig.from_env().with_runtime_root(tmp_path / "runtime")

    with pytest.raises(RepositorySafetyStop) as exc:
        build_audit_package(config, AuditRequest("v1.0", "task-04", base_sha, head_sha, spec, plan, None, None))

    assert exc.value.status == "REPOSITORY_SAFETY_STOP"
    assert "protected contract" in str(exc.value).lower()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_failure_semantics.py::test_dirty_worktree_blocks_evidence_generation tests/test_failure_semantics.py::test_protected_contract_change_blocks_normal_task -v`

Expected: FAIL because repository safety checks are absent.

- [ ] **Step 3: Write minimal implementation**

Reject package generation when:

```text
git status --porcelain contains any line
base_sha or head_sha cannot be resolved
current HEAD differs from requested head_sha
protected contract files changed between base_sha and head_sha
runtime_root resolves inside the audited worktree
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_failure_semantics.py::test_dirty_worktree_blocks_evidence_generation tests/test_failure_semantics.py::test_protected_contract_change_blocks_normal_task -v`

Expected: PASS.

- [ ] **Step 5: Run regression**

Run: `pytest -v`

Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add scripts/audit_bridge.py tests/test_failure_semantics.py
git commit -m "feat: enforce repository safety stops"
```

---

### Task 7: Auditor Prompts And Read-Only Headless AGY Invocation

**Files:**
- Create: `prompts/task_audit.md`
- Create: `prompts/escalation_audit.md`
- Create: `prompts/final_phase_audit.md`
- Modify: `scripts/audit_bridge.py`
- Modify: `tests/test_audit_bridge.py`

**Interfaces:**
- Produces: `render_auditor_prompt(kind: str, package_dir: Path, model: str) -> str`
- Produces: `run_agy_audit(config: BridgeConfig, package_dir: Path, prompt_kind: str) -> str`

- [ ] **Step 1: Write the failing test**

```python
from scripts.audit_bridge import render_auditor_prompt, run_agy_audit


def test_task_prompt_enforces_read_only_shell_prohibition(tmp_path):
    package_dir = tmp_path / "attempt-01"
    package_dir.mkdir()
    (package_dir / "manifest.json").write_text("{}", encoding="utf-8")

    prompt = render_auditor_prompt("task", package_dir, "Gemini 3.8 Flash Medium")

    assert "You are an independent READ-ONLY code auditor." in prompt
    assert "DO NOT:" in prompt
    assert "execute shell commands" in prompt
    assert "write files" in prompt
    assert "Return only the required verdict JSON." in prompt


def test_agy_invocation_uses_model_and_never_accepts_edits(fake_agy_runner, bridge_config, tmp_path):
    package_dir = tmp_path / "attempt-01"
    package_dir.mkdir()
    fake_agy_runner.output = '{"verdict":"TASK_APPROVED","spec_compliance":"APPROVED","code_quality":"APPROVED","test_evidence":"PASS","architecture_stop":false,"findings":[],"confidence":"MEDIUM"}'

    run_agy_audit(bridge_config.with_agy_runner(fake_agy_runner), package_dir, "task")

    command = " ".join(fake_agy_runner.last_command)
    assert "Gemini 3.8 Flash Medium" in command
    assert "--dangerously-skip-permissions" not in command
    assert "--mode=accept-edits" not in command
    assert fake_agy_runner.last_cwd == package_dir
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_audit_bridge.py::test_task_prompt_enforces_read_only_shell_prohibition tests/test_audit_bridge.py::test_agy_invocation_uses_model_and_never_accepts_edits -v`

Expected: FAIL because prompt templates and AGY runner do not exist.

- [ ] **Step 3: Write minimal implementation**

Prompt files must include the required posture from spec section 8 verbatim enough to preserve meaning:

```text
You are an independent READ-ONLY code auditor.

DO NOT:
- execute shell commands;
- use command tools;
- write files;
- modify source code;
- create patches;
- fix findings;
- alter Git state.

Use read_file only.

Audit the actual provided:
- frozen spec;
- approved implementation plan;
- deterministic audit manifest;
- Git diff;
- changed source files;
- test evidence.

Return only the required verdict JSON.
```

AGY command shape:

```text
agy --model "<model>" --prompt-file "<package_dir>/agy-prompt.txt"
```

Launch with `cwd=package_dir` and no write-capable flags.

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_audit_bridge.py::test_task_prompt_enforces_read_only_shell_prohibition tests/test_audit_bridge.py::test_agy_invocation_uses_model_and_never_accepts_edits -v`

Expected: PASS.

- [ ] **Step 5: Run regression**

Run: `pytest -v`

Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add prompts/task_audit.md prompts/escalation_audit.md prompts/final_phase_audit.md scripts/audit_bridge.py tests/test_audit_bridge.py
git commit -m "feat: add read-only auditor prompts"
```

---

### Task 8: Auditor Failure, Retry, And AUDITOR_INFRA_STOP

**Files:**
- Modify: `scripts/audit_bridge.py`
- Modify: `tests/test_failure_semantics.py`

**Interfaces:**
- Produces: `run_audit_with_retries(config: BridgeConfig, package_dir: Path, prompt_kind: str, schema_path: Path) -> BridgeResult`
- Produces status strings: `AUDITOR_FAILURE`, `AUDITOR_INFRA_STOP`

- [ ] **Step 1: Write the failing test**

```python
from scripts.audit_bridge import run_audit_with_retries


def test_invalid_auditor_output_retries_twice_then_infra_stop(fake_agy_runner, bridge_config, tmp_path, schema_path):
    package_dir = tmp_path / "attempt-01"
    package_dir.mkdir()
    fake_agy_runner.outputs = ["not json", "", "{\"verdict\":\"APPROVED\"}"]

    result = run_audit_with_retries(bridge_config.with_agy_runner(fake_agy_runner), package_dir, "task", schema_path)

    assert result.status == "AUDITOR_INFRA_STOP"
    assert fake_agy_runner.call_count == 3
    assert (package_dir / "agy-raw-output.txt").read_text(encoding="utf-8") == "{\"verdict\":\"APPROVED\"}"


def test_timeout_never_becomes_task_approved(fake_agy_runner, bridge_config, tmp_path, schema_path):
    package_dir = tmp_path / "attempt-01"
    package_dir.mkdir()
    fake_agy_runner.raise_timeout = True

    result = run_audit_with_retries(bridge_config.with_agy_runner(fake_agy_runner), package_dir, "task", schema_path)

    assert result.status == "AUDITOR_INFRA_STOP"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_failure_semantics.py::test_invalid_auditor_output_retries_twice_then_infra_stop tests/test_failure_semantics.py::test_timeout_never_becomes_task_approved -v`

Expected: FAIL because retry semantics are absent.

- [ ] **Step 3: Write minimal implementation**

Retry policy:

```text
attempt 1: run AGY, parse output
attempt 2: run AGY again only if failure is infrastructure or invalid verdict
attempt 3: final retry because MAX_AUDITOR_RETRIES = 2 means two retries after the first try
no code changes are made between retries
return AUDITOR_INFRA_STOP after final failed parse, timeout, non-zero exit, permission failure, or missing model
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_failure_semantics.py::test_invalid_auditor_output_retries_twice_then_infra_stop tests/test_failure_semantics.py::test_timeout_never_becomes_task_approved -v`

Expected: PASS.

- [ ] **Step 5: Run regression**

Run: `pytest -v`

Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add scripts/audit_bridge.py tests/test_failure_semantics.py
git commit -m "feat: fail closed on auditor infrastructure errors"
```

---

### Task 9: Verdict Routing, Fix Attempts, High Escalation, And Architecture Stops

**Files:**
- Modify: `scripts/audit_bridge.py`
- Modify: `tests/test_failure_semantics.py`

**Interfaces:**
- Produces: `route_verdict(verdict: dict[str, object], fix_attempt_count: int) -> BridgeResult`
- Produces: `write_architecture_stop(package_dir: Path, request: AuditRequest, finding: dict[str, object]) -> Path`
- Produces status strings: `TASK_APPROVED`, `FIX_REQUIRED`, `ESCALATE_TO_HIGH_REVIEW`, `ARCHITECTURE_STOP`

- [ ] **Step 1: Write the failing test**

```python
from scripts.audit_bridge import route_verdict, write_architecture_stop


def test_fix_required_routes_to_tdd_fix_until_limit(tmp_path, audit_request):
    verdict = {
        "verdict": "FIX_REQUIRED",
        "spec_compliance": "CHANGES_REQUIRED",
        "code_quality": "CHANGES_REQUIRED",
        "test_evidence": "FAIL",
        "architecture_stop": False,
        "findings": [{
            "id": "F-01",
            "severity": "MEDIUM",
            "contract": "section 10",
            "file": "scripts/audit_bridge.py",
            "line": 10,
            "evidence": "invalid JSON accepted",
            "required_proof": "invalid JSON returns AUDITOR_FAILURE",
        }],
        "confidence": "HIGH",
    }

    assert route_verdict(verdict, fix_attempt_count=0).status == "FIX_REQUIRED"
    assert route_verdict(verdict, fix_attempt_count=3).status == "ESCALATE_TO_HIGH_REVIEW"


def test_architecture_stop_writes_required_artifact(tmp_path, audit_request):
    finding = {
        "id": "F-99",
        "severity": "CRITICAL",
        "contract": "Protected historical fingerprint",
        "file": "goldens/fingerprint.txt",
        "line": 1,
        "evidence": "fingerprint changed",
        "required_proof": "approved architecture ruling",
    }

    artifact = write_architecture_stop(tmp_path, audit_request, finding)

    text = artifact.read_text(encoding="utf-8")
    assert "ARCHITECTURE_STOP" in text
    assert "WHY_THIS_IS_NOT_A_NORMAL_BUG:" in text
    assert "IMPLEMENTATION_STATUS:\nSTOPPED" in text
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_failure_semantics.py::test_fix_required_routes_to_tdd_fix_until_limit tests/test_failure_semantics.py::test_architecture_stop_writes_required_artifact -v`

Expected: FAIL because verdict routing and architecture stop artifacts are absent.

- [ ] **Step 3: Write minimal implementation**

Routing rules:

```text
TASK_APPROVED -> status TASK_APPROVED only when test_evidence is PASS and architecture_stop is false
FIX_REQUIRED with fix_attempt_count < 3 -> status FIX_REQUIRED
FIX_REQUIRED with fix_attempt_count >= 3 -> status ESCALATE_TO_HIGH_REVIEW
any finding severity HIGH -> status ESCALATE_TO_HIGH_REVIEW after medium re-audit
any finding severity CRITICAL -> status ARCHITECTURE_STOP
verdict ARCHITECTURE_STOP -> status ARCHITECTURE_STOP
architecture_stop true -> status ARCHITECTURE_STOP
```

Architecture stop artifact must contain every field listed in spec section 19.

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_failure_semantics.py::test_fix_required_routes_to_tdd_fix_until_limit tests/test_failure_semantics.py::test_architecture_stop_writes_required_artifact -v`

Expected: PASS.

- [ ] **Step 5: Run regression**

Run: `pytest -v`

Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add scripts/audit_bridge.py tests/test_failure_semantics.py
git commit -m "feat: route audit verdict stops"
```

---

### Task 10: HEAD Approval Binding And Audit Provenance

**Files:**
- Modify: `scripts/audit_bridge.py`
- Modify: `tests/test_verdict_parser.py`
- Modify: `tests/test_audit_bridge.py`

**Interfaces:**
- Produces: `calculate_audit_package_id(package_dir: Path) -> str`
- Produces: `write_normalized_verdict(package_dir: Path, verdict: dict[str, object], audited_head_sha: str) -> Path`
- Produces status string: `AUDIT_PROVENANCE_INVALID`

- [ ] **Step 1: Write the failing test**

```python
import json

import pytest

from scripts.audit_bridge import AuditProvenanceInvalid, calculate_audit_package_id, write_normalized_verdict


def test_audit_package_id_includes_raw_output_and_manifest(tmp_path):
    package_dir = tmp_path / "attempt-01"
    package_dir.mkdir()
    (package_dir / "manifest.json").write_text('{"head_sha":"abc"}', encoding="utf-8")
    (package_dir / "diff.patch").write_text("diff --git a/a b/a\n", encoding="utf-8")
    (package_dir / "agy-raw-output.txt").write_text('{"verdict":"TASK_APPROVED"}', encoding="utf-8")

    first = calculate_audit_package_id(package_dir)
    (package_dir / "agy-raw-output.txt").write_text('{"verdict":"FIX_REQUIRED"}', encoding="utf-8")
    second = calculate_audit_package_id(package_dir)

    assert first != second


def test_normalized_verdict_must_match_audited_head(tmp_path):
    package_dir = tmp_path / "attempt-01"
    package_dir.mkdir()
    (package_dir / "manifest.json").write_text(json.dumps({"head_sha": "abc"}), encoding="utf-8")
    verdict = {
        "verdict": "TASK_APPROVED",
        "spec_compliance": "APPROVED",
        "code_quality": "APPROVED",
        "test_evidence": "PASS",
        "architecture_stop": False,
        "findings": [],
        "confidence": "HIGH",
    }

    with pytest.raises(AuditProvenanceInvalid) as exc:
        write_normalized_verdict(package_dir, verdict, audited_head_sha="def")

    assert exc.value.status == "AUDIT_PROVENANCE_INVALID"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_verdict_parser.py::test_audit_package_id_includes_raw_output_and_manifest tests/test_verdict_parser.py::test_normalized_verdict_must_match_audited_head -v`

Expected: FAIL because provenance functions are absent.

- [ ] **Step 3: Write minimal implementation**

Hash canonical bytes in this order:

```text
manifest.json
git-status.txt
git-log.txt
files-changed.json
diff.patch
production_diff.patch
test_diff.patch
contract_diff.patch
test-summary.json
test-output.txt
tdd-evidence.md
agy-prompt.txt
agy-raw-output.txt
```

Write `auditor-verdict.json` only after confirming the manifest `head_sha` equals the audited head SHA supplied to the function.

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_verdict_parser.py::test_audit_package_id_includes_raw_output_and_manifest tests/test_verdict_parser.py::test_normalized_verdict_must_match_audited_head -v`

Expected: PASS.

- [ ] **Step 5: Run regression**

Run: `pytest -v`

Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add scripts/audit_bridge.py tests/test_verdict_parser.py tests/test_audit_bridge.py
git commit -m "feat: bind approvals to audited head"
```

---

### Task 11: Final Phase Push And Pull Request Gate

**Files:**
- Modify: `scripts/audit_bridge.py`
- Modify: `tests/test_audit_bridge.py`

**Interfaces:**
- Produces: `finalize_after_approval(config: BridgeConfig, package_dir: Path, remote: str, branch: str, pr_title: str, pr_body: str) -> BridgeResult`
- Produces status strings: `PR_CREATED`, `REPOSITORY_SAFETY_STOP`

- [ ] **Step 1: Write the failing test**

```python
from scripts.audit_bridge import finalize_after_approval


def test_finalize_pushes_and_creates_pr_only_after_high_final_approval(fake_git_runner, fake_gh_runner, bridge_config, tmp_path):
    package_dir = tmp_path / "attempt-01"
    package_dir.mkdir()
    (package_dir / "auditor-verdict.json").write_text(
        '{"verdict":"TASK_APPROVED","spec_compliance":"APPROVED","code_quality":"APPROVED","test_evidence":"PASS","architecture_stop":false,"findings":[],"confidence":"HIGH","prompt_kind":"final"}',
        encoding="utf-8",
    )

    result = finalize_after_approval(
        bridge_config.with_git_runner(fake_git_runner).with_gh_runner(fake_gh_runner),
        package_dir,
        remote="origin",
        branch="feature/audit-bridge",
        pr_title="Implement independent audit bridge",
        pr_body="Final AGY High audit approved this HEAD.",
    )

    assert result.status == "PR_CREATED"
    assert fake_git_runner.commands == [["git", "push", "origin", "feature/audit-bridge"]]
    assert fake_gh_runner.commands[0][:3] == ["gh", "pr", "create"]


def test_finalize_refuses_merge_or_non_final_approval(fake_git_runner, fake_gh_runner, bridge_config, tmp_path):
    package_dir = tmp_path / "attempt-01"
    package_dir.mkdir()
    (package_dir / "auditor-verdict.json").write_text(
        '{"verdict":"TASK_APPROVED","spec_compliance":"APPROVED","code_quality":"APPROVED","test_evidence":"PASS","architecture_stop":false,"findings":[],"confidence":"MEDIUM","prompt_kind":"task"}',
        encoding="utf-8",
    )

    result = finalize_after_approval(
        bridge_config.with_git_runner(fake_git_runner).with_gh_runner(fake_gh_runner),
        package_dir,
        remote="origin",
        branch="feature/audit-bridge",
        pr_title="Implement independent audit bridge",
        pr_body="Task audit only.",
    )

    assert result.status == "REPOSITORY_SAFETY_STOP"
    assert fake_git_runner.commands == []
    assert fake_gh_runner.commands == []
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_audit_bridge.py::test_finalize_pushes_and_creates_pr_only_after_high_final_approval tests/test_audit_bridge.py::test_finalize_refuses_merge_or_non_final_approval -v`

Expected: FAIL because finalization is absent.

- [ ] **Step 3: Write minimal implementation**

Allow finalization only when:

```text
auditor-verdict.json verdict is TASK_APPROVED
spec_compliance is APPROVED
code_quality is APPROVED
test_evidence is PASS
architecture_stop is false
confidence is HIGH
prompt_kind is final
branch is not main or master
requested operation is push plus PR creation only
```

Run:

```text
git push <remote> <branch>
gh pr create --base main --head <branch> --title <title> --body <body>
```

Never run `git merge`, `gh pr merge`, auto-merge commands, force-push, rebase, or squash.

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_audit_bridge.py::test_finalize_pushes_and_creates_pr_only_after_high_final_approval tests/test_audit_bridge.py::test_finalize_refuses_merge_or_non_final_approval -v`

Expected: PASS.

- [ ] **Step 5: Run regression**

Run: `pytest -v`

Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add scripts/audit_bridge.py tests/test_audit_bridge.py
git commit -m "feat: gate final push and pr creation"
```

---

### Task 12: SKILL.md Policy Rewrite

**Files:**
- Modify: `SKILL.md`
- Modify: `PRESSURE_TESTS.md`

**Interfaces:**
- Produces user-facing skill sections:
  - `Roles and Authority`
  - `Required TDD Loop`
  - `Audit Package`
  - `Auditor Verdict Contract`
  - `Stop Taxonomy`
  - `Protected Contracts`
  - `Test Anti-Gaming`
  - `Final Push and PR Policy`
  - `Aurum V1.6 Closeout`

- [ ] **Step 1: Write the failing check**

Run:

```powershell
$required = @(
  'Codex is the implementer',
  'Gemini 3.8 Flash Medium',
  'Gemini 3.8 Flash High',
  'AUDITOR_INFRA_STOP',
  'REPOSITORY_SAFETY_STOP',
  'ARCHITECTURE_STOP',
  'MAX_AUTOMATIC_FIX_ATTEMPTS = 3',
  'merge is never automatic',
  'Aurum V1.6 closeout'
)
$text = Get-Content -Raw SKILL.md
$missing = $required | Where-Object { $text -notlike "*$_*" }
if ($missing) { throw "Missing required skill text: $($missing -join ', ')" }
```

Expected: FAIL because the current skill is provider-agnostic and does not yet encode the approved AGY/Gemini authority model.

- [ ] **Step 2: Write minimal documentation implementation**

Rewrite `SKILL.md` so it states:

```text
Codex is the implementer.
AGY / Gemini 3.8 Flash Medium is the default independent task auditor.
AGY / Gemini 3.8 Flash High is the escalation and final-phase auditor.
ChatGPT is architectural arbiter only.
Human user retains merge authority.
Every implementation task follows RED observed -> minimal implementation -> GREEN -> regression -> focused commit -> deterministic package -> independent audit.
TASK_APPROVED is valid only for the exact audited HEAD.
FIX_REQUIRED triggers a new RED for the finding and a new immutable attempt.
AUDITOR_INFRA_STOP blocks progress when AGY cannot run reliably.
REPOSITORY_SAFETY_STOP blocks unsafe Git or evidence states.
ARCHITECTURE_STOP blocks frozen contract changes.
Final AGY High approval permits push and PR creation.
Merge is never automatic.
Aurum V1.6 closeout is the first real integration case.
```

- [ ] **Step 3: Run check to verify it passes**

Run the PowerShell check from Step 1.

Expected: PASS.

- [ ] **Step 4: Run regression**

Run: `pytest -v`

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add SKILL.md PRESSURE_TESTS.md
git commit -m "docs: align skill policy with approved audit spec"
```

---

### Task 13: README And Operator Documentation

**Files:**
- Modify: `README.md`

**Interfaces:**
- Documents commands:
  - `python -m scripts.audit_bridge package ...`
  - `python -m scripts.audit_bridge audit ...`
  - `python -m scripts.audit_bridge finalize ...`

- [ ] **Step 1: Write the failing check**

Run:

```powershell
$required = @(
  'python -m scripts.audit_bridge package',
  'python -m scripts.audit_bridge audit',
  'python -m scripts.audit_bridge finalize',
  '%LOCALAPPDATA%\AurumAuditRuntime',
  'Gemini 3.8 Flash Medium',
  'Gemini 3.8 Flash High',
  'No merge command is run by this project'
)
$text = Get-Content -Raw README.md
$missing = $required | Where-Object { $text -notlike "*$_*" }
if ($missing) { throw "Missing README text: $($missing -join ', ')" }
```

Expected: FAIL because README does not yet document the deterministic bridge workflow.

- [ ] **Step 2: Write minimal documentation implementation**

Add README sections:

```text
Install
Configuration
Deterministic Audit Package
AGY Headless Read-Only Audit
Verdict Semantics
Automatic Fix Loop
Final Phase Push and PR
Aurum V1.6 Closeout
```

Include exact command examples for package, audit, and finalize with `--phase`, `--task-id`, `--base-sha`, `--head-sha`, `--spec-path`, and `--plan-path`.

- [ ] **Step 3: Run check to verify it passes**

Run the PowerShell check from Step 1.

Expected: PASS.

- [ ] **Step 4: Run regression**

Run: `pytest -v`

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add README.md
git commit -m "docs: document audit bridge workflow"
```

---

### Task 14: Real Aurum V1.6 Closeout Integration Case

**Files:**
- Modify: `scripts/audit_bridge.py`
- Modify: `tests/test_audit_bridge.py`
- Modify: `README.md`

**Interfaces:**
- Produces: `build_aurum_v16_closeout_request(worktree: Path, merge_readiness_doc: Path) -> AuditRequest`
- Produces status string: `V16_CLOSEOUT_AUDIT_READY`

- [ ] **Step 1: Write the failing test**

```python
from scripts.audit_bridge import build_aurum_v16_closeout_request


def test_aurum_v16_closeout_request_uses_audited_head_and_blocks_v17(git_repo):
    merge_doc = git_repo.write_file("docs/merge-readiness.md", "AUDITED_HEAD=stale\n")
    git_repo.commit_all("base")

    request = build_aurum_v16_closeout_request(git_repo.path, merge_doc)

    assert request.phase == "v1.6-closeout"
    assert request.task_id == "aurum-v1.6-closeout"
    assert request.base_sha == "7804af0896d686a3376c2a6d3c3bc3bcb8be7f9d"
    assert request.head_sha
    assert "v1.7 must not begin" in request.tdd_evidence_path.read_text(encoding="utf-8").lower()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_audit_bridge.py::test_aurum_v16_closeout_request_uses_audited_head_and_blocks_v17 -v`

Expected: FAIL because the Aurum V1.6 closeout helper does not exist.

- [ ] **Step 3: Write minimal implementation**

The helper creates a request with:

```text
phase = v1.6-closeout
task_id = aurum-v1.6-closeout
base_sha = 7804af0896d686a3376c2a6d3c3bc3bcb8be7f9d
head_sha = current HEAD
objective = identify why the merge-readiness document does not match the audited HEAD
hard rule = V1.7 must not begin until V1.6 operational closeout is resolved and merged
```

The helper does not modify the Aurum worktree. It only writes runtime evidence under the configured audit runtime root.

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_audit_bridge.py::test_aurum_v16_closeout_request_uses_audited_head_and_blocks_v17 -v`

Expected: PASS.

- [ ] **Step 5: Run regression**

Run: `pytest -v`

Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add scripts/audit_bridge.py tests/test_audit_bridge.py README.md
git commit -m "feat: support aurum v1.6 closeout audit"
```

---

## Final Verification Before Implementation Completion

- [ ] Run full Python tests.

```bash
pytest -v
```

Expected: PASS.

- [ ] Run documentation contract checks from Tasks 12 and 13.

Expected: PASS.

- [ ] Inspect the final package files.

```bash
python -m scripts.audit_bridge package --phase dry-run --task-id verification --base-sha <BASE_SHA> --head-sha <HEAD_SHA> --spec-path docs/superpowers/specs/2026-09-06-orchestrating-independent-code-audits-design.md --plan-path docs/superpowers/plans/2026-09-06-orchestrating-independent-code-audits.md
```

Expected: creates runtime evidence outside the repo and leaves `git status --short` clean except for intentional committed work.

- [ ] Run a fake AGY audit fixture in tests and a real AGY read-only smoke test where AGY is installed.

Expected: fake test passes in CI; real smoke test confirms the actual model identifier is available before any real audit is trusted.

- [ ] Confirm no merge operation exists in the codebase.

```bash
rg "gh pr merge|git merge|--auto|--squash|--rebase|--force|--force-with-lease" scripts tests README.md SKILL.md
```

Expected: no implementation path invokes merge, auto-merge, force-push, squash, or rebase.

---

## Self-Review Against Spec

**Spec coverage:** Covered. Tasks map to `SKILL.md`, `audit_bridge.py`, strict JSON schema, auditor prompts, AGY read-only headless execution, Gemini Medium default, Gemini High escalation/final, immutable attempts, protected contracts, test anti-gaming, `AUDITOR_INFRA_STOP`, `REPOSITORY_SAFETY_STOP`, `ARCHITECTURE_STOP`, final push plus PR creation, merge prohibition, and Aurum V1.6 closeout.

**Placeholder scan:** Clean. The plan contains concrete tests, commands, interfaces, and expected outcomes for every task.

**Type consistency:** Consistent names are used across tasks: `BridgeConfig`, `BridgeResult`, `AuditRequest`, `build_audit_package`, `parse_auditor_output`, `run_audit_with_retries`, `route_verdict`, `write_architecture_stop`, `calculate_audit_package_id`, `write_normalized_verdict`, `finalize_after_approval`, and `build_aurum_v16_closeout_request`.

**Implementation stop:** This plan is ready for execution, but execution must not begin until the human explicitly asks to implement it.
