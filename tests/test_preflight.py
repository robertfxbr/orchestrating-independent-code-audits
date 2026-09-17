from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from scripts.bindings import parse_bindings
from scripts.preflight import (
    MANUAL,
    MODEL_UNAVAILABLE,
    NOT_INSTALLED,
    NOT_SIGNED_IN,
    READY,
    check_auditors,
    run_check,
)

EXAMPLE = yaml.safe_load(Path("audit-orchestration.example.yaml").read_text(encoding="utf-8"))
BINDINGS = parse_bindings(EXAMPLE)
AGY_MODELS = "gemini-3.8-flash-high\tGemini 3.8 Flash (High)\ngemini-3.8-flash-medium\tGemini 3.8 Flash (Medium)\n"


class Checks:
    """Fake read-only checks; records what would have been executed."""

    def __init__(self, claude=(0, '{"loggedIn": true, "email": "someone@example.com"}'), agy=(0, AGY_MODELS)):
        self.answers = {"claude": claude, "agy": agy}
        self.commands: list[list[str]] = []

    def __call__(self, command: list[str]) -> tuple[int, str]:
        self.commands.append(command)
        return self.answers[command[0]]


def on_path(name: str) -> str:
    return "/bin/" + name


def status_of(checks, agent):
    return next(c for c in checks if c.agent == agent)


def test_signed_in_auditors_are_ready_and_only_status_commands_run():
    run = Checks()

    checks = check_auditors(BINDINGS, ["agy-gemini-medium", "claude-opus-5"], run=run, which=on_path)

    assert [c.status for c in checks] == [READY, READY]
    assert run.commands == [["agy", "models"], ["claude", "auth", "status"]]


def test_signed_out_claude_blocks_with_login_instructions():
    checks = check_auditors(BINDINGS, ["claude-opus-5"], run=Checks(claude=(0, '{"loggedIn": false}')), which=on_path)

    check = status_of(checks, "claude-opus-5")
    assert check.status == NOT_SIGNED_IN
    assert check.blocks
    assert "claude auth login" in check.fix


@pytest.mark.parametrize("answer", [(1, ""), (0, "not json")])
def test_unreadable_claude_status_counts_as_signed_out(answer):
    checks = check_auditors(BINDINGS, ["claude-opus-5"], run=Checks(claude=answer), which=on_path)

    assert checks[0].status == NOT_SIGNED_IN


def test_agy_that_cannot_list_models_is_not_signed_in():
    checks = check_auditors(BINDINGS, ["agy-gemini-medium"], run=Checks(agy=(1, "")), which=on_path)

    assert checks[0].status == NOT_SIGNED_IN
    assert "agy models" in checks[0].fix


def test_agy_model_missing_from_the_account_is_reported():
    checks = check_auditors(BINDINGS, ["agy-gemini-medium"], run=Checks(agy=(0, "gemini-3.1-pro-high\tGemini 3.1 Pro (High)\n")),
                            which=on_path)

    assert checks[0].status == MODEL_UNAVAILABLE
    assert "providers.agy-gemini-medium.model" in checks[0].fix


def test_missing_command_is_not_installed_and_nothing_runs():
    run = Checks()

    checks = check_auditors(BINDINGS, ["claude-opus-5"], run=run, which=lambda name: None)

    assert checks[0].status == NOT_INSTALLED
    assert run.commands == []


def test_manual_auditor_does_not_block_and_runs_nothing():
    run = Checks()

    checks = check_auditors(BINDINGS, ["gpt-6-astra"], run=run, which=on_path)

    assert checks[0].status == MANUAL
    assert not checks[0].blocks
    assert run.commands == []


def test_check_output_never_carries_the_account_email():
    checks = check_auditors(BINDINGS, ["claude-opus-5"], run=Checks(), which=on_path)

    assert "example.com" not in str([c.as_dict() for c in checks])


def test_run_check_reports_a_missing_program_instead_of_raising():
    assert run_check(["definitely-not-an-installed-program-xyz"]) == (127, "")
