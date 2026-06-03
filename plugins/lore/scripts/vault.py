"""Shared config resolver for the lore plugin.

Every hook and CLI call resolves the vault location and the acting user
through these two pure functions. Vault location comes from $LORE_VAULT
(default ~/lore); the acting user from $LORE_USER, then git config, then
a generic fallback. Neither function raises.
"""
from __future__ import annotations

import os
import re
import subprocess
from pathlib import Path

# Strip control characters (incl. newlines/tabs) from user-provided strings.
_CONTROL_RE = re.compile(r"[\x00-\x1f\x7f]")


def resolve_vault() -> str:
    """Return the resolved vault path.

    Priority: $LORE_VAULT (expanded + resolved), else ~/lore resolved.
    Never raises.
    """
    raw = os.environ.get("LORE_VAULT", "").strip()
    target = raw if raw else "~/lore"
    try:
        return str(Path(target).expanduser().resolve())
    except Exception:
        return str(Path(target).expanduser())


def _sanitize(value: str) -> str:
    """Strip control chars (newlines/tabs included) and surrounding whitespace."""
    return _CONTROL_RE.sub("", value).strip()


def resolve_user() -> str:
    """Return the acting user's name.

    Fixed fallback order: $LORE_USER → `git config user.name` → "you".
    Sanitized (control chars stripped, whitespace trimmed). Never raises.
    """
    raw = os.environ.get("LORE_USER", "")
    name = _sanitize(raw)
    if name:
        return name

    try:
        result = subprocess.run(
            ["git", "config", "user.name"],
            capture_output=True, text=True, timeout=5,
        )
        if result.returncode == 0:
            name = _sanitize(result.stdout or "")
            if name:
                return name
    except Exception:
        pass

    return "you"


def resolve_project(cwd: Path | None = None) -> str:
    """Infer the current project name from the git remote URL.

    `https://github.com/acme/my-repo.git` → `my-repo`
    `git@github.com:acme/project.git` → `project`

    Falls back to the CWD's directory name. Never raises.
    """
    target = cwd or Path.cwd()
    try:
        result = subprocess.run(
            ["git", "-C", str(target), "remote", "get-url", "origin"],
            capture_output=True, text=True, timeout=5,
        )
        url = (result.stdout or "").strip()
        if url and result.returncode == 0:
            m = re.search(r"[/:]([^/:]+?)(?:\.git)?/?$", url)
            if m:
                return m.group(1)
    except Exception:
        pass

    return target.name


_DATE_PREFIX_RE = re.compile(r"^\d{4}-\d{2}-\d{2}")

# Matches the timestamp prefix and captures everything after it as the worktree.
_STEM_WORKTREE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}-\d{4}-(.+)$")


def _worktree_from_stem(stem: str) -> str | None:
    """Return the worktree name encoded in a session note stem, or None."""
    m = _STEM_WORKTREE_RE.match(stem)
    return m.group(1) if m else None


def find_session_note(vault: Path, worktree_name: str | None = None) -> Path | None:
    """Return the newest matching session note in vault/sessions/, or None.

    Candidates must have a date-prefixed filename (``YYYY-MM-DD-HHMM-<worktree>.md``).
    When *worktree_name* is given, only notes whose stem encodes exactly that
    worktree are considered — this prevents a note from worktree ``beta``
    being returned when the caller belongs to worktree ``alpha``.  The match
    is done by parsing the worktree out of the stem (anchored on the timestamp
    boundary) so ``foo`` cannot accidentally match ``super-foo``.
    When *worktree_name* is None, returns the newest dated note overall.
    Returns None when no matching note exists or the sessions dir is missing.
    """
    sessions_dir = Path(vault) / "sessions"
    if not sessions_dir.is_dir():
        return None

    def _is_candidate(p: Path) -> bool:
        if not _DATE_PREFIX_RE.match(p.name):
            return False
        if worktree_name is None:
            return True
        return _worktree_from_stem(p.stem) == worktree_name

    notes = sorted(
        (p for p in sessions_dir.glob("*.md") if _is_candidate(p)),
        reverse=True,
    )
    return notes[0] if notes else None
