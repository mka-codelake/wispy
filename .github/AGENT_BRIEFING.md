# Agent Briefing — Autonomous Issue Workflow

This file is loaded into every Claude Code Action run via `--append-system-prompt`. It defines the **non-negotiable** behavior for agents working on wispy issues. The repo's `CLAUDE.md` provides project context (architecture, stack, constraints); this file defines workflow discipline.

## Three-Phase Discipline (Mandatory)

You MUST proceed through these phases in order. Do not skip phases. Do not implement before the plan is documented.

### Phase 1 — Analyze

- Read the linked issue in full, including all comments.
- Read `CLAUDE.md` and the relevant source files in `src/wispy/`.
- Identify affected modules, the data flow involved, and any cross-cutting concerns (config, paths, threading, Windows-only APIs).
- Summarize findings in 5–10 bullets at the start of the PR description under a `## Analysis` heading.

### Phase 2 — Plan

Before writing any code, post a `## Plan` section in the PR description containing:

- **Files to change** — list with one-line per file describing the change.
- **Approach** — 3–6 sentences on the implementation strategy and why this approach over alternatives.
- **Test strategy** — what you will run to validate. If the change touches Windows-only APIs (audio devices, hotkeys, clipboard, winsound, UAC elevation), explicitly state: "Cannot validate on the Linux runner — manual Windows test required by reviewer." Mark the PR title with `[needs-windows-test]`.
- **Risks / open questions** — anything you are uncertain about.

The PR is opened as **Draft** until the plan is in the description.

### Phase 3 — Implement

- Only after Phase 2 is in the PR body: write code, run tests, commit.
- Keep commits focused. One logical change per commit.
- After implementation, update the PR description with a `## Result` section: what was done, what was tested, what remains untested.

## Escalation Rules

If you are blocked or uncertain, do **not** guess. Stop and escalate:

- **Ambiguous requirement**: post a comment with numbered options (max 3), apply label `blocked-by-ambiguity`, stop.
- **Multiple valid implementations with no clear winner**: post a comment listing trade-offs, apply label `needs-human`, stop. Do not spawn parallel implementations.
- **External dependency or destructive action needed** (git history rewrite, dependency removal, schema migration): apply label `needs-human`, stop and ask.
- **CI fails after one fix attempt**: do not chain endless fix attempts. Post the failure analysis as a comment, apply `needs-human`, stop.

## PR Lifecycle

The dispatcher and reviewer workflows manage the PR's draft/ready state — you do not need to. For your awareness:

- **Initial**: dispatcher's auto-create step opens the PR as **Draft** the first time you push commits for an issue.
- **During fix iterations** (after `@claude fix` triggers another dispatcher run): PR stays Draft.
- **After reviewer's APPROVED verdict**: reviewer flips PR to **Ready for review** via `gh pr ready`. This is the signal that human approval and merge can happen.

You **never** flip a PR from Draft to Ready yourself, and you never close, merge, or modify the draft state of any PR.

## Hard Constraints

- **Never** auto-merge. Never approve your own PR. Never push to `main`.
- **Never** modify `release.yml` or `.github/workflows/claude-*.yml` without explicit human direction in the issue.
- **Never** modify `.gitignore` unless the issue explicitly asks for it. The current ignore list represents deliberate project decisions; do not "tidy it up" or remove entries on your own initiative.
- **`CLAUDE.md` is project metadata** (committed). Modify it only when the issue explicitly requests an update — same rule as any other tracked file. Treat its contents (architecture notes, status, conventions) as authoritative project context that you should read before planning, but do not edit casually.
- **Stay strictly within the issue's scope.** If you discover related work that the issue does not explicitly request — formatting nits, adjacent bugs, doc gaps, refactoring opportunities — leave them. Mention them in the PR body under an "Out of Scope (suggested follow-ups)" section, then stop. Scope expansion without an explicit follow-up from the maintainer is a hard "no".
- **Never** commit secrets, tokens, `*.env`, or credential files. Hard refuse.
- Respect existing labels:
  - `do-not-automate` — issue is hands-off, no exceptions.
  - `parked` — issue is intentionally deferred for later re-evaluation. Treat as hands-off; typically paired with `do-not-automate`. Do not "unpark" the issue by removing the label on your own initiative — only the maintainer decides when a parked issue becomes active again.
- The runtime target is **Windows native** (not WSL2, not Linux). The CI runner is Linux — anything you cannot validate there must be flagged as untested.

## Style

- Match the existing code style. The repo uses German for user-facing strings and CLAUDE.md; keep code identifiers and PR descriptions in English for tooling compatibility.
- No new dependencies without justification in the plan.
- No speculative abstractions. Solve the issue, nothing beyond it.
- Keep comments minimal — explain *why*, not *what*.
