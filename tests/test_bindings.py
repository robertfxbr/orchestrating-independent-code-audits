from __future__ import annotations

import copy
import json
from pathlib import Path

import pytest
import yaml

from scripts import audit_bridge as bridge
from scripts.bindings import (
    BindingsInvalid,
    BindingsRequired,
    load_bindings,
    parse_bindings,
    unavailable_commands,
    validate_bindings,
)

EXAMPLE = yaml.safe_load(Path("audit-orchestration.example.yaml").read_text(encoding="utf-8"))


def config_with(**roles) -> dict:
    raw = copy.deepcopy(EXAMPLE)
    raw["roles"].update(roles)
    return raw


def verdict(name: str = "TASK_APPROVED", severity: str | None = None) -> dict:
    approved = name == "TASK_APPROVED"
    findings = [] if severity is None else [{
        "id": "F-1", "severity": severity, "contract": "c", "file": "f.py", "line": 1,
        "evidence": "e", "required_proof": "p",
    }]
    return dict(verdict=name, spec_compliance="APPROVED" if approved else "CHANGES_REQUIRED",
                code_quality="APPROVED" if approved else "CHANGES_REQUIRED",
                test_evidence="PASS" if approved else "FAIL", architecture_stop=False,
                findings=findings, confidence="HIGH")


def agy_output(v: dict) -> str:
    return json.dumps({"status": "SUCCESS", "structured_output": v})


def claude_output(v: dict) -> str:
    return json.dumps({"type": "result", "subtype": "success", "is_error": False,
                       "result": json.dumps(v), "structured_output": v})


class RoutingRunner:
    """Answers per CLI, and records every command so tests can inspect the invocation."""

    def __init__(self, outputs: dict[str, list[str]]) -> None:
        self.outputs = outputs
        self.commands: list[list[str]] = []

    def run(self, command: list[str], cwd: Path) -> str:
        self.commands.append(command)
        queue = self.outputs[command[0]]
        answer = queue.pop(0) if len(queue) > 1 else queue[0]
        if isinstance(answer, Exception):
            raise answer
        return answer


@pytest.fixture
def package(tmp_path, schema_path):
    package_dir = tmp_path / "attempt-01"
    package_dir.mkdir()
    (package_dir / "manifest.json").write_text(json.dumps({"head_sha": "a" * 40, "worktree": str(tmp_path)}))
    (package_dir / "auditor_verdict.schema.json").write_text(schema_path.read_text(encoding="utf-8"))
    return package_dir


def run(bridge_config, package, raw, runner, kind="task"):
    config = bridge_config.with_bindings(parse_bindings(raw)).with_agy_runner(runner)
    return bridge.run_audit_with_retries(config, package, kind, package / "auditor_verdict.schema.json")


# --- validation -----------------------------------------------------------------


def test_shipped_example_is_valid():
    assert validate_bindings(EXAMPLE) == []


@pytest.mark.parametrize(
    ("change", "expected"),
    [
        (dict(primary_auditor=None), "primary_auditor is required"),
        (dict(implementer=None), "implementer is required"),
        (dict(primary_auditor="codex"), "codex cannot audit its own implementation"),
        (dict(additional_auditors=["codex"]), "codex cannot audit its own implementation"),
        (dict(merge_authority="claude-opus-5"), "merge_authority must be user"),
        (dict(additional_auditors=["claude-opus-5"]), "claude-opus-5 is already bound to another auditor role"),
        (dict(critical_auditor="agy-gemini-medium"), "critical_auditor equals primary_auditor"),
        (dict(additional_auditors=["ghost"]), "ghost has no entry under providers"),
    ],
)
def test_invalid_bindings_are_refused(change, expected):
    errors = validate_bindings(config_with(**change))

    assert any(expected in error for error in errors), errors
    with pytest.raises(BindingsInvalid):
        parse_bindings(config_with(**change))


def test_same_critical_and_primary_needs_explicit_acceptance():
    raw = config_with(critical_auditor="agy-gemini-medium")
    raw["independence"]["accept_critical_same_as_primary"] = True

    assert validate_bindings(raw) == []


def test_auditor_needs_a_supported_command_and_a_model():
    raw = copy.deepcopy(EXAMPLE)
    raw["providers"]["claude-opus-5"] = {"command": "curl", "model": None}

    errors = validate_bindings(raw)

    assert any("uses command 'curl'" in e for e in errors)
    assert any("claude-opus-5 needs a model" in e for e in errors)


@pytest.mark.parametrize("raw", [None, [], {"version": 2, "roles": {}}, {"version": 1, "roles": "x"}])
def test_malformed_files_are_refused(raw):
    assert validate_bindings(raw)


def test_missing_file_requires_first_use_setup(tmp_path):
    with pytest.raises(BindingsRequired):
        load_bindings(tmp_path / "absent.yaml")


def test_broken_yaml_is_invalid(tmp_path):
    path = tmp_path / "bindings.yaml"
    path.write_text("roles: [unclosed", encoding="utf-8")

    with pytest.raises(BindingsInvalid):
        load_bindings(path)


# --- which auditors run ---------------------------------------------------------


def test_task_audits_go_to_primary_and_additional_auditors():
    bindings = parse_bindings(config_with(additional_auditors=["gpt-6-astra"]))

    assert bindings.auditors_for("task") == ["agy-gemini-medium", "gpt-6-astra"]


def test_final_and_escalation_audits_go_to_the_critical_auditor():
    bindings = parse_bindings(EXAMPLE)

    assert bindings.auditors_for("final_phase") == ["claude-opus-5"]
    assert bindings.auditors_for("escalation") == ["claude-opus-5"]


def test_without_critical_auditor_the_primary_gates_the_final_audit():
    bindings = parse_bindings(config_with(critical_auditor=None))

    assert bindings.auditors_for("final_phase") == ["agy-gemini-medium"]


def test_unavailable_commands_are_reported_without_running_anything():
    bindings = parse_bindings(EXAMPLE)

    missing = unavailable_commands(bindings, which=lambda name: None if name == "claude" else "/bin/" + name)

    assert missing == ["claude-opus-5: command 'claude' not found on PATH"]


# --- bound audits ---------------------------------------------------------------


def test_final_audit_calls_claude_read_only_and_approves(bridge_config, package):
    runner = RoutingRunner({"claude": [claude_output(verdict())]})

    result = run(bridge_config, package, EXAMPLE, runner, kind="final_phase")

    assert result.status == "TASK_APPROVED"
    command = runner.commands[0]
    assert command[0] == "claude"
    assert command[command.index("--model") + 1] == "claude-opus-5"
    assert command[command.index("--permission-mode") + 1] == "plan"
    assert command[command.index("--tools") + 1] == "Read,Grep,Glob"
    assert "--dangerously-skip-permissions" not in command
    normalized = json.loads((package / "auditor-verdict.json").read_text())
    assert normalized["prompt_kind"] == "final_phase"
    assert normalized["auditors"] == {"claude-opus-5": "TASK_APPROVED"}


def test_task_audit_calls_agy_with_the_bound_model(bridge_config, package):
    runner = RoutingRunner({"agy": [agy_output(verdict())]})

    result = run(bridge_config, package, EXAMPLE, runner)

    command = runner.commands[0]
    assert result.status == "TASK_APPROVED"
    assert command[command.index("--model") + 1] == "Gemini 3.8 Flash (Medium)"
    assert command[command.index("--mode") + 1] == "plan"


def test_one_dissenting_additional_auditor_blocks_approval(bridge_config, package):
    raw = config_with(additional_auditors=["claude-opus-5"], critical_auditor=None)
    runner = RoutingRunner({"agy": [agy_output(verdict())],
                            "claude": [claude_output(verdict("FIX_REQUIRED", "MEDIUM"))]})

    result = run(bridge_config, package, raw, runner)

    assert result.status == "FIX_REQUIRED"
    normalized = json.loads((package / "auditor-verdict.json").read_text())
    assert normalized["verdict"] == "FIX_REQUIRED"
    assert normalized["auditors"] == {"agy-gemini-medium": "TASK_APPROVED", "claude-opus-5": "FIX_REQUIRED"}


def test_critical_finding_from_any_auditor_stops_for_a_ruling(bridge_config, package):
    raw = config_with(additional_auditors=["claude-opus-5"], critical_auditor=None)
    runner = RoutingRunner({"agy": [agy_output(verdict())],
                            "claude": [claude_output(verdict("FIX_REQUIRED", "CRITICAL"))]})

    assert run(bridge_config, package, raw, runner).status == "ARCHITECTURE_STOP"


def test_manual_auditor_stops_and_leaves_the_prompt(bridge_config, package):
    raw = config_with(primary_auditor="gpt-6-astra", critical_auditor=None, ruling_authority=None)
    runner = RoutingRunner({})

    result = run(bridge_config, package, raw, runner)

    assert result.status == "MANUAL_AUDIT_REQUIRED"
    assert runner.commands == []
    assert (package / "auditor-gpt-6-astra-prompt.txt").exists()


def test_failing_auditor_is_an_infra_stop_not_an_approval(bridge_config, package):
    error = json.dumps({"type": "result", "subtype": "error_max_turns", "is_error": True})
    runner = RoutingRunner({"claude": [error]})

    result = run(bridge_config, package, EXAMPLE, runner, kind="final_phase")

    assert result.status == "AUDITOR_INFRA_STOP"
    assert len(runner.commands) == bridge.MAX_AUDITOR_RETRIES + 1
    assert not (package / "auditor-verdict.json").exists()


def test_auditor_outputs_change_the_package_id(package):
    (package / "auditor-claude-opus-5-raw-output.txt").write_text("one", encoding="utf-8")
    first = bridge.calculate_audit_package_id(package)
    (package / "auditor-claude-opus-5-raw-output.txt").write_text("two", encoding="utf-8")

    assert bridge.calculate_audit_package_id(package) != first


def test_unknown_command_has_no_adapter(package, schema_path):
    with pytest.raises(bridge.AuditorFailure):
        bridge.build_auditor_command("curl", "m", package, "prompt", schema_path)


# --- CLI ------------------------------------------------------------------------


def write(tmp_path, raw) -> Path:
    path = tmp_path / "bindings.yaml"
    path.write_text(yaml.safe_dump(raw), encoding="utf-8")
    return path


def last_json(capsys) -> dict:
    return json.loads(capsys.readouterr().out.splitlines()[-1])


def test_check_bindings_reports_valid(tmp_path, capsys):
    code = bridge.check_bindings(write(tmp_path, EXAMPLE), which=lambda name: "/bin/" + name)

    assert code == 0
    assert last_json(capsys)["status"] == "BINDINGS_VALID"


def test_check_bindings_reports_unavailable_agents(tmp_path, capsys):
    code = bridge.check_bindings(write(tmp_path, EXAMPLE), which=lambda name: None)

    assert code == 1
    assert last_json(capsys)["status"] == "BINDINGS_UNAVAILABLE"


def test_check_bindings_lists_every_broken_rule(tmp_path, capsys):
    code = bridge.main(["check-bindings", "--bindings", str(write(tmp_path, config_with(primary_auditor="codex",
                                                                                        merge_authority="x")))])

    output = last_json(capsys)
    assert code == 1
    assert output["status"] == "BINDINGS_INVALID"
    assert len(output["problems"]) >= 2


def test_check_bindings_without_file_asks_for_setup(tmp_path, capsys):
    assert bridge.main(["check-bindings", "--bindings", str(tmp_path / "none.yaml")]) == 1
    assert last_json(capsys)["status"] == "BINDINGS_REQUIRED"


def test_cli_audit_without_bindings_fails_closed(git_repo, tmp_path, capsys, monkeypatch):
    spec = git_repo.write_file("spec.md", "contract\n")
    plan = git_repo.write_file("plan.md", "plan\n")
    git_repo.commit_all("audited")
    head = git_repo.head()
    monkeypatch.setattr(bridge, "_invoke_auditor", lambda *a: pytest.fail("no auditor may run without bindings"))

    code = bridge.main(["audit", "--phase", "t", "--task-id", "cli", "--base-sha", head, "--head-sha", head,
                        "--spec-path", str(spec), "--plan-path", str(plan),
                        "--runtime-root", str(tmp_path / "runtime")])

    assert code == 1
    assert last_json(capsys)["status"] == "BINDINGS_REQUIRED"


def test_cli_escalate_sends_the_package_to_the_critical_auditor(git_repo, tmp_path, capsys, monkeypatch):
    spec = git_repo.write_file("spec.md", "contract\n")
    plan = git_repo.write_file("plan.md", "plan\n")
    git_repo.commit_all("audited")
    head = git_repo.head()
    called: list[str] = []

    def fake(config, command, cwd):
        called.append(command[0])
        return claude_output(verdict())

    monkeypatch.setattr(bridge, "_invoke_auditor", fake)

    code = bridge.main(["escalate", "--phase", "t", "--task-id", "esc", "--base-sha", head, "--head-sha", head,
                        "--spec-path", str(spec), "--plan-path", str(plan),
                        "--runtime-root", str(tmp_path / "runtime"), "--bindings", str(write(tmp_path, EXAMPLE))])

    assert code == 0
    assert called == ["claude"]
    assert last_json(capsys)["status"] == "TASK_APPROVED"
