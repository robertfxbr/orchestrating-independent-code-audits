"""Load and validate `.agents/audit-orchestration.yaml`, the role bindings chosen on first use."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import yaml

DEFAULT_BINDINGS_PATH = Path(".agents") / "audit-orchestration.yaml"

# Auditor commands the bridge knows how to call. `None` means manual: the user relays the package.
SUPPORTED_AUDITOR_COMMANDS = {"agy", "claude", None}


class BindingsInvalid(Exception):
    def __init__(self, errors: list[str]) -> None:
        super().__init__("; ".join(errors))
        self.errors = errors
        self.status = "BINDINGS_INVALID"


class BindingsRequired(Exception):
    def __init__(self, path: Path) -> None:
        super().__init__(f"no bindings file at {path}; run the skill's first-use setup")
        self.status = "BINDINGS_REQUIRED"


@dataclass(frozen=True)
class Provider:
    name: str
    command: str | None
    model: str | None


@dataclass(frozen=True)
class Bindings:
    implementer: str
    primary_auditor: str
    critical_auditor: str | None
    additional_auditors: tuple[str, ...]
    ruling_authority: str | None
    providers: dict[str, Provider]

    def auditors_for(self, prompt_kind: str) -> list[str]:
        """Gate auditor first, then every additional auditor. All of them must approve."""
        high_stakes = prompt_kind in {"escalation", "final_phase"}
        gate = self.critical_auditor if high_stakes and self.critical_auditor else self.primary_auditor
        return [gate, *(a for a in self.additional_auditors if a != gate)]


def _name(value: object) -> str | None:
    return value if isinstance(value, str) and value.strip() else None


def validate_bindings(raw: object) -> list[str]:
    """Return every rule the configuration breaks. An empty list means it is valid."""
    if not isinstance(raw, dict):
        return ["the file must be a YAML mapping"]
    errors: list[str] = []
    if raw.get("version") != 1:
        errors.append("version must be 1")
    roles = raw.get("roles")
    providers = raw.get("providers")
    if not isinstance(roles, dict):
        return [*errors, "roles must be a mapping"]
    if not isinstance(providers, dict):
        providers = {}
        errors.append("providers must be a mapping")

    implementer = _name(roles.get("implementer"))
    primary = _name(roles.get("primary_auditor"))
    critical = _name(roles.get("critical_auditor"))
    ruling = _name(roles.get("ruling_authority"))
    additional = roles.get("additional_auditors") or []

    if implementer is None:
        errors.append("implementer is required")
    if primary is None:
        errors.append("primary_auditor is required")
    if roles.get("critical_auditor") is not None and critical is None:
        errors.append("critical_auditor must be an agent name or null")
    if not isinstance(additional, list) or not all(_name(a) for a in additional):
        errors.append("additional_auditors must be a list of agent names")
        additional = []
    if len(set(additional)) != len(additional):
        errors.append("additional_auditors must not repeat an agent")
    if roles.get("merge_authority") != "user":
        errors.append("merge_authority must be user")
    if ruling == "user":
        ruling = None

    auditors = [a for a in (primary, critical, *additional) if a]
    if implementer and implementer in auditors:
        errors.append(f"{implementer} cannot audit its own implementation")
    for agent in additional:
        if agent in (primary, critical):
            errors.append(f"{agent} is already bound to another auditor role")

    independence = raw.get("independence") or {}
    if critical and critical == primary and not independence.get("accept_critical_same_as_primary"):
        errors.append(
            "critical_auditor equals primary_auditor; set independence.accept_critical_same_as_primary "
            "to true only if the user accepts that it is not an independent second opinion"
        )

    for agent in {a for a in (implementer, ruling, *auditors) if a}:
        if agent not in providers:
            errors.append(f"{agent} has no entry under providers")
    for agent in auditors:
        entry = providers.get(agent)
        if not isinstance(entry, dict):
            continue
        command = entry.get("command")
        if command not in SUPPORTED_AUDITOR_COMMANDS:
            errors.append(f"{agent} uses command {command!r}; the bridge can call agy, claude, or null for manual")
        if command is not None and not _name(entry.get("model")):
            errors.append(f"{agent} needs a model")
    return errors


def parse_bindings(raw: object) -> Bindings:
    errors = validate_bindings(raw)
    if errors:
        raise BindingsInvalid(errors)
    roles = raw["roles"]
    ruling = _name(roles.get("ruling_authority"))
    return Bindings(
        implementer=roles["implementer"],
        primary_auditor=roles["primary_auditor"],
        critical_auditor=_name(roles.get("critical_auditor")),
        additional_auditors=tuple(roles.get("additional_auditors") or ()),
        ruling_authority=None if ruling == "user" else ruling,
        providers={
            name: Provider(name, entry.get("command"), entry.get("model"))
            for name, entry in raw["providers"].items()
            if isinstance(entry, dict)
        },
    )


def load_bindings(path: Path) -> Bindings:
    if not path.exists():
        raise BindingsRequired(path)
    try:
        raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    except yaml.YAMLError as exc:
        raise BindingsInvalid([f"not valid YAML: {exc}"]) from exc
    return parse_bindings(raw)
