---
name: orchestrating-independent-code-audits
description: Use when implementing multi-step software changes that require independent review, critical escalation, or provider-swappable coding and audit roles.
---

# Orchestrating Independent Code Audits

This skill governs multi-step implementation with an independent audit after every focused commit. Behavior is defined by roles. Which agent fills each role is the user's choice, asked on first use and stored in the project.

## First Use: Agree On The Bindings

Before any implementation, look for `.agents/audit-orchestration.yaml` in the project.

- **If it exists and passes the binding rules below**, use it. Do not ask again.
- **If it is missing or invalid**, stop and ask the user. Never assume a binding silently.

Ask in this order:

1. **Show the suggested binding** and say it is only a starting point:

   | Role | Suggested | Required |
   |---|---|---|
   | `implementer` | Codex | yes |
   | `primary_auditor` | AGY with Gemini 3.8 Flash Medium | yes |
   | `critical_auditor` | AGY with Gemini 3.8 Flash High, also used for escalation and final audit | no |
   | `additional_auditors` | none | no |
   | `ruling_authority` | ChatGPT, architectural rulings only | no, defaults to the user |
   | `merge_authority` | the user | always the user |

2. **Ask which agents the user actually has installed and signed in.** A binding to an unavailable agent is not a valid binding.
3. **Offer the three kinds of change:** keep as suggested, remove an optional role, or add auditors. Any role may be bound to a different agent.
4. **Explain the consequence of each removal before accepting it:**
   - Without `critical_auditor`, a critical finding goes straight to `ruling_authority` as `ARCHITECTURE_STOP`, and the final audit is done by `primary_auditor`.
   - Without `ruling_authority`, the user rules on every architectural stop and disagreement.
5. **Validate the answer against the binding rules**, show the resulting file, and write `.agents/audit-orchestration.yaml` only after the user confirms it.

Change the bindings later only when the user asks. A binding that stops working is an `AUDITOR_INFRA_STOP`, not a reason to switch agents: fall back only to an agent the user listed under `fallbacks`.

## Binding Rules

- `implementer` and `primary_auditor` are required.
- `primary_auditor`, `critical_auditor` and every additional auditor must be a different agent from `implementer`.
- `critical_auditor` should differ from `primary_auditor`. The same agent at a higher model tier is allowed only when the user accepts that it is not an independent second opinion.
- `merge_authority` is always the user. No agent can hold it.
- An agent may hold `ruling_authority` only for architectural rulings. It never approves a task and never merges.

## Roles and Authority

- `implementer` writes RED tests, implements, verifies GREEN and regression, and commits. It cannot approve its own work, replace an auditor with self-review, or silently change the frozen spec.
- `primary_auditor` reviews every task independently.
- `critical_auditor` performs adversarial review for critical findings, always-critical tasks, escalation after repeated fixes, and the final phase.
- `additional_auditors` each review every task. Approval requires every configured auditor to approve the same HEAD; any `FIX_REQUIRED` blocks it.
- `ruling_authority` decides architectural stops and material disagreement between auditors.
- `merge_authority` merges. Merge is never automatic.

## Required TDD Loop

Every task follows: RED observed -> minimal implementation -> GREEN -> regression -> focused commit -> deterministic audit package -> independent audit.

`TASK_APPROVED` advances only for the exact audited HEAD. `FIX_REQUIRED` creates a new RED for the finding, a minimal fix, a new immutable attempt, and re-audit. `MAX_AUTOMATIC_FIX_ATTEMPTS = 3`; after that, escalate to `critical_auditor`, or to `ruling_authority` when there is none.

## Audit Package

The bridge records exact base/head/tree identity, manifest, Git status and log, separated production/test/contract diffs, test output, TDD evidence, prompt, raw auditor output, normalized verdict, and a deterministic package ID. Runtime artifacts are outside the worktree. Every attempt is immutable.

## Auditor Verdict Contract

Every auditor runs read-only, with explicit package and repository directories, strict JSON schema validation, and no command execution, permission bypass, or edit mode. The normalized verdict is `TASK_APPROVED`, `FIX_REQUIRED`, or `ARCHITECTURE_STOP`.

## Stop Taxonomy

- `AUDITOR_INFRA_STOP`: a configured auditor cannot reliably run, authenticate, return output, or satisfy the schema after bounded retries.
- `REPOSITORY_SAFETY_STOP`: dirty or mismatched Git state, invalid SHAs, unsafe runtime placement, or other evidence hazards.
- `ARCHITECTURE_STOP`: frozen contract, protected golden/fingerprint, or architectural meaning requires a ruling.

Stops fail closed. No normal task advances through a stop.

## Protected Contracts

Frozen specs, approved contract-bearing plans, scientific identity goldens, and historical fingerprints are protected. A protected contract change is `ARCHITECTURE_STOP`; passing tests never override it.

## Test Anti-Gaming

Modified, deleted, and new tests are surfaced separately. Removing assertions, weakening expected values, deleting contract coverage, or silently rebaselining fingerprints is a finding. A finding must be reproduced by a regression test before the fix is accepted.

## Final Push and PR Policy

Only a final approval on the exact HEAD permits `git push` and PR creation: from `critical_auditor` when configured, otherwise from `primary_auditor`, plus every additional auditor. The gate never runs merge, auto-merge, force-push, rebase, or squash commands.

## Bundled Bridge

`scripts/audit_bridge.py` automates the suggested binding only: AGY with Gemini 3.8 Flash Medium for task audits and Gemini 3.8 Flash High for escalation and final audit. With any other binding, follow the same loop and stops, and run the audits through the chosen agents.

## Aurum V1.6 Closeout

Aurum V1.6 closeout is the first real integration case. Its closeout must use the same immutable package, exact HEAD binding, independent final audit, stop taxonomy, and push-plus-PR gate.
