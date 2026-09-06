from __future__ import annotations

import pytest

from scripts.audit_bridge import (
    ARCHITECTURE_STOP,
    ArchitectureStop,
    AuditRequest,
    BridgeConfig,
    RepositorySafetyStop,
    build_audit_package,
)


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

    with pytest.raises(ArchitectureStop) as exc:
        build_audit_package(config, AuditRequest("v1.0", "task-04", base_sha, head_sha, spec, plan, None, None))

    assert exc.value.status == ARCHITECTURE_STOP
    assert "protected contract" in str(exc.value).lower()


def test_invalid_git_sha_is_a_repository_safety_stop(tmp_path, git_repo):
    spec = git_repo.write_file("spec.md", "contract\n")
    plan = git_repo.write_file("plan.md", "plan\n")
    git_repo.commit_all("base")
    head_sha = git_repo.head()
    config = BridgeConfig.from_env().with_runtime_root(tmp_path / "runtime")

    with pytest.raises(RepositorySafetyStop) as exc:
        build_audit_package(
            config,
            AuditRequest("v1.0", "task-05", "not-a-sha", head_sha, spec, plan, None, None),
        )

    assert exc.value.status == "REPOSITORY_SAFETY_STOP"
    assert "sha" in str(exc.value).lower()
