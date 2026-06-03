"""Subsystem recall logic for the lore plugin.

Derives the branch-to-subsystem keyword map at runtime from vault frontmatter
(no hardcoded taxonomy). On a branch match, loads the subsystem profile in
full plus related open deferred items, dead-ends, active lessons, and recent
sessions.

Public API:
    derive_subsystem_keywords(vault) -> dict[str, list[str]]
    infer_subsystems(vault, branch) -> list[str]
    render_subsystem_block(vault, subsystems, project) -> str | None
"""
from __future__ import annotations

from pathlib import Path
from typing import Callable

import frontmatter as fm_module


def derive_subsystem_keywords(vault: Path) -> dict[str, list[str]]:
    """Scan <vault>/subsystems/*.md and return {name: [keyword, ...]} for
    each profile that declares a non-empty inline `keywords:` list.

    Profiles with absent or empty `keywords:` are excluded — they should
    never auto-load on branch matches.
    """
    vault = Path(vault)
    subsystems_dir = vault / "subsystems"
    if not subsystems_dir.is_dir():
        return {}

    result: dict[str, list[str]] = {}
    for p in subsystems_dir.glob("*.md"):
        parsed = fm_module.parse_frontmatter(p)
        kws = parsed.get("keywords", [])
        if isinstance(kws, list) and kws:
            result[p.stem] = kws
        # Absent or empty keywords → omit from result
    return result


def infer_subsystems(vault: Path, branch: str) -> list[str]:
    """Return every subsystem whose declared keyword is a substring of branch.

    Branch is lowercased before comparison; each keyword is also lowercased.
    Returns [] when the subsystems dir is empty or absent — never raises.
    """
    keyword_map = derive_subsystem_keywords(vault)
    branch_lower = branch.lower()
    matched: list[str] = []
    for name, keywords in keyword_map.items():
        for kw in keywords:
            if kw.lower() in branch_lower:
                matched.append(name)
                break
    return matched


# ---------------------------------------------------------------------------
# Rendering helpers
# ---------------------------------------------------------------------------

def _find_notes(
    directory: Path, predicate: Callable[[dict], bool]
) -> list[tuple[Path, dict]]:
    """Return (path, frontmatter) pairs matching predicate, sorted by name."""
    if not directory.is_dir():
        return []
    hits: list[tuple[Path, dict]] = []
    for md in sorted(directory.glob("*.md")):
        parsed = fm_module.parse_frontmatter(md)
        if predicate(parsed):
            hits.append((md, parsed))
    return hits


def _first_heading(path: Path) -> str:
    """Return the first `# Heading` from a note, or the stem as fallback."""
    try:
        for line in path.read_text().splitlines()[:40]:
            stripped = line.strip()
            if stripped.startswith("# "):
                return stripped[2:].strip()
    except Exception:
        pass
    return path.stem


def _has_overlap(fm_list: object, needle: set[str]) -> bool:
    """True if fm_list (str or list) shares at least one element with needle."""
    if isinstance(fm_list, str):
        fm_list = [fm_list]
    if not isinstance(fm_list, list):
        return False
    return any(item in needle for item in fm_list)


def _matches_project(fm: dict, project: str | None) -> bool:
    """True if the note is project-agnostic or its project matches."""
    if project is None:
        return True
    fm_project = fm.get("project")
    if not fm_project:
        return True
    return fm_project == project


def _relevant_profiles(vault: Path, subsystems: list[str]) -> list[Path]:
    """Return paths to subsystem profiles that exist in the vault."""
    out: list[Path] = []
    for name in subsystems:
        p = vault / "subsystems" / f"{name}.md"
        if p.exists():
            out.append(p)
    return out


def _relevant_deferred(
    vault: Path, sub_set: set[str], project: str | None
) -> list[tuple[Path, dict]]:
    """Open deferred items whose surfaces overlap the matched subsystems.

    Only notes whose project matches (or is absent) are returned.
    """
    def pred(parsed: dict) -> bool:
        return (
            parsed.get("type") == "deferred"
            and parsed.get("status") in ("open", "scheduled", "resurfaced")
            and _has_overlap(parsed.get("surfaces"), sub_set)
            and _matches_project(parsed, project)
        )
    return _find_notes(vault / "deferred", pred)


def _relevant_dead_ends(
    vault: Path, sub_set: set[str]
) -> list[tuple[Path, dict]]:
    """Dead-ends whose subsystems field overlaps the matched set.

    Dead-ends are project-agnostic by design — a failed approach generalizes.
    """
    def pred(parsed: dict) -> bool:
        return (
            parsed.get("type") == "dead-end"
            and _has_overlap(parsed.get("subsystems"), sub_set)
        )
    return _find_notes(vault / "dead-ends", pred)


def _relevant_lessons(
    vault: Path, sub_set: set[str]
) -> list[tuple[Path, dict]]:
    """Active lessons whose subsystems field overlaps the matched set.

    Lessons are project-agnostic — process mistakes generalize.
    """
    def pred(parsed: dict) -> bool:
        return (
            parsed.get("type") == "lesson"
            and parsed.get("status", "active") == "active"
            and _has_overlap(parsed.get("subsystems"), sub_set)
        )
    return _find_notes(vault / "lessons", pred)


def _recent_sessions(
    vault: Path, sub_set: set[str], project: str | None, limit: int = 3
) -> list[tuple[Path, dict]]:
    """Recent sessions whose subsystems overlap and project matches."""
    def pred(parsed: dict) -> bool:
        return (
            parsed.get("type") == "session"
            and _has_overlap(parsed.get("subsystems"), sub_set)
            and _matches_project(parsed, project)
        )
    hits = _find_notes(vault / "sessions", pred)
    return sorted(hits, key=lambda h: h[0].stat().st_mtime, reverse=True)[:limit]


def render_subsystem_block(
    vault: Path,
    subsystems: list[str],
    project: str | None = None,
) -> str | None:
    """Build a markdown recall block for the given subsystem names.

    Loads each profile in full plus related open deferred items, dead-ends,
    active lessons, and recent sessions. Returns None when nothing substantive
    could be loaded.
    """
    vault = Path(vault)
    if not subsystems:
        return None

    sub_set = set(subsystems)
    parts: list[str] = ["## Subsystem recall", ""]
    baseline = len(parts)

    profiles = _relevant_profiles(vault, subsystems)
    if profiles:
        parts.append("### Subsystem profiles")
        parts.append("")
        for p in profiles:
            try:
                rel = p.relative_to(vault)
            except ValueError:
                rel = p.name
            parts.append(f"#### `{rel}`")
            parts.append("")
            try:
                parts.append(p.read_text())
            except Exception:
                parts.append("(could not read)")
            parts.append("")

    deferred = _relevant_deferred(vault, sub_set, project)
    if deferred:
        parts.append("### Open deferred items")
        parts.append("")
        for path, parsed in deferred:
            try:
                rel = path.relative_to(vault)
            except ValueError:
                rel = path.name
            next_check = parsed.get("next-check", "")
            parts.append(
                f"- **{_first_heading(path)}** ([[{rel}]]) — revisit when: {next_check}"
            )
        parts.append("")

    dead = _relevant_dead_ends(vault, sub_set)
    if dead:
        parts.append("### Dead-ends in this area")
        parts.append("")
        parts.append(
            "_These approaches have been tried and failed. "
            "Check each revive condition before proposing them again._"
        )
        parts.append("")
        for path, parsed in dead:
            try:
                rel = path.relative_to(vault)
            except ValueError:
                rel = path.name
            revive = parsed.get("revive-condition", "")
            parts.append(
                f"- **{_first_heading(path)}** ([[{rel}]]) — revive when: {revive}"
            )
        parts.append("")

    lessons = _relevant_lessons(vault, sub_set)
    if lessons:
        parts.append("### Lessons learned in this area")
        parts.append("")
        parts.append(
            "_Mistakes made here, with prevention checks. Consult before proposing changes._"
        )
        parts.append("")
        for path, parsed in lessons:
            try:
                rel = path.relative_to(vault)
            except ValueError:
                rel = path.name
            severity = parsed.get("severity", "")
            sev_disp = f" [{severity}]" if severity else ""
            parts.append(
                f"- **{_first_heading(path)}**{sev_disp} ([[{rel}]])"
            )
        parts.append("")

    sessions = _recent_sessions(vault, sub_set, project)
    if sessions:
        parts.append("### Recent sessions touching this area")
        parts.append("")
        for path, parsed in sessions:
            try:
                rel = path.relative_to(vault)
            except ValueError:
                rel = path.name
            status = parsed.get("status", "")
            parts.append(
                f"- [[{rel}]] — {_first_heading(path)} (status: {status})"
            )
        parts.append("")

    if len(parts) == baseline:
        return None
    return "\n".join(parts)
