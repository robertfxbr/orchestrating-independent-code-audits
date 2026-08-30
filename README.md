# orchestrating-independent-code-audits

A provider-agnostic process skill for software work where the implementer must not approve its own code.

It defines canonical roles for implementation, primary audit, critical audit, and architecture ruling, then keeps those roles independent even when the concrete providers change.

## Install

Copy the skill files into a global agent skills directory:

```powershell
New-Item -ItemType Directory -Force "$env:USERPROFILE\.agents\skills\orchestrating-independent-code-audits"
Copy-Item .\SKILL.md,.\audit-orchestration.example.yaml,.\PRESSURE_TESTS.md "$env:USERPROFILE\.agents\skills\orchestrating-independent-code-audits\"
```

## Configure

Projects can define `.agents/audit-orchestration.yaml` using this shape:

```yaml
version: 1

roles:
  implementer: codex
  primary_auditor: gemini
  critical_auditor: claude
  ruling_authority: user

providers:
  codex:
    command: null
  gemini:
    command: null
  claude:
    command: null

critical_policy:
  trigger_on_primary_severity:
    - CRITICAL

  always_critical_tasks: []

fallbacks:
  primary_auditor: null
  critical_auditor: null

independence:
  require_implementer_different_from_primary_auditor: true
  require_critical_auditor_different_from_implementer: true
```

Provider names in the example are illustrative bindings only.

## Roles

- `implementer`: writes RED tests, implements, verifies GREEN/regression, and commits.
- `primary_auditor`: reviews every task independently.
- `critical_auditor`: performs adversarial review for critical findings or always-critical tasks.
- `ruling_authority`: decides when auditors materially disagree.

## Flow

The implementer works through RED, expected-failure confirmation, minimal implementation, GREEN, regression, commit, and audit package. The primary auditor then returns `APPROVED`, `FIX_REQUIRED`, or a critical finding.

Findings are fixed through TDD: regression test first, RED, fix, GREEN, regression, new commit, re-audit.

Critical escalation calls the critical auditor. If primary and critical auditors agree, the implementer fixes through TDD and requests re-audit. If they materially disagree, the workflow stops for `ARCHITECTURE_RULING_REQUIRED`.

## Provider Swapping

The workflow depends on canonical roles, not provider names. A project may bind those roles to any suitable tools or agents as long as independence rules hold.

## Auditor Unavailable

Auditor unavailability never means approval. A missing primary auditor blocks as `TASK_APPROVAL_BLOCKED`; a missing required critical auditor blocks as `CRITICAL_REVIEW_BLOCKED`.

## Commit Pinning

Every audit must name the exact commit SHA. Approval of one commit does not approve later HEADs.

## Example Use

Use the skill before a multi-step implementation where independent approval is required. Resolve bindings, verify independence, implement via TDD, commit, package the evidence, and wait for the configured auditor verdict.

## Limits

This skill does not authorize push, merge, release, or deploy. Those actions require separate authorization.
