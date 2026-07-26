#!/usr/bin/env python3
"""Shared immutable-release file contract for production tooling."""

from __future__ import annotations


PUBLIC_RUNTIME_FILES = frozenset({
    "index.html", "works.html", "about.html", "contact.html", "lightbox.html", "privacy.html",
    "creator.html", "collections.html", "auth.html", "mfa.html", "account-settings.html",
    "dashboard.html", "upload-studio.html", "notifications.html", "inbox.html", "admin-reviews.html",
    "admin-works.html", "admin-users.html", "admin-audit.html", "manage.html",
    "styles.css", "privacy.css", "admin-audit.css",
    "script.js", "global-header.js", "archive.js", "archive-data.js", "archive-upload.js", "public-archive.js",
    "public-navigation.js", "series-data.js", "lightbox.js", "contact.js", "creator.js",
    "collections.js", "auth.js", "mfa.js", "account-menu.js", "account-settings.js",
    "dashboard.js", "upload-studio.js", "notifications.js", "inbox.js", "site-footer.js",
    "admin-reviews.js", "admin-works.js", "admin-users.js", "admin-audit.js", "manage.js",
})

DATABASE_MIGRATION_FILES = frozenset({
    "database/migrations/20260713_admin_mfa_hardening.sql",
    "database/migrations/20260714_account_profile_boundary.sql",
    "database/migrations/20260715_workspace_drafts_folders.sql",
    "database/migrations/20260716_upload_retry_cancel.sql",
    "database/migrations/20260716_workspace_draft_compliance.sql",
    "database/migrations/20260716_workspace_draft_versioning.sql",
    "database/migrations/20260716_workspace_folder_integrity.sql",
    "database/migrations/20260716_workspace_submit_readiness.sql",
    "database/migrations/20260717_review_queue.sql",
    "database/migrations/20260717_workspace_asset_scanner.sql",
    "database/migrations/20260722_public_delivery.sql",
    "database/migrations/20260722_user_dashboard.sql",
    "database/migrations/20260722_workspace_trash_restore.sql",
    "database/migrations/20260722_z_creator_profile.sql",
    "database/migrations/20260723_admin_works_governance.sql",
    "database/migrations/20260723_b_admin_user_governance.sql",
    "database/migrations/20260723_c_profile_avatar_upload.sql",
    "database/migrations/20260723_d_communications_audit.sql",
})

REQUIRED_RELEASE_FILES = PUBLIC_RUNTIME_FILES | DATABASE_MIGRATION_FILES | frozenset({
    "server.py",
    "requirements-scanner.txt",
    "workers/image_probe.py",
    "workers/image_scanner.py",
    "workers/scan_adapters.py",
    "database/product_schema.sql",
    "deploy/database-environment.example",
    "deploy/scanner-environment.example",
    "deploy/web-environment.example",
    "deploy/mt-presence-healthcheck.service",
    "deploy/mt-presence-healthcheck.timer",
    "deploy/mt-presence-scanner.service",
    "deploy/mt-presence.service",
    "deploy/nginx-mt-presence.conf",
    "deploy/nginx-proxy.conf",
    "docs/operations/production-deployment.md",
    "scripts/backup_production_database.sh",
    "scripts/build_production_release.sh",
    "scripts/database_acceptance_gate.sh",
    "scripts/deploy_supabase_phase1.sh",
    "scripts/manage_production_release.py",
    "scripts/production_preflight.py",
    "scripts/production_release_contract.py",
    "scripts/release_gate.sh",
    "scripts/validate_communications_audit.py",
    "scripts/verify_production.py",
    "scripts/verify_production_backup.sh",
})

FORBIDDEN_RELEASE_FILES = frozenset({".env", ".env.worker"})
