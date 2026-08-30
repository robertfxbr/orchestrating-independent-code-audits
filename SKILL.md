---
name: orchestrating-independent-code-audits
description: Use when implementing multi-step software changes that require independent review, critical escalation, or provider-swappable coding and audit roles.
---

# Orchestrating Independent Code Audits

Use this skill when one agent implements and each task needs independent audit before it can advance. The workflow is provider-agnostic: concrete provider names are bindings for canonical roles, not workflow logic.

## Canonical Roles

Use exactly these roles:

- `implementer`: writes failing tests, code, fixes, and commits.
- `primary_auditor`: first independent reviewer for every task.
- `critical_auditor`: adversarial independent reviewer for critical findings or always-critical tasks.
- `ruling_authority`: human or architecture authority that resolves material disagreement.

Do not add provider-specific roles.

## Resolve Bindings

Resolve role providers in this order:

1. Explicit user instruction.
2. Project config at `.agents/audit-orchestration.yaml`.
3. If still unresolved, ask the user before implementation.

Never choose or swap providers silently. Fallbacks are valid only when explicitly configured.

## Independence Gate

Before implementation starts, verify:

- `implementer != primary_auditor`.
- The implementer never approves its own code.
- When `critical_auditor` is required, it must differ from `implementer` for the review to count as independent.

Invalid bindings produce `CONFIGURATION_ERROR` and stop the task.

## Canonical Workflow

For each task:

1. `implementer` creates a failing test or executable check first (`RED`).
2. Confirm RED failed for the expected reason.
3. Implement the minimum change.
4. Run focused checks to reach `GREEN`.
5. Run relevant regression checks.
6. Commit the task.
7. Build an audit package pinned to the exact commit SHA.
8. Send the package to `primary_auditor`.

If `primary_auditor` returns `APPROVED`, that exact commit may advance.

If `primary_auditor` returns `FIX_REQUIRED`, the implementer first creates a regression test reproducing the finding, verifies RED, fixes minimally, verifies GREEN, runs regression checks, commits, and requests re-audit.

If `primary_auditor` reports severity `CRITICAL`, or the task matches configured `always_critical_tasks`, send the package to `critical_auditor` for adversarial independent review.

If `primary_auditor` and `critical_auditor` materially agree on the problem, the implementer fixes via TDD and the relevant auditors re-audit.

If they materially diverge, return verdict `ARCHITECTURE_STOP` with reason `ARCHITECTURE_RULING_REQUIRED`. No agent may advance until `ruling_authority` decides.

## Auditor Availability

Unavailable auditors block approval:

- `primary_auditor` unavailable: `TASK_APPROVAL_BLOCKED`.
- Required `critical_auditor` unavailable: `CRITICAL_REVIEW_BLOCKED`.

Auditor failure, auth failure, timeout, or missing response is not approval.

## Commit Pinning

Every audit must identify the exact audited commit SHA. Approval of commit A does not approve commit B. Any relevant change after audit creates a new HEAD and requires re-audit according to scope.

## Audit Package

Include only relevant evidence:

- Task id and task/spec section.
- Exact commit SHA.
- Relevant diff.
- Tests, commands, outputs, and exit codes.
- Invariants and acceptance criteria.
- Prior finding when requesting re-audit.

For critical review, include the primary finding and instruct `critical_auditor` to verify independently.

## Normalized Audit Result

Auditor output may be prose, but it must be normalizable to:

```json
{
  "verdict": "APPROVED | FIX_REQUIRED | ARCHITECTURE_STOP",
  "severity": "NONE | LOW | MEDIUM | HIGH | CRITICAL",
  "task_id": "string",
  "audited_commit": "sha",
  "findings": []
}
```

Do not proceed unless these fields are unambiguous.

## Limits

This skill does not authorize push, merge, release, or deploy. Those actions require separate authorization.

`ARCHITECTURE_STOP`, unresolved critical findings, unresolved material disagreement, and auditor unavailability block progress.
