"""Every shipped lore skill must be generic — zero brain-vault structural strings.

This test enforces the mechanical definition of "generic" via structural brain
seams, parametrized over skills discovered in plugins/lore/skills/*/SKILL.md.

## Structural brain seams (literal strings — never denylisted)
These strings definitionally belong to brain's private infrastructure. They are
safe to embed as literals here because they do NOT appear in the machine-local
leak-gate.denylist (the denylist carries identifying tokens; "mcp__brain__" and
"code/brain" are structural — deliberately kept off the denylist so THIS file
can reference them without tripping the gate).

  - "mcp__brain__"  — brain MCP tool prefix
  - "code/brain"    — matches ~/code/brain and /Users/.../code/brain

Identifying tokens (developer handle / org name / machine path) are NOT checked
here — those are the leak gate's exclusive responsibility. Adding them here as
literals would trip the gate on this file itself (the P1-F self-referential trap).

`skills/_shared/` is a reference doc, not a skill, and is exempt.
"""
from __future__ import annotations

from pathlib import Path

import pytest

SKILLS_DIR = Path(__file__).parent.parent / "plugins" / "lore" / "skills"

STRUCTURAL_SEAMS: list[str] = [
    "mcp__brain__",
    "code/brain",
]


def _skill_files() -> list[Path]:
    return sorted(
        d / "SKILL.md"
        for d in SKILLS_DIR.iterdir()
        if d.is_dir() and d.name != "_shared" and (d / "SKILL.md").exists()
    )


@pytest.mark.parametrize("skill_md", _skill_files(), ids=lambda p: p.parent.name)
def test_skill_has_no_structural_brain_seams(skill_md: Path):
    """Skill must contain no structural brain-vault strings."""
    text = skill_md.read_text()
    for seam in STRUCTURAL_SEAMS:
        assert seam not in text, (
            f"{skill_md.parent.name}/SKILL.md contains the structural brain seam "
            f"{seam!r}. Genericize: drop mcp__brain__ tools, strip code/brain paths."
        )
