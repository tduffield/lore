"""Canonical frontmatter schema for vault notes.

Single source of truth for which frontmatter fields each note type carries.
The frontmatter validator (and its optional pre-commit guard) check notes
against this.

Two field tiers:
- UNIVERSAL_REQUIRED — on every note (`type`, and `group` when the vault opts
  into group enforcement; see below).
- REQUIRED[type]     — additional fields a note of that type must carry. The
                       key must be present; an empty value is allowed.

`status` is intentionally NOT listed in REQUIRED: it is omitted when unknown
(an empty `status:` is rejected by the status guard; a missing one passes), and
its value vocabulary is validated by status_validator, not here.

Groups are vault-specific, so lore ships no hardcoded group vocabulary. A vault
opts into the `group` convention by placing a `.lore-groups` file at its root:

    # .lore-groups — one allowed group value per line; '*' means "any value".
    alpha
    beta

When that file is present the frontmatter guard is enabled, `group` becomes a
required field, and group values are constrained to the listed set (blank is
always allowed, for one-offs). When it is absent, the guard is a no-op and
`group` is not required — so lore stays generic and backward-compatible.

FIELD_ALIASES maps known *drifted* field names to their canonical spelling;
the validator surfaces these as warnings (drift signal), not hard errors.
"""
from __future__ import annotations

from pathlib import Path

# --- universal -------------------------------------------------------------
# `type` is always required. `group` is required only when the vault opts in
# (a `.lore-groups` file exists); see group_config().
UNIVERSAL_REQUIRED: tuple[str, ...] = ("type", "group")

# --- per-type required fields (beyond the universal ones) ------------------
# Keyed by the singular note `type:` value. Directory/plural names map via
# _TYPE_ALIASES so callers can pass either.
REQUIRED: dict[str, tuple[str, ...]] = {
    "session": ("project", "worktree", "branch", "started", "ended"),
    "lesson": ("date", "areas", "phases", "severity"),
    "deferred": ("surfaces", "raised"),
    "plan": ("project", "created", "updated"),
    "decision": ("date", "areas", "phases"),
    "spec": ("project", "created", "updated"),
    "area": ("name", "key-files", "keywords", "last-touched"),
    "dead-end": ("tried", "areas", "phases", "revive-condition"),
    "radar": ("source", "target", "check", "added"),
    "follow-up": ("source", "target", "check", "added"),
    "design": ("project", "date", "areas"),
    "collaboration": ("date", "areas", "phases", "actions"),
    "tool": ("name", "summary", "phases", "last-touched"),
    "morning-briefing": ("date", "surfaced"),
    "post-merge-incident": ("incident_id", "detected_at", "merge_set"),
}

# --- per-type known optional fields (for --strict unknown-field reporting) --
OPTIONAL: dict[str, tuple[str, ...]] = {
    "session": ("status", "areas", "implements", "phase", "sub_phase", "session_id",
                "plan", "tokens_total", "tokens_input", "tokens_output",
                "tokens_cache_read", "tokens_cache_write", "cost_usd_estimate",
                "turn_count", "models", "totals_computed_at"),
    "lesson": ("status", "last-reviewed", "related", "project", "harvest-hash"),
    "deferred": ("status", "raised-in", "source-plan", "source-spec", "next-check",
                 "revisit-after", "last-reviewed", "effort", "value",
                 "consolidation-group", "closed", "closure-reason", "areas",
                 "project", "harvest-hash"),
    "plan": ("status", "slug", "spec", "related-spec", "related-areas", "areas",
             "asana_task"),
    "decision": ("supersedes", "raised-in", "source-plan", "source-spec",
                 "status", "project", "harvest-hash"),
    "spec": ("areas", "asana_task"),
    "area": ("project", "last-updated", "related-areas", "status"),
    "dead-end": ("status", "last-reviewed", "raised-in", "source-plan",
                 "source-spec", "project", "harvest-hash"),
    "radar": ("raised-in", "source-plan", "source-spec", "last-checked",
              "last-state", "revisit-after", "project", "status"),
    "follow-up": ("last-checked", "last-state", "last-reviewed", "revisit-after",
                  "closed", "closure-reason", "project", "status", "harvest-hash"),
    "design": ("related_spec", "related_plan", "related_session", "related_page",
               "status"),
    "collaboration": ("status", "graduated-to", "graduated-on"),
    "tool": (),
    "morning-briefing": ("generated-at", "brain-head", "last-run-prior"),
    "post-merge-incident": ("status", "agent_recommendation", "human_decision",
                            "human_decided_at", "actual_outcome",
                            "subsystems_affected", "wait_count",
                            "supersedes_decision"),
}

# Fields acceptable on ANY type (cross-cutting / machine-written), so --strict
# does not flag them as unknown.
GLOBAL_OPTIONAL: frozenset[str] = frozenset({
    "project", "status", "areas", "phases", "surfaces", "slug", "date",
    "created", "updated", "last-reviewed", "last-updated", "name", "description",
    "raised-in", "source-plan", "source-spec", "related", "related-areas",
    "related-spec", "related-plan", "related-decision", "related-session",
    "related-design", "related-deferred", "supersedes", "superseded-by",
    "superseded-on", "harvest-hash", "tags", "revisit-after",
})

# --- known field-name drift (canonical ← variants) -------------------------
FIELD_ALIASES: dict[str, str] = {
    "subsystems": "areas",
    "related-subsystems": "related-areas",
    "revisit_when": "revisit-after", "revisit-when": "revisit-after",
    "revisit": "revisit-after", "revisit-trigger": "revisit-after",
    "related_plan": "related-plan", "related-plans": "related-plan",
    "related_spec": "related-spec", "related-specs": "related-spec",
    "related_design": "related-design",
    "related_session": "related-session", "related-sessions": "related-session",
    "related_deferred": "related-deferred", "related_pr": "related-pr",
    "related-decisions": "related-decision",
    "closed-on": "closed", "closed-in": "closed", "closed-by": "closed",
    "closed-via": "closed", "resolved": "closed", "resolved-in": "closed",
    "resolved-by": "closed", "resolved-on": "closed", "resolved_by": "closed",
    "resolved-at": "closed",
    "last_checked": "last-checked", "check_interval": "check-cadence",
    "last_updated": "last-updated",
}

# type:/dir-name aliasing, matching status_validator's mapping.
_TYPE_ALIASES: dict[str, str] = {
    "plans": "plan", "specs": "spec", "sessions": "session",
    "lessons": "lesson", "dead-ends": "dead-end", "deferreds": "deferred",
}

GROUP_CONFIG_FILE = ".lore-groups"


def canonical_type(note_type: str | None) -> str | None:
    """Normalize a note type/dir name to its singular canonical form."""
    if not note_type:
        return None
    nt = note_type.strip()
    return _TYPE_ALIASES.get(nt, nt)


def required_fields(note_type: str | None) -> tuple[str, ...]:
    """Per-type required fields (not including the universal ones)."""
    return REQUIRED.get(canonical_type(note_type), ())


def known_fields(note_type: str | None) -> frozenset[str]:
    """All recognized fields for a type — used by --strict unknown reporting."""
    ct = canonical_type(note_type)
    return frozenset(
        set(UNIVERSAL_REQUIRED)
        | set(REQUIRED.get(ct, ()))
        | set(OPTIONAL.get(ct, ()))
        | set(GLOBAL_OPTIONAL)
    )


def group_config(vault: str | Path) -> tuple[bool, frozenset[str] | None]:
    """Read <vault>/.lore-groups → (require_group, allowed_values).

    - File absent          → (False, None)  — group not enforced.
    - File present, values → (True, {values}) — group required, constrained.
    - File present, only '*' or empty/comments → (True, None) — group required,
      any value allowed.
    """
    p = Path(vault) / GROUP_CONFIG_FILE
    if not p.exists():
        return (False, None)
    values: set[str] = set()
    wildcard = False
    try:
        lines = p.read_text().splitlines()
    except Exception:
        return (True, None)
    for line in lines:
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if line == "*":
            wildcard = True
            continue
        values.add(line)
    allowed = None if (wildcard or not values) else frozenset(values)
    return (True, allowed)


def is_valid_group(group: object, allowed: frozenset[str] | None) -> bool:
    """Validate a group VALUE (presence is handled by the validator).

    Blank is always allowed (one-off). When `allowed` is None, any non-blank
    value passes; otherwise the value must be in the allowlist.
    """
    if group is None:
        return False
    if isinstance(group, str) and group.strip() == "":
        return True
    if allowed is None:
        return True
    return group in allowed
