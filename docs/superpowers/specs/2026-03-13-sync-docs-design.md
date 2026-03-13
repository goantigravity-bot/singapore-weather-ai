# Design Spec: `sync-docs` Skill

**Date**: 2026-03-13
**Status**: Draft
**Purpose**: A Claude Code skill that ensures documentation stays in sync with code changes — invoked after every bug fix or improvement, before committing.

---

## Overview

The `sync-docs` skill reads staged git changes, identifies affected documentation, proposes targeted edits with reasons, waits for user confirmation, then applies and stages the changes. Code fix and doc updates are committed together in a single commit.

**Trigger**: Two ways:
1. **Manual** — developer runs `/sync-docs` after finishing a fix, before committing
2. **Git pre-commit hook** — auto-triggers on `git commit` via a shell script in `.git/hooks/pre-commit`

---

## Phase 1: Analysis

### Step 1 — Guard check
Skip immediately (exit 0) if **all** staged files are under `docs/` — this prevents re-entry when the skill itself stages doc edits and a retry commit is attempted.

### Step 2 — Read staged changes
```bash
git diff --staged
```
Extracts: changed files, added/removed lines, inferred change type.

### Step 3 — Classify the change
| Changed Path | Inferred Type |
|---|---|
| `services/api/backend/` | Bug fix or API improvement |
| `services/training/` | Model or training improvement |
| `services/download/` | Data pipeline fix |
| `db/` | Schema change |
| `infra/` or `tools/` | Infrastructure or tooling change |

### Step 4 — Scan docs in priority order

| Priority | Folder | What it checks |
|---|---|---|
| 1 | `docs/10.requirements/*.md` | Requirements now fulfilled |
| 2 | `docs/20.technicaldesign/*.md` | Structural or component changes |
| 2 | `docs/20.technicaldesign/data-model/*.md` | Data model changes |
| 2 | `docs/20.technicaldesign/db/*.md` | Schema or query changes |
| 3 | `docs/30.model/eda-report.md` | EDA findings without ✅ now addressable |
| 3 | `docs/30.model/improvement-strategy.md` | Pending improvements now implemented |
| 3 | `docs/30.model/model-tuning*.md` | Model architecture or parameter changes |
| 3 | `docs/30.model/training-evaluation*.md` | Training results needing update |
| 3 | `docs/30.model/temporal-satellite-*.md` | Feature design/plan status |
| 4 | `docs/40.test/*.md` | Test and performance report changes |
| 5 | `docs/50.deployment/*.md` | New env vars, cron jobs, infra changes |
| 5 | `docs/50.deployment/integration/*.md` | Integration milestones completed |
| 6 | `docs/60.bugs/*.md` | Open bugs matching changed files → mark Fixed |
| 9 | `docs/90.reports/work-report/*.md` | Notable work items to log |
| 9 | `docs/90.reports/releases/*.md` | Version bump if applicable |
| 9 | `docs/90.reports/presentations/**/*.md` | Presentation docs referencing resolved issues |
| 9 | `docs/90.reports/changelog.md` | **Always updated** — exempt from skip rule (see Constraints) |

> `docs/99.data/` is excluded entirely (in `.gitignore`).

### Step 5 — Produce proposal report

For each affected doc, output:
```
📄 docs/60.bugs/20260306-confidence-null-in-smart-query.md
   WHY:    smart_query.py modified — confidence propagation fix detected in diff
   CHANGE: Update Status "Open" → "Fixed", add ## Resolution section with date + code reference

📄 docs/90.reports/changelog.md
   WHY:    Always updated on every staged change
   CHANGE: Append new entry — [2026-03-13] Fix confidence NULL in smart-query forecast records
```

### Step 6 — Confirmation

After presenting the full proposal, the skill asks:
```
Apply these changes? (yes / no / edit)
```
- `yes` — proceed to Phase 2
- `no` — abort, no files touched
- `edit` — user can specify which docs to include/exclude before proceeding

---

## Phase 2: Apply

Apply changes in priority order (10 → 90):

### Edit types
| Change Type | What is written |
|---|---|
| Bug fixed | `Status: Fixed`, adds `## Resolution` section with date + code file reference |
| EDA finding resolved | Updates table row to ✅, adds resolution callout under the relevant §5 section |
| Improvement completed | Marks item done with date + commit reference |
| Requirement fulfilled | Updates requirement status field |
| Deployment change | Adds/updates step, env var, or config instruction |
| Architecture change | Updates component or data flow description |
| Always | Appends new entry to `docs/90.reports/changelog.md` |

### Per-edit confirmation output
After writing each file, the skill stages it immediately:
```bash
git add <edited-doc-path>
```
Then prints:
```
✅ Updated docs/60.bugs/20260306-confidence-null-in-smart-query.md — Status: Open → Fixed  [staged]
✅ Updated docs/90.reports/changelog.md — New entry added  [staged]
```

### Constraints
- **Surgical edits only** — no full document rewrites
- **No auto-commit** — developer runs `git commit` manually after the skill completes
- **Skip if no connection** — docs with no relevant link to the staged change are not touched; `docs/90.reports/changelog.md` is explicitly exempt from this rule and always updated
- **Guard against re-entry** — if all staged files are under `docs/`, the skill exits immediately (Step 1)

---

## End State

After the skill completes:
- All affected docs updated and staged via `git add`
- `docs/90.reports/changelog.md` has a new entry and is staged
- Developer runs one `git commit` that includes both code fix + doc updates together

---

## Pre-commit Hook Integration

The Claude Code hooks system does not support a `PreCommit` event. Instead, a standard git pre-commit shell hook is used:

**File**: `.git/hooks/pre-commit`
```bash
#!/bin/bash
# Trigger sync-docs skill before every commit
# Guard: skip if only doc files are staged (prevents re-entry loop)
NON_DOC_STAGED=$(git diff --staged --name-only | grep -v '^docs/')
if [ -z "$NON_DOC_STAGED" ]; then
  exit 0
fi
claude --skill sync-docs
```

Make executable:
```bash
chmod +x .git/hooks/pre-commit
```

> Note: `.git/hooks/` is not committed to the repo. Document the setup step in `docs/50.deployment/local-setup.md`.

---

## Skill File Location

```
.claude/skills/sync-docs/
└── sync-docs.md    ← skill definition
```
