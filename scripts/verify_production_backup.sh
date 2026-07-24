#!/usr/bin/env bash
set -euo pipefail

backup="${1:-}"
manifest="${2:-${backup}.sha256}"
if [[ -z "$backup" || ! -f "$backup" || ! -f "$manifest" ]]; then
  echo "Usage: $0 <backup.dump> [backup.dump.sha256]" >&2
  exit 2
fi

pg_restore_bin="$(command -v pg_restore || true)"
if [[ -z "$pg_restore_bin" ]]; then
  echo "pg_restore is required." >&2
  exit 3
fi

expected="$(awk 'NR == 1 { print $1 }' "$manifest")"
if [[ ! "$expected" =~ ^[a-fA-F0-9]{64}$ ]]; then
  echo "Backup SHA-256 manifest is invalid." >&2
  exit 4
fi

if command -v sha256sum >/dev/null 2>&1; then
  actual="$(sha256sum "$backup" | awk '{ print $1 }')"
else
  actual="$(shasum -a 256 "$backup" | awk '{ print $1 }')"
fi
actual_lower="$(printf '%s' "$actual" | tr '[:upper:]' '[:lower:]')"
expected_lower="$(printf '%s' "$expected" | tr '[:upper:]' '[:lower:]')"
if [[ "$actual_lower" != "$expected_lower" ]]; then
  echo "Backup checksum does not match." >&2
  exit 5
fi

listing="$(mktemp)"
trap 'rm -f "$listing"' EXIT
"$pg_restore_bin" --list "$backup" > "$listing"
if ! grep -q " TABLE " "$listing" || ! grep -q " FUNCTION " "$listing"; then
  echo "Backup catalog is incomplete." >&2
  exit 6
fi

echo "Production backup checksum and catalog verification passed."
