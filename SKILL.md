---
name: orchestrating-independent-code-audits
description: Use when implementing multi-step software changes that require independent review, critical escalation, or provider-swappable coding and audit roles.
---

# Orchestrating Independent Code Audits

This skill governs multi-step implementation with an independent AGY audit after every focused commit.

## Roles and Authority

- Codex is the implementer.
- AGY / Gemini 3.8 Flash Medium is the default independent task auditor.
- AGY / Gemini 3.8 Flash High is the escalation and final-phase auditor.
- ChatGPT is architectural arbiter only.
- The human user retains merge authority.

The implementer cannot approve its own work, replace AGY with self-review, or silently change the frozen spec.

## Required TDD Loop

Every task follows: RED observed -> minimal implementation -> GREEN -> regression -> focused commit -> deterministic audit package -> independent audit.

`TASK_APPROVED` advances only for the exact audited HEAD. `FIX_REQUIRED` creates a new RED for the finding, a minimal fix, a new immutable attempt, and re-audit. `MAX_AUTOMATIC_FIX_ATTEMPTS = 3`; after that, escalate to Gemini High.

## Audit Package

The bridge records exact base/head/tree identity, manifest, Git status and log, separated production/test/contract diffs, test output, TDD evidence, prompt, raw auditor output, normalized verdict, and a deterministic package ID. Runtime artifacts are outside the worktree. Every attempt is immutable.

## Auditor Verdict Contract

AGY runs headlessly with read-only sandbox access, explicit package/repository directories, strict JSON schema validation, and no `command(*)`, `--dangerously-skip-permissions`, or edit mode. The normalized verdict is `TASK_APPROVED`, `FIX_REQUIRED`, or `ARCHITECTURE_STOP`.

## Stop Taxonomy

- `AUDITOR_INFRA_STOP`: AGY cannot reliably run, authenticate, return output, or satisfy the schema after bounded retries.
- `REPOSITORY_SAFETY_STOP`: dirty or mismatched Git state, invalid SHAs, unsafe runtime placement, or other evidence hazards.
- `ARCHITECTURE_STOP`: frozen contract, protected golden/fingerprint, or architectural meaning requires a ruling.

Stops fail closed. No normal task advances through a stop.

## Protected Contracts

Frozen specs, approved contract-bearing plans, scientific identity goldens, and historical fingerprints are protected. A protected contract change is `ARCHITECTURE_STOP`; passing tests never override it.

## Test Anti-Gaming

Modified, deleted, and new tests are surfaced separately. Removing assertions, weakening expected values, deleting contract coverage, or silently rebaselining fingerprints is a finding. A finding must be reproduced by a regression test before the fix is accepted.

## Final Push and PR Policy

Only a final AGY Gemini High approval on the exact HEAD permits `git push` and PR creation. The gate never runs merge, auto-merge, force-push, rebase, or squash commands. Merge is never automatic.

## Aurum V1.6 Closeout

Aurum V1.6 closeout is the first real integration case. Its closeout must use the same immutable package, exact HEAD binding, independent final audit, stop taxonomy, and push-plus-PR gate.
