from __future__ import annotations

import json

from scripts.audit_bridge import AuditRequest, BridgeConfig, BridgeResult, build_audit_package, main


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
