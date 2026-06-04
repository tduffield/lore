---
name: finished
description: End-of-session wrap-up — fill in the session note sections (What we did / Decided / Learned / Open questions), run `lore finish` to set status=complete and commit. Use for /finished, "I'm done", "wrap up", "close this out", "finalize the session".
---

# Finished — end-of-session wrap-up

Fills the session note from in-context synthesis, then calls `lore finish` to set `status: complete`, stamp `ended:`, and commit.

## Process

### Step 1 — Locate and check the session note

Find the active session note for this session (resolves by id, falling back to
the worktree name — prints a vault-relative path):

```bash
lore session-note
```

Read it:
```bash
cat "$LORE_VAULT/$(lore session-note)"
```

Check frontmatter `status`. If already `complete` or `shelved`: report "Already finalized" and stop.

### Step 2 — Draft sections from in-session context

You lived through this session. Draft from the conversation — not by re-reading the transcript.

If a section already has bullets from a prior `/checkpoint`, **extend** (do not duplicate) them.

Sections:
- **What we did** — concrete work completed. Files touched, key outcomes.
- **Decided** — non-obvious choices made and their reasoning.
- **Deferred** — threads intentionally set aside (reference any `deferred/` notes created).
- **Learned** — domain gotchas, corrections, dead-end links.
- **Open questions** — unresolved threads for the next session.

Keep bullets tight — a future reader should skim in 30 seconds.

### Step 3 — Write the sections

For each section with content:

```bash
lore patch "$LORE_VAULT/$(lore session-note)" "<Section>" --text "<bullets>"
```

One call per section. Sections with nothing new are left untouched.

Alternatively, open the note in an Edit call and fill in the sections directly if that is cleaner for the amount of content.

### Step 4 — Finalize and commit

```bash
lore finish
```

This sets `status: complete` and `ended:` to the current UTC timestamp, then commits the session note. If no origin remote is configured, the commit is made locally and a notice is printed — relay that notice.

### Step 5 — Report to the user

```
Finalized `sessions/<file>`.

What we did: <one-line summary>
Committed and pushed (or: committed locally — no remote).
```

## Edge cases

- **No session note.** Unusual — the SessionStart hook should have created one. Tell the user and offer to create one manually before calling `lore finish`.
- **Session note already `complete`.** `lore finish` detects this and exits 0 without re-writing. Report it and stop.
- **Non-git vault.** `lore finish` will write the frontmatter update but skip the commit (notice on stderr). Relay the notice.
- **`lore finish` exits non-zero.** Report the error; do not retry silently.
