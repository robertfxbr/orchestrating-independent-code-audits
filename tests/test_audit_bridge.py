from __future__ import annotations

from scripts.audit_bridge import BridgeConfig, BridgeResult, main


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
