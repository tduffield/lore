# Glossary

Project-specific vocabulary. Grows as new terms are encountered. Each entry
is one sentence; link to an area profile or decision note for depth.

## Terms

<!-- Seed entries; expand as needed. Example shape:
- **term** — one-sentence definition. See [[areas/...]] for depth.
-->

## Frontmatter schema

Every note carries a YAML frontmatter block. `type` (the note class — session,
lesson, deferred, plan, decision, spec, area, dead-end, radar, follow-up,
design, collaboration, tool, …) is always required and is the first line.

Each type also has required per-type fields (e.g. a `session` needs
`project`/`worktree`/`branch`/`started`/`ended`; a `lesson` needs
`date`/`areas`/`phases`/`severity`). The canonical sets live in
`scripts/frontmatter_schema.py`.

### Groups (opt-in)

`group` is a coarse rollup above the finer `project:` field — the
product/initiative a note belongs to. It is **opt-in**: create a `.lore-groups`
file at the vault root listing your allowed groups (one per line; `*` = any
value), e.g.

    # .lore-groups
    alpha
    beta

When that file exists, `group` becomes a required field (the second line),
values are constrained to the list (blank is always allowed, for one-offs), and
the pre-commit frontmatter guard turns on. Without it, lore does not require or
constrain `group`.

### Enforcement

- **`lore validate`** scans the whole vault and reports notes missing required
  fields, invalid `group` values, and field-name *drift* (e.g. `revisit_when`
  where the canonical name is `revisit-after`). `--strict` also flags unknown
  fields.
- The optional **pre-commit frontmatter guard**
  (`scripts/frontmatter_validator.py`, enabled by `.lore-groups`) blocks commits
  that introduce notes missing required frontmatter. Drift is a non-blocking
  warning.

`status:` is intentionally *not* a required field — it is omitted when unknown
and its value vocabulary is governed separately (below).

## Status vocabulary

Each note type has a canonical `status:` set enforced by the status guard
(`scripts/status_validator.py` and the optional pre-commit hook). Do not
invent statuses outside these sets — drift makes recall unreliable.

### Work-tracking note types

- **plans/** — `draft` → `ready` → `in-progress` → `complete`. Side-state: `shelved`. Off-path terminal: `superseded`, `dropped`.
- **specs/** — `draft` → `ready` → `planned` → `complete`. Side-state: `shelved`. Off-path terminal: `superseded`, `dropped`.
- **sessions/** — `active` (in flight) → `complete` (wrapped). Side-state: `shelved` (handed off, awaiting pickup).

### Observation note types

- **deferred/** — `open` → `resolved` / `dropped` / `graduated`. Variant: `scheduled` (date-bound `open` — resurface on/after a set date). Edge: `resurfaced` (trigger condition met, action pending).
- **radar/** — `active` → `resolved` / `dropped`.
- **lessons/** — `active` → `superseded` (when guarded structurally).
- **dead-ends/** — `active` → `archived` (when the revive condition is obsolete).

### `shelved` semantics

`shelved` is a cross-note-type side-state meaning *"this work is paused;
resume by going back to its prior in-flight state."* Set when work is handed
off (on the active session note plus any linked in-progress plan) and cleared
on pickup (flips back to the prior in-flight status). Distinct from `dropped`
(not coming back) and individual `deferred/*` notes (a specific question to
revisit, not a whole work-stream).
