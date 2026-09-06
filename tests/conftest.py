from __future__ import annotations

from pathlib import Path
import subprocess

import pytest


@pytest.fixture
def schema_path() -> Path:
    return Path("schemas/auditor_verdict.schema.json")


class GitRepo:
    def __init__(self, path: Path) -> None:
        self.path = path
        self.path.mkdir(parents=True)
        subprocess.run(["git", "init"], cwd=path, check=True, capture_output=True, text=True)
        subprocess.run(["git", "config", "user.email", "test@example.com"], cwd=path, check=True)
        subprocess.run(["git", "config", "user.name", "Test User"], cwd=path, check=True)

    def write_file(self, relative_path: str, content: str) -> Path:
        path = self.path / relative_path
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
        return path

    def commit_all(self, message: str) -> None:
        subprocess.run(["git", "add", "."], cwd=self.path, check=True)
        subprocess.run(["git", "commit", "-m", message], cwd=self.path, check=True)

    def head(self) -> str:
        return subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=self.path,
            check=True,
            capture_output=True,
            text=True,
        ).stdout.strip()


@pytest.fixture
def git_repo(tmp_path) -> GitRepo:
    return GitRepo(tmp_path / "repo")


class FakeAgyRunner:
    def __init__(self) -> None:
        self.output = ""
        self.last_command: list[str] = []
        self.last_cwd: Path | None = None

    def run(self, command: list[str], cwd: Path) -> str:
        self.last_command = command
        self.last_cwd = cwd
        return self.output


@pytest.fixture
def fake_agy_runner() -> FakeAgyRunner:
    return FakeAgyRunner()


@pytest.fixture
def bridge_config(tmp_path) -> object:
    from scripts.audit_bridge import BridgeConfig

    return BridgeConfig.from_env().with_runtime_root(tmp_path / "runtime")
