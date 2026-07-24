#!/usr/bin/env bash
set -euo pipefail
umask 077

required=(PGHOST PGDATABASE PGUSER PGPASSWORD MT_BACKUP_DIR)
missing=()
for name in "${required[@]}"; do
  if [[ -z "${!name:-}" ]]; then
    missing+=("$name")
  fi
done
if ((${#missing[@]})); then
  echo "Missing backup environment variables: ${missing[*]}" >&2
  exit 2
fi

pg_dump_bin="$(command -v pg_dump || true)"
if [[ -z "$pg_dump_bin" ]]; then
  echo "pg_dump is required." >&2
  exit 3
fi

timestamp="$(date -u +%Y%m%dT%H%M%SZ)"
mkdir -p "$MT_BACKUP_DIR"
backup="$MT_BACKUP_DIR/mt-presence-${timestamp}.dump"
manifest="$backup.sha256"

"$pg_dump_bin" \
  --format=custom \
  --no-owner \
  --no-privileges \
  --file="$backup" \
  --host="$PGHOST" \
  --port="${PGPORT:-5432}" \
  --username="$PGUSER" \
  "$PGDATABASE"

if command -v sha256sum >/dev/null 2>&1; then
  sha256sum "$backup" > "$manifest"
else
  shasum -a 256 "$backup" > "$manifest"
fi

echo "Database backup completed: $backup"
