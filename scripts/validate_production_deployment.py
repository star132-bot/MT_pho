#!/usr/bin/env python3
"""Static contract checks for the production deployment artifacts."""

from __future__ import annotations

import ast
from html.parser import HTMLParser
from pathlib import Path

from production_release_contract import PUBLIC_RUNTIME_FILES, REQUIRED_RELEASE_FILES


ROOT = Path(__file__).resolve().parents[1]


def source(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def require(text: str, marker: str, label: str) -> None:
    if marker not in text:
        raise AssertionError(f"{label}: missing {marker!r}")


def reject(text: str, marker: str, label: str) -> None:
    if marker in text:
        raise AssertionError(f"{label}: forbidden {marker!r}")


def literal_set(path: str, assignment: str) -> set[str]:
    tree = ast.parse(source(path), filename=path)
    for node in tree.body:
        if isinstance(node, (ast.Assign, ast.AnnAssign)):
            targets = node.targets if isinstance(node, ast.Assign) else [node.target]
            if any(isinstance(target, ast.Name) and target.id == assignment for target in targets):
                value = ast.literal_eval(node.value)
                if isinstance(value, set) and all(isinstance(item, str) for item in value):
                    return value
    raise AssertionError(f"{path}: missing literal set {assignment}")


class ScriptContractParser(HTMLParser):
    def __init__(self, path: Path) -> None:
        super().__init__(convert_charrefs=True)
        self.path = path
        self.inline_scripts: list[int] = []
        self.identity_nodes: list[tuple[str, int]] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attributes = dict(attrs)
        line, _ = self.getpos()
        if tag == "script" and not attributes.get("src"):
            self.inline_scripts.append(line)
        if attributes.get("id") == "mt-header-identity":
            self.identity_nodes.append((tag, line))


def validate_html_script_contracts() -> None:
    failures: list[str] = []
    for path in sorted(ROOT.glob("*.html")):
        parser = ScriptContractParser(path)
        parser.feed(path.read_text(encoding="utf-8"))
        for line in parser.inline_scripts:
            failures.append(f"{path.name}:{line} contains an inline script blocked by production CSP")
        for tag, line in parser.identity_nodes:
            if tag != "template":
                failures.append(f"{path.name}:{line} header identity must use a non-executable template")
    if failures:
        raise AssertionError("HTML script contracts failed:\n" + "\n".join(failures))


def main() -> None:
    web_service = source("deploy/mt-presence.service")
    scanner_service = source("deploy/mt-presence-scanner.service")
    nginx = source("deploy/nginx-mt-presence.conf")
    proxy = source("deploy/nginx-proxy.conf")
    web_environment = source("deploy/web-environment.example")
    scanner_environment = source("deploy/scanner-environment.example")
    database_environment = source("deploy/database-environment.example")
    health_service = source("deploy/mt-presence-healthcheck.service")
    health_timer = source("deploy/mt-presence-healthcheck.timer")
    preflight = source("scripts/production_preflight.py")
    release_manager = source("scripts/manage_production_release.py")
    release_builder = source("scripts/build_production_release.sh")
    backup = source("scripts/backup_production_database.sh")
    backup_verifier = source("scripts/verify_production_backup.sh")
    verifier = source("scripts/verify_production.py")
    release_gate = source("scripts/release_gate.sh")
    database_gate = source("scripts/database_acceptance_gate.sh")

    for marker in (
        "User=mtpresence",
        "EnvironmentFile=/etc/mt-presence/web.env",
        "--runtime web",
        "--host 127.0.0.1",
        "NoNewPrivileges=true",
        "ProtectSystem=strict",
        "CapabilityBoundingSet=",
    ):
        require(web_service, marker, "web systemd")
    reject(web_service, "User=root", "web systemd")

    for marker in (
        "User=mtpresence-scanner",
        "EnvironmentFile=/etc/mt-presence/scanner.env",
        "--runtime scanner",
        "workers/image_scanner.py",
        "ReadWritePaths=/var/lib/mt-presence-scanner",
    ):
        require(scanner_service, marker, "scanner systemd")
    reject(scanner_service, "User=root", "scanner systemd")

    for marker in (
        "return 301 https://$host$request_uri",
        "ssl_protocols TLSv1.2 TLSv1.3",
        "Strict-Transport-Security",
        "Content-Security-Policy",
        "location = /api/inquiries",
        "limit_req zone=mt_inquiry",
        "$request_method $uri $status",
        "client_max_body_size 100m",
        "client_body_timeout 120s",
        "limit_req_status 429",
        "server_tokens off",
        "add_header X-Request-ID $request_id always",
    ):
        require(nginx, marker, "nginx")
    reject(nginx, "$request ", "query-safe access log")

    for marker in (
        "proxy_set_header Host $host",
        "proxy_set_header X-Forwarded-Proto https",
        "proxy_set_header X-Request-ID $request_id",
        "proxy_connect_timeout 5s",
        "proxy_read_timeout 120s",
    ):
        require(proxy, marker, "nginx proxy")

    for marker in ("MT_RUNTIME_ENVIRONMENT=production", "MT_COOKIE_SECURE=1", "MT_TRUST_PROXY=1", "MT_MAX_REQUEST_THREADS=32", "MT_PUBLIC_BASE_URL=https://"):
        require(web_environment, marker, "web environment")
    for forbidden in ("PGPASSWORD=", "SUPABASE_SECRET_KEY=", "SUPABASE_SERVICE_ROLE_KEY="):
        reject(web_environment, forbidden, "web environment")
    require(scanner_environment, "SUPABASE_SECRET_KEY=", "scanner environment")
    require(scanner_environment, "MT_SCANNER_ID=production-scanner-01", "scanner environment")
    require(scanner_environment, "MT_SCANNER_CLAMAV_COMMAND=clamscan --no-summary", "scanner environment")
    require(scanner_environment, "MT_SCANNER_TEMP_DIR=/var/lib/mt-presence-scanner", "scanner environment")
    reject(scanner_environment, "MT_SCANNER_WORKER_ID", "scanner environment")
    for marker in ("PGPASSWORD=", "PGSSLMODE=require", "MT_DEPLOY_ENVIRONMENT=production", "MT_APPLY_PHASE1_BASELINE=no"):
        require(database_environment, marker, "database environment")
    for marker in ("User=mtpresence", "--max-time 8", "http://127.0.0.1:8131/readyz", "NoNewPrivileges=true"):
        require(health_service, marker, "health service")
    for marker in ("OnBootSec=2min", "OnUnitActiveSec=1min", "Persistent=true"):
        require(health_timer, marker, "health timer")

    for marker in (
        'required_environment("MT_RUNTIME_ENVIRONMENT")',
        'required_environment("MT_COOKIE_SECURE")',
        '"SUPABASE_SERVICE_ROLE_KEY", "PGPASSWORD"',
        'Path("/var/lib/mt-presence-scanner")',
        'required_environment("MT_SCANNER_ID")',
        'required_environment("MT_SCANNER_CLAMAV_COMMAND")',
        'if "--fdpass" in scanner_command',
        'from production_release_contract import FORBIDDEN_RELEASE_FILES, REQUIRED_RELEASE_FILES',
    ):
        require(preflight, marker, "runtime preflight")

    for marker in (
        "validate_archive_member",
        "FORBIDDEN_RELEASE_FILES",
        "sha256_file(archive)",
        "os.replace(temporary, link)",
        'os.environ.get("MT_ALLOW_ROLLBACK") != "yes"',
        "from production_release_contract import FORBIDDEN_RELEASE_FILES, REQUIRED_RELEASE_FILES",
    ):
        require(release_manager, marker, "release manager")
    for marker in ("MT_RELEASE_APPROVED", "status --porcelain", "describe --tags --exact-match", "git -C"):
        require(release_builder, marker, "release builder")
    for marker in ("umask 077", "pg_dump", "--format=custom", "sha256"):
        require(backup, marker, "database backup")
    for marker in ("pg_restore", "--list", "checksum does not match", 'grep -q " TABLE "', 'grep -q " FUNCTION "'):
        require(backup_verifier, marker, "database backup verifier")
    for marker in (
        'request(base_url, "/healthz")',
        'request(readiness_url, "/readyz")',
        'readiness.get("dependencies") != {"supabase": "available"}',
        '"/admin/audit"',
        "SENSITIVE_WORK_FIELDS",
        "PRIVATE_STATIC_PATHS",
        '"/%64atabase/product_schema.sql"',
        "SameSite=Strict",
    ):
        require(verifier, marker, "production verifier")

    for marker in (
        "validate_communications_audit.py",
        "test_communications_audit_boundary.py",
        "test_production_health.py",
        "test_manage_production_release.py",
        "test_verify_production.py",
        "bash -n",
        "MT_TEST_ENVIRONMENT=development bash scripts/database_acceptance_gate.sh",
        "node scripts/test_public_interaction_state.js",
        "git diff --check",
    ):
        require(release_gate, marker, "release gate")

    database_tests = (
        "scripts/test_user_dashboard_database.py",
        "scripts/test_public_delivery_database.py",
        "scripts/test_admin_works_database.py",
        "scripts/test_admin_users_database.py",
        "scripts/test_communications_audit_database.py",
    )
    for marker in (
        '"${MT_TEST_ENVIRONMENT:-}" != "development"',
        '"${MT_ALLOW_PRODUCTION:-}" == "yes"',
        *database_tests,
    ):
        require(database_gate, marker, "database acceptance gate")
    positions = [database_gate.index(test) for test in database_tests]
    if positions != sorted(positions):
        raise AssertionError("database acceptance gate: test order drifted")

    server_public_files = literal_set("server.py", "PUBLIC_ROOT_STATIC_FILES")
    if server_public_files != set(PUBLIC_RUNTIME_FILES):
        missing = sorted(server_public_files - set(PUBLIC_RUNTIME_FILES))
        stale = sorted(set(PUBLIC_RUNTIME_FILES) - server_public_files)
        raise AssertionError(f"production release public manifest drift: missing={missing}, stale={stale}")
    missing_release_files = sorted(path for path in REQUIRED_RELEASE_FILES if not (ROOT / path).is_file())
    if missing_release_files:
        raise AssertionError(f"production release contract references missing files: {missing_release_files}")

    validate_html_script_contracts()

    print("Production deployment static contracts passed (13 groups).")


if __name__ == "__main__":
    main()
