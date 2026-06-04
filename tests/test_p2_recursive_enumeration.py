"""Slice 2: recursive YYYY-MM bucket enumeration across the lore toolchain.

Every session/plan/spec/design enumeration must recurse exactly one level into
``<folder>/YYYY-MM/`` while still finding notes at the flat top level
(behavior-neutral until the migration runs). The out-of-scope living folders
(deferred/dead-ends/lessons/radar) must keep flat globbing.

TDD: tests written before implementation. All fixtures are SYNTHETIC.
"""
from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).parent.parent
PLUGIN_ROOT = REPO_ROOT / "plugins" / "lore"
SCRIPTS_DIR = PLUGIN_ROOT / "scripts"


def load_script(name: str):
    """Load a module from plugins/lore/scripts/ freshly (no cache)."""
    if str(SCRIPTS_DIR) not in sys.path:
        sys.path.insert(0, str(SCRIPTS_DIR))
    for cached in (name, "vault", "frontmatter", "status_validator", "sessions",
                   "config", "recall", "reflect_sessions"):
        sys.modules.pop(cached, None)
    spec = importlib.util.spec_from_file_location(name, SCRIPTS_DIR / f"{name}.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _session_note(
    vault: Path,
    rel: str,
    *,
    worktree: str = "alpha-worktree",
    status: str = "active",
    started: str = "2026-06-01T10:00:00Z",
    ended: str | None = None,
) -> Path:
    """Write a synthetic session note at ``vault/sessions/<rel>``."""
    path = vault / "sessions" / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    ended_line = f"ended: {ended}" if ended else "ended:"
    path.write_text(
        "---\n"
        "type: session\n"
        "project: test-project\n"
        f"worktree: {worktree}\n"
        "branch: feature-branch\n"
        f"started: {started}\n"
        f"{ended_line}\n"
        "subsystems: []\n"
        "phase: Orient\n"
        f"status: {status}\n"
        "---\n\n"
        f"# Session: {worktree}\n\n"
        "## What we did\n\n## Decided\n\n## Deferred\n\n## Learned\n\n## Open questions\n"
    )
    return path


@pytest.fixture
def vault(tmp_path: Path) -> Path:
    v = tmp_path / "testvault"
    (v / "sessions").mkdir(parents=True)
    return v


# ---------------------------------------------------------------------------
# vault.find_session_note
# ---------------------------------------------------------------------------

class TestFindSessionNote:
    def test_finds_flat(self, vault):
        flat = _session_note(vault, "2026-06-01-1000-alpha-worktree.md")
        v = load_script("vault")
        assert v.find_session_note(vault, "alpha-worktree") == flat

    def test_finds_bucketed(self, vault):
        bucketed = _session_note(vault, "2026-06/2026-06-01-1000-alpha-worktree.md")
        v = load_script("vault")
        assert v.find_session_note(vault, "alpha-worktree") == bucketed

    def test_newest_across_buckets_by_stem(self, vault):
        """Newest derives from the filename stem, not the parent-dir name."""
        _session_note(vault, "2026-05/2026-05-10-0900-alpha-worktree.md")
        newest = _session_note(vault, "2026-06/2026-06-20-1100-alpha-worktree.md")
        v = load_script("vault")
        assert v.find_session_note(vault, "alpha-worktree") == newest

    def test_newest_flat_beats_older_bucket(self, vault):
        _session_note(vault, "2026-05/2026-05-10-0900-alpha-worktree.md")
        flat_newest = _session_note(vault, "2026-07-01-0800-alpha-worktree.md")
        v = load_script("vault")
        assert v.find_session_note(vault, "alpha-worktree") == flat_newest


# ---------------------------------------------------------------------------
# sessions.all_session_notes_for_worktree
# ---------------------------------------------------------------------------

class TestAllSessionNotes:
    def test_finds_flat_and_bucketed(self, vault):
        flat = _session_note(vault, "2026-07-01-0800-alpha-worktree.md")
        bucketed = _session_note(vault, "2026-06/2026-06-01-1000-alpha-worktree.md")
        sessions = load_script("sessions")
        result = sessions.all_session_notes_for_worktree(vault, "alpha-worktree")
        assert set(result) == {flat, bucketed}

    def test_newest_first_across_buckets(self, vault):
        older = _session_note(vault, "2026-05/2026-05-10-0900-alpha-worktree.md")
        newer = _session_note(vault, "2026-06/2026-06-20-1100-alpha-worktree.md")
        sessions = load_script("sessions")
        assert sessions.all_session_notes_for_worktree(vault, "alpha-worktree") == [newer, older]

    def test_other_worktree_excluded(self, vault):
        mine = _session_note(vault, "2026-06/2026-06-01-1000-alpha-worktree.md")
        _session_note(vault, "2026-06/2026-06-02-1000-beta-worktree.md", worktree="beta-worktree")
        sessions = load_script("sessions")
        assert sessions.all_session_notes_for_worktree(vault, "alpha-worktree") == [mine]


# ---------------------------------------------------------------------------
# sessions.session_note_path
# ---------------------------------------------------------------------------

class TestSessionNotePath:
    def test_finds_bucketed(self, vault):
        bucketed = _session_note(vault, "2026-06/2026-06-01-1000-alpha-worktree.md")
        sessions = load_script("sessions")
        assert sessions.session_note_path(vault, "alpha-worktree") == bucketed

    def test_newest_across_buckets(self, vault):
        _session_note(vault, "2026-05/2026-05-10-0900-alpha-worktree.md")
        newest = _session_note(vault, "2026-06/2026-06-20-1100-alpha-worktree.md")
        sessions = load_script("sessions")
        assert sessions.session_note_path(vault, "alpha-worktree") == newest


# ---------------------------------------------------------------------------
# sessions.sweep_orphan_skeletons
# ---------------------------------------------------------------------------

class TestSweepOrphanSkeletons:
    def test_sweeps_bucketed_skeleton(self, vault):
        import os
        import time
        skeleton = _session_note(vault, "2026-06/2026-06-01-1000-beta-worktree.md", worktree="beta-worktree")
        # Make it old enough to be eligible for sweep.
        old = time.time() - 60 * 60
        os.utime(skeleton, (old, old))
        sessions = load_script("sessions")
        deleted = sessions.sweep_orphan_skeletons(vault, exclude=set())
        assert skeleton in deleted
        assert not skeleton.exists()

    def test_excludes_passed_bucketed_note(self, vault):
        import os
        import time
        keep = _session_note(vault, "2026-06/2026-06-01-1000-alpha-worktree.md")
        old = time.time() - 60 * 60
        os.utime(keep, (old, old))
        sessions = load_script("sessions")
        deleted = sessions.sweep_orphan_skeletons(vault, exclude={keep})
        assert keep not in deleted
        assert keep.exists()


# ---------------------------------------------------------------------------
# sessions.find_shelved_notes
# ---------------------------------------------------------------------------

class TestFindShelvedNotes:
    def test_finds_bucketed_shelved(self, vault):
        shelved = _session_note(
            vault, "2026-06/2026-06-01-1000-alpha-worktree.md",
            status="shelved", ended="2026-06-01T11:00:00Z",
        )
        sessions = load_script("sessions")
        assert sessions.find_shelved_notes(vault) == [shelved]

    def test_finds_flat_and_bucketed_shelved(self, vault):
        flat = _session_note(
            vault, "2026-07-01-0800-alpha-worktree.md",
            status="shelved", ended="2026-07-01T09:00:00Z",
        )
        bucketed = _session_note(
            vault, "2026-06/2026-06-01-1000-beta-worktree.md",
            worktree="beta-worktree", status="shelved", ended="2026-06-01T11:00:00Z",
        )
        sessions = load_script("sessions")
        assert sessions.find_shelved_notes(vault) == [flat, bucketed]


# ---------------------------------------------------------------------------
# sessions.get_vault_stats
# ---------------------------------------------------------------------------

class TestGetVaultStats:
    def test_counts_flat_and_bucketed_sessions(self, vault):
        _session_note(vault, "2026-07-01-0800-alpha-worktree.md")
        _session_note(vault, "2026-06/2026-06-01-1000-beta-worktree.md", worktree="beta-worktree")
        sessions = load_script("sessions")
        stats = sessions.get_vault_stats(vault)
        assert stats["sessions"] == 2

    def test_deferred_stays_flat(self, vault):
        """Out-of-scope deferred folder must NOT recurse."""
        deferred = vault / "deferred"
        (deferred / "2026-06").mkdir(parents=True)
        (deferred / "2026-06" / "bucketed.md").write_text(
            "---\ntype: deferred\nstatus: open\n---\n# Bucketed\n"
        )
        (deferred / "flat.md").write_text(
            "---\ntype: deferred\nstatus: open\n---\n# Flat\n"
        )
        sessions = load_script("sessions")
        stats = sessions.get_vault_stats(vault)
        assert stats["open_deferred"] == 1


# ---------------------------------------------------------------------------
# recall._recent_sessions (recursive) vs out-of-scope folders (flat)
# ---------------------------------------------------------------------------

class TestRecallRecursion:
    def _subsystem(self, vault: Path):
        sub = vault / "subsystems"
        sub.mkdir(parents=True, exist_ok=True)
        (sub / "widget-flow.md").write_text(
            "---\ntype: subsystem\nkeywords: [widget]\n---\n# widget-flow\n"
        )

    def _session_with_subsystem(self, vault: Path, rel: str):
        path = vault / "sessions" / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            "---\ntype: session\nproject: test-project\n"
            'subsystems: ["widget-flow"]\nstatus: active\n---\n# Session\n'
        )
        return path

    def test_recent_sessions_recurses(self, vault):
        self._subsystem(vault)
        self._session_with_subsystem(vault, "2026-06/2026-06-01-1000-alpha-worktree.md")
        recall = load_script("recall")
        hits = recall._recent_sessions(vault, {"widget-flow"}, "test-project")
        assert len(hits) == 1

    def test_deferred_recall_stays_flat(self, vault):
        """recall deferred lookup must not pick up a bucketed deferred note."""
        deferred = vault / "deferred"
        (deferred / "2026-06").mkdir(parents=True)
        (deferred / "2026-06" / "bucketed.md").write_text(
            "---\ntype: deferred\nstatus: open\nsurfaces: [widget-flow]\n---\n# Bucketed\n"
        )
        recall = load_script("recall")
        hits = recall._relevant_deferred(vault, {"widget-flow"}, "test-project")
        assert hits == []


# ---------------------------------------------------------------------------
# reflect_sessions
# ---------------------------------------------------------------------------

class TestReflectSessions:
    def test_finds_bucketed_in_window(self, vault):
        _session_note(
            vault, "2026-06/2026-06-15-1000-alpha-worktree.md",
            status="complete", ended="2026-06-15T11:00:00Z",
        )
        rs = load_script("reflect_sessions")
        result = rs.sessions_in_window(vault, "2026-06", "2026-06-01", "2026-06-30")
        assert len(result) == 1

    def test_finds_flat_and_bucketed_in_window(self, vault):
        _session_note(
            vault, "2026-06-10-0800-alpha-worktree.md",
            status="complete", ended="2026-06-10T09:00:00Z",
        )
        _session_note(
            vault, "2026-06/2026-06-15-1000-beta-worktree.md",
            worktree="beta-worktree", status="complete", ended="2026-06-15T11:00:00Z",
        )
        rs = load_script("reflect_sessions")
        result = rs.sessions_in_window(vault, "2026-06", "2026-06-01", "2026-06-30")
        assert len(result) == 2


# ---------------------------------------------------------------------------
# Iterator scoping: underscore skip + one-level depth
# ---------------------------------------------------------------------------

class TestIteratorScoping:
    def test_skips_underscore_file(self, vault):
        _session_note(vault, "2026-06/2026-06-01-1000-alpha-worktree.md")
        (vault / "sessions" / "_index.md").write_text(
            "---\ntype: session\nstatus: active\n---\n# Index\n"
        )
        sessions = load_script("sessions")
        names = {p.name for p in sessions.all_session_notes_for_worktree(vault, "alpha-worktree")}
        assert "_index.md" not in names

    def test_skips_underscore_dir(self, vault):
        _session_note(vault, "_test/2026-06-01-1000-alpha-worktree.md")
        sessions = load_script("sessions")
        assert sessions.all_session_notes_for_worktree(vault, "alpha-worktree") == []

    def test_does_not_descend_two_levels(self, vault):
        deep = vault / "sessions" / "2026-06" / "extra"
        deep.mkdir(parents=True)
        _session_note(vault, "2026-06/extra/2026-06-01-1000-alpha-worktree.md")
        sessions = load_script("sessions")
        assert sessions.all_session_notes_for_worktree(vault, "alpha-worktree") == []
