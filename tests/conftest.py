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
