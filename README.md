# orchestrating-independent-code-audits

A process skill for software work where the implementer must not approve its own code, plus a Python bridge that enforces most of it.

The repository has two layers, and they promise different things:

- **The skill** ([`SKILL.md`](SKILL.md)) defines canonical roles for implementation, primary audit, critical audit and architecture ruling. It is provider-agnostic: the roles, not the agent names, drive the flow, and on first use it asks the user which agents fill them.
- **The bridge** ([`scripts/audit_bridge.py`](scripts/audit_bridge.py)) reads the bindings the user chose, refuses invalid ones, packages evidence, calls every auditor bound to the phase, validates their verdicts and gates publication. It can call AGY and Claude Code; an agent without a command is treated as manual.

[![CI](https://github.com/robertfxbr/orchestrating-independent-code-audits/actions/workflows/ci.yml/badge.svg)](https://github.com/robertfxbr/orchestrating-independent-code-audits/actions/workflows/ci.yml)

## Rejected

What the workflow refuses to do. The cases come from the eleven failure scenarios in
[`PRESSURE_TESTS.md`](PRESSURE_TESTS.md), written before the rules that prevent them.

### Enforced by the bridge, with a test

| Refused | How the bridge refuses it | Test |
|---|---|---|
| Counting a missing auditor as a pass | An auditor timeout never becomes `TASK_APPROVED`; malformed output is retried twice, then `AUDITOR_INFRA_STOP` | [timeout](tests/test_failure_semantics.py#L85), [malformed output](tests/test_failure_semantics.py#L69) |
| Publishing without final approval | Push and PR creation run only after a final high-review approval; `FIX_REQUIRED` never publishes | [final approval](tests/test_audit_bridge.py#L179), [fix required](tests/test_cli_execution.py#L62) |
| Merging | No merge command exists; a request that is not a final approval is refused with no `git` or `gh` call | [refuses merge](tests/test_audit_bridge.py#L214) |
| Carrying approval forward | A verdict must name the audited HEAD; the final gate rejects a Git state that differs from the audited one | [verdict HEAD](tests/test_verdict_parser.py#L56), [final gate](tests/test_final_identity.py#L9) |
| Auditing a moving target | A dirty worktree or an invalid SHA blocks packaging; a new attempt cannot overwrite earlier evidence | [dirty worktree](tests/test_failure_semantics.py#L18), [invalid SHA](tests/test_failure_semantics.py#L52), [immutable attempts](tests/test_audit_bridge.py#L92) |
| Letting the auditor edit code | AGY runs in plan mode with a sandbox; Claude Code runs in plan mode with only `Read`, `Grep` and `Glob` | [AGY read-only](tests/test_audit_bridge.py#L159), [Claude read-only](tests/test_bindings.py#L184) |
| Approving past a critical finding | A `CRITICAL` finding or an `architecture_stop` flag routes to `ARCHITECTURE_STOP`, even inside a `TASK_APPROVED` verdict | [critical stop](tests/test_failure_semantics.py#L130) |
| Fixing forever | After three fix attempts the task escalates to high review | [escalation](tests/test_failure_semantics.py#L97) |
| Auditing without agreed bindings | `audit`, `escalate` and `finalize` stop with `BINDINGS_REQUIRED` when there is no bindings file, before any auditor runs | [no bindings](tests/test_bindings.py#L312) |
| Bindings that break independence | An implementer that audits itself, a missing primary auditor, merge given to an agent, or a critical auditor equal to the primary without explicit acceptance is `BINDINGS_INVALID` | [invalid bindings](tests/test_bindings.py#L116), [explicit acceptance](tests/test_bindings.py#L124) |
| Outvoting a dissenting auditor | Every auditor bound to the phase runs; one `FIX_REQUIRED` blocks approval, one critical finding stops for a ruling | [dissent](tests/test_bindings.py#L212), [critical from any auditor](tests/test_bindings.py#L225) |
| Sending high-stakes audits to the wrong agent | Escalation and final audits go to `critical_auditor`, or to `primary_auditor` when none is bound | [routing](tests/test_bindings.py#L168), [escalate CLI](tests/test_bindings.py#L327) |
| Starting an audit an auditor cannot finish | Before any audit, each bound auditor is checked without calling a model: installed, signed in (`claude auth status`), and able to use its model (`agy models`). A failed check stops as `AUDITOR_NOT_READY` with the command that fixes it | [signed out blocks](tests/test_bindings.py#L350), [checks](tests/test_preflight.py#L53) |
| Guessing a manual auditor's answer | An auditor without a command stops as `MANUAL_AUDIT_REQUIRED` and leaves the prompt; nothing is called | [manual](tests/test_bindings.py#L233) |

### Process rules in `SKILL.md`, not enforced by code

- **Self-approval.** The implementer never approves its own code. The bridge makes approval come from the auditor's verdict, but it does not check who the implementer was.
- **Patching a finding directly.** Every finding is reproduced by a failing regression test before the fix. The bridge records test evidence; it does not verify that a regression test came first.
- **Choosing agents for the user.** The first-use conversation is the skill's job. The bridge refuses to audit without a bindings file, but it cannot tell whether the user or the agent wrote it.
- **Falling back to a listed agent.** `fallbacks` is part of the file, but the bridge does not switch to a fallback; it stops.
- **Recording a manual verdict.** The bridge stops for a manual auditor, but reading that auditor's answer back into the package is not automated yet.

## Contract

**In:** a Git worktree, the exact `--base-sha` and `--head-sha`, the frozen spec and the approved plan.

**Out:** an immutable audit package written outside the repository (Git state, diff, test evidence, prompt, raw auditor output) and one routed status:
`PACKAGE_CREATED`, `TASK_APPROVED`, `PR_CREATED`, or a fail-closed stop: `AUDITOR_INFRA_STOP`, `REPOSITORY_SAFETY_STOP`, `ARCHITECTURE_STOP`, `BINDINGS_REQUIRED`, `BINDINGS_INVALID`, `AUDITOR_NOT_READY`, `MANUAL_AUDIT_REQUIRED`.
`check-bindings` returns `BINDINGS_VALID`, `AUDITOR_NOT_READY`, `BINDINGS_INVALID` or `BINDINGS_REQUIRED`, with each auditor's status and the fix for every problem.
Auditor output that does not match [`schemas/auditor_verdict.schema.json`](schemas/auditor_verdict.schema.json) is rejected, not interpreted.

## Evidence

- 90 tests, 94% line coverage on the bridge, CI on Python 3.11, 3.12 and 3.13 with a 90% coverage floor.
- The shipped example configuration is tested against the binding rules: both required roles bound, no auditor equal to the implementer, merge always with the user.
- Tests drive real Git repositories in temporary directories and replace the auditor CLIs and `gh` with fakes, so the suite needs no network, no credentials and no model calls. The Claude Code result shape the fakes return was taken from one real `claude --print --output-format json --json-schema` call.

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
  accept_critical_same_as_primary: false   # true only if the user accepts a non-independent second opinion
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

In the bridge: `escalate` and `finalize` call `critical_auditor`. A critical finding or an `architecture_stop` flag from any auditor routes to `ARCHITECTURE_STOP` for a ruling, even when another auditor approved.

### Provider Swapping

The workflow depends on canonical roles, not provider names. A project may bind those roles to any suitable tools or agents as long as independence rules hold.

In the bridge: swapping agents is a change to `.agents/audit-orchestration.yaml`. The bridge has adapters for `agy` and `claude`; any other command is refused as `BINDINGS_INVALID` until an adapter exists.

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

### Bindings

`audit`, `escalate` and `finalize` read `.agents/audit-orchestration.yaml` from the audited worktree, or the file passed with `--bindings`, then check the auditors of that phase before calling any of them. Run the same check for every auditor before the first audit:

```bash
python -m scripts.audit_bridge check-bindings --bindings .agents/audit-orchestration.yaml
```

### Auditor Adapters

| Command | Invocation | Read-only by |
|---|---|---|
| `agy` | `agy --model <model> --mode plan --sandbox --add-dir <package> --add-dir <worktree> --output-format json --json-schema <schema file> --print <prompt>` | plan mode and sandbox |
| `claude` | `claude --print <prompt> --model <model> --output-format json --json-schema <schema> --permission-mode plan --tools Read,Grep,Glob --add-dir <package> --add-dir <worktree>` | plan mode and a read-only tool list |
| `null` | nothing is called; the prompt is written to the package and the bridge stops as `MANUAL_AUDIT_REQUIRED` | the user relays it |

Readiness checks, run before every audit and by `check-bindings`, never send a prompt:

| Command | Check | Not ready means | Fix shown to the user |
|---|---|---|---|
| any | on `PATH` | `NOT_INSTALLED` | install it and confirm with `<command> --version` |
| `claude` | `claude auth status` reports `loggedIn: true` | `NOT_SIGNED_IN` | `claude auth login` |
| `agy` | `agy models` succeeds | `NOT_SIGNED_IN` | open `agy` and complete sign-in |
| `agy` | the bound model is in `agy models` | `MODEL_UNAVAILABLE` | pick a listed model in the bindings file |

The results are saved as `preflight.json` in the package. Only the signed-in flag is read from `claude auth status`; the account email is not stored.

Each auditor's prompt and raw output are kept as `auditor-<agent>-prompt.txt` and `auditor-<agent>-raw-output.txt`, and the raw outputs feed the package ID.

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

The implementer follows RED, minimal fix, GREEN, regression, focused commit, package, and independent audit. After three automatic fix attempts, the status is `ESCALATE_TO_HIGH_REVIEW`; run `escalate` to send the package to `critical_auditor`.

### Final Phase Push and PR

Only a final approval from `critical_auditor` (or `primary_auditor` when none is bound), plus every additional auditor, permits push and PR creation:

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
`--bindings` points to a bindings file outside the worktree.

No merge command is run by this project. The user retains merge authority.

### Aurum V1.6 Closeout

The Aurum V1.6 closeout is the first real integration case. `build_aurum_v16_closeout_request` binds the closeout to the audited base `7804af0896d686a3376c2a6d3c3bc3bcb8be7f9d` and the current HEAD, while recording merge-readiness evidence outside the worktree. V1.7 must not begin until the V1.6 merge-readiness evidence is audited against the exact HEAD and the final PR gate is satisfied.
