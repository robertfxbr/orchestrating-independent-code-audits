# Orchestrating Independent Code Audits — Design Specification

**Status:** DRAFT FOR HUMAN REVIEW  
**Date:** 2026-09-06  
**Repository:** `robertfxbr/orchestrating-independent-code-audits`  
**Scope:** reusable Codex ↔ AGY/Gemini independent-audit orchestration  
**Primary workflow:** fully automatic task loop, human-controlled merge

---

## 1. Purpose

This project defines a reusable skill and deterministic audit bridge for development workflows where:

- **Codex** is the implementer.
- **AGY / Gemini 3.8 Flash Medium** is the default independent task auditor.
- **AGY / Gemini 3.8 Flash High** is the escalation and final-phase auditor.
- **ChatGPT** acts only as architectural arbiter when a frozen contract or architecture must be reconsidered.
- The **human user** retains merge authority.

The goal is to make implementation and audit loops automatic while keeping the auditor read-only and independent from the implementer's narrative.

The system must not depend on UI interaction.

---

## 2. Operating Model

### 2.1 Default loop

```text
TASK_READY
  ↓
CODEX_TDD
  ↓
LOCAL_VERIFY
  ↓
COMMIT_TASK
  ↓
BUILD_AUDIT_PACKAGE
  ↓
AGY_MEDIUM_AUDIT
  ├── TASK_APPROVED
  │      ↓
  │   NEXT_TASK
  │
  ├── FIX_REQUIRED
  │      ↓
  │   CODEX_RED_FOR_FINDING
  │      ↓
  │   FIX + TEST + COMMIT
  │      ↓
  │   NEW_ATTEMPT
  │      ↓
  │   AGY_REAUDIT
  │
  └── ARCHITECTURE_STOP
         ↓
      STOP_ALL
         ↓
      CHATGPT_ARCHITECT
```

### 2.2 Phase closeout

```text
ALL_TASKS_APPROVED
  ↓
FINAL_REGRESSION
  ↓
FINAL_AUDIT_PACKAGE
  ↓
AGY_HIGH_FINAL_AUDIT
  ↓
MERGE_READINESS = READY
  ↓
CODEX PUSHES BRANCH
  ↓
CODEX CREATES PR
  ↓
STOP
  ↓
HUMAN AUTHORIZES MERGE
```

Automatic merge is explicitly out of scope.

---

## 3. Roles and Authority

### 3.1 Codex — Implementer

Codex may:

- modify implementation code;
- add and modify tests;
- run tests and deterministic checks;
- commit local task work;
- fix auditor findings using TDD;
- invoke the audit bridge;
- push an approved phase branch;
- create an approved pull request.

Codex may not:

- substitute self-review for AGY;
- ignore an AGY finding;
- alter normalized auditor verdict files;
- weaken tests merely to achieve GREEN;
- silently change frozen specifications;
- silently rebaseline historical fingerprints or goldens;
- force-push;
- merge;
- bypass an `ARCHITECTURE_STOP`;
- bypass an `AUDITOR_INFRA_STOP`;
- bypass a `REPOSITORY_SAFETY_STOP`.

Task completion is not established by Codex claiming completion.

A task is complete only when deterministic checks pass and an independent AGY audit returns `TASK_APPROVED`.

### 3.2 AGY / Gemini — Independent Auditor

Default task auditor:

```text
Gemini 3.8 Flash Medium
```

Escalation and final-phase auditor:

```text
Gemini 3.8 Flash High
```

AGY is read-only.

AGY may:

- read the frozen spec;
- read the approved implementation plan;
- read the deterministic audit package;
- read the actual changed files at HEAD;
- evaluate code, tests, contracts, and evidence;
- return a structured verdict.

AGY may not:

- edit source code;
- create patches;
- write project files;
- execute arbitrary shell commands;
- run Git mutations;
- implement fixes;
- alter Git state.

AGY must audit evidence rather than the implementer's prose explanation.

### 3.3 ChatGPT — Architectural Arbiter

ChatGPT is not part of the normal implementation loop.

Escalate to ChatGPT only when:

- the frozen spec may need to change;
- a scientific or architectural contract is ambiguous or incompatible;
- a new contract vocabulary appears necessary;
- an existing hard invariant cannot be preserved;
- a disputed HIGH/CRITICAL finding remains unresolved after stronger independent review.

### 3.4 Human User

The human user:

- approves architecture/specification changes;
- authorizes merge;
- may stop or override automation at any time.

Push and PR creation may be automatic after final approval.

Merge is never automatic.

---

## 4. Repository Structure

Target structure:

```text
orchestrating-independent-code-audits/
├── SKILL.md
├── README.md
├── scripts/
│   └── audit_bridge.py
├── schemas/
│   └── auditor_verdict.schema.json
├── prompts/
│   ├── task_audit.md
│   ├── escalation_audit.md
│   └── final_phase_audit.md
├── tests/
│   ├── test_audit_bridge.py
│   ├── test_verdict_parser.py
│   └── test_failure_semantics.py
└── docs/
    └── superpowers/
        └── specs/
            └── 2026-09-06-orchestrating-independent-code-audits-design.md
```

The skill is the policy.

The bridge is the deterministic evidence and orchestration helper.

The prompts define auditor behavior.

The JSON schema defines the machine-readable verdict contract.

---

## 5. Audit Runtime Isolation

Audit runtime artifacts must not dirty the scientific or implementation worktree.

Default runtime root:

```text
%LOCALAPPDATA%\AurumAuditRuntime\
```

The root must be configurable for reuse outside Aurum.

Example:

```text
%LOCALAPPDATA%\AurumAuditRuntime\
  robertfxbr_Aurum-Brain\
    v1.7\
      task-03\
        attempt-01\
```

The implementation repository should only receive audit artifacts when an approved project-specific specification explicitly requires durable evidence to be committed.

---

## 6. Audit Attempt Identity

Every audit attempt is bound to exact repository and contract state.

The bridge records at minimum:

```text
phase
task_id
attempt
repository
worktree
branch
base_sha
head_sha
tree_sha
spec_path
spec_sha256
plan_path
plan_sha256
```

Once an audit package is generated, that attempt is immutable.

If HEAD changes:

```text
old attempt remains historical
new attempt is mandatory
new evidence is generated
new audit is required
```

An approval is valid only for the exact HEAD and evidence set that was audited.

---

## 7. Deterministic Audit Package

Codex supplies only the minimum orchestration inputs, such as:

```text
phase
task_id
base_sha
head_sha
spec_path
plan_path
```

The bridge derives repository evidence directly from Git.

The implementer does not choose which changed files are disclosed.

Per-attempt package:

```text
manifest.json
task.md
git-status.txt
git-log.txt
commit.json
files-changed.json
diff.patch
production_diff.patch
test_diff.patch
contract_diff.patch
test-summary.json
test-output.txt
tdd-evidence.md
agy-prompt.txt
agy-raw-output.txt
auditor-verdict.json
bridge-result.json
```

The bridge obtains evidence using deterministic read operations such as:

```text
git rev-parse
git status
git diff
git diff --name-status
git log
git show
```

The exact command set may be adjusted during implementation, but the resulting evidence must be reproducible from the declared Git state.

---

## 8. Auditor Input Policy

AGY must receive:

- frozen spec;
- approved task/plan;
- manifest;
- full diff;
- separated production/test/contract diffs where applicable;
- test evidence;
- all changed scientific/source/test files at HEAD.

The auditor must not rely only on `diff.patch`.

For every changed source, scientific, or test file, the auditor should inspect the current HEAD version when context is required.

The AGY prompt must explicitly prohibit shell and writes.

Required posture:

```text
You are an independent READ-ONLY code auditor.

DO NOT:
- execute shell commands;
- use command tools;
- write files;
- modify source code;
- create patches;
- fix findings;
- alter Git state.

Use read_file only.

Audit the actual provided:
- frozen spec;
- approved implementation plan;
- deterministic audit manifest;
- Git diff;
- changed source files;
- test evidence.

Return only the required verdict JSON.
```

The bridge must not use:

```text
--dangerously-skip-permissions
--mode=accept-edits
```

The AGY process should be launched from the intended worktree rather than depending on a `--cwd` flag.

---

## 9. Auditor Verdict Contract

Top-level verdicts:

```text
TASK_APPROVED
FIX_REQUIRED
ARCHITECTURE_STOP
```

Infrastructure failures are represented separately by the bridge:

```text
AUDITOR_FAILURE
AUDITOR_INFRA_STOP
REPOSITORY_SAFETY_STOP
```

Required normalized audit result:

```json
{
  "verdict": "TASK_APPROVED",
  "spec_compliance": "APPROVED",
  "code_quality": "APPROVED",
  "test_evidence": "PASS",
  "architecture_stop": false,
  "findings": [],
  "confidence": "MEDIUM"
}
```

Allowed `spec_compliance` values:

```text
APPROVED
CHANGES_REQUIRED
ARCHITECTURE_STOP
```

Allowed `code_quality` values:

```text
APPROVED
CHANGES_REQUIRED
```

Allowed `test_evidence` values:

```text
PASS
INSUFFICIENT
FAIL
```

Each finding must contain enough evidence to reproduce the concern.

Recommended shape:

```json
{
  "id": "F-01",
  "severity": "HIGH",
  "contract": "spec section or task requirement",
  "file": "path/to/file.py",
  "line": 123,
  "evidence": "Observed contract violation.",
  "required_proof": "What must be demonstrated to close the finding."
}
```

The auditor should identify the failed contract and required proof rather than prescribe the implementation in detail.

---

## 10. JSON Validation and Failure Semantics

AGY output is not trusted until validated against the schema.

The bridge must distinguish:

```text
FIX_REQUIRED
```

from:

```text
AUDITOR_FAILURE
```

Examples of `AUDITOR_FAILURE`:

- no output;
- invalid JSON;
- missing required field;
- unknown verdict;
- parser failure;
- timeout;
- AGY non-zero exit;
- permission failure;
- unexpected surrounding output when strict output is required.

An auditor infrastructure failure must never become `TASK_APPROVED`.

Operational retry policy:

```text
MAX_AUDITOR_RETRIES = 2
```

No code changes may occur between infrastructure retries.

If retries are exhausted:

```text
AUDITOR_INFRA_STOP
```

---

## 11. Finding Severity and Escalation

### LOW

Examples:

- style;
- clarity;
- minor defensive validation;
- documentation quality;
- redundant or missing narrow test.

Flow:

```text
Codex fixes via TDD
→ AGY Medium reaudits
```

### MEDIUM

Examples:

- localized functional bug;
- edge case;
- local determinism issue;
- path-safety issue;
- schema validation defect;
- persistence bug without identity impact.

Flow:

```text
Codex fixes via TDD
→ AGY Medium reaudits
```

### HIGH

Examples:

- identity/hash;
- causal behavior;
- state isolation;
- lifecycle/authorization;
- scientific fingerprint;
- stable identifier;
- canonical runner integration;
- decision gate;
- legacy behavior;
- acceptance/evidence semantics.

Flow:

```text
Codex fixes via TDD if contract is unambiguous
→ AGY Medium reaudits
→ AGY High performs mandatory second pass
```

### CRITICAL

Examples:

- frozen spec must change;
- second Runner would be required;
- second fill/state machine would be required;
- historical identifier semantics must change;
- historical fingerprint must change;
- historical causal behavior must change;
- new contract vocabulary is required;
- Decision Gate semantics must change;
- legacy path becomes incompatible.

Flow:

```text
ARCHITECTURE_STOP
```

Do not automatically implement around a CRITICAL contract issue.

---

## 12. Automatic Fix Loop

For `FIX_REQUIRED`:

```text
finding
→ Codex creates/reproduces RED
→ minimal corrective implementation
→ focused tests GREEN
→ broader regression
→ new commit
→ new audit attempt
→ AGY reaudits
```

Prior attempts remain immutable.

Example:

```text
attempt-01 → FIX_REQUIRED
attempt-02 → FIX_REQUIRED
attempt-03 → TASK_APPROVED
```

Automatic fix limit:

```text
MAX_AUTOMATIC_FIX_ATTEMPTS = 3
```

If the same finding remains unresolved after three attempts:

```text
ESCALATE_TO_HIGH_REVIEW
```

Do not continue producing increasingly speculative patches.

---

## 13. Disputed Findings

Codex may disagree with an AGY finding, but may not ignore it.

Flow:

```text
DISPUTED_FINDING
→ AGY High independent review
```

If High resolves the dispute, follow the High ruling.

If still materially ambiguous:

```text
NEEDS_ARCHITECTURE_REVIEW
→ ARCHITECTURE_STOP
→ ChatGPT
```

The auditor is not made authoritative merely by being the auditor; unresolved contract ambiguity belongs to architecture.

---

## 14. Protected Contract Files

Each phase may declare:

```text
PROTECTED_CONTRACT_FILES
```

Examples:

- frozen specification;
- architecture freeze document;
- scientific identity goldens;
- historical fingerprints;
- approved contract-bearing plan sections.

If Codex modifies a protected contract file during a normal implementation task:

```text
PROTECTED_CONTRACT_CHANGED
→ ARCHITECTURE_STOP
```

Passing tests do not override this rule.

---

## 15. Test Anti-Gaming Rules

Tests are classified as:

```text
NEW_TEST
MODIFIED_EXISTING_TEST
DELETED_TEST
```

### New tests

Allowed and expected under TDD.

### Modified existing tests

The auditor must verify that the change strengthens, corrects, or legitimately adapts the test without weakening the frozen contract.

### Deleted tests

Default severity:

```text
HIGH
```

Deletion requires explicit justification and stronger review.

### Historical regression tests

Tests protecting items such as:

- identity goldens;
- historical fingerprints;
- causality fixtures;
- Decision Gate semantics;
- stable legacy behavior;

must not be silently rebaselined.

A changed expected value in such a test is a hard stop unless a previously approved architectural ruling explicitly authorizes it.

---

## 16. Test Weakening Detection

The auditor should explicitly inspect for:

- removed assertions;
- reduced assertion specificity;
- exact comparison changed to approximate comparison;
- newly added `skip`;
- newly added `xfail`;
- widened thresholds;
- weakened fixtures;
- removed test cases;
- updated golden values;
- expected fingerprint replacement.

If detected:

```text
TEST_WEAKENING
```

The normal resolution is to restore contract coverage.

If the weakening is genuinely necessary because the contract changed:

```text
ARCHITECTURE_STOP
```

---

## 17. Hard Stops

The following conditions override ordinary severity:

```text
historical fingerprint changed
historical stable identifier changed
legacy scientific behavior changed
Decision Gate regression
future-data leak detected
unexpected scientific artifact rewrite
protected contract modified
wrong worktree
wrong branch
unexpected dirty state affecting evidence
audited HEAD changed after approval
destructive Git operation required
merge requested automatically
```

These must become either:

```text
REPOSITORY_SAFETY_STOP
```

or:

```text
ARCHITECTURE_STOP
```

depending on whether the issue is operational or contractual.

Never silently:

```text
update expected
rebaseline
accept new fingerprint
```

---

## 18. Stop Taxonomy

### FIX_REQUIRED

Implementation defect within an unambiguous contract.

Normal autonomous repair is allowed.

### AUDITOR_INFRA_STOP

The independent auditor could not run reliably.

Examples:

- repeated AGY timeout;
- repeated permission failure;
- repeated invalid output;
- missing AGY executable/model.

No architectural escalation is required by default.

### REPOSITORY_SAFETY_STOP

Repository state makes the evidence or requested operation unsafe.

Examples:

- unexpected dirty worktree;
- SHA mismatch;
- wrong worktree;
- wrong branch;
- unexpected tracked runtime artifacts;
- destructive Git cleanup would be required.

Do not silently mutate the repository to clear this stop.

### ARCHITECTURE_STOP

A frozen contract or architecture requires a human architectural ruling.

All implementation, push, and PR activity stops.

---

## 19. Architecture Stop Artifact

When an `ARCHITECTURE_STOP` occurs, generate:

```text
architecture-stop-<task>.md
```

Required fields:

```text
ARCHITECTURE_STOP

TASK:
BASE_SHA:
HEAD_SHA:

CONTRACT:
<spec section>

OBSERVED:
<what the repository requires>

WHY_THIS_IS_NOT_A_NORMAL_BUG:
<reason>

WHY_MINIMAL_ADAPTATION_IS_INSUFFICIENT:
<reason>

IMPACT:
- identity
- fingerprints
- runner
- gate
- causal semantics
- legacy behavior
- other relevant contracts

OPTIONS:
A.
B.

RECOMMENDATION:
<optional>

IMPLEMENTATION_STATUS:
STOPPED
```

After a ruling, record:

```text
architecture-ruling.md
```

Implementation may resume only after the ruling is approved and incorporated into the authoritative contract source where necessary.

---

## 20. Audit Provenance

Codex must not author the normalized auditor verdict.

The evidence chain is:

```text
AGY stdout
→ raw output captured by bridge
→ schema validation
→ normalized verdict
```

The bridge may calculate an operational package identifier:

```text
audit_package_id =
SHA256(canonical manifest + evidence + raw auditor output)
```

This identifier is operational provenance only and must not alter scientific identity contracts of the target project.

If normalized verdict provenance cannot be established:

```text
AUDIT_PROVENANCE_INVALID
→ STOP
```

---

## 21. Model Policy

Preferred policy:

```text
DEFAULT_AUDITOR_MODEL = Gemini 3.8 Flash Medium
ESCALATION_AUDITOR_MODEL = Gemini 3.8 Flash High
FINAL_PHASE_AUDITOR_MODEL = Gemini 3.8 Flash High
```

The implementation must not assume an unverified AGY CLI model identifier.

The bridge should resolve or validate the actual installed model identifier before execution.

If the requested model is unavailable:

- fail closed;
- report auditor infrastructure failure;
- do not silently downgrade to a weaker model unless the user explicitly configured an allowed fallback.

---

## 22. Git and PR Policy

Codex may automatically:

- create focused local commits;
- push a fully approved phase branch;
- create the pull request.

Codex may not:

- force-push;
- merge;
- enable auto-merge;
- rewrite audited commit history;
- squash audited history unless explicitly approved;
- rebase an already audited final HEAD unless re-audited.

After successful PR creation:

```text
STOP
```

The human user decides merge.

---

## 23. Security Posture

The goal is independent audit isolation, not hostile-code sandboxing.

The design assumes:

- Codex has normal implementation access;
- the bridge has narrowly scoped deterministic shell access;
- AGY has read-only file access;
- AGY does not receive arbitrary command execution permission.

The system must not require `command(*)` for AGY.

The system must not depend on `--dangerously-skip-permissions`.

---

## 24. Reusability

Although initially motivated by Aurum Research Lab, the skill must remain generic.

Project-specific items must be supplied through configuration or task context, including:

- protected contract files;
- historical fingerprints;
- goldens;
- required regression commands;
- special hard-stop conditions;
- final phase evidence requirements.

The skill must not hardcode Aurum scientific contracts.

---

## 25. First Real Use — Aurum V1.6 Closeout

Known state at design time:

```text
AUDITED_HEAD =
7804af0896d686a3376c2a6d3c3bc3bcb8be7f9d

AUDITED_COMMIT_EXISTS = YES
LOCAL_BRANCH_AT_AUDITED_HEAD = YES
VERIFY_STATUS_CLEAN = YES
REMOTE_BRANCH_EXISTS = NO
MERGE_READINESS_DOC_HEAD_MATCH = NO
SCIENTIFIC_REAUDIT_REQUIRED = NO
OPERATIONAL_CLOSEOUT_BLOCKED = YES
```

The first real use should be:

```text
V1.6 CLOSEOUT AUDIT
```

The objective is to identify why the merge-readiness document does not match the audited HEAD.

### Scenario A — stale documentation only

If the scientific implementation remains exactly the audited implementation:

```text
correct documentation
→ new HEAD
→ independent AGY audit of documentation delta and provenance relation
→ final closeout audit
→ push
→ create PR
→ STOP before merge
```

The existing scientific audit is not discarded merely because documentation is stale.

### Scenario B — closeout document exposes a substantive mismatch

If the mismatch indicates that the claimed audited scientific closure does not correspond to the actual audited HEAD:

```text
REPOSITORY_SAFETY_STOP
```

Investigate before publishing any branch.

V1.7 must not begin until V1.6 operational closeout is resolved and merged.

---

## 26. Interaction with Aurum V1.7

After V1.6 merge, the Aurum handoff should reflect:

```text
1.4 Genome / Setup Registry ✅ CLOSED
1.5 Evolution Engine         ✅ CLOSED
1.6 Boss Benchmark           ✅ CLOSED
1.7 Audit Workflow           ⬜ NEXT
```

Aurum V1.7 may later formalize some of the ideas in this generic skill as project-specific audit workflow.

The generic skill should remain reusable and external to Aurum-specific scientific identity.

---

## 27. Non-Goals

This version does not attempt to provide:

- autonomous merge;
- RBAC;
- cryptographic code signing;
- malicious-code sandboxing;
- remote distributed workers;
- CI platform replacement;
- UI dashboard;
- LLM-based implementation by the auditor;
- automatic rewriting of frozen specs;
- automatic approval of new scientific baselines.

---

## 28. Definition of Done for the Skill

The skill is ready for real use when all of the following are demonstrated:

1. `SKILL.md` clearly assigns implementer/auditor/architect/human roles.
2. The bridge creates a deterministic audit package from `BASE_SHA` and `HEAD_SHA`.
3. Runtime evidence is created outside the target worktree by default.
4. AGY runs headlessly without write permission and without arbitrary command permission.
5. Gemini 3.8 Flash Medium is usable as default task auditor.
6. Gemini High is usable for escalation/final audit.
7. Auditor output is validated against a strict JSON schema.
8. Invalid/no-output/timeouts fail closed.
9. `FIX_REQUIRED` triggers a new immutable attempt.
10. HEAD changes invalidate prior task approval for completion purposes.
11. Protected contract changes cause `ARCHITECTURE_STOP`.
12. Historical golden/fingerprint rebaselining cannot pass silently.
13. Modified/deleted tests are surfaced to the auditor.
14. Test weakening patterns are explicitly reviewed.
15. `MAX_AUTOMATIC_FIX_ATTEMPTS = 3` is enforced.
16. Repeated auditor infrastructure failure produces `AUDITOR_INFRA_STOP`.
17. Unsafe repository state produces `REPOSITORY_SAFETY_STOP`.
18. `ARCHITECTURE_STOP` produces a structured escalation artifact.
19. Codex cannot substitute its own prose review for AGY approval.
20. Final phase approval permits push + PR creation but never merge.
21. A real Aurum V1.6 closeout audit can run through the workflow without dirtying the verified worktree.

---

## 29. Approved Design Decisions

The following decisions were explicitly selected during design:

- **Automation mode:** fully automatic task loop.
- **Git authority:** Codex may push and create PR after final approval; merge requires human approval.
- **Default auditor:** AGY / Gemini 3.8 Flash Medium.
- **Escalation/final auditor:** AGY / Gemini 3.8 Flash High.
- **ChatGPT role:** architectural arbiter only.
- **Auditor permissions:** read-only, no arbitrary shell.
- **Evidence source:** deterministic Git-derived audit package plus actual changed files.
- **Audit runtime:** outside target worktree by default.
- **Automatic correction:** permitted for unambiguous implementation findings through TDD.
- **Maximum automatic correction attempts:** 3.
- **High-risk review:** stronger independent second pass.
- **Architecture changes:** hard stop.
- **Merge:** never automatic.

---

## 30. Next Step

After human review and approval of this written specification:

1. create a TDD implementation plan;
2. implement the skill and bridge in the dedicated repository;
3. validate the bridge and verdict failure semantics;
4. prove AGY headless read-only operation;
5. use Aurum V1.6 closeout as the first real integration case.

No implementation should begin before this written specification is approved.
