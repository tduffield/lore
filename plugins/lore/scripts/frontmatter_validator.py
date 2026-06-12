"""Frontmatter validator for vault notes.

Checks a note's frontmatter against the canonical schema in
`frontmatter_schema.py`:

- ERROR  every note must carry `type`; each note type's required fields must be
         present. When the vault opts into the group convention (a `.lore-groups`
         file at its root), `group` is also required and its value must be in the
         configured allowlist (blank — a one-off — is always allowed).
- WARN   known field-name *drift* (e.g. `revisit_when` instead of
         `revisit-after`). With `strict=True`, unknown fields are also warned.

`status` value vocabulary is owned by status_validator (and its own pre-commit
guard), not duplicated here.

Files without a frontmatter block (generated/data files: _index.md, daily
dumps, etc.) are skipped — the validator only judges notes that already have
frontmatter.

Group enforcement is parameterized so the same logic serves the opt-in
pre-commit guard and the explicit `lore validate` command. The CLI invocation
reads the require/allowlist from the LORE_REQUIRE_GROUP / LORE_GROUPS env vars
the guard exports.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import NamedTuple

_here = Path(__file__).resolve().parent
if str(_here) not in sys.path:
    sys.path.insert(0, str(_here))

import frontmatter as _fm  # noqa: E402
import frontmatter_schema as schema  # noqa: E402

ERROR = "error"
WARN = "warning"


class Issue(NamedTuple):
    severity: str  # ERROR | WARN
    message: str


def _blank(v: object) -> bool:
    return v is None or (isinstance(v, str) and v.strip() == "")


def validate_meta(
    meta: dict,
    *,
    require_group: bool = False,
    allowed_groups: frozenset[str] | None = None,
    strict: bool = False,
) -> list[Issue]:
    """Validate a parsed frontmatter mapping against the schema."""
    issues: list[Issue] = []
    note_type = meta.get("type")

    if "type" not in meta or _blank(note_type):
        issues.append(Issue(ERROR, "missing required field 'type'"))
        note_type = None

    if require_group:
        if "group" not in meta:
            issues.append(Issue(ERROR, "missing required field 'group'"))
        elif not schema.is_valid_group(meta.get("group"), allowed_groups):
            allowed_str = (
                ", ".join(sorted(allowed_groups)) if allowed_groups else "(any)"
            )
            issues.append(Issue(
                ERROR,
                f"invalid group {meta.get('group')!r} — allowed: {allowed_str}, or blank",
            ))

    if note_type:
        ct = schema.canonical_type(note_type)
        for field in schema.required_fields(note_type):
            if field not in meta:
                issues.append(Issue(ERROR, f"missing required field {field!r} for type {ct!r}"))

    for field in meta:
        if field in schema.FIELD_ALIASES:
            issues.append(Issue(
                WARN, f"drifted field {field!r} — canonical name is {schema.FIELD_ALIASES[field]!r}",
            ))

    if strict and note_type:
        known = schema.known_fields(note_type)
        for field in meta:
            if field in schema.FIELD_ALIASES or field in known:
                continue
            issues.append(Issue(
                WARN, f"unknown field {field!r} for type {schema.canonical_type(note_type)!r}",
            ))

    return issues


def has_frontmatter(text: str) -> bool:
    """True if the document opens with a frontmatter block."""
    return text.startswith("---\n") and "\n---" in text[3:]


def validate_file(
    path: str | Path,
    *,
    require_group: bool = False,
    allowed_groups: frozenset[str] | None = None,
    strict: bool = False,
) -> list[Issue]:
    """Validate a note file. Returns [] for files with no frontmatter block."""
    try:
        text = Path(path).read_text()
    except Exception as e:
        return [Issue(ERROR, f"unreadable: {type(e).__name__}: {e}")]
    if not has_frontmatter(text):
        return []
    meta = _fm.parse_frontmatter_str(text)
    if not meta:
        return [Issue(ERROR, "frontmatter block present but empty/unparseable")]
    return validate_meta(
        meta, require_group=require_group, allowed_groups=allowed_groups, strict=strict
    )


def _group_opts_from_env() -> tuple[bool, frozenset[str] | None]:
    """Read group enforcement from env (set by the pre-commit guard)."""
    require = os.environ.get("LORE_REQUIRE_GROUP") == "1"
    raw = os.environ.get("LORE_GROUPS", "").strip()
    allowed = frozenset(g for g in (s.strip() for s in raw.split(",")) if g) or None
    return require, allowed


def main(argv: list[str] | None = None) -> int:
    """CLI entry point. Validates each given file; exits 1 on any ERROR.

    Warnings print to stderr but do not fail the run (so drift surfaces without
    blocking commits during the migration window). Group enforcement comes from
    the LORE_REQUIRE_GROUP / LORE_GROUPS env vars.
    """
    args = argv if argv is not None else sys.argv[1:]
    strict = "--strict" in args
    files = [a for a in args if a != "--strict"]
    require_group, allowed_groups = _group_opts_from_env()

    errors: list[str] = []
    warnings: list[str] = []
    for path_str in files:
        for issue in validate_file(
            path_str, require_group=require_group, allowed_groups=allowed_groups, strict=strict
        ):
            line = f"  {path_str}: {issue.message}"
            (errors if issue.severity == ERROR else warnings).append(line)

    if warnings:
        print("frontmatter-validator: drift warning(s):", file=sys.stderr)
        for w in warnings:
            print(w, file=sys.stderr)
    if errors:
        print("frontmatter-validator: invalid frontmatter:", file=sys.stderr)
        for e in errors:
            print(e, file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
