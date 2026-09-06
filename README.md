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

## Deterministic Audit Package

Runtime evidence is written outside the repository under `%LOCALAPPDATA%\AurumAuditRuntime` by default. Each package is bound to exact `--base-sha` and `--head-sha` values and contains immutable Git, diff, test, prompt, and auditor evidence.

```powershell
python -m scripts.audit_bridge package `
  --phase implementation `
  --task-id task-01 `
  --base-sha <BASE_SHA> `
  --head-sha <HEAD_SHA> `
  --spec-path docs/superpowers/specs/2026-09-06-orchestrating-independent-code-audits-design.md `
  --plan-path docs/superpowers/plans/2026-09-06-orchestrating-independent-code-audits.md
```

## AGY Headless Read-Only Audit

AGY uses Gemini 3.8 Flash Medium for normal task audits and Gemini 3.8 Flash High for escalation and final audits. It runs headlessly with sandboxed read-only access, explicit package/repository directories, and strict JSON schema validation. No command permission, edit mode, or dangerous permission bypass is allowed.

```powershell
python -m scripts.audit_bridge audit `
  --phase implementation `
  --task-id task-01 `
  --base-sha <BASE_SHA> `
  --head-sha <HEAD_SHA> `
  --spec-path docs/superpowers/specs/2026-09-06-orchestrating-independent-code-audits-design.md `
  --plan-path docs/superpowers/plans/2026-09-06-orchestrating-independent-code-audits.md
```

## Verdict Semantics

`TASK_APPROVED` applies only to the exact audited HEAD. `FIX_REQUIRED` starts a new RED test and immutable attempt. `AUDITOR_INFRA_STOP`, `REPOSITORY_SAFETY_STOP`, and `ARCHITECTURE_STOP` fail closed.

## Automatic Fix Loop

The implementer follows RED, minimal fix, GREEN, regression, focused commit, package, and independent audit. After three automatic fix attempts, the task escalates to Gemini 3.8 Flash High.

## Final Phase Push and PR

Only final Gemini 3.8 Flash High approval permits push and PR creation:

```powershell
python -m scripts.audit_bridge finalize `
  --phase final `
  --task-id final-closeout `
  --base-sha <BASE_SHA> `
  --head-sha <HEAD_SHA> `
  --spec-path docs/superpowers/specs/2026-09-06-orchestrating-independent-code-audits-design.md `
  --plan-path docs/superpowers/plans/2026-09-06-orchestrating-independent-code-audits.md
```

No merge command is run by this project. The user retains merge authority.

## Aurum V1.6 Closeout

The Aurum V1.6 closeout is the first real integration case. `build_aurum_v16_closeout_request` binds the closeout to the audited base `7804af0896d686a3376c2a6d3c3bc3bcb8be7f9d` and the current HEAD, while recording merge-readiness evidence outside the worktree. V1.7 must not begin until the V1.6 merge-readiness evidence is audited against the exact HEAD and the final PR gate is satisfied.
