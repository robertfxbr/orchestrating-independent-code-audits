# orchestrating-independent-code-audits

A process skill for software work where the implementer must not approve its own code, plus a Python bridge that enforces part of it.

The repository has two layers, and they promise different things:

- **The skill** ([`SKILL.md`](SKILL.md)) defines canonical roles for implementation, primary audit, critical audit and architecture ruling. It is provider-agnostic: the roles, not the agent names, drive the flow, and on first use it asks the user which agents fill them.
- **The bridge** ([`scripts/audit_bridge.py`](scripts/audit_bridge.py)) packages evidence, calls an auditor, validates its verdict and gates publication. Today it runs one auditor binding, AGY with Gemini, so provider independence holds for the skill, not yet for the bridge.

[![CI](https://github.com/robertfxbr/orchestrating-independent-code-audits/actions/workflows/ci.yml/badge.svg)](https://github.com/robertfxbr/orchestrating-independent-code-audits/actions/workflows/ci.yml)

## Rejected

What the workflow refuses to do. The cases come from the ten failure scenarios in
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
| Approving past a critical finding | A `CRITICAL` finding or an `architecture_stop` flag routes to `ARCHITECTURE_STOP`, even inside a `TASK_APPROVED` verdict | [critical stop](tests/test_failure_semantics.py#L130) |
| Fixing forever | After three fix attempts the task escalates to high review | [escalation](tests/test_failure_semantics.py#L97) |

### Process rules in `SKILL.md`, not enforced by code

- **Self-approval.** The implementer never approves its own code. The bridge makes approval come from the auditor's verdict, but it does not check who the implementer was.
- **Patching a finding directly.** Every finding is reproduced by a failing regression test before the fix. The bridge records test evidence; it does not verify that a regression test came first.
- **Picking the convenient verdict.** When the primary and critical auditors materially disagree, work stops for a human ruling. The bridge calls one auditor, so it cannot see a disagreement: a critical finding stops the task as `ARCHITECTURE_STOP` for a human, instead of going to a second auditor.
- **Choosing agents for the user.** On first use the skill stops, suggests a binding, and asks which agents to keep, remove or add before writing `.agents/audit-orchestration.yaml`. No code checks this: the bridge does not read that file, and it automates only the primary audit of the suggested binding.
- **Letting one dissenting auditor be outvoted.** With additional auditors, approval needs every configured auditor on the same HEAD. The bridge calls one auditor, so this rule applies only when the audits run through the chosen agents.

## Contract

**In:** a Git worktree, the exact `--base-sha` and `--head-sha`, the frozen spec and the approved plan.

**Out:** an immutable audit package written outside the repository (Git state, diff, test evidence, prompt, raw auditor output) and one routed status:
`PACKAGE_CREATED`, `TASK_APPROVED`, `PR_CREATED`, or a fail-closed stop: `AUDITOR_INFRA_STOP`, `REPOSITORY_SAFETY_STOP`, `ARCHITECTURE_STOP`.
Auditor output that does not match [`schemas/auditor_verdict.schema.json`](schemas/auditor_verdict.schema.json) is rejected, not interpreted.

## Evidence

- 45 tests, 92% line coverage on the bridge, CI on Python 3.11, 3.12 and 3.13 with a 90% coverage floor.
- The shipped example configuration is tested against the binding rules: both required roles bound, no auditor equal to the implementer, merge always with the user.
- Tests drive real Git repositories in temporary directories and replace the auditor CLI and `gh` with fakes, so the suite needs no network, no credentials and no model calls.

What the tests do not prove: the quality of a real model's review, or that the process rules above were followed. They prove that the bridge packages evidence, validates verdicts and gates publication on the paths listed in the table.

## Development

Requires Python 3.11 or newer and Git on `PATH`. The suite needs no network, no credentials and no auditor CLI.

```bash
git clone https://github.com/robertfxbr/orchestrating-independent-code-audits.git
cd orchestrating-independent-code-audits
python -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate
pip install -e ".[test]"
pytest --cov=scripts --cov-report=term-missing
```

CI runs the same command on Python 3.11, 3.12 and 3.13 and fails below 90% coverage.

## The skill

The sections from here to **Limits** describe the process skill. Where the bridge behaves differently, the section says so.

### Install

Copy the skill files into a global agent skills directory:

```powershell
New-Item -ItemType Directory -Force "$env:USERPROFILE\.agents\skills\orchestrating-independent-code-audits"
Copy-Item .\SKILL.md,.\audit-orchestration.example.yaml,.\PRESSURE_TESTS.md "$env:USERPROFILE\.agents\skills\orchestrating-independent-code-audits\"
```

### Configure

There is nothing to configure before first use. When a project has no `.agents/audit-orchestration.yaml`, the skill stops before implementing and walks the user through the bindings:

1. It shows the suggested binding: Codex implements, AGY with Gemini 3.8 Flash Medium audits every task, Claude Opus 5 handles critical findings, escalation and the final audit, GPT-6 Astra (or GPT-5.6 Sol) holds architectural rulings, and the user merges.
2. It asks which agents are installed and signed in, and checks each one that has a command. An agent without a command, such as the ruling model in the suggestion, is manual: the user relays the package and the answer.
3. The user keeps the suggestion, removes optional roles (`critical_auditor`, `ruling_authority`), adds auditors, or rebinds any role. The skill explains what each removal changes and refuses bindings that break independence, such as an implementer that audits itself.
4. After the user confirms, it writes the file, asks whether to commit it, and does not ask again.

The written file has this shape, shown here with the suggested binding ([`audit-orchestration.example.yaml`](audit-orchestration.example.yaml)):

```yaml
# Written by the skill on first use, after the user confirms the bindings.
# The values below are the suggested binding. Every agent can be changed.
version: 1

roles:
  implementer: codex                      # required
  primary_auditor: agy-gemini-medium      # required, must differ from implementer
  critical_auditor: claude-opus-5         # optional: null sends critical findings to ruling_authority
  additional_auditors: []                 # optional: e.g. [claude]; each must approve the same HEAD
  ruling_authority: gpt-6-astra           # optional: or gpt-5.6-sol; null means the user rules
  merge_authority: user                   # always the user

providers:
  codex:
    command: null
  agy-gemini-medium:
    command: agy
    model: Gemini 3.8 Flash (Medium)
  claude-opus-5:
    command: claude
    model: claude-opus-5
  gpt-6-astra:
    command: null                          # manual: the user relays the package and the ruling
    model: GPT-6 Astra

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
  require_additional_auditors_different_from_implementer: true
```

### Roles

- `implementer`: writes RED tests, implements, verifies GREEN/regression, and commits.
- `primary_auditor`: reviews every task independently.
- `critical_auditor`: performs adversarial review for critical findings or always-critical tasks.
- `additional_auditors`: optional extra reviewers; every one must approve the same HEAD.
- `ruling_authority`: decides architectural stops and material disagreement between auditors; the user when unset.
- `merge_authority`: always the user.

### Flow

The implementer works through RED, expected-failure confirmation, minimal implementation, GREEN, regression, commit, and audit package. The primary auditor then returns `APPROVED`, `FIX_REQUIRED`, or a critical finding.

Findings are fixed through TDD: regression test first, RED, fix, GREEN, regression, new commit, re-audit.

Critical escalation calls the critical auditor. If primary and critical auditors agree, the implementer fixes through TDD and requests re-audit. If they materially disagree, the workflow stops for `ARCHITECTURE_RULING_REQUIRED`.

In the bridge: there is no second auditor call. A critical finding, or a verdict that sets `architecture_stop`, routes to `ARCHITECTURE_STOP` for a human ruling, even when the verdict says `TASK_APPROVED`.

### Provider Swapping

The workflow depends on canonical roles, not provider names. A project may bind those roles to any suitable tools or agents as long as independence rules hold.

In the bridge: the auditor binding is AGY with Gemini, set in code. Swapping it today means changing `scripts/audit_bridge.py`.

### Auditor Unavailable

Auditor unavailability never means approval. A configured auditor that cannot run, authenticate or return a valid verdict ends as `AUDITOR_INFRA_STOP`. The skill falls back only to an agent the user listed under `fallbacks`; it never picks a replacement on its own.

### Commit Pinning

Every audit must name the exact commit SHA. Approval of one commit does not approve later HEADs.

### Example Use

Use the skill before a multi-step implementation where independent approval is required. Resolve bindings, verify independence, implement via TDD, commit, package the evidence, and wait for the configured auditor verdict.

### Limits

This skill does not authorize push, merge, release, or deploy. Those actions require separate authorization.

## The bridge

The sections from here on describe `scripts/audit_bridge.py`.

### Deterministic Audit Package

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

### AGY Headless Read-Only Audit

AGY uses Gemini 3.8 Flash Medium for normal task audits and Gemini 3.8 Flash High for escalation and final audits. The High tier is the bridge's own escalation path; it is not the suggested `critical_auditor` (Claude Opus 5), whose audits run outside the bridge. It runs headlessly with sandboxed read-only access, explicit package/repository directories, and strict JSON schema validation. No command permission, edit mode, or dangerous permission bypass is allowed.

```powershell
python -m scripts.audit_bridge audit `
  --phase implementation `
  --task-id task-01 `
  --base-sha <BASE_SHA> `
  --head-sha <HEAD_SHA> `
  --spec-path docs/superpowers/specs/2026-09-06-orchestrating-independent-code-audits-design.md `
  --plan-path docs/superpowers/plans/2026-09-06-orchestrating-independent-code-audits.md
```

### Verdict Semantics

`TASK_APPROVED` applies only to the exact audited HEAD. `FIX_REQUIRED` starts a new RED test and immutable attempt. `AUDITOR_INFRA_STOP`, `REPOSITORY_SAFETY_STOP`, and `ARCHITECTURE_STOP` fail closed.

### Automatic Fix Loop

The implementer follows RED, minimal fix, GREEN, regression, focused commit, package, and independent audit. After three automatic fix attempts, the task escalates to Gemini 3.8 Flash High.

### Final Phase Push and PR

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

### Aurum V1.6 Closeout

The Aurum V1.6 closeout is the first real integration case. `build_aurum_v16_closeout_request` binds the closeout to the audited base `7804af0896d686a3376c2a6d3c3bc3bcb8be7f9d` and the current HEAD, while recording merge-readiness evidence outside the worktree. V1.7 must not begin until the V1.6 merge-readiness evidence is audited against the exact HEAD and the final PR gate is satisfied.
