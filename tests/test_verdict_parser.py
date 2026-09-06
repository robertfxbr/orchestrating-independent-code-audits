from __future__ import annotations

import json

import pytest

from scripts.audit_bridge import (
    AuditProvenanceInvalid,
    AuditorFailure,
    calculate_audit_package_id,
    parse_auditor_output,
    write_normalized_verdict,
)


def test_valid_task_approved_verdict_passes_schema(schema_path):
    raw = json.dumps(
        {
            "verdict": "TASK_APPROVED",
            "spec_compliance": "APPROVED",
            "code_quality": "APPROVED",
            "test_evidence": "PASS",
            "architecture_stop": False,
            "findings": [],
            "confidence": "MEDIUM",
        }
    )

    verdict = parse_auditor_output(raw, schema_path)

    assert verdict["verdict"] == "TASK_APPROVED"


@pytest.mark.parametrize("raw", ["", "not json", '{"verdict":"APPROVED"}'])
def test_invalid_output_fails_closed(schema_path, raw):
    with pytest.raises(AuditorFailure) as exc:
        parse_auditor_output(raw, schema_path)

    assert exc.value.status == "AUDITOR_FAILURE"


def test_audit_package_id_includes_raw_output_and_manifest(tmp_path):
    package_dir = tmp_path / "attempt-01"
    package_dir.mkdir()
    (package_dir / "manifest.json").write_text('{"head_sha":"abc"}', encoding="utf-8")
    (package_dir / "diff.patch").write_text("diff --git a/a b/a\n", encoding="utf-8")
    (package_dir / "agy-raw-output.txt").write_text('{"verdict":"TASK_APPROVED"}', encoding="utf-8")

    first = calculate_audit_package_id(package_dir)
    (package_dir / "agy-raw-output.txt").write_text('{"verdict":"FIX_REQUIRED"}', encoding="utf-8")
    second = calculate_audit_package_id(package_dir)

    assert first != second


def test_normalized_verdict_must_match_audited_head(tmp_path):
    package_dir = tmp_path / "attempt-01"
    package_dir.mkdir()
    (package_dir / "manifest.json").write_text('{"head_sha":"abc"}', encoding="utf-8")
    verdict = {
        "verdict": "TASK_APPROVED",
        "spec_compliance": "APPROVED",
        "code_quality": "APPROVED",
        "test_evidence": "PASS",
        "architecture_stop": False,
        "findings": [],
        "confidence": "HIGH",
    }

    with pytest.raises(AuditProvenanceInvalid) as exc:
        write_normalized_verdict(package_dir, verdict, audited_head_sha="def")

    assert exc.value.status == "AUDIT_PROVENANCE_INVALID"
