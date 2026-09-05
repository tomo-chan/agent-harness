#!/usr/bin/env bash
set -euo pipefail

# Deterministic example gate. Customize verification commands per repository.

expected_branch_regex="${EXPECTED_BRANCH_REGEX:-^feature/}"
branch="$(git branch --show-current)"

if [[ ! "$branch" =~ $expected_branch_regex ]]; then
  echo "completion gate: unexpected branch: $branch" >&2
  exit 20
fi

if [[ -n "$(git status --porcelain)" ]]; then
  echo "completion gate: worktree is dirty" >&2
  git status --short >&2
  exit 21
fi

if [[ -n "${VERIFY_COMMAND:-}" ]]; then
  echo "completion gate: running verification command"
  bash -lc "$VERIFY_COMMAND"
fi

if ! git rev-parse HEAD >/dev/null 2>&1; then
  echo "completion gate: no commit exists" >&2
  exit 22
fi

if [[ "${REQUIRE_UPSTREAM:-1}" == "1" ]]; then
  upstream="$(git rev-parse --abbrev-ref --symbolic-full-name '@{u}' 2>/dev/null || true)"
  if [[ -z "$upstream" ]]; then
    echo "completion gate: branch has no upstream" >&2
    exit 23
  fi
fi

echo "completion gate: PASS ($branch)"
