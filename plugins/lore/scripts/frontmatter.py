"""Frontmatter parser and byte-careful edit primitives for vault notes.

`parse_frontmatter` is a minimal reader (key: value plus flat [a, b, c]
lists) — not a general YAML parser, only the shapes this vault uses.

`set_status` and `patch_section` are the two ergonomic write operations the
CLI exposes: a frontmatter status flip and a section-targeted append. Both
leave everything they don't touch byte-identical.
"""
from __future__ import annotations

from pathlib import Path


def _parse_fm_text(text: str) -> dict:
    """Parse frontmatter from raw text. Returns {} when no frontmatter block found."""
    if not text.startswith("---"):
        return {}
    end = text.find("\n---", 3)
    if end < 0:
        return {}
    fm: dict[str, object] = {}
    for line in text[3:end].strip().splitlines():
        if ":" not in line:
            continue
        k, _, v = line.partition(":")
        k = k.strip()
        v = v.strip()
        if v.startswith("[") and v.endswith("]"):
            inner = v[1:-1]
            items = [p.strip().strip('"').strip("'") for p in inner.split(",") if p.strip()]
            fm[k] = items
        else:
            fm[k] = v.strip('"').strip("'")
    return fm


def parse_frontmatter(path: Path) -> dict:
    """Minimal frontmatter parser — key: value and flat [a, b, c] lists.

    Not a general YAML parser; only handles the shapes this vault uses.
    Returns {} when the file is missing or has no frontmatter.
    """
    try:
        text = Path(path).read_text()
    except Exception:
        return {}
    return _parse_fm_text(text)


def parse_frontmatter_str(text: str) -> dict:
    """Parse frontmatter from a raw string instead of a file path.

    Same semantics as parse_frontmatter but takes text directly. Useful
    for validating rendered templates before writing to disk.
    """
    return _parse_fm_text(text)


def _split(text: str) -> tuple[str, str] | None:
    """Split a document into (frontmatter_body, rest) including delimiters.

    Returns (fm_text, body) where fm_text is the content between the opening
    and closing ``---`` lines, and body is everything from the closing
    delimiter onward (``\\n---`` included). Returns None when there is no
    frontmatter block.
    """
    if not text.startswith("---"):
        return None
    end = text.find("\n---", 3)
    if end < 0:
        return None
    return text[3:end], text[end:]


def set_status(path: Path, value: str) -> bool:
    """Set or replace the ``status:`` frontmatter key.

    Replaces the existing status line in place if present, otherwise appends
    one to the end of the frontmatter block. All other lines stay
    byte-identical. Returns True on write.
    """
    path = Path(path)
    text = path.read_text()
    split = _split(text)
    if split is None:
        return False
    fm_text, body = split
    fm_lines = fm_text.splitlines()

    new_line = f"status: {value}"
    replaced = False
    for i, line in enumerate(fm_lines):
        if line.strip() == "status:" or line.startswith("status:"):
            fm_lines[i] = new_line
            replaced = True
            break
    if not replaced:
        fm_lines.append(new_line)

    new_text = "---" + "\n".join(fm_lines) + body
    path.write_text(new_text)
    return True


def patch_section(path: Path, section: str, text_to_add: str) -> bool:
    """Append ``text_to_add`` under the ``## <section>`` heading.

    Inserts the text immediately before the next sibling heading (or at the
    end of the section's content) so every other section stays byte-identical.
    If the section heading is absent, appends a fresh ``## <section>`` block
    at the end of the document. Returns True on write.
    """
    path = Path(path)
    content = path.read_text()
    lines = content.split("\n")
    heading = f"## {section}"

    heading_idx = None
    for i, line in enumerate(lines):
        if line.rstrip() == heading:
            heading_idx = i
            break

    addition = text_to_add.rstrip("\n")

    if heading_idx is None:
        # Section missing — append it at the end of the document.
        suffix = "" if content.endswith("\n") else "\n"
        new_content = content + suffix + f"\n## {section}\n{addition}\n"
        path.write_text(new_content)
        return True

    # Find the end of this section: the next line starting with "## " (a
    # sibling-or-higher heading) after the heading, else end of document.
    end_idx = len(lines)
    for j in range(heading_idx + 1, len(lines)):
        if lines[j].startswith("## "):
            end_idx = j
            break

    # Walk back over trailing blank lines so the append sits flush against
    # the section's content, then re-pad with one blank line before the next
    # heading.
    insert_at = end_idx
    while insert_at > heading_idx + 1 and lines[insert_at - 1] == "":
        insert_at -= 1

    new_lines = lines[:insert_at] + [addition] + lines[insert_at:]
    path.write_text("\n".join(new_lines))
    return True
