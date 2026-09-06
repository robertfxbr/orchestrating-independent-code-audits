from __future__ import annotations

import json

import pytest

from scripts.audit_bridge import AuditorFailure, parse_auditor_output


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
