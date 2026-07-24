#!/usr/bin/env bash
set -euo pipefail

if [[ "${MT_TEST_ENVIRONMENT:-}" != "development" ]]; then
  echo "Database acceptance refused: MT_TEST_ENVIRONMENT must be development." >&2
  exit 2
fi
if [[ "${MT_ALLOW_PRODUCTION:-}" == "yes" ]]; then
  echo "Database acceptance refused: MT_ALLOW_PRODUCTION=yes is forbidden." >&2
  exit 3
fi

root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$root"
export PYTHONDONTWRITEBYTECODE=1

tests=(
  scripts/test_user_dashboard_database.py
  scripts/test_public_delivery_database.py
  scripts/test_admin_works_database.py
  scripts/test_admin_users_database.py
  scripts/test_communications_audit_database.py
)

for test_file in "${tests[@]}"; do
  printf '\n==> Rollback-only database acceptance: %s\n' "$test_file"
  python3 "$test_file"
done

printf '\nRollback-only database acceptance gate passed.\n'
