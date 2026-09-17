"""The shipped example must obey the binding rules that SKILL.md asks the agent to enforce."""

from __future__ import annotations

from pathlib import Path

import yaml

EXAMPLE = Path("audit-orchestration.example.yaml")


def load_roles() -> dict[str, object]:
    return yaml.safe_load(EXAMPLE.read_text(encoding="utf-8"))["roles"]


def test_required_roles_are_bound():
    roles = load_roles()

    assert roles["implementer"]
    assert roles["primary_auditor"]


def test_no_auditor_is_the_implementer():
    roles = load_roles()
    auditors = [roles["primary_auditor"], roles["critical_auditor"], *roles["additional_auditors"]]

    assert roles["implementer"] not in [a for a in auditors if a]


def test_merge_authority_is_always_the_user():
    assert load_roles()["merge_authority"] == "user"


def test_every_bound_agent_has_a_provider_entry():
    config = yaml.safe_load(EXAMPLE.read_text(encoding="utf-8"))
    roles = config["roles"]
    bound = {roles["implementer"], roles["primary_auditor"], roles["critical_auditor"], roles["ruling_authority"]}
    bound.update(roles["additional_auditors"])
    bound.discard(None)
    bound.discard("user")

    assert bound <= set(config["providers"])
