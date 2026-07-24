#!/usr/bin/env bash
set -euo pipefail

root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$root"

export PYTHONDONTWRITEBYTECODE=1

run_group() {
  local label="$1"
  shift
  printf '\n==> %s\n' "$label"
  "$@"
}

static_validators=(
  scripts/validate_local_archive_db.py
  scripts/validate_product_phase0.py
  scripts/validate_auth_foundation.py
  scripts/validate_supabase_phase1_rls.py
  scripts/validate_workspace_phase2.py
  scripts/validate_workspace_asset_scanner.py
  scripts/validate_review_queue_phase3.py
  scripts/validate_public_delivery.py
  scripts/validate_user_dashboard.py
  scripts/validate_profile_avatar.py
  scripts/validate_admin_works.py
  scripts/validate_admin_users.py
  scripts/validate_communications_audit.py
  scripts/validate_interaction_integrity.py
  scripts/validate_production_deployment.py
)

browser_scripts=(
  auth.js
  mfa.js
  account-settings.js
  upload-studio.js
  admin-reviews.js
  admin-works.js
  admin-users.js
  admin-audit.js
  dashboard.js
  account-menu.js
  site-footer.js
  public-navigation.js
  archive.js
  public-archive.js
  lightbox.js
  contact.js
  notifications.js
  inbox.js
  creator.js
  manage.js
)

boundary_tests=(
  scripts/test_header_identity_boundary.py
  scripts/test_auth_security_boundary.py
  scripts/test_workspace_phase2_boundary.py
  scripts/test_configure_development_scanner.py
  scripts/test_workspace_asset_scanner.py
  scripts/test_review_queue_boundary.py
  scripts/test_public_delivery_boundary.py
  scripts/test_user_dashboard_boundary.py
  scripts/test_admin_works_boundary.py
  scripts/test_admin_users_boundary.py
  scripts/test_communications_audit_boundary.py
  scripts/test_supabase_deploy_script.py
)

production_tests=(
  scripts/test_production_health.py
  scripts/test_production_preflight.py
  scripts/test_manage_production_release.py
  scripts/test_verify_production.py
)

run_group "Python syntax" python3 -m py_compile \
  server.py \
  workers/image_probe.py \
  workers/image_scanner.py \
  workers/scan_adapters.py \
  scripts/production_release_contract.py \
  scripts/production_preflight.py \
  scripts/manage_production_release.py \
  scripts/verify_production.py \
  "${static_validators[@]}" \
  "${boundary_tests[@]}" \
  "${production_tests[@]}"

run_group "Shell syntax" bash -n \
  scripts/release_gate.sh \
  scripts/database_acceptance_gate.sh \
  scripts/build_production_release.sh \
  scripts/backup_production_database.sh \
  scripts/verify_production_backup.sh

for validator in "${static_validators[@]}"; do
  run_group "Static contract: $validator" python3 "$validator"
done

for script in "${browser_scripts[@]}"; do
  run_group "JavaScript syntax: $script" node --check "$script"
done
run_group "Public interaction state" node scripts/test_public_interaction_state.js

for test_file in "${boundary_tests[@]}"; do
  run_group "Boundary test: $test_file" python3 "$test_file"
done

for test_file in "${production_tests[@]}"; do
  run_group "Production test: $test_file" python3 "$test_file"
done

run_group "Patch integrity" git diff --check

printf '\nRelease gate passed. Before tagging, run rollback-only database acceptance with:\n'
printf '  MT_TEST_ENVIRONMENT=development bash scripts/database_acceptance_gate.sh\n'
printf 'Then complete browser visual acceptance. Never run the database gate against production.\n'
