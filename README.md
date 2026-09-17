# orchestrating-independent-code-audits

A process skill for software work where the implementer must not approve its own code, plus a Python bridge that enforces part of it.

The repository has two layers, and they promise different things:

- **The skill** ([`SKILL.md`](SKILL.md)) defines canonical roles for implementation, primary audit, critical audit and architecture ruling. It is provider-agnostic: the roles, not the agent names, drive the flow.
- **The bridge** ([`scripts/audit_bridge.py`](scripts/audit_bridge.py)) packages evidence, calls an auditor, validates its verdict and gates publication. Today it runs one auditor binding, AGY with Gemini, so provider independence holds for the skill, not yet for the bridge.

[![CI](https://github.com/robertfxbr/orchestrating-independent-code-audits/actions/workflows/ci.yml/badge.svg)](https://github.com/robertfxbr/orchestrating-independent-code-audits/actions/workflows/ci.yml)

## Rejected

What the workflow refuses to do. The cases come from the seven failure scenarios in
[`PRESSURE_TESTS.md`](PRESSURE_TESTS.md), written before the rules that prevent them.

### Enforced by the bridge, with a test

| Refused | How the bridge refuses it | Test |
|---|---|---|
| Counting a missing auditor as a pass | An auditor timeout never becomes `TASK_APPROVED`; malformed output is retried twice, then `AUDITOR_INFRA_STOP` | [timeout](tests/test_failure_semantics.py#L85), [malformed output](tests/test_failure_semantics.py#L69) |
| Publishing without final approval | Push and PR creation run only after a final high-review approval; `FIX_REQUIRED` never publishes | [final approval](tests/test_audit_bridge.py#L179), [fix required](tests/test_cli_execution.py#L62) |
| Merging | No merge command exists; a request that is not a final approval is refused with no `git` or `gh` call | [refuses merge](tests/test_audit_bridge.py#L214) |
| Carrying approval forward | A verdict must name the audited HEAD; the final gate rejects a Git state that differs from the audited one | [verdict HEAD](tests/test_verdict_parser.py#L56), [final gate](tests/test_final_identity.py#L9) |
| Auditing a moving target | A dirty worktree or an invalid SHA blocks packaging; a new attempt cannot overwrite earlier evidence | [dirty worktree](tests/test_failure_semantics.py#L18), [invalid SHA](tests/test_failure_semantics.py#L52), [immutable attempts](tests/test_audit_bridge.py#L92) |
| Letting the auditor edit code | The auditor runs read-only and the invocation never accepts edits | [read-only](tests/test_audit_bridge.py#L159) |
| Fixing forever | After three fix attempts the task escalates to high review | [escalation](tests/test_failure_semantics.py#L97) |

### Process rules in `SKILL.md`, not enforced by code

- **Self-approval.** The implementer never approves its own code. The bridge makes approval come from the auditor's verdict, but it does not check who the implementer was.
- **Patching a finding directly.** Every finding is reproduced by a failing regression test before the fix. The bridge records test evidence; it does not verify that a regression test came first.
- **Picking the convenient verdict.** When the primary and critical auditors materially disagree, work stops for a human ruling. The bridge calls one auditor, so it cannot see a disagreement: a critical finding stops the task as `ARCHITECTURE_STOP` for a human, instead of going to a second auditor.
- **Workflow logic that depends on a provider.** Swapping which agent implements and which audits is a configuration change in the skill. In the bridge it would be a code change.

## Contract

**In:** a Git worktree, the exact `--base-sha` and `--head-sha`, the frozen spec and the approved plan.

**Out:** an immutable audit package written outside the repository (Git state, diff, test evidence, prompt, raw auditor output) and one routed status:
`PACKAGE_CREATED`, `TASK_APPROVED`, `PR_CREATED`, or a fail-closed stop: `AUDITOR_INFRA_STOP`, `REPOSITORY_SAFETY_STOP`, `ARCHITECTURE_STOP`.
Auditor output that does not match [`schemas/auditor_verdict.schema.json`](schemas/auditor_verdict.schema.json) is rejected, not interpreted.

## Evidence

- 38 tests, 92% line coverage on the bridge, CI on Python 3.11, 3.12 and 3.13 with a 90% coverage floor.
- Tests drive real Git repositories in temporary directories and replace the auditor CLI and `gh` with fakes, so the suite needs no network, no credentials and no model calls.

What the tests do not prove: the quality of a real model's review, or that the process rules above were followed. They prove that the bridge packages evidence, validates verdicts and gates publication on the paths listed in the table.

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
  --plan-path docs/superpowers/plans/2026-09-06-orchestrating-independent-code-audits.md `
  --pr-title "Independent audit bridge" `
  --pr-body-file <PR_BODY_FILE>
```

Use `--test-output-path` and `--tdd-evidence-path` to include validation evidence.
`--runtime-root` selects an external evidence directory for a new immutable attempt.
The installed AGY model identifiers are `Gemini 3.8 Flash (Medium)` and
`Gemini 3.8 Flash (High)`; these implement the policy labels above without a provider change.

No merge command is run by this project. The user retains merge authority.

## Aurum V1.6 Closeout

The Aurum V1.6 closeout is the first real integration case. `build_aurum_v16_closeout_request` binds the closeout to the audited base `7804af0896d686a3376c2a6d3c3bc3bcb8be7f9d` and the current HEAD, while recording merge-readiness evidence outside the worktree. V1.7 must not begin until the V1.6 merge-readiness evidence is audited against the exact HEAD and the final PR gate is satisfied.
