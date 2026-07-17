#!/usr/bin/env bash
set -euo pipefail

required=(PGHOST PGDATABASE PGUSER PGPASSWORD)
missing=()
for name in "${required[@]}"; do
  if [[ -z "${!name:-}" ]]; then
    missing+=("$name")
  fi
done

if ((${#missing[@]})); then
  echo "Missing required database environment variables: ${missing[*]}" >&2
  exit 2
fi

psql_bin="$(command -v psql || true)"
if [[ -z "$psql_bin" && -x /opt/homebrew/opt/libpq/bin/psql ]]; then
  psql_bin=/opt/homebrew/opt/libpq/bin/psql
fi
if [[ -z "$psql_bin" ]]; then
  echo "psql is required. Install PostgreSQL client tools before deployment." >&2
  exit 3
fi

case "${MT_DEPLOY_ENVIRONMENT:-development}" in
  development|staging) ;;
  production)
    if [[ "${MT_ALLOW_PRODUCTION:-}" != "yes" ]]; then
      echo "Production deployment refused. Set MT_ALLOW_PRODUCTION=yes only after release approval." >&2
      exit 4
    fi
    ;;
  *)
    echo "MT_DEPLOY_ENVIRONMENT must be development, staging, or production." >&2
    exit 5
    ;;
esac

case "${MT_APPLY_PHASE1_BASELINE:-yes}" in
  yes|no) ;;
  *)
    echo "MT_APPLY_PHASE1_BASELINE must be yes or no." >&2
    exit 6
    ;;
esac

root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

echo "Validating migration contracts..."
python3 "$root/scripts/validate_product_phase0.py"
python3 "$root/scripts/validate_supabase_phase1_rls.py"
python3 "$root/scripts/validate_workspace_phase2.py"
python3 "$root/scripts/validate_workspace_asset_scanner.py"

if [[ "${MT_APPLY_PHASE1_BASELINE:-yes}" == "yes" ]]; then
  echo "Applying the Phase 0 schema and Phase 1 Auth/RLS baseline atomically to ${MT_DEPLOY_ENVIRONMENT:-development}..."
  "$psql_bin" --set ON_ERROR_STOP=1 --single-transaction \
    --file "$root/database/product_schema.sql" \
    --file "$root/database/supabase_phase1_auth_rls.sql"
else
  echo "Skipping the Phase 0/1 baseline for an existing database."
fi

shopt -s nullglob
migration_files=("$root"/database/migrations/*.sql)
shopt -u nullglob
for migration_file in "${migration_files[@]}"; do
  echo "Applying incremental migration $(basename "$migration_file")..."
  "$psql_bin" --set ON_ERROR_STOP=1 --file "$migration_file"
done

echo "Supabase database deployment completed. Run the security boundary checks next."
