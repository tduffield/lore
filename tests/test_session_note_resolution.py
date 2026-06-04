"""Session-note resolution: by session-id (exact, cwd-independent) and by a
robust worktree-name detection that matches how the note filename is created.

These cover the resolver in `vault.py` plus the `lore session-note` CLI
subcommand that fronts it. The motivating bug: callers degraded to a fuzzy
worktree+mtime guess because the session-id was never consulted.
"""

import importlib.util
import os
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).parent.parent
PLUGIN_ROOT = REPO_ROOT / "plugins" / "lore"
SCRIPTS_DIR = PLUGIN_ROOT / "scripts"
CLI_PATH = PLUGIN_ROOT / "cli" / "lore"


def load_script(name: str):
    if str(SCRIPTS_DIR) not in sys.path:
        sys.path.insert(0, str(SCRIPTS_DIR))
    for cached in (name, "vault", "frontmatter", "status_validator", "sessions", "config"):
        sys.modules.pop(cached, None)
    spec = importlib.util.spec_from_file_location(name, SCRIPTS_DIR / f"{name}.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def run_cli(args, env=None, cwd=None):
    full_env = dict(os.environ)
    # Drop session-id env that the host shell may carry, so tests are hermetic.
    for k in ("CLAUDE_CODE_SESSION_ID", "CLAUDE_SESSION_ID", "CLAUDE_PROJECT_DIR"):
        full_env.pop(k, None)
    if env:
        full_env.update(env)
    return subprocess.run(
        [sys.executable, str(CLI_PATH), *args],
        capture_output=True, text=True, env=full_env, cwd=cwd,
    )


def _write_note(sessions_dir: Path, stem: str, worktree: str, session_id: str = "") -> Path:
    p = sessions_dir / f"{stem}-{worktree}.md"
    sid_line = f"session_id: {session_id}\n" if session_id else "session_id:\n"
    p.write_text(
        "---\n"
        "type: session\n"
        f"worktree: {worktree}\n"
        f"{sid_line}"
        "status: active\n"
        "---\n\n"
        f"# Session: {worktree}\n"
        # A body line that mentions a session_id-looking string must NOT match.
        f"\nNote: earlier session_id: decoy-{session_id or 'x'} referenced here.\n"
    )
    return p


# ---------------------------------------------------------------------------
# find_session_note_by_session_id
# ---------------------------------------------------------------------------

def test_by_session_id_matches_frontmatter(tmp_path):
    vault = tmp_path / "v"
    sd = vault / "sessions"
    sd.mkdir(parents=True)
    _write_note(sd, "2026-06-01-1000", "alpha", session_id="aaa")
    want = _write_note(sd, "2026-06-02-1000", "beta", session_id="bbb")

    v = load_script("vault")
    assert v.find_session_note_by_session_id(vault, "bbb") == want


def test_by_session_id_ignores_body_mentions(tmp_path):
    """A `session_id:` string in the body must not count — frontmatter only."""
    vault = tmp_path / "v"
    sd = vault / "sessions"
    sd.mkdir(parents=True)
    # Note's real id is 'real'; its body mentions 'decoy-real'. Searching the
    # decoy must miss.
    _write_note(sd, "2026-06-01-1000", "alpha", session_id="real")

    v = load_script("vault")
    assert v.find_session_note_by_session_id(vault, "decoy-real") is None


def test_by_session_id_empty_returns_none(tmp_path):
    vault = tmp_path / "v"
    (vault / "sessions").mkdir(parents=True)
    v = load_script("vault")
    assert v.find_session_note_by_session_id(vault, "") is None


def test_by_session_id_no_sessions_dir_returns_none(tmp_path):
    vault = tmp_path / "v"
    vault.mkdir()
    v = load_script("vault")
    assert v.find_session_note_by_session_id(vault, "aaa") is None


# ---------------------------------------------------------------------------
# detect_worktree_name
# ---------------------------------------------------------------------------

def test_detect_prefers_claude_project_dir(monkeypatch, tmp_path):
    """CLAUDE_PROJECT_DIR basename wins — it is what named the note."""
    monkeypatch.setenv(
        "CLAUDE_PROJECT_DIR",
        "/Users/x/code/orchestrator/.claude/worktrees/my-feature",
    )
    v = load_script("vault")
    # cwd is somewhere unrelated; env must still win.
    assert v.detect_worktree_name(cwd=tmp_path) == "my-feature"


def test_detect_walks_worktrees_segment(monkeypatch, tmp_path):
    """With no CLAUDE_PROJECT_DIR, a `.claude/worktrees/<name>/` segment in a
    sibling-repo or subdir cwd resolves to <name>."""
    monkeypatch.delenv("CLAUDE_PROJECT_DIR", raising=False)
    v = load_script("vault")
    cwd = Path("/Users/x/code/platform/.claude/worktrees/my-feature/apps/platform")
    assert v.detect_worktree_name(cwd=cwd) == "my-feature"


def test_detect_falls_back_to_cwd_basename(monkeypatch, tmp_path):
    monkeypatch.delenv("CLAUDE_PROJECT_DIR", raising=False)
    plain = tmp_path / "just-a-dir"
    plain.mkdir()
    v = load_script("vault")
    assert v.detect_worktree_name(cwd=plain) == "just-a-dir"


def test_detect_uses_git_toplevel_basename(monkeypatch, tmp_path):
    """A subdir of a git repo (not under .claude/worktrees) resolves to the
    repo toplevel basename, not the subdir name."""
    monkeypatch.delenv("CLAUDE_PROJECT_DIR", raising=False)
    repo = tmp_path / "myrepo"
    (repo / "sub").mkdir(parents=True)
    subprocess.run(["git", "init", "-q"], cwd=repo, check=True)
    v = load_script("vault")
    assert v.detect_worktree_name(cwd=repo / "sub") == "myrepo"


# ---------------------------------------------------------------------------
# resolve_session_note (combinator)
# ---------------------------------------------------------------------------

def test_resolve_session_id_beats_newer_worktree_note(tmp_path):
    """The exact session-id match wins even when a NEWER note exists for the
    same worktree — this is the core bug being fixed."""
    vault = tmp_path / "v"
    sd = vault / "sessions"
    sd.mkdir(parents=True)
    mine = _write_note(sd, "2026-06-01-1000", "feat", session_id="mine")
    _write_note(sd, "2026-06-02-1000", "feat", session_id="other")  # newer, same worktree

    v = load_script("vault")
    got = v.resolve_session_note(vault, session_id="mine", worktree_name="feat")
    assert got == mine


def test_resolve_falls_back_to_worktree_when_id_unmatched(tmp_path):
    vault = tmp_path / "v"
    sd = vault / "sessions"
    sd.mkdir(parents=True)
    _write_note(sd, "2026-06-01-1000", "feat", session_id="x")
    newest = _write_note(sd, "2026-06-02-1000", "feat", session_id="y")

    v = load_script("vault")
    # session id 'absent' matches nothing → newest note for worktree 'feat'.
    got = v.resolve_session_note(vault, session_id="absent", worktree_name="feat")
    assert got == newest


# ---------------------------------------------------------------------------
# `lore session-note` CLI
# ---------------------------------------------------------------------------

def test_cli_resolves_via_claude_code_session_id_env(tmp_path):
    vault = tmp_path / "v"
    sd = vault / "sessions"
    sd.mkdir(parents=True)
    _write_note(sd, "2026-06-01-1000", "feat", session_id="old")
    want = _write_note(sd, "2026-06-02-1000", "feat", session_id="live")

    r = run_cli(
        ["session-note"],
        env={"LORE_VAULT": str(vault), "CLAUDE_CODE_SESSION_ID": "live"},
    )
    assert r.returncode == 0, r.stderr
    assert r.stdout.strip() == f"sessions/{want.name}"


def test_cli_session_id_flag_overrides_env(tmp_path):
    vault = tmp_path / "v"
    sd = vault / "sessions"
    sd.mkdir(parents=True)
    want = _write_note(sd, "2026-06-01-1000", "feat", session_id="flagged")
    _write_note(sd, "2026-06-02-1000", "feat", session_id="envid")

    r = run_cli(
        ["session-note", "--session-id", "flagged"],
        env={"LORE_VAULT": str(vault), "CLAUDE_CODE_SESSION_ID": "envid"},
    )
    assert r.returncode == 0, r.stderr
    assert r.stdout.strip() == f"sessions/{want.name}"


def test_cli_worktree_flag_fallback(tmp_path):
    vault = tmp_path / "v"
    sd = vault / "sessions"
    sd.mkdir(parents=True)
    _write_note(sd, "2026-06-01-1000", "alpha", session_id="a")
    want = _write_note(sd, "2026-06-02-1000", "beta", session_id="b")

    # No session id at all → resolve by explicit --worktree.
    r = run_cli(
        ["session-note", "--worktree", "beta"],
        env={"LORE_VAULT": str(vault)},
    )
    assert r.returncode == 0, r.stderr
    assert r.stdout.strip() == f"sessions/{want.name}"


def test_cli_miss_exits_1_with_diagnostic(tmp_path):
    vault = tmp_path / "v"
    (vault / "sessions").mkdir(parents=True)

    r = run_cli(
        ["session-note", "--session-id", "nope", "--worktree", "ghost"],
        env={"LORE_VAULT": str(vault)},
    )
    assert r.returncode == 1
    assert not r.stdout.strip()
    # Diagnostic explains what was tried, so callers don't run exploratory ls.
    assert "session-note" in r.stderr
    assert "nope" in r.stderr
    assert "ghost" in r.stderr
