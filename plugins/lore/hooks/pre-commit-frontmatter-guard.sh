#!/usr/bin/env bash
# pre-commit-frontmatter-guard.sh — reject commits that introduce notes missing
# required frontmatter (type / group / per-type required fields) or an invalid
# group value. Field-name drift is reported as a warning but does not block.
#
# Shipped as part of the lore plugin. install-vault-hooks.sh wires a thin
# wrapper into a vault's .git/hooks/pre-commit that sets LORE_PLUGIN_ROOT and
# delegates here, alongside the status guard.
#
# OPT-IN: this guard is a no-op unless the vault declares its group vocabulary
# in a `.lore-groups` file at the repo root. That file's presence enables the
# guard (group becomes required) and its lines are the allowed group values
# ('*' = any). Vaults that don't use groups are unaffected.
#
# Validates staged .md files (diff-filter=ACM). Skips deleted files, non-.md
# files, and paths outside the vault note space (.claude/, .templates/,
# templates/, .pytest_cache/, .obsidian/) — those are not lore notes. Files
# with no frontmatter block (generated/data files) validate clean.
#
# Exits 0 when clean, 1 (with offending file+reason) on any error.

set -euo pipefail

# Opt-in gate: find the repo root and bail out unless .lore-groups exists.
ROOT="$(git rev-parse --show-toplevel 2>/dev/null || pwd)"
GROUP_CONFIG="$ROOT/.lore-groups"
if [ ! -f "$GROUP_CONFIG" ]; then
    exit 0
fi

# Export group enforcement for the validator (require + comma-joined allowlist;
# '*'/comments/blank lines mean "any value").
export LORE_REQUIRE_GROUP=1
LORE_GROUPS="$(grep -vE '^\s*(#|\*|$)' "$GROUP_CONFIG" 2>/dev/null | tr '\n' ',' | sed 's/,$//')"
export LORE_GROUPS

if [ -z "${LORE_PLUGIN_ROOT:-}" ]; then
    if [ -n "${LORE_GUARD_STRICT:-}" ]; then
        echo "lore frontmatter guard: LORE_PLUGIN_ROOT not set — reinstall with \`lore init\` or the hook installer; commit blocked" >&2
        exit 1
    fi
    echo "pre-commit-frontmatter-guard: LORE_PLUGIN_ROOT not set — skipping guard" >&2
    exit 0
fi

VALIDATOR="$LORE_PLUGIN_ROOT/scripts/frontmatter_validator.py"

if [ ! -f "$VALIDATOR" ]; then
    if [ -n "${LORE_GUARD_STRICT:-}" ]; then
        echo "lore frontmatter guard: validator not found at $VALIDATOR — reinstall with \`lore init\` or the hook installer; commit blocked" >&2
        exit 1
    fi
    echo "pre-commit-frontmatter-guard: validator not found at $VALIDATOR — skipping" >&2
    exit 0
fi

# Paths outside the vault note space — not lore notes, never validated here.
is_excluded() {
    case "$1" in
        .claude/*|.templates/*|templates/*|.pytest_cache/*|.obsidian/*) return 0 ;;
        *) return 1 ;;
    esac
}

staged_files=()
while IFS= read -r -d '' file; do
    case "$file" in
        *.md) is_excluded "$file" || staged_files+=("$file") ;;
    esac
done < <(git diff --cached -z --name-only --diff-filter=ACM 2>/dev/null || true)

if [ "${#staged_files[@]}" -eq 0 ]; then
    exit 0
fi

# Validate STAGED blob content (not working-tree files) so that fixing the
# working copy without re-staging cannot fool the guard.
tmp_dir="$(mktemp -d)"
trap 'rm -rf "$tmp_dir"' EXIT

validator_exit=0
violations=()

for f in "${staged_files[@]}"; do
    tmp_file="$tmp_dir/staged.md"
    if ! git show ":$f" > "$tmp_file" 2>/dev/null; then
        continue
    fi
    rc=0
    raw_out="$(python3 "$VALIDATOR" "$tmp_file" 2>&1)" || rc=$?
    if [ "$rc" -ne 0 ]; then
        validator_exit=1
        detail="$(echo "$raw_out" | grep -v '^frontmatter-validator' | sed "s|$tmp_file|$f|g" | sed '/^[[:space:]]*$/d')"
        violations+=("$detail")
    fi
done

if [ "$validator_exit" -ne 0 ]; then
    echo "" >&2
    echo "pre-commit rejected: notes missing required frontmatter:" >&2
    echo "" >&2
    for v in "${violations[@]}"; do
        echo "$v" >&2
    done
    echo "" >&2
    echo "See the vault's docs/frontmatter-glossary.md for required fields, or run \`lore validate\`." >&2
    echo "" >&2
    exit 1
fi

exit 0
