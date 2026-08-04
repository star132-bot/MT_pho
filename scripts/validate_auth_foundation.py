#!/usr/bin/env python3
"""Contract checks for the Phase 1 authentication foundation."""

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def require(text: str, tokens: set[str], label: str) -> None:
    missing = sorted(token for token in tokens if token not in text)
    if missing:
        raise RuntimeError(f"{label} is missing: {', '.join(missing)}")


def main() -> None:
    server = (ROOT / "server.py").read_text()
    auth_html = (ROOT / "auth.html").read_text()
    auth_js = (ROOT / "auth.js").read_text()
    terms_html = (ROOT / "terms.html").read_text()
    mfa_html = (ROOT / "mfa.html").read_text()
    mfa_js = (ROOT / "mfa.js").read_text()
    account_html = (ROOT / "account-settings.html").read_text()
    account_js = (ROOT / "account-settings.js").read_text()
    upload_html = (ROOT / "upload-studio.html").read_text()
    upload_js = (ROOT / "upload-studio.js").read_text()
    manage_js = (ROOT / "manage.js").read_text()
    deploy_script = (ROOT / "scripts" / "deploy_supabase_phase1.sh").read_text()
    nginx = (ROOT / "deploy" / "nginx-mt-presence.conf").read_text()

    require(server, {
        'SUPABASE_URL', 'SUPABASE_PUBLISHABLE_KEY', 'HttpOnly; SameSite=Lax',
        '/api/auth/register', '/api/auth/sign-in', '/api/auth/sign-out', '/api/me',
        '/workspace', 'AUTH_NOT_CONFIGURED', 'INVALID_CREDENTIALS', 'EMAIL_NOT_VERIFIED',
        'rpc/current_authorization', 'ADMIN_REQUIRED', 'MFA_REQUIRED', 'ACCOUNT_RESTRICTED',
        '/api/auth/mfa/factors', '/api/auth/mfa/enroll', '/api/auth/mfa/challenge',
        '/api/auth/mfa/verify', '/api/admin/access-check', 'MFA_CODE_INVALID',
        'all_factors = user.get("factors") or []',
        '_pending_response_cookies', 'self._pending_response_cookies = self.session_cookie_headers(session)',
        'if cookies is not None:', 'send_current_user_error',
        'method="DELETE"', 'MFA_RESET_FAILED', 'MFA_ALREADY_ENROLLED',
        '/api/auth/forgot-password', '/api/auth/recovery-session', '/api/auth/reset-password',
        '/api/auth/verify-email', '/api/auth/verify-email-code', '/api/auth/resend-verification', '/api/auth/recovery-status', '/api/auth/csrf',
        '/api/auth/verification-status',
        'recover?', 'token_hash', 'method="PUT"', 'logout?scope=global',
        'CSRF_REJECTED', 'X-CSRF-Token', 'RECOVERY_GRANTS', 'MT_PUBLIC_BASE_URL',
        'normalize_auth_email', 'AUTH_PASSWORD_MIN_LENGTH', 'TERMS_POLICY_VERSION',
        'consume_auth_email_rate_limit', 'consume_auth_otp_rate_limit', 'AUTH_EMAIL_OTP_PATTERN',
        'EMAIL_CODE_INVALID', 'VERIFICATION_RATE_LIMITED',
        'session_has_auth_method(session, "recovery")', 'request_id',
        'session_has_auth_method({"access_token": self.current_access_token(user)}, "recovery")',
        'parsed.path == "/upload-studio.html"', '"/workspace/images"',
        'legacy_upload_asset_access', 'is_public_derivative', 'canonical_path == "/assets/uploads"',
        'canonical_path.startswith("/assets/uploads/")',
        '"/settings/account"', '"/api/me/profile"', '"/api/me/sessions"',
        'normalize_profile_update', 'rpc/update_my_profile', 'handle_session_revoke',
    }, "server auth boundary")
    require(auth_html, {
        'href="/styles.css', 'src="/assets/', 'src="/auth.js',
        'autocomplete="email"', 'autocomplete="current-password"',
        'data-field-error="email"', 'data-field-error="password"',
        'role="status"', 'data-auth-submit',
        'data-auth-open-browser',
        'data-auth-field="password_confirmation"', 'data-auth-forgot-link',
        'data-auth-resend-link', 'href="/terms.html"', 'href="/privacy.html"',
        'data-auth-loading', 'data-auth-next-link', 'tabindex="-1"',
        'data-auth-field="verification_code"', 'autocomplete="one-time-code"',
        'inputmode="numeric"', 'pattern="[0-9]{8}"',
    }, "auth page")
    require(auth_js, {
        'credentials: "same-origin"', 'form.reportValidity()',
        'aria-invalid', '/api/auth/', '/workspace/images', 'result.next_action === "mfa"',
        'authRequest("/api/me")', 'cache: "no-store"', 'Open sign-in in a full browser',
        'safeInternalPath', 'sessionCheck.response.status === 401',
        'forgotPassword', 'resetPassword', 'verifyEmail', 'callbackParameters',
        '/api/auth/verification-status',
        'history.replaceState', 'token_hash', 'refresh_token', 'X-CSRF-Token',
        'If an account exists for this email', 'password_confirmation',
        'resendVerification', '/api/auth/resend-verification',
        '/api/auth/verify-email-code', 'pending_email',
    }, "auth client")
    require(terms_html, {
        'Terms of Use', 'id="account"', 'id="content"', 'id="conduct"',
        'href="/privacy.html"', 'data-global-header', 'data-site-footer',
    }, "terms page")
    require(nginx, {
        'zone=mt_auth_email', 'zone=mt_auth_login',
        'register|resend-verification|forgot-password', 'location = /api/auth/sign-in',
        'location = /api/auth/verify-email-code',
    }, "auth nginx rate limits")
    require(mfa_html, {
        'autocomplete="one-time-code"', 'inputmode="numeric"', 'pattern="[0-9]{6}"',
        'data-mfa-enrollment', 'data-mfa-qr', 'data-mfa-secret', 'data-mfa-form',
        'role="status"', 'src="/mfa.js',
    }, "MFA page")
    require(mfa_js, {
        '/api/auth/mfa/factors', '/api/auth/mfa/enroll', '/api/auth/mfa/challenge',
        '/api/auth/mfa/verify', '/api/admin/access-check', 'credentials: "same-origin"',
        'form.reportValidity()', 'safeInternalPath', 'Resetting the incomplete authenticator setup',
        'decodeURIComponent(payload)', 'source.startsWith("<?xml")',
        '/api/auth/csrf', 'X-CSRF-Token',
    }, "MFA client")
    require(account_html, {
        'data-profile-form', 'data-preferences-form', 'data-session-list',
        'data-session-action="others"', 'data-session-action="all"',
        'role="status"', 'aria-live="polite"', 'data-dialog-notice',
        'tabindex="-1"', 'src="/account-settings.js',
        'data-professional-role-picker', 'data-professional-role-options',
        'name="professional_headline" type="hidden"', 'data-professional-role-count',
    }, "Account Settings page")
    require(account_js, {
        'credentials: "same-origin"', 'cache: "no-store"', '/api/me/profile',
        '/api/me/sessions', 'method: "PATCH"', 'method: "DELETE"',
        '/api/auth/csrf', 'X-CSRF-Token', 'form.reportValidity()',
        'RECOVERY_SESSION_RESTRICTED', 'MFA_REQUIRED', 'beforeunload',
        'submittedPayload', 'currentPayload[name] === submittedPayload[name]',
        'Newer edits remain unsaved.', 'suppressBeforeUnload',
        'navigateWithoutDirtyPrompt', 'Sign out failed. Your session remains active.',
        '}).catch((error) => {', 'dialogNotice.focus();',
        'PROFESSIONAL_ROLE_LIMIT = 3', 'setProfessionalRoles(',
        'syncProfessionalRolePicker()', 'addLegacyProfessionalRole(',
        'professionalHeadlineValue.value = selected.map((input) => input.value).join(", ")',
    }, "Account Settings client")
    if 'id="account-headline"' in account_html or 'name="professional_headline" type="text"' in account_html:
        raise RuntimeError("Professional headline must use the bounded multi-select role picker, not free text")
    require(deploy_script, {
        'MT_APPLY_PHASE1_BASELINE', 'database/migrations/*.sql',
        'Skipping the Phase 0/1 baseline for an existing database',
    }, "Phase 1 incremental deployment")

    require(upload_html, {
        'href="/workspace/images"', 'href="/admin/reviews"', 'src="/upload-studio.js',
    }, "protected Workspace links")
    require(account_html, {'href="/admin/reviews"'}, "protected Account Review links")
    protected_review_links = (
        ("Upload Studio", upload_html, 1),
        ("Account Settings", account_html, 1),
    )
    for label, source, expected_count in protected_review_links:
        if source.count('href="/admin/reviews"') != expected_count or 'href="/manage.html"' in source:
            raise RuntimeError(f"{label} must route its protected Review links to /admin/reviews")
    require(upload_js + manage_js, {'archiveMutationFetch', '/api/auth/csrf', 'X-CSRF-Token'}, "legacy Archive CSRF client")

    if "retry with a fresh administrator test account" in mfa_js:
        raise RuntimeError("MFA recovery must not strand users on an incomplete TOTP factor")

    forbidden = ["localStorage", "sessionStorage", "indexedDB"]
    combined = auth_html + auth_js + mfa_html + mfa_js + account_html + account_js
    used = [token for token in forbidden if token in combined]
    if used:
        raise RuntimeError(f"Auth client must not store sessions in browser storage: {', '.join(used)}")

    print("Phase 1 authentication foundation validated.")


if __name__ == "__main__":
    main()
