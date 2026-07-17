# Provider Decisions

## Phase 0 boundary

- Authentication: use **Supabase Auth**. The application database maps its immutable user UUID to `users.auth_subject`; passwords and session tokens never enter business tables or browser storage.
- Sessions: exchange the Supabase session at the application boundary for server-managed `HttpOnly`, `Secure`, `SameSite=Lax` cookies; admin roles require Supabase MFA and a short application session.
- Object storage: use **Supabase Storage** private buckets with short-lived signed upload intents. Originals remain private; only generated display/thumbnail assets may be copied to a public delivery bucket after publication.
- Authorization: every business API resolves the provider subject to `users`, then applies owner and role checks server-side. UI visibility is not an authorization boundary.

Phase 1 must configure separate development and production Supabase projects, key rotation, redirect allowlists, MFA policy, and storage bucket policies before authentication endpoints are exposed.

The application sets `redirect_to` from the fixed `MT_PUBLIC_BASE_URL`; it never builds email callbacks from untrusted request payloads or non-loopback Host headers. Supabase Auth must allow the exact `/auth/verify-email` and `/auth/reset-password` callback URLs. Default Supabase implicit email links are supported by immediately exchanging the fragment refresh token for server-managed HttpOnly cookies and scrubbing the URL without browser storage. Production email templates should prefer first-party fragments containing `token_hash` and `type`, for example `/auth/verify-email#token_hash={{ .TokenHash }}&type=signup` and `/auth/reset-password#token_hash={{ .TokenHash }}&type=recovery`, so the application can POST the one-time hash to Supabase `/verify` without exposing access/refresh tokens to page code or request logs.

## Phase 1 migration order

1. On a fresh project, run `database/product_schema.sql` and `database/supabase_phase1_auth_rls.sql` through `bash scripts/deploy_supabase_phase1.sh`.
2. The Phase 1 baseline installs the `auth.users` mapping trigger, owner RLS, strict owner-only Profile RPC, role checks, Admin AAL2 checks, public Works policies, and private Storage namespace policies.
3. Apply `database/migrations/*.sql` in filename order after the baseline. For an existing Phase 1 project, use `MT_APPLY_PHASE1_BASELINE=no bash scripts/deploy_supabase_phase1.sh` so the non-idempotent baseline is not replayed.
4. Configure Auth email verification and allowed redirect URLs.
5. The Phase 2A migration creates private `image-originals`, `image-display`, and `image-thumbnails` buckets with JPEG/PNG/WebP allowlists and 50/20/10 MiB limits. Originals remain private.
6. Grant Reviewer/Admin/Super Admin roles only through an audited service-side operation. Authenticated clients have no direct role-write policy.

`public.user_roles` is the authorization source of truth. JWT claims may later cache role information for UI routing, but database/API authorization must continue to validate the protected role table and the Supabase-verified `aal` claim.

## Phase 2A Workspace boundary

- Folder, upload-intent, Draft, version, and asset writes use validated `workspace_*` RPCs. Authenticated clients have no generic INSERT/UPDATE/DELETE grants on these tables.
- Storage object keys are generated server-side as `{auth.uid}/{image_id}/{kind}.{ext}`. The browser receives only short-lived signed upload URLs and never receives the Supabase access token.
- `original`, `display`, and `thumbnail` objects remain in separate private buckets. Draft reads receive short-lived signed URLs through the application server.
- Drafts may be incomplete. Publication status, workflow state, ownership, asset keys, and version locks are never accepted as editable Draft fields.
- IndexedDB is a read-only offline cache for this slice. It is not an authority and cannot queue mutations while disconnected.
- Phase 2B uses a bounded two-worker browser queue. Queued and in-flight tasks can be canceled, failed/canceled tasks can be retried or removed, and network uploads are AbortController-aware.
- Cancel is server-authoritative: an owner-scoped RPC records `canceled_at` and `cleanup_status`, then the application deletes the three intended object paths through the Storage API and records the cleanup result. Completed intents cannot be canceled.
- Delivered after Phase 2B: autosave/conflict recovery and authoritative Submit readiness/transaction are completed slices; the trusted scanner code and database state machine are complete while its persistent runtime is not yet provisioned. Resumable/TUS uploads, scheduled orphan repair, quotas/rate limiting, Admin Review/Publish, and the Trash restore browser view remain deferred.

## Phase 2F trusted scanner boundary

- The scanner is an independent Python process. `server.py`, browser code, signed upload responses, cookies, and CSRF flows never receive `SUPABASE_SECRET_KEY` or a legacy service-role key.
- A current `sb_secret_` key is sent only as the Supabase `apikey` header. Legacy service-role JWTs use both `apikey` and `Authorization: Bearer`; neither form is written to logs.
- `asset_scan_jobs` and `asset_scan_events` have RLS enabled and no table grant for anon, authenticated, or service_role. The worker implementation invokes only the claim/retry/complete SECURITY DEFINER RPCs granted to service_role. The secret/service-role credential itself remains broadly privileged and must be isolated and rotated; the RPC-only implementation is not a capability-limited key.
- Claim uses `FOR UPDATE SKIP LOCKED`, a bounded lease, attempt count, random token, and an immutable asset/object metadata snapshot. Completion is token-bound and same-token idempotent; expired or superseded workers cannot overwrite a newer verdict.
- The worker rejects HTTP redirects before forwarding credentials, streams a private Storage object to a `0600` file under a private per-worker directory, validates SHA-256 and magic/MIME, and invokes ClamAV with a scrubbed environment. Only then does a credential-free isolated Pillow process fully decode non-malicious JPEG/PNG/WebP under time and resource limits. Dependency, network, timeout, provider, or ambiguous outcomes schedule retry and never become clean.
- `clean` requires exact object identity, Storage metadata, observed bytes, checksum, format and EXIF-oriented dimensions. Malware is `flagged`; deterministic corruption/mismatch is `failed`; all three active assets must be clean before Submit readiness can pass.

## Repeatable deployment and isolation test

- Export the non-secret project URL/publishable key and the PostgreSQL `PG*` variables shown in `.env.example`.
- Run `bash scripts/deploy_supabase_phase1.sh` for a fresh database or `MT_APPLY_PHASE1_BASELINE=no bash scripts/deploy_supabase_phase1.sh` for an existing baseline. The script validates contracts first, applies ordered incremental migrations, and refuses production unless the release process explicitly sets `MT_ALLOW_PRODUCTION=yes`.
- Run `python3 scripts/test_supabase_deploy_script.py` locally/CI to verify both deployment modes without contacting a database.
- Create two disposable, email-verified development users through Supabase Auth.
- Export the `MT_TEST_USER_A_*` and `MT_TEST_USER_B_*` values, then run `python3 scripts/test_supabase_phase1_isolation.py`.
- The isolation test is read-only: each user must see only its own user/profile/role rows and receive a matching `current_authorization` result.
- Never use production identities or the Supabase service-role key for this test; a service-role key bypasses RLS and would invalidate the result.

## Development deployment status

- 2026-07-13：Phase 0 product schema 与 Phase 1 Auth/RLS migration 已部署到独立 Supabase development 项目。
- 远程只读核对：12/12 目标业务表存在并启用 RLS；34/34 Phase 1 policies 与 5/5 authorization functions 存在。
- 匿名 PostgREST 核对：`public_works` 可访问且当前为空；`users` 与 `user_roles` 均返回零行，未泄露私有数据。
- 2026-07-13：已创建两个 disposable development users；开发项目临时关闭 Confirm email 后，两者均由 Supabase Auth 标记为已验证，并由数据库 trigger 自动创建 active 业务用户、profile 与默认 `user` 角色。
- A/B RLS 验证通过：以 `authenticated` + 各自 JWT claims 模拟两个用户时，每人只能读取自己的 user/profile/role 各 1 行，对方 user 行为 0；`current_authorization` 的 user id 与默认角色均一致。测试未使用 service-role key，且未保存或记录随机密码。
- 2026-07-13：真实 Supabase TOTP/AAL2 集成测试通过。可逆地复用一个 disposable 用户，验证 Admin+AAL1 无跨用户权限、TOTP challenge/verify 签发真实 AAL2 JWT、Admin+AAL2 获得受保护读取范围、移除 Admin 后即使保持 AAL2 也只能读自身；测试最终恢复密码 hash，移除临时角色/MFA factor 并撤销测试 session。
- Admin 登录现在根据服务端角色/AAL 返回 `mfa` next action；`/auth/mfa` 通过服务端 HttpOnly session 代理 factors/enroll/challenge/verify，浏览器永不接触 access/refresh token。`/api/admin/access-check` 同时检查 active account、Admin/Super Admin role 与 AAL2。
- 已向 development 部署 `20260713_admin_mfa_hardening.sql`：inactive/suspended privileged user 不再通过 `has_any_role` 获得 Reviewer/Admin RLS scope。
- 2026-07-13：已把一个已验证 disposable identity 固化为 persistent development Admin；随机强密码仅保存在权限 `0600`、gitignored 的 `.env`，旧 Supabase sessions 已撤销，`development_admin.provisioned` 已写入 append-only audit log。密码登录验证为 Admin+AAL1，跨用户范围仍为 denied，等待真实管理员本人完成 TOTP enrollment 后升级 AAL2。
- 2026-07-14：修复真实浏览器登录后 MFA factor list 的 405；Supabase Auth 的 `GET /factors` 不存在，官方 client 的 `listFactors()` 复用 authenticated current-user payload。服务端现在从 `/user` 响应的 `factors` 规范化 `all/totp/phone`，`POST /factors` 仅保留用于 enrollment。
- 2026-07-15：使用 `MT_APPLY_PHASE1_BASELINE=no` 向 development 成功部署 `20260713_admin_mfa_hardening.sql` 与 `20260714_account_profile_boundary.sql`；两个 migration 均在独立事务中提交。部署后只读核对 5/5 通过：`update_my_profile(jsonb)` 存在、authenticated 可执行、anon 不可执行、authenticated 不再拥有 `user_profiles` 通用 UPDATE、`profiles_update_self` policy 不存在。
- 2026-07-15：向 development 部署 `20260715_workspace_drafts_folders.sql`。只读核对确认 `upload_intents` RLS 已启用，三个 bucket 均为 private 且限制为 50/20/10 MiB，五张 Workspace 写表的 authenticated 通用写权限为 0，11 个 `workspace_*` RPC 仅授予 authenticated，anon grant 为 0，全部现有账户均有受保护 system Inbox，Storage owner insert/select/delete policies 共 3 条。
- 2026-07-16：向 development 部署 `20260716_upload_retry_cancel.sql`。只读核对确认 `upload_intents.canceled_at` / `cleanup_status` 已存在，`workspace_cancel_upload_intent` 与 `workspace_finish_upload_cleanup` 均只授予 authenticated，anon 不可执行；取消响应不向浏览器返回 Storage asset keys。
- 2026-07-17：重放并部署最新 `20260717_workspace_asset_scanner.sql` 与 current-policy readiness。只读核对确认 scanner tables 2/2 启用 RLS，anon/authenticated/service_role 表 grant 为 0，service_role scanner RPC EXECUTE 为 3/3、anon/authenticated 为 0/6，两个关键 constraint 已验证、三个 trigger object 存在；现有 3 个 pending asset 对应 3 个 queued job/3 个 queued event，terminal job 与 invalid prerequisite 均为 0。另在单事务内执行真实 claim/complete/retry/lease-expiry/attempt-exhaustion 状态机测试并成功 `ROLLBACK`，数据库仍为 3 queued/3 pending，未保存或伪造 clean verdict。Worker 代码与 DB boundary 已完成，但 development 尚无 scanner secret/ClamAV 常驻进程，因此自动处理尚未投入运行。
- 待人工确认：开发项目 Confirm email 已重新开启；正式 Admin 身份必须由真实管理员使用自己的验证器完成 enrollment，不复用 disposable 测试因子。
