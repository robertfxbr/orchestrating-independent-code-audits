from __future__ import annotations

import json

import pytest

from scripts.audit_bridge import (
    AttemptAlreadyExistsError,
    AuditRequest,
    BridgeConfig,
    BridgeResult,
    build_audit_package,
    classify_changed_file,
    _diff_for_paths,
    main,
    render_auditor_prompt,
    run_agy_audit,
    finalize_after_approval,
)


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


def test_bridge_result_records_status_and_head(tmp_path):
    result = BridgeResult(
        status="PACKAGE_CREATED",
        attempt_dir=tmp_path,
        head_sha="abc123",
        message="created",
    )

    assert result.status == "PACKAGE_CREATED"
    assert result.attempt_dir == tmp_path
    assert result.head_sha == "abc123"
    assert result.message == "created"


def test_package_contains_git_derived_evidence(tmp_path, git_repo, schema_path):
    spec = git_repo.write_file("spec.md", "frozen contract\n")
    plan = git_repo.write_file("plan.md", "approved plan\n")
    git_repo.commit_all("base")
    base_sha = git_repo.head()
    git_repo.write_file("src.py", "print('changed')\n")
    git_repo.commit_all("change")
    head_sha = git_repo.head()
    config = BridgeConfig.from_env().with_runtime_root(tmp_path / "runtime")

    result = build_audit_package(
        config,
        AuditRequest(
            phase="v1.0",
            task_id="task-01",
            base_sha=base_sha,
            head_sha=head_sha,
            spec_path=spec,
            plan_path=plan,
            test_output_path=None,
            tdd_evidence_path=None,
        ),
    )

    manifest = json.loads((result.attempt_dir / "manifest.json").read_text(encoding="utf-8"))
    assert result.status == "PACKAGE_CREATED"
    assert manifest["base_sha"] == base_sha
    assert manifest["head_sha"] == head_sha
    assert manifest["tree_sha"]
    assert (result.attempt_dir / "git-status.txt").exists()
    assert (result.attempt_dir / "git-log.txt").exists()
    assert (result.attempt_dir / "files-changed.json").exists()
    assert "src.py" in (result.attempt_dir / "diff.patch").read_text(encoding="utf-8")


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


def test_package_classifies_test_changes(tmp_path, git_repo):
    spec = git_repo.write_file("spec.md", "contract\n")
    plan = git_repo.write_file("plan.md", "plan\n")
    git_repo.write_file("tests/test_old.py", "def test_old():\n    assert 1 == 1\n")
    git_repo.commit_all("base")
    base_sha = git_repo.head()
    git_repo.write_file("tests/test_old.py", "def test_old():\n    assert 2 == 2\n")
    git_repo.write_file("tests/test_new.py", "def test_new():\n    assert 'x' == 'x'\n")
    git_repo.commit_all("head")
    head_sha = git_repo.head()
    config = BridgeConfig.from_env().with_runtime_root(tmp_path / "runtime")

    result = build_audit_package(
        config,
        AuditRequest("v1.0", "task-02", base_sha, head_sha, spec, plan, None, None),
    )

    summary = json.loads((result.attempt_dir / "test-summary.json").read_text(encoding="utf-8"))
    assert summary["tests/test_old.py"] == "MODIFIED_EXISTING_TEST"
    assert summary["tests/test_new.py"] == "NEW_TEST"


def test_protected_contract_paths_are_classified_for_auditor_evidence():
    assert (
        classify_changed_file(
            "goldens/fingerprint.txt",
            "M",
            ("goldens/fingerprint.txt",),
        )
        == "PROTECTED_CONTRACT"
    )


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


def test_agy_invocation_uses_model_and_never_accepts_edits(
    fake_agy_runner, bridge_config, tmp_path
):
    package_dir = tmp_path / "attempt-01"
    package_dir.mkdir()
    fake_agy_runner.output = (
        '{"verdict":"TASK_APPROVED","spec_compliance":"APPROVED",'
        '"code_quality":"APPROVED","test_evidence":"PASS",'
        '"architecture_stop":false,"findings":[],"confidence":"MEDIUM"}'
    )

    run_agy_audit(bridge_config.with_agy_runner(fake_agy_runner), package_dir, "task")

    command = " ".join(fake_agy_runner.last_command)
    assert "Gemini 3.8 Flash Medium" in command
    assert "--dangerously-skip-permissions" not in command
    assert "--mode=accept-edits" not in command
    assert fake_agy_runner.last_cwd == package_dir


def test_finalize_pushes_and_creates_pr_only_after_high_final_approval(
    fake_git_runner, fake_gh_runner, bridge_config, tmp_path
):
    package_dir = tmp_path / "attempt-01"
    package_dir.mkdir()
    (package_dir / "auditor-verdict.json").write_text(
        '{"verdict":"TASK_APPROVED","spec_compliance":"APPROVED",'
        '"code_quality":"APPROVED","test_evidence":"PASS",'
        '"architecture_stop":false,"findings":[],"confidence":"HIGH",'
        '"prompt_kind":"final"}',
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


def test_finalize_refuses_merge_or_non_final_approval(
    fake_git_runner, fake_gh_runner, bridge_config, tmp_path
):
    package_dir = tmp_path / "attempt-01"
    package_dir.mkdir()
    (package_dir / "auditor-verdict.json").write_text(
        '{"verdict":"TASK_APPROVED","spec_compliance":"APPROVED",'
        '"code_quality":"APPROVED","test_evidence":"PASS",'
        '"architecture_stop":false,"findings":[],"confidence":"MEDIUM",'
        '"prompt_kind":"task"}',
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


def test_contract_diff_evidence_preserves_protected_change(tmp_path, git_repo):
    protected = git_repo.write_file("goldens/fingerprint.txt", "abc\n")
    git_repo.commit_all("base")
    base_sha = git_repo.head()
    git_repo.write_file("goldens/fingerprint.txt", "def\n")
    git_repo.commit_all("contract change")
    head_sha = git_repo.head()

    contract_diff = _diff_for_paths(
        git_repo.path,
        base_sha,
        head_sha,
        [str(protected.relative_to(git_repo.path))],
    )

    assert "goldens/fingerprint.txt" in contract_diff
    assert "-abc" in contract_diff
    assert "+def" in contract_diff
