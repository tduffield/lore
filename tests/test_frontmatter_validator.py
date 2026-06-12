"""Frontmatter validator tests.

The validator answers: does a note's frontmatter carry the required universal
(`type`, and `group` when the vault opts in) and per-type fields, is `group` a
valid value, and does any field name show known drift?

Groups are opt-in: a `.lore-groups` file at the vault root enables group
enforcement and lists the allowed values. All fixtures use SYNTHETIC vocabulary
(synth-* / alpha / beta) per the public-repo fixture discipline — never real
vault content, never private group names.

Contract:
- Missing `type` → ERROR (always).
- With group enforcement: missing `group` → ERROR; value outside the allowlist
  → ERROR; blank group (one-off) → OK.
- Without group enforcement: `group` is not checked.
- Missing a per-type required field → ERROR.
- Drifted field name (e.g. `subsystems`, `revisit_when`) → WARNING (non-fatal).
- A file with no frontmatter block (generated/data file) → skipped, no issues.
- CLI exits 1 on ERROR, 0 when only warnings; group enforcement driven by
  `.lore-groups`.
"""
from __future__ import annotations

from conftest import load_script


def _v():
    return load_script("frontmatter_validator")


def _sev(issues):
    return {i.severity for i in issues}


def _msgs(issues):
    return " | ".join(i.message for i in issues)


# ---------------------------------------------------------------------------
# Schema constants + group config
# ---------------------------------------------------------------------------

class TestSchema:
    def test_type_always_universal(self):
        s = load_script("frontmatter_schema")
        assert "type" in s.UNIVERSAL_REQUIRED

    def test_no_hardcoded_group_vocab(self):
        """Lore ships no group vocabulary — it's vault-configured."""
        s = load_script("frontmatter_schema")
        assert not hasattr(s, "GROUP_VOCAB")

    def test_blank_group_allowed(self):
        s = load_script("frontmatter_schema")
        assert s.is_valid_group("", frozenset({"alpha"})) is True
        assert s.is_valid_group("alpha", frozenset({"alpha"})) is True
        assert s.is_valid_group("nope", frozenset({"alpha"})) is False
        assert s.is_valid_group("anything", None) is True  # unconstrained
        assert s.is_valid_group(None, None) is False

    def test_required_fields_per_type(self):
        s = load_script("frontmatter_schema")
        assert "started" in s.required_fields("session")
        assert s.required_fields("reference") == ()  # unknown type: no extras

    def test_status_not_required(self):
        s = load_script("frontmatter_schema")
        for t in ("session", "deferred", "lesson", "plan"):
            assert "status" not in s.required_fields(t)

    def test_type_dir_alias(self):
        s = load_script("frontmatter_schema")
        assert s.canonical_type("sessions") == "session"
        assert s.required_fields("lessons") == s.required_fields("lesson")

    def test_group_config_absent(self, tmp_path):
        s = load_script("frontmatter_schema")
        assert s.group_config(tmp_path) == (False, None)

    def test_group_config_with_values(self, tmp_path):
        s = load_script("frontmatter_schema")
        (tmp_path / ".lore-groups").write_text("# my groups\nalpha\nbeta\n")
        require, allowed = s.group_config(tmp_path)
        assert require is True
        assert allowed == frozenset({"alpha", "beta"})

    def test_group_config_wildcard(self, tmp_path):
        s = load_script("frontmatter_schema")
        (tmp_path / ".lore-groups").write_text("*\n")
        assert s.group_config(tmp_path) == (True, None)


# ---------------------------------------------------------------------------
# validate_meta — required fields
# ---------------------------------------------------------------------------

class TestRequired:
    def test_complete_note_passes_without_group_enforcement(self):
        v = _v()
        meta = {"type": "deferred", "status": "open",
                "surfaces": ["synth-alpha"], "raised": "2026-01-01"}
        assert v.validate_meta(meta) == []

    def test_missing_type(self):
        v = _v()
        issues = v.validate_meta({"group": "alpha"})
        assert v.ERROR in _sev(issues)
        assert "type" in _msgs(issues)

    def test_group_not_checked_when_not_required(self):
        v = _v()
        meta = {"type": "lesson", "date": "x", "areas": [], "phases": [], "severity": "low"}
        assert v.validate_meta(meta, require_group=False) == []

    def test_missing_group_when_required(self):
        v = _v()
        meta = {"type": "lesson", "date": "x", "areas": [], "phases": [], "severity": "low"}
        issues = v.validate_meta(meta, require_group=True)
        assert any(i.severity == v.ERROR and "group" in i.message for i in issues)

    def test_blank_group_ok_when_required(self):
        v = _v()
        meta = {"type": "session", "group": "", "project": "x", "worktree": "x",
                "branch": "x", "started": "x", "ended": "x"}
        assert v.validate_meta(meta, require_group=True, allowed_groups=frozenset({"alpha"})) == []

    def test_group_value_outside_allowlist(self):
        v = _v()
        meta = {"type": "lesson", "group": "banana", "date": "x", "areas": [],
                "phases": [], "severity": "low"}
        issues = v.validate_meta(meta, require_group=True, allowed_groups=frozenset({"alpha", "beta"}))
        assert any(i.severity == v.ERROR and "group" in i.message for i in issues)

    def test_missing_per_type_required_field(self):
        v = _v()
        issues = v.validate_meta({"type": "deferred"})
        msgs = _msgs(issues)
        assert "surfaces" in msgs and "raised" in msgs
        assert v.ERROR in _sev(issues)

    def test_empty_required_value_is_present(self):
        v = _v()
        meta = {"type": "deferred", "surfaces": "", "raised": ""}
        assert v.validate_meta(meta) == []


# ---------------------------------------------------------------------------
# Drift
# ---------------------------------------------------------------------------

class TestDrift:
    def test_subsystems_alias_warns(self):
        v = _v()
        meta = {"type": "lesson", "date": "x", "subsystems": [],
                "phases": [], "severity": "low", "areas": []}
        issues = v.validate_meta(meta)
        assert v.WARN in _sev(issues)
        assert any("subsystems" in i.message and "areas" in i.message
                   for i in issues if i.severity == v.WARN)

    def test_drift_is_not_fatal(self):
        v = _v()
        meta = {"type": "deferred", "surfaces": [], "raised": "x", "revisit_when": "later"}
        issues = v.validate_meta(meta)
        assert v.ERROR not in _sev(issues)
        assert v.WARN in _sev(issues)

    def test_strict_flags_unknown_field(self):
        v = _v()
        meta = {"type": "lesson", "date": "x", "areas": [], "phases": [],
                "severity": "low", "totally_made_up": 1}
        assert not any("totally_made_up" in i.message for i in v.validate_meta(meta, strict=False))
        assert any("totally_made_up" in i.message for i in v.validate_meta(meta, strict=True))


# ---------------------------------------------------------------------------
# validate_file
# ---------------------------------------------------------------------------

class TestFile:
    def test_no_frontmatter_skipped(self, tmp_path):
        v = _v()
        f = tmp_path / "generated.md"
        f.write_text("# Daily dump\n\nrow1\nrow2\n")
        assert v.validate_file(f) == []

    def test_valid_note_file(self, tmp_path):
        v = _v()
        f = tmp_path / "n.md"
        f.write_text("---\ntype: lesson\ndate: 2026-01-01\n"
                     "areas: []\nphases: []\nseverity: low\n---\n\nbody\n")
        assert v.validate_file(f) == []

    def test_cli_exit_1_on_error(self, tmp_path, capsys):
        v = _v()
        f = tmp_path / "bad.md"
        f.write_text("---\ntype: deferred\n---\nbody\n")  # missing required fields
        rc = v.main([str(f)])
        assert rc == 1
        assert "invalid frontmatter" in capsys.readouterr().err

    def test_cli_exit_0_on_warning_only(self, tmp_path, capsys):
        v = _v()
        f = tmp_path / "drift.md"
        f.write_text("---\ntype: deferred\nsurfaces: []\n"
                     "raised: x\nrevisit_when: later\n---\nbody\n")
        rc = v.main([str(f)])
        assert rc == 0
        assert "drift warning" in capsys.readouterr().err


# ---------------------------------------------------------------------------
# `lore validate` end-to-end (subprocess against a temp vault)
# ---------------------------------------------------------------------------

import os  # noqa: E402
import subprocess  # noqa: E402
import sys  # noqa: E402

from conftest import CLI_PATH  # noqa: E402


def _run_validate(vault, *flags):
    env = dict(os.environ)
    env["LORE_VAULT"] = str(vault)
    return subprocess.run(
        [sys.executable, str(CLI_PATH), "validate", *flags],
        capture_output=True, text=True, env=env,
    )


class TestValidateCommand:
    def _note(self, vault, rel, body):
        p = vault / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(body)

    def _opt_in(self, vault):
        vault.mkdir(parents=True, exist_ok=True)
        (vault / ".lore-groups").write_text("alpha\nbeta\n")

    def test_clean_vault_exits_0(self, tmp_path):
        vault = tmp_path / "vault"
        self._opt_in(vault)
        self._note(vault, "lessons/2026-01/a.md",
                   "---\ntype: lesson\ngroup: alpha\ndate: 2026-01-01\n"
                   "areas: []\nphases: []\nseverity: low\n---\nbody\n")
        r = _run_validate(vault)
        assert r.returncode == 0, r.stdout + r.stderr
        assert "ok:" in r.stdout

    def test_missing_group_fails_when_opted_in(self, tmp_path):
        vault = tmp_path / "vault"
        self._opt_in(vault)
        self._note(vault, "lessons/2026-01/b.md",
                   "---\ntype: lesson\ndate: 2026-01-01\nareas: []\n"
                   "phases: []\nseverity: low\n---\nbody\n")
        r = _run_validate(vault)
        assert r.returncode == 1
        assert "missing required field 'group'" in r.stdout
        assert "FAIL" in r.stdout

    def test_group_not_required_without_optin(self, tmp_path):
        vault = tmp_path / "vault"
        # no .lore-groups → group not enforced
        self._note(vault, "lessons/2026-01/b.md",
                   "---\ntype: lesson\ndate: 2026-01-01\nareas: []\n"
                   "phases: []\nseverity: low\n---\nbody\n")
        r = _run_validate(vault)
        assert r.returncode == 0, r.stdout + r.stderr

    def test_group_value_constrained(self, tmp_path):
        vault = tmp_path / "vault"
        self._opt_in(vault)
        self._note(vault, "lessons/2026-01/c.md",
                   "---\ntype: lesson\ngroup: gamma\ndate: 2026-01-01\n"
                   "areas: []\nphases: []\nseverity: low\n---\nbody\n")
        r = _run_validate(vault)
        assert r.returncode == 1
        assert "invalid group" in r.stdout

    def test_generated_and_archive_files_ignored(self, tmp_path):
        vault = tmp_path / "vault"
        self._opt_in(vault)
        self._note(vault, "deferred/_index.md", "# index\n- x\n")
        self._note(vault, "ops/prod-errors/2026-01-01.md", "# report\n\ndata\n")
        r = _run_validate(vault)
        assert r.returncode == 0, r.stdout + r.stderr

    def test_drift_warns_without_failing(self, tmp_path):
        vault = tmp_path / "vault"
        self._opt_in(vault)
        self._note(vault, "deferred/2026-01/c.md",
                   "---\ntype: deferred\ngroup: alpha\nstatus: open\n"
                   "surfaces: []\nraised: 2026-01-01\nrevisit_when: later\n---\nbody\n")
        r = _run_validate(vault)
        assert r.returncode == 0, r.stdout + r.stderr
        assert "drifted field 'revisit_when'" in r.stdout
