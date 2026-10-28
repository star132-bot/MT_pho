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
    deploy_script = (ROOT / "scripts" / "deploy_supabase_phase1.sh").read_text()
    nginx = (ROOT / "deploy" / "nginx-mt-presence.conf").read_text()

    require(server, {
        'SUPABASE_URL', 'SUPABASE_PUBLISHABLE_KEY', 'HttpOnly; SameSite=Lax',
        '/api/auth/register', '/api/auth/sign-in', '/api/auth/sign-out', '/api/me',
        '/workspace', 'AUTH_NOT_CONFIGURED', 'INVALID_CREDENTIALS', 'EMAIL_NOT_VERIFIED',
        'rpc/current_authorization', 'ADMIN_REQUIRED', 'MFA_REQUIRED', 'ACCOUNT_RESTRICTED',
        '/api/auth/mfa/factors', '/api/auth/mfa/enroll', '/api/auth/mfa/challenge',
        '/api/auth/mfa/verify', '/api/auth/mfa/status', '/api/auth/mfa', '/api/admin/access-check',
        'MFA_CODE_INVALID', 'clean_mfa_factors', 'verified_totp_factors', 'clean_mfa_enrollment',
        'mfa_status_payload', 'mfa_required_for_session', 'allow_mfa_challenge', 'MFA_MANDATORY',
        '_pending_response_cookies', 'self._pending_response_cookies = self.session_cookie_headers(session)',
        'if cookies is not None:', 'send_current_user_error',
        'method="DELETE"', 'MFA_RESET_FAILED', 'MFA_ALREADY_ENROLLED',
        '/api/auth/forgot-password', '/api/auth/recovery-session', '/api/auth/reset-password',
        '/api/auth/verify-email', '/api/auth/verify-email-code', '/api/auth/verify-recovery-code', '/api/auth/resend-verification', '/api/auth/recovery-status', '/api/auth/csrf',
        'recover?', 'token_hash', 'method="PUT"', 'logout?scope=global',
        'CSRF_REJECTED', 'X-CSRF-Token', 'RECOVERY_GRANTS', 'MT_PUBLIC_BASE_URL',
        'normalize_auth_email', 'AUTH_PASSWORD_MIN_LENGTH', 'TERMS_POLICY_VERSION',
        'consume_auth_email_rate_limit', 'consume_auth_otp_rate_limit', 'AUTH_EMAIL_OTP_PATTERN',
        'RETIRED_REGISTRATION_PAGES', 'RETIRED_REGISTRATION_ENDPOINTS', 'REGISTRATION_CLOSED',
        'HTTPStatus.GONE', 'STAFF_ONLY', 'def is_staff_authorization(authorization) -> bool:',
        'self._pending_response_cookies = self.clear_session_cookie_headers()',
        'session_has_auth_method(session, "recovery")', 'request_id',
        'def is_recovery_session(self, user: dict)', 'self.is_recovery_session(user)',
        'RECOVERY_SESSION_TTL_SECONDS',
        'OAUTH_STATE_COOKIE', 'OAUTH_FLOWS', 'OAUTH_PROVIDERS', 'IDENTITY_PROVIDERS', 'create_oauth_flow', 'consume_oauth_flow',
        'code_challenge_method', 'token?grant_type=pkce', '"auth_code": code',
        'parsed.path in {"/auth/oauth/google", "/auth/oauth/apple"}', 'parsed.path == "/auth/oauth/callback"',
        'handle_oauth_start', 'handle_oauth_callback', 'handle_identity_link_start', 'handle_identity_unlink',
        'clean_auth_identities', 'valid_oauth_provider_redirect', 'clear_oauth_state_cookie_header',
        'purpose == "link"', 'user_has_oauth_provider',
        'user/identities/authorize', 'skip_http_redirect', 'IDENTITY_LAST_BLOCKED',
        'parsed.path == "/upload-studio.html"', '"/workspace/images"',
        'self.send_header("Location", "/auth/sign-in?next=/works.html")',
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
        'data-auth-resend-link',
        'data-auth-loading', 'data-auth-next-link', 'tabindex="-1"',
        'autocomplete="one-time-code"',
        'inputmode="numeric"', 'pattern="[0-9]{8}"',
        'data-auth-field="recovery_code"', 'data-field-error="recovery_code"',
        'data-auth-oauth', 'data-auth-google', 'data-auth-provider="google"', 'data-auth-provider="apple"',
        '使用 Google 登录', '使用 Apple 登录', 'href="/auth/oauth/apple"',
        'auth-google-logo', 'fill="#4285F4"', 'fill="#34A853"',
        'fill="#FBBC05"', 'fill="#EA4335"', 'auth-apple-logo',
    }, "auth page")
    # Public registration is closed; staff accounts are provisioned by an operator.
    for forbidden in ('/auth/register', 'Create an account', 'data-auth-field="display_name"', 'data-auth-field="terms_accepted"'):
        if forbidden in auth_html:
            raise RuntimeError(f"auth page still exposes retired registration UI: {forbidden}")
    for forbidden in ('register', 'resendVerification', 'verifyEmail', '/api/auth/verify-email-code'):
        if forbidden in auth_js:
            raise RuntimeError(f"auth client still contains retired registration flow: {forbidden}")
    form_end = auth_html.index("</form>")
    oauth_start = auth_html.index('class="auth-oauth"')
    divider_start = auth_html.index('class="auth-divider"')
    google_start = auth_html.index('class="auth-oauth-button"')
    apple_start = auth_html.index('data-auth-provider="apple"')
    if not form_end < oauth_start < divider_start < google_start < apple_start:
        raise RuntimeError("OAuth providers must follow the email form and its divider")
    require(auth_js, {
        'credentials: "same-origin"', 'form.reportValidity()',
        'aria-invalid', '/api/auth/', 'DEFAULT_AUTH_DESTINATION = "/works.html"', 'result.next_action === "mfa"',
        'authRequest("/api/me")', 'cache: "no-store"', '在完整浏览器中打开登录页',
        'safeInternalPath', 'sessionCheck.response.status === 401',
        'forgotPassword', 'resetPassword', 'callbackParameters',
        'history.replaceState', 'token_hash', 'refresh_token', 'X-CSRF-Token',
        '如果这个邮箱有账号', 'password_confirmation',
        '/api/auth/verify-recovery-code', 'recovery_code',
        '/auth/oauth/${provider}?next=', 'showOAuthResult', 'oauth_error', 'oauth_provider',
    }, "auth client")
    require(terms_html, {
        'Terms of Use', 'id="account"', 'id="content"', 'id="conduct"',
        'href="/privacy.html"', 'data-global-header', 'data-site-footer',
    }, "terms page")
    require(nginx, {
        'zone=mt_auth_email', 'zone=mt_auth_login',
        'register|resend-verification|forgot-password', 'location = /api/auth/sign-in',
        'location = /api/auth/verify-email-code', 'location = /api/auth/verify-recovery-code',
    }, "auth nginx rate limits")
    require(mfa_html, {
        'autocomplete="one-time-code"', 'inputmode="numeric"', 'pattern="[0-9]{6}"',
        'data-mfa-enrollment', 'data-mfa-qr', 'data-mfa-secret', 'data-mfa-form',
        'role="status"', 'src="/mfa.js',
    }, "MFA page")
    require(mfa_js, {
        '/api/auth/mfa/factors', '/api/auth/mfa/enroll', '/api/auth/mfa/challenge',
        '/api/auth/mfa/verify', '/api/auth/mfa/status', '/api/admin/access-check', 'credentials: "same-origin"',
        'form.reportValidity()', 'safeInternalPath', 'Resetting the incomplete authenticator setup',
        'decodeURIComponent(payload)', 'source.startsWith("<?xml")',
        '/api/auth/csrf', 'X-CSRF-Token', 'DEFAULT_AUTH_DESTINATION = "/works.html"',
    }, "MFA client")
    require(account_html, {
        'data-profile-form', 'data-preferences-form', 'data-session-list',
        'data-session-action="others"', 'data-session-action="all"',
        'role="status"', 'aria-live="polite"', 'data-dialog-notice',
        'tabindex="-1"', 'src="/account-settings.js',
        'data-professional-role-picker', 'data-professional-role-options',
        'name="professional_headline" type="hidden"', 'data-professional-role-count',
        'data-linked-identities', 'data-identity-list', 'data-identity-connect-provider="google"',
        'data-identity-connect-provider="apple"', 'data-identity-dialog',
        'data-mfa-settings', 'data-mfa-status', 'data-mfa-action', 'data-mfa-dialog',
    }, "Account Settings page")
    require(account_js, {
        'credentials: "same-origin"', 'cache: "no-store"', '/api/me/profile',
        '/api/me/sessions', 'method: "PATCH"', 'method: "DELETE"',
        '/api/auth/csrf', 'X-CSRF-Token', 'form.reportValidity()',
        'RECOVERY_SESSION_RESTRICTED', 'MFA_REQUIRED', 'beforeunload',
        'submittedPayload', 'currentPayload[name] === submittedPayload[name]',
        '新的修改还没保存', 'suppressBeforeUnload',
        'navigateWithoutDirtyPrompt', '退出失败，仍保持登录。',
        '}).catch((error) => {', 'dialogNotice.focus();',
        'PROFESSIONAL_ROLE_LIMIT = 3', 'setProfessionalRoles(',
        'syncProfessionalRolePicker()', 'addLegacyProfessionalRole(',
        'professionalHeadlineValue.value = selected.map((input) => input.value).join(", ")',
        '/api/me/identities', '/api/me/identities/link', 'data-identity-remove',
        'identity_status', 'suppressBeforeUnload = true',
        '/api/auth/mfa', 'disable-mfa', 'renderMfaSettings', 'data-mfa-action',
    }, "Account Settings client")
    if 'id="account-headline"' in account_html or 'name="professional_headline" type="text"' in account_html:
        raise RuntimeError("Professional headline must use the bounded multi-select role picker, not free text")
    require(deploy_script, {
        'MT_APPLY_PHASE1_BASELINE', 'database/migrations/*.sql',
        'Skipping the Phase 0/1 baseline for an existing database',
    }, "Phase 1 incremental deployment")

    require(upload_html, {
        'href="/workspace/images"', 'href="/admin"', 'src="/upload-studio.js',
    }, "protected Workspace links")
    # The review queue and browser editor were retired; staff pages link to /admin.
    for label, source in (("Upload Studio", upload_html), ("Account Settings", account_html)):
        if 'href="/admin"' not in source:
            raise RuntimeError(f"{label} must link back to the staff admin")
        if 'href="/admin/reviews"' in source or 'href="/manage.html"' in source:
            raise RuntimeError(f"{label} still links to a retired staff page")
    require(upload_js, {'archiveMutationFetch', '/api/auth/csrf', 'X-CSRF-Token'}, "Archive CSRF client")

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
