#!/usr/bin/env bash
set -euo pipefail

if [[ "${MT_RELEASE_APPROVED:-}" != "yes" ]]; then
  echo "Release build refused. Set MT_RELEASE_APPROVED=yes only after the release gate passes." >&2
  exit 2
fi

root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
ref="${1:-HEAD}"
output_dir="${2:-$root/dist}"

if [[ -n "$(git -C "$root" status --porcelain --untracked-files=normal)" ]]; then
  echo "Release build refused: the Git worktree is not clean." >&2
  exit 3
fi

commit="$(git -C "$root" rev-parse --verify "${ref}^{commit}")"
release_id="$(git -C "$root" describe --tags --exact-match "$commit" 2>/dev/null || true)"
if [[ -z "$release_id" ]]; then
  echo "Release build refused: the selected commit must have an exact Git tag." >&2
  exit 4
fi
if [[ ! "$release_id" =~ ^[A-Za-z0-9][A-Za-z0-9._-]{0,95}$ ]]; then
  echo "Release build refused: the exact tag is not a safe release identifier." >&2
  exit 5
fi

mkdir -p "$output_dir"
archive_name="mt-presence-${release_id}.tar.gz"
archive="$output_dir/$archive_name"
git -C "$root" archive --format=tar.gz --output="$archive" "$commit"

(
  cd "$output_dir"
  if command -v sha256sum >/dev/null 2>&1; then
    sha256sum "$archive_name" > "$archive_name.sha256"
  else
    shasum -a 256 "$archive_name" > "$archive_name.sha256"
  fi
)

echo "Built $archive from $commit"
