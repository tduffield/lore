#!/usr/bin/env python3
"""PreToolUse hook: log every tool invocation for this session so later
permission-harvesting can surface frequently-used calls worth allow-listing.

Writes one JSON line per call to `<vault>/permission-log/<session_id>.jsonl`.
The signature extraction is coarse on purpose — it buckets repeated calls
(e.g. `git -C a status` and `git -C b status` collapse to `git status`).

Project-agnostic; resolves the vault via `resolve_vault()`. Never raises —
never blocks a tool call.
"""
from __future__ import annotations

import datetime as dt
import json
import os
import re
import shlex
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

from vault import resolve_vault  # noqa: E402


def read_stdin_json() -> dict:
    try:
        data = sys.stdin.read()
        if not data.strip():
            return {}
        return json.loads(data)
    except Exception:
        return {}


def _bash_signature(command: str) -> str:
    """Reduce a bash command string to a coarse signature."""
    head = re.split(r"[|&;]| && | \|\| ", command.strip(), maxsplit=1)[0].strip()
    if not head:
        return "bash"
    try:
        tokens = shlex.split(head)
    except ValueError:
        tokens = head.split()
    if not tokens:
        return "bash"

    if tokens[0] == "git":
        i = 1
        while i < len(tokens) and tokens[i].startswith("-"):
            if tokens[i] in ("-C", "-c"):
                i += 2
            else:
                i += 1
        if i < len(tokens):
            return f"git {tokens[i]}"
        return "git"

    if tokens[0] == "env":
        i = 1
        while i < len(tokens) and "=" in tokens[i]:
            i += 1
        tokens = tokens[i:]
        if not tokens:
            return "env"

    cmd = tokens[0]
    if cmd in {"npm", "mix", "gh", "bundle", "asdf", "cargo", "pnpm", "yarn", "brew"}:
        if len(tokens) > 1 and not tokens[1].startswith("-"):
            return f"{cmd} {tokens[1]}"
    return cmd


def signature_for(tool: str, tool_input: dict) -> tuple[str, str]:
    """Return (signature, raw_snippet) for logging."""
    if tool == "Bash":
        raw = str(tool_input.get("command", ""))[:200]
        return _bash_signature(raw), raw
    if tool in ("Edit", "Write", "Read", "NotebookEdit"):
        path = str(tool_input.get("file_path") or tool_input.get("notebook_path") or "")
        return f"{tool}({path})", path[:200]
    if tool in ("Grep", "Glob"):
        return tool, str(tool_input.get("pattern", ""))[:200]
    if tool.startswith("mcp__"):
        return tool, ""
    return tool, ""


def main() -> int:
    try:
        payload = read_stdin_json()
        tool = payload.get("tool_name") or payload.get("tool") or ""
        tool_input = payload.get("tool_input") or payload.get("input") or {}
        if not tool:
            return 0

        sig, raw = signature_for(tool, tool_input if isinstance(tool_input, dict) else {})

        session_id = (
            os.environ.get("CLAUDE_SESSION_ID")
            or payload.get("session_id")
            or "unknown"
        )
        log_dir = Path(resolve_vault()) / "permission-log"
        log_dir.mkdir(parents=True, exist_ok=True)
        log_path = log_dir / f"{session_id}.jsonl"

        record = {
            "ts": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
            "tool": tool,
            "signature": sig,
            "raw": raw,
        }
        with log_path.open("a") as f:
            f.write(json.dumps(record) + "\n")
    except Exception:
        pass
    return 0


if __name__ == "__main__":
    sys.exit(main())
