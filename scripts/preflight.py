"""Before any audit: is each bound auditor installed, signed in, and able to use its model?

Every check is read-only and costs nothing: no prompt is sent to a model.
"""

from __future__ import annotations

import json
import shutil
import subprocess
from collections.abc import Callable
from dataclasses import dataclass

from scripts.bindings import Bindings

READY = "READY"
MANUAL = "MANUAL"
NOT_INSTALLED = "NOT_INSTALLED"
NOT_SIGNED_IN = "NOT_SIGNED_IN"
MODEL_UNAVAILABLE = "MODEL_UNAVAILABLE"

CHECK_TIMEOUT_SECONDS = 60

Runner = Callable[[list[str]], tuple[int, str]]


@dataclass(frozen=True)
class AuditorCheck:
    agent: str
    status: str
    fix: str

    @property
    def blocks(self) -> bool:
        return self.status not in {READY, MANUAL}

    def as_dict(self) -> dict[str, str]:
        return {"agent": self.agent, "status": self.status, "fix": self.fix}


def run_check(command: list[str]) -> tuple[int, str]:
    try:
        completed = subprocess.run(command, capture_output=True, text=True, timeout=CHECK_TIMEOUT_SECONDS, check=False)
    except FileNotFoundError:
        return 127, ""
    except subprocess.TimeoutExpired:
        return 124, ""
    return completed.returncode, completed.stdout


def _check_claude(agent: str, run: Runner) -> AuditorCheck:
    code, out = run(["claude", "auth", "status"])
    try:
        logged_in = code == 0 and json.loads(out).get("loggedIn") is True
    except (json.JSONDecodeError, AttributeError):
        logged_in = False
    if not logged_in:
        return AuditorCheck(agent, NOT_SIGNED_IN,
                            "Run `claude auth login` in a terminal, finish signing in, then run `claude auth status` "
                            "and confirm it shows \"loggedIn\": true.")
    return AuditorCheck(agent, READY, "")


def _check_agy(agent: str, model: str, run: Runner) -> AuditorCheck:
    code, out = run(["agy", "models"])
    if code != 0:
        return AuditorCheck(agent, NOT_SIGNED_IN,
                            "`agy models` could not reach your account. Open `agy` in a terminal, complete the sign-in, "
                            "then run `agy models` and confirm it lists models.")
    if model not in out:
        return AuditorCheck(agent, MODEL_UNAVAILABLE,
                            f"`agy models` does not list {model!r}. Pick a model it lists and update "
                            f"providers.{agent}.model in the bindings file.")
    return AuditorCheck(agent, READY, "")


def check_auditors(
    bindings: Bindings,
    agents: list[str],
    run: Runner = run_check,
    which: Callable[[str], str | None] = shutil.which,
) -> list[AuditorCheck]:
    checks = []
    for agent in dict.fromkeys(agents):
        provider = bindings.providers[agent]
        if provider.command is None:
            checks.append(AuditorCheck(agent, MANUAL,
                                       "Manual auditor: the bridge will write the prompt and stop so you can relay it."))
        elif which(provider.command) is None:
            checks.append(AuditorCheck(agent, NOT_INSTALLED,
                                       f"`{provider.command}` is not on PATH. Install it, open a new terminal, "
                                       f"and run `{provider.command} --version` to confirm."))
        elif provider.command == "claude":
            checks.append(_check_claude(agent, run))
        else:
            checks.append(_check_agy(agent, provider.model, run))
    return checks


def all_auditors(bindings: Bindings) -> list[str]:
    return [a for a in (bindings.primary_auditor, bindings.critical_auditor, *bindings.additional_auditors) if a]
