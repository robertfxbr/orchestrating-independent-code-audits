from __future__ import annotations

import pytest

from scripts.audit_bridge import (
    ARCHITECTURE_STOP,
    ArchitectureStop,
    AuditRequest,
    BridgeConfig,
    RepositorySafetyStop,
    build_audit_package,
    run_audit_with_retries,
    route_verdict,
    write_architecture_stop,
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


def test_invalid_auditor_output_retries_twice_then_infra_stop(
    fake_agy_runner, bridge_config, tmp_path, schema_path
):
    package_dir = tmp_path / "attempt-01"
    package_dir.mkdir()
    fake_agy_runner.outputs = ["not json", "", '{"verdict":"APPROVED"}']

    result = run_audit_with_retries(
        bridge_config.with_agy_runner(fake_agy_runner), package_dir, "task", schema_path
    )

    assert result.status == "AUDITOR_INFRA_STOP"
    assert fake_agy_runner.call_count == 3
    assert (package_dir / "agy-raw-output.txt").read_text(encoding="utf-8") == '{"verdict":"APPROVED"}'


def test_timeout_never_becomes_task_approved(fake_agy_runner, bridge_config, tmp_path, schema_path):
    package_dir = tmp_path / "attempt-01"
    package_dir.mkdir()
    fake_agy_runner.raise_timeout = True

    result = run_audit_with_retries(
        bridge_config.with_agy_runner(fake_agy_runner), package_dir, "task", schema_path
    )

    assert result.status == "AUDITOR_INFRA_STOP"


def test_fix_required_routes_to_tdd_fix_until_limit():
    verdict = {
        "verdict": "FIX_REQUIRED",
        "spec_compliance": "CHANGES_REQUIRED",
        "code_quality": "CHANGES_REQUIRED",
        "test_evidence": "FAIL",
        "architecture_stop": False,
        "findings": [
            {
                "id": "F-01",
                "severity": "MEDIUM",
                "contract": "section 10",
                "file": "scripts/audit_bridge.py",
                "line": 10,
                "evidence": "invalid JSON accepted",
                "required_proof": "invalid JSON returns AUDITOR_FAILURE",
            }
        ],
        "confidence": "HIGH",
    }

    assert route_verdict(verdict, fix_attempt_count=0).status == "FIX_REQUIRED"
    assert route_verdict(verdict, fix_attempt_count=3).status == "ESCALATE_TO_HIGH_REVIEW"


@pytest.mark.parametrize(
    ("verdict_value", "architecture_flag", "severity"),
    [
        ("TASK_APPROVED", False, "CRITICAL"),
        ("FIX_REQUIRED", False, "CRITICAL"),
        ("TASK_APPROVED", True, "LOW"),
    ],
)
def test_critical_finding_or_architecture_flag_stops_for_human_ruling(verdict_value, architecture_flag, severity):
    verdict = {
        "verdict": verdict_value,
        "spec_compliance": "APPROVED",
        "code_quality": "APPROVED",
        "test_evidence": "PASS",
        "architecture_stop": architecture_flag,
        "findings": [
            {
                "id": "F-02",
                "severity": severity,
                "contract": "protected contract",
                "file": "scripts/audit_bridge.py",
                "line": 1,
                "evidence": "contract changed",
                "required_proof": "architecture ruling",
            }
        ],
        "confidence": "HIGH",
    }

    result = route_verdict(verdict, fix_attempt_count=0)

    assert result.status == ARCHITECTURE_STOP


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
