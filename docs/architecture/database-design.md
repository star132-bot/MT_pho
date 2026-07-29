# Database Design

## 当前状态

除非明确写明其他环境，本文所有“已部署”均指 development。当前仓库是生产候选，不表示已有生产数据库或生产服务被激活；所有会创建 fixture 的 rollback-only 数据库验收均为 development-only，发布演练只能连接 development 或隔离的 staging/生产恢复克隆，不能连接生产主库。

Phase 2A-2G 已把账户 owner-scoped Folder、Upload Intent、Draft、Version、Asset metadata、可靠取消/清理、private Supabase Storage、权威 readiness、Submit transaction、可信 asset scanner 与 Trash/Restore 接入当前 development boundary，并新增 authenticated-only User Dashboard 聚合和受保护 creator profile/editor。Phase 3 Supabase Review Queue/Detail/decision migration 与 Web 边界已部署；常规 assignment/start/decision 仍对所有角色禁止 self-review。`20260729_super_admin_self_publish.sql` 增加独立的 Super Admin+AAL2 owner 例外，只处理 untouched/unassigned Submitted submission，并再次核验 CAS、readiness、current version 和三类 current-policy-clean 资产；original 保持 private，专用审计 action 为 `review.super_admin_self_publish`。公开 Works 与 public creator portfolio 已切到 published-only Supabase DTO；legacy Review Center/SQLite 仅保留开发过渡用途。不要下载 MySQL，也不要执行历史 `database/schema.sql` 作为当前 production baseline。

Phase 4A Admin Works 数据库切片由 `20260723_admin_works_governance.sql` 承担：active Admin/Super Admin+AAL2 通过固定 RPC 读取全量作品和有界详情历史，并以 image `version` CAS、UUID idempotency、非空原因执行 Unpublish、Takedown、Restore。详情 provider DTO 为 current/history version、latest review、submission、decision、governance action 和 audit event 带上逐层父记录 ID，BFF 必须绑定后再投影浏览器字段。动作原子更新 publication/derivative visibility、`takedown_cases`、用户通知和 append-only audit；`image_governance_actions` 保存不可变请求与结果快照。通过 actor guard 且目标作品存在的 CAS、幂等、状态、legal hold、资产门禁和参数拒绝也会写 `admin.image.governance_failed`，其 metadata 仅保留 allowlisted action/reason、错误码、版本和 policy，不记录用户消息、内部备注或 token；不存在作品不创建攻击者可控的审计目标。Restore 会重新核验 active owner、ready/approved/current locked version、三类 current-policy clean 资产、scan job 与 Storage object 精确一致；original 始终 private，且不进入 Admin Works 详情 DTO 或签名路径。独立 Storage RLS 只允许 active Admin/Super Admin+AAL2、非 recovery 会话读取元数据完全匹配的 clean display/thumbnail；Review policy 对 Admin-only 同样禁止 original，只有 assigned Reviewer 在有效 submission 状态下保留既有原图权限。

Phase 4B Admin Users 数据库切片由按字典序位于 Phase 4A 之后的 `20260723_b_admin_user_governance.sql` 承担。它为 `users` 增加正整数 `version` 与显式 `is_system_identity`，安全补齐历史账户的基础 `user` role，并安装 `admin_list_users`、`admin_get_user`、`admin_govern_user` 三条 authenticated-only SECURITY DEFINER RPC。状态、角色和 session intent 使用 user-version CAS、UUID idempotency 和全局 transaction advisory lock；同一事务写 `notifications`、append-only `user_governance_actions` 与 success/failure `audit_logs`。Admin 不能治理 Admin/Super Admin；角色变化只允许 Super Admin；self/system/baseline-role/inactive privileged grant/最后 active non-system Super Admin 均失败关闭。当前 Web 进程不持有 Supabase Auth Admin credential，数据库只记录 `revoke_sessions` provider intent 并返回 `provider_action_required=true`；MFA、active session count 和 quota 明确为 unavailable/provider-managed，不从应用角色或活动时间推断。

`server.py` 维护分离的浏览器边界：`/api/me/profile*` 是受保护 owner profile/cover；`/api/folders`、`/api/uploads/*`、`/api/images*` 是 Supabase Workspace/Submit；`/api/admin/review-submissions*`、`/api/admin/works*`、`/api/admin/users*` 与 `/api/admin/audit-logs*` 是按角色/AAL2 收口的运营 API；`/api/inquiries`、`/api/notifications*` 与 `/api/inbox*` 是项目咨询和账户通信；`/api/archive/images*` 仅是 Admin+AAL2 legacy SQLite prototype。公开静态文件由显式 allowlist 提供，不能把 migration、脚本、部署文件或仓库文档暴露为下载路径。

Phase 5 通信与审计切片由 `20260723_d_communications_audit.sql` 承担。匿名访客和 active member 可通过同一幂等 inquiry RPC 建立会话；数据库的匿名结果只含 reference/status/created_at/replayed/selected-work count，BFF 对浏览器进一步收紧为 opaque reference/status，均不暴露 conversation、recipient、owner 或 work UUID。收件人通过 owner-isolated list/detail/read/reply/status RPC 管理 Inbox；reply 与 Close/Reopen 使用 conversation version CAS 和 UUID idempotency，同一请求重放返回首个不可变结果。访客回复在没有邮件 provider 时只记录 `provider_unavailable`，浏览器提供显式 manual mailto/copy，不声称邮件已发送。通知 DTO 固定为 `id,type,title,message,created_at,read_at,href`，`href` 只能是 allowlisted 站内路径，不返回 raw payload 或 recipient ID。

Audit Ledger 只允许 active Admin/Super Admin+AAL2、非 recovery 会话读取。list/detail/export RPC 返回安全 actor 摘要和 allowlisted change fields，不暴露 email、auth subject、Storage 坐标、token、IP 或原始 before/after JSON。导出需要 allowlisted reason 与 UUID idempotency、最多 1,000 行，并把 `audit.exported` 自身写入 append-only audit；相同 key/same payload 重放首个 snapshot，冲突 payload 拒绝。

当前新增了一个本地 SQLite 验证库，不作为生产后端，也不改变页面数据源：

- `database/local_archive_schema.sql`：SQLite 版本的本地作品档案 schema，用于验证表结构、标签关系和查询视图。
- `scripts/seed_local_archive_db.py`：从 `archive-data.js` 读取 27 张本地 sample 图片，写入 `data/archive.db`。
- `scripts/validate_local_archive_db.py`：创建临时 SQLite 数据库，运行 seed，并验证表/视图、外键、数据量、多版本资产、标签 JSON、比例分类、展示 URL fallback 和本地资源路径。
- `.github/workflows/database.yml`：在 pull request、`main`/`master` push 和手动触发时运行本地数据库验证。
- `server.py`：读取 `data/archive.db` 并通过 `GET /api/archive/images` 返回 `archive_image_view` 中 `visibility = 'published'` 且有 `image_url` 的作品；支持 `type`、`ratio`、`limit` 和调试用 `include_missing_assets` 查询参数；multipart `POST /api/archive/images` 保存上传资产到 ignored `assets/uploads/` 并写入 `images`、`image_assets`、`image_square_slices` 和标签关系；`PATCH /api/archive/images/{id}` 更新既有图片的标题、说明、系列、可见性、排序和标签关系；`DELETE /api/archive/images/{id}` 只删除 upload 来源作品并清理本地上传文件夹。
- `archive.js`：公开 Works 页面启动时优先读取 `/api/archive/images`，失败或无结果时回退到本地 sample/IndexedDB。
- `upload-studio.js`：个人上传平台；通过 signed URL 写入三个 private Storage bucket，完成/保存/readiness/Submit/Trash 走 Supabase RPC-backed API，IndexedDB 仅为离线只读 cache。
- `manage.js`：保存已有 seed 作品时同步调用 legacy SQLite API；首页设置仍在 IndexedDB 过渡层，dirty signature 只比较可编辑字段；当前不消费 Supabase submissions。
- `data/archive.db`：本地生成文件，已被 `.gitignore` 忽略；包含 `images`、`image_assets`、`image_tags`、`image_taggings`、`collections`、`collection_images` 和 `archive_image_view`。

生成命令：

```bash
python3 scripts/seed_local_archive_db.py
```

验收命令：

```bash
python3 scripts/validate_local_archive_db.py
```

验收脚本不会覆盖现有 `data/archive.db`，默认使用临时数据库；如需保留结果可使用 `--keep-db`，如需指定新文件可使用 `--db path/to/archive.db`。

## Protected creator profile boundary

- `database/migrations/20260722_z_creator_profile.sql` 以 transaction-wrapped migration 为 `user_profiles` 增加 `professional_headline`、`company`、`city`、`availability_status`、`instagram_url`、`linkedin_url` 与 nullable `cover_asset_id`；与既有 `display_name`、`bio`、`website_url`、`country_code` 合成页面的十字段 creator editor，偏好字段继续保留在同一 owner row。
- `database/migrations/20260723_c_profile_avatar_upload.sql` 为 `user_profiles` 增加当前头像的稳定私有 Storage metadata，并新增 owner-scoped upload intent。浏览器只接收短期 signed upload/read URL；complete RPC 在同一事务锁定 profile/intent，并核对 `storage.objects` 的 owner、bucket、key、MIME 和 size 后切换当前头像。取消、替换、删除返回受服务端再次校验的旧对象定位用于 best-effort 清理，locator 不进入浏览器 DTO。
- `update_my_profile(jsonb)` 只允许固定字段，拒绝空 patch、未知 key、非法长度/enum/country/locale/timezone/license、非 HTTPS URL，以及非 Instagram/LinkedIn 官方 host 的 social URL。普通 active authenticated user 可执行；recovery、inactive 和 Admin/Super Admin AAL1 失败关闭。
- `get_my_profile_cover()` 按当前 owner 的 image 选择最多 24 个候选：image 必须 non-deleted、`processing_status=ready` 且引用 current version；每个 image 优先 current-policy scanner-clean private `display`，缺失时回退 `thumbnail`。Asset 与 scan job 的 bucket-kind、key、MIME、size、dimensions、checksum 和 clean verdict 必须一致。
- `set_my_profile_cover(uuid|null)` 只接受上述候选或显式移除；拒绝跨 owner、original、pending/flagged、旧 scan policy、deleted image 和 bucket-kind mismatch，失败不改变已保存 cover。
- `require_creator_profile_user()` 与 `creator_profile_cover_asset_json(uuid,uuid)` 是 `SECURITY DEFINER`、空 `search_path` 的 owner-only helper；`update_my_profile(jsonb)`、`get_my_profile_cover()`、`set_my_profile_cover(uuid)` 只授予 `postgres + authenticated`，不授予 public/anon/service_role。
- Web 的 `GET/PATCH /api/me/profile/cover` 只返回 `{cover,candidates}` 或 `{cover,saved}` 的固定 DTO。每个非空 cover DTO 仅含 `id,image_id,title,kind,mime_type,width,height,signed_url,expires_in`；bucket、key、owner、scan internals 与 provider payload 不离开服务端，PATCH 还要求 same-origin CSRF。若 `set_my_profile_cover` 已提交但随后 Storage 临时签名失败，PATCH 必须如实返回 HTTP 200 `{cover:null,saved:true}`，客户端显示“已保存、预览暂不可用”并允许后续重新加载；不能把已提交 mutation 误报成保存失败。
- 这是受保护的个人账户边界。它不创建公开 profile slug、published-only creator DTO 或 public cover URL，也不改变公开 Works 当前的 SQLite/sample 数据源。

## 目标

当前 development Supabase 已保存私人 Draft，能权威计算 readiness、创建 immutable submission snapshots、锁定 submitted workflow，并由独立 Review Queue 执行 assignment/start/decision；受保护 creator profile/editor、owner-scoped cover、published-only Works/creator delivery 和 Admin Works/Users 已接入 development。project inquiry、Notifications/Inbox 与 Audit Ledger 的 Web/SQL 边界已形成生产候选，但 Phase 5 migration 与 development-only rollback acceptance 仍是环境提升门禁。尚未完成的生产运营项包括正式域名/TLS、生产 secrets、对象存储恢复策略、真实邮件 provider（可选）和上线后的监控告警；关系数据库保存 metadata、状态和对象 key，真实图片文件保存在 Supabase Storage。

核心要求：

- 保存图片真实原始尺寸，不能因为展示需要改写原始宽高。
- 上传一张作品时必须生成多版本资产：`original` 完整保留，`display` 用于前台展示，`thumbnail` 用于列表和后台快速预览，`square_slice` 用于非方图的后续归档/发布工作。
- 上传后根据原始尺寸自动匹配最近的比例分类：`1:1`、`4:3`、`4:5`、`2:3`、`3:2`、`16:9`、`Panorama`。
- 展示比例使用分类后的标准比例，所以 `800x850` 会保存为原始 `800x850`，但展示时可按 `1:1` 显示。
- 抽象作品保存为 `abstract` 并使用 `black_white` 展示模式；具象作品保存为 `concrete` 并使用 `color` 展示模式。
- 非 `1:1` 上传图保留原图，同时记录自动生成的 `1:1` 切片。
- 支持 Archive 页面按 Type 和 Ratio 过滤，也支持首页精选作品集合。

## 多版本图片资产策略

摄影原图通常为 10MB-50MB，不能直接用于前台画廊渲染。上传流程必须把“归档原图”和“网页展示图”拆开：

| 版本 | 用途 | 尺寸/质量 | 入库位置 |
| --- | --- | --- | --- |
| `original` | 原始归档、后续重新生成展示图、AI 分析、下载授权 | 不压缩、不改尺寸；保存 MIME、byte size、checksum、EXIF | `image_assets(kind = 'original')`，对象存储原图 bucket，默认不公开 |
| `display` | Works Archive、首页 Selected Works、详情展示 | 最长边 2200px-2400px；JPEG/WebP 质量 0.82-0.9；不放大、不裁切、不加黑边 | `image_assets(kind = 'display')`，展示 bucket，可公开或签名 URL |
| `thumbnail` | 后台列表、快速预览、管理界面 | 最长边 480px-720px；质量 0.72-0.82；保持比例 | `image_assets(kind = 'thumbnail')`，不替代作品展示图 |
| `square_slice` | 非 `1:1` 图片的方形切片归档/发布 | 来源坐标按原图记录；输出边长限制 1200px-1600px | `image_assets(kind = 'square_slice')` + `image_square_slices` |

Archive 页面展示时读取 `archive_image_view.image_url`。该字段优先使用 `display` 的 URL，没有 `display` 时才 fallback 到 `original`。`thumbnail` 只用于列表和后台，不作为作品主展示图。`images.original_width` / `images.original_height` 永远来自 `original`，不能被压缩后的 `display` 尺寸覆盖。

当前 Upload Studio 在浏览器生成 `original`、`display`、`thumbnail`，服务端创建 `{auth.uid}/{image_id}/{kind}.{ext}` signed destination，浏览器直传 private Storage，再由 complete RPC 创建 Draft/version/asset rows。Folder/Draft/readiness/Submit 以 PostgreSQL 为 authority，IndexedDB 只缓存最近成功响应。上传永远不会直接 published；成功 Submit 只进入 `submitted`，之后由独立 Supabase Review Queue 领取并决定。真实 asset 初始 `scan_status=pending`，Phase 2F 独立 worker 通过仅授予 service_role 的 leased RPC 读取并验证 private object，只有三个资产都以当前 policy 明确 `clean` 才允许 Submit；当前没有 user quota/capacity policy。Trash 是 soft delete，owner-scoped Trash view 与 Restore/Inbox fallback 已实现并通过真库与浏览器验收。公开 Works 已消费 strict Supabase publication DTO；只有 Admin/Super Admin+AAL2 的 Approve and publish 会把 clean display/thumbnail 公开，Reviewer Approve 仍保持 unpublished。

## 文件

- `database/schema.sql`：PostgreSQL/Supabase 兼容作品档案 schema，包含表、枚举、索引、更新时间 trigger、比例分类函数和 Archive 视图。
- `database/local_archive_schema.sql`：SQLite 本地验证 schema，字段命名和核心关系对齐目标 schema，但使用 `TEXT` ID 和 SQLite check/index/view 能力。
- `scripts/seed_local_archive_db.py`：本地 seed 脚本；读取 `archive-data.js`，写入本地 sample 图片、三类资产、派生标签、标签关联、`archive-featured` collection 和分析记录。
- `scripts/validate_local_archive_db.py`：本地和 CI 共用的数据库验收脚本；运行 seed 后检查 SQLite integrity/foreign key、核心表和 `archive_image_view`、published 数量、三类资产、URL fallback、标签 JSON、比例 code 和本地图片路径。
- `.github/workflows/database.yml`：数据库检查工作流；安装 Python 3.11 和 Node 20 后执行 `python3 scripts/validate_local_archive_db.py`。
- `archive-upload.js`：当前内部上传的本地处理管线，输出可迁移到 `images`、`image_assets` 和 `image_square_slices` 的对象。
- `upload-studio.js`：当前个人 Draft/Submit 客户端；signed upload、Folder、Draft、readiness、Submit、Trash 走 Supabase API，IndexedDB 仅为离线只读 cache。
- `admin-reviews.html` / `admin-reviews.js`：独立 Phase 3 Supabase Review Queue/Detail 客户端；通过服务端稳定 DTO 执行筛选、原子 claim/start、submitted snapshot inspection 与 versioned/idempotent decisions，不直接读取表或拼接 Storage key。
- `manage.js`：当前 legacy Review Center metadata 写入来源；已有 seed 作品保存到本地 SQLite，首页设置保存在 IndexedDB；尚未读取 Supabase `review_submissions`。
- `archive.js`：当前公开 Works 读取模型来源；优先读取本地只读 API 的 published 作品，失败时使用 sample/IndexedDB fallback，写入仍停留在浏览器本地过渡层。
- `server.py`：本地静态服务器；除 legacy Archive API 外，提供受保护的 Supabase Folder/upload/Draft/readiness/Submit 和 scoped Review Queue/Detail/assignment/start/decision 边界，对 provider/error/DTO/signed asset 做 allowlist 清洗；不提供消息 API。
- `database/migrations/20260716_workspace_submit_readiness.sql`：Phase 2E 增量；增加 submission UUID/readiness/asset snapshots 和 immutability guards，安装五项 readiness 与 versioned Submit RPC，收紧 submission table/Storage delete 权限，并把 workflow、notification、audit 写入同一事务。
- `database/migrations/20260717_workspace_asset_scanner.sql`：Phase 2F 增量；新增 restricted leased jobs、append-only events、INSERT enqueue trigger、SKIP LOCKED claim、token-bound retry/complete、attempt exhaustion、Storage object/观察值校验、scan notification/audit，并只向 service_role 授予三条 RPC 的 EXECUTE。
- `database/migrations/20260717_review_queue.sql`：Phase 3 增量；新增 scoped list/detail、atomic assignment/start 与 versioned/idempotent decision RPC，禁止 self-review，收紧 role-stacking RLS、current-clean private Storage bucket-kind/lifecycle、direct table/函数 ACL，并在事务内保存非空 expected version/result snapshot、notification 与覆盖 assignment/workflow/asset visibility 的真实 before/after audit。
- `database/migrations/20260729_super_admin_self_publish.sql`：不修改常规审核函数，新增独立 `review_super_admin_self_publish`；只有 active Super Admin+AAL2 且 owner=actor、submission 未分配/未开始/Submitted 时才可执行，固定 `approve_and_publish`，复用 current version/readiness/clean assets/CAS/idempotency/public derivative 边界并写专用审计。
- `database/migrations/20260722_user_dashboard.sql`：User Dashboard 聚合读模型；`dashboard_image_json(uuid)` 仅供 `postgres` owner 内部调用，`get_my_dashboard()` 仅授权 `postgres + authenticated`，拒绝 recovery session 并返回 owner-scoped counts/attention/recent/review/storage/capabilities。
- `database/migrations/20260722_workspace_trash_restore.sql`：Phase 2G owner-scoped Trash 列表；`workspace_list_trashed_drafts()` 仅授权 `postgres + authenticated`，拒绝 recovery session，只返回当前 owner 的 soft-deleted editable Draft。
- `database/migrations/20260722_z_creator_profile.sql`：Protected creator profile 增量；扩展十字段编辑合同与 availability enum，安装 strict profile update、cover eligibility helper，以及 authenticated-only owner cover read/write RPC。
- `database/migrations/20260723_admin_works_governance.sql`：Phase 4A Admin Works 增量；安装 publication-status/search/sort/pagination 列表、无 original locator 的单图有界详情、CAS/idempotent Unpublish/Takedown/Restore RPC，以及 Admin derivative-only Storage RLS；新增 append-only `image_governance_actions`，并在同一事务同步 derivative visibility、takedown case、notification 与 audit。
- `database/migrations/20260723_c_profile_avatar_upload.sql`：Profile Avatar 增量；安装 private `profile-avatars` bucket、512x512 JPEG/1 MiB 限制、owner intent RLS、create/complete/cancel/remove RPC 和仅允许当前公开头像对象的精确读取策略。
- `scripts/test_admin_works_database.py`：development-only、rollback-only Admin Works 真库验收；覆盖精确函数 ACL、角色/AAL2/recovery、列表/详情 DTO、无 submission 的跨 owner Admin Storage、Review Admin-only/assigned-Reviewer 原图边界、CAS 与不同 payload 幂等冲突、公开投递即时隐藏/恢复、legal hold、scanner/Storage restore gate、严格 append-only 与 fixture absence。
- `database/migrations/20260723_b_admin_user_governance.sql`：Phase 4B Admin Users 增量；安装用户 read model、version/system identity、baseline role repair、CAS/idempotent status/role/session-intent governance、全局 last-Super guard、notification 与 immutable success/failure audit。
- `scripts/validate_admin_users.py` / `scripts/test_admin_users_boundary.py` / `scripts/test_admin_users_database.py`：Admin Users 静态、secret-free Web 和 development rollback-only PostgreSQL 验收；覆盖 exact ACL/RLS、AAL2/recovery、profile-less user、DTO/关系绑定、CSRF、CAS/幂等、角色/身份保护、truthful provider intent、append-only 与 fixture absence。
- `scripts/test_user_dashboard_database.py`：development-only、rollback-only Dashboard/Trash/creator-profile 真库验收；十二个 marker 覆盖八个函数的安全元数据与精确 ACL、聚合结果、扩展字段、social host、owner 隔离、current-clean cover 与 bucket-kind filter、identity guards、Trash owner/state filter、事务回滚和独立 fixture absence。
- `scripts/validate_review_queue_phase3.py` / `scripts/test_review_queue_boundary.py`：Review SQL/UI/API/CI 静态合同和 secret-free fake-provider HTTP 回归。
- `scripts/test_review_queue_database.sql`：development-only、rollback-only 数据库验收；真实覆盖 User/Reviewer/stacked Admin AAL1/Admin AAL2、self-review、direct RLS、current-scan Storage 生命周期、CAS、Approve 后 Publish 仍稳定的 same-payload replay、冲突重放、notification 与 audit。
- `scripts/test_review_queue_concurrency.py`：development-only committed-fixture 双会话验收；启动六个独立 `psql` 会话并确保每组竞争使用不同 backend PID，覆盖 Start/claim、不同 key CAS 和 same-key replay 竞争，并在运行前后清理 fixture。
- `scripts/test_review_queue_browser.py`：development-only 真实 disposable 多身份浏览器验收；覆盖 Reviewer A claim、Reviewer B 越权拒绝、Request Changes、Admin AAL2 Approve、assigned Reviewer 的 original/display/thumbnail 与纯 Admin 的 derivative-only display/thumbnail 权限、桌面/移动 responsive、focus/dialog、console/session 与 fixture cleanup。
- `workers/scan_adapters.py` / `workers/image_scanner.py` / `workers/image_probe.py`：不进入 Web 进程的 trusted scanner；使用隔离的高权限 secret 下载 private object，拒绝 redirect 并核对 size/checksum/magic；ClamAV 与 Pillow 在无凭据子进程中执行，完整 decode/EXIF-oriented dimensions 受 time/resource limit 约束，明确区分 terminal failure 与 transient retry。

## 数据表

### `ratio_categories`

比例分类字典表。这里不用前端文案直接做主键，而使用稳定 code：

| code | label | display ratio |
| --- | --- | --- |
| `one_to_one` | `1:1` | 1 / 1 |
| `four_to_three` | `4:3` | 4 / 3 |
| `four_to_five` | `4:5` | 4 / 5 |
| `two_to_three` | `2:3` | 2 / 3 |
| `three_to_two` | `3:2` | 3 / 2 |
| `sixteen_to_nine` | `16:9` | 16 / 9 |
| `panorama` | `Panorama` | 2 / 1 |

`closest_ratio_category(width, height)` 会根据真实宽高返回最接近的分类 code。

### `artists`

作者表。当前站点只有 MT Presence 一个作者，但保留该表可以支持后续多作者或后台账号绑定。

关键字段：

- `auth_user_id`：可绑定 Supabase Auth 或自建登录用户 ID；不加外键，保持普通 PostgreSQL 可执行。
- `display_name`
- `slug`
- `email`
- `bio`
- `website_url`

### `images`

作品主表，保存每张图片的核心元数据和分类结果。

关键字段：

- `original_width` / `original_height`：真实原始尺寸。
- `original_aspect_ratio`：数据库自动生成的真实宽高比。
- `description` / `curatorial_note` / `artist_statement`：作品鉴赏层使用的说明、策展短注和长说明。
- `series`：作品所属系列或集合名，供鉴赏层和归档筛选使用。
- `ratio_category_code`：分类后的标准比例。
- `display_ratio_override`：特殊作品需要人工覆盖展示比例时使用，默认为空。
- `content_type`：`abstract` 或 `concrete`。
- `display_mode`：`black_white` 或 `color`。当前约束为抽象等于黑白，具象等于彩色。
- `ai_model` / `ai_confidence` / `ai_analysis`：AI 视觉分析结果。
- `exif`：相机、镜头、焦段、拍摄时间等 EXIF 原始信息。
- `visibility`：`draft`、`private`、`published`、`archived`。
- `sort_order`：人工排序，主要用于精选集或后台管理。

### `image_assets`

图片文件资产表。一个作品可以有多个文件版本：

- `original`：原始上传图。
- `display`：网页展示优化图。
- `thumbnail`：后台或列表缩略图。
- `square_slice`：自动生成的 `1:1` 切片文件。

关键字段：

- `storage_bucket`
- `storage_path`
- `public_url`
- `url_expires_at`：当 `public_url` 是签名 URL 时记录过期时间；公开 URL 可为空。
- `mime_type`
- `byte_size`
- `width`
- `height`
- `checksum_sha256`
- `source_asset_id`：`display`、`thumbnail`、`square_slice` 指向派生来源，通常是 `original`。

### `image_square_slices`

非方图自动切分后的 `1:1` 切片元数据。切片文件本身仍在 `image_assets` 中，`image_square_slices.asset_id` 指向对应资产。

关键字段：

- `slice_index`：切片顺序。
- `source_x` / `source_y`：切片在原图中的起点。
- `source_size`：原图中被截取的正方形边长。
- `width` / `height`：切片输出尺寸，数据库约束必须相等。

### `image_analysis_events`

AI 分析审计表。每次重新分析图片都新增一条记录，`images` 表只保存当前最新可用结果。

用途：

- 追踪使用过的 AI 模型。
- 保留历史分析 JSON。
- 允许人工复核后覆盖 `images.content_type`。

### `image_tags` / `image_taggings`

标签系统，后续可用于主题、地点、系列、材质、颜色等搜索。`image_tags.group_name` 用于前台鉴赏层按 Subject、Place、Form / Ratio、Mood、Material / Surface、Palette / Tone、Series / Collection 等轻量分组展示，避免把标签渲染成无序 chip 墙；Subject 内保留 Landscape、House / Building、Architecture、Animal、Object、Coast / Water、Mountain / Valley、Stone、Surface / Pattern 等主体类别。

### `collections` / `collection_images`

作品集合。首页 Selected Works 或未来专题都应该用集合表达，不要硬编码图片列表。

典型集合：

- `homepage-selected`
- `archive-featured`
- `black-white-landscape`

当前静态过渡层把首页 hero 和 Statement 设置保存到 IndexedDB `site_settings.homepage`。其中图片选择用 `database_shape.collection_images` 记录 `collection_slug = 'homepage-selected'`、`role`、`image_id` 和 `sort_order`，未来可以迁移到 `collections` / `collection_images`；hero/Statement 的文字属于页面内容配置，后续若需要服务端化，建议新增 `site_settings` 或 `page_content_blocks` 表承接，不要写入 `images.description` 等作品字段。

## 上传入库流程

1. 前端或后端读取图片真实尺寸、文件大小、MIME 类型、checksum 和 EXIF。
2. 原图不压缩上传到对象存储，准备写入 `image_assets(kind = 'original')`。
3. 基于原图尺寸调用 `closest_ratio_category(width, height)` 得到 `ratio_category_code`。
4. 调用视觉模型分析图片内容，判断 `abstract` 或 `concrete`；根据内容类型设置展示模式：`abstract -> black_white`，`concrete -> color`。
5. 插入 `images` 主记录，保存 `original_filename`、原始尺寸、比例分类、内容类型、展示模式、EXIF 和 `visibility = 'draft'`。
6. 写入 `image_assets(kind = 'original')`。
7. 生成 `display`：最长边 2200px-2400px，质量 0.82-0.9，保持原始比例，不放大、不裁切、不拉伸、不加黑边；写入 `image_assets(kind = 'display', source_asset_id = original_asset.id)`。
8. 生成 `thumbnail`：最长边 480px-720px，质量 0.72-0.82，保持比例；写入 `image_assets(kind = 'thumbnail', source_asset_id = original_asset.id)`。
9. 如果图片不是 `1:1`，按原图坐标生成方形切片；每个切片文件写入 `image_assets(kind = 'square_slice', source_asset_id = original_asset.id)`，坐标和顺序写入 `image_square_slices`。
10. 写入一条 `image_analysis_events`，保留本次 AI 分析原始结果。

## 前端字段映射

当前 `archive.js` 的 IndexedDB 结构可以这样迁移：

| 当前字段 | 数据库位置 |
| --- | --- |
| `id` | `images.id` |
| `title` | `images.title` |
| `src` | `archive_image_view.image_url`，优先 display，缺失时 fallback original |
| `width` | `images.original_width` |
| `height` | `images.original_height` |
| `ratio` | `ratio_categories.label` / `images.ratio_category_code` |
| `type` | `images.content_type` |
| `description` | `images.description` |
| `curatorial_note` | `images.curatorial_note` |
| `artist_statement` | `images.artist_statement` |
| `captured_at` | `images.captured_at` |
| `series` | `images.series` |
| `tags[]` | `archive_image_view.tags` |
| `tag_groups[]` | `archive_image_view.tag_groups` |
| `image_url` | `archive_image_view.image_url` |
| `thumbnail_url` | `archive_image_view.thumbnail_url` |
| `display_mode` | `images.display_mode` |
| `source` | `images.source_type` |
| `createdAt` | `images.created_at` 或 `images.uploaded_at` |
| `squareSliceCount` | `archive_image_view.square_slice_count` |
| `squareSlices` | `image_square_slices` + `image_assets(kind = 'square_slice')` |
| `imageRecord` | `images` 主记录草稿 |
| `assets[]` | 对象存储文件 + `image_assets` 多版本资产记录 |
| 旧版 `blob` | 兼容字段；迁移时作为 `image_assets(kind = 'original')` |

## Archive 页面查询

读取已发布作品：

```sql
SELECT *
FROM public.archive_image_view
WHERE visibility = 'published'
ORDER BY sort_order ASC, uploaded_at DESC;
```

筛选抽象作品：

```sql
SELECT *
FROM public.archive_image_view
WHERE visibility = 'published'
  AND content_type = 'abstract'
ORDER BY sort_order ASC, uploaded_at DESC;
```

筛选 `4:3` 作品：

```sql
SELECT *
FROM public.archive_image_view
WHERE visibility = 'published'
  AND ratio_category_code = 'four_to_three'
ORDER BY sort_order ASC, uploaded_at DESC;
```

首页精选作品：

```sql
SELECT v.*
FROM public.collections c
JOIN public.collection_images ci
  ON ci.collection_id = c.id
JOIN public.archive_image_view v
  ON v.id = ci.image_id
WHERE c.slug = 'homepage-selected'
  AND v.visibility = 'published'
ORDER BY ci.sort_order ASC, ci.created_at ASC;
```

## API 边界

当前 legacy SQLite 接口：

- `GET /api/archive/images`：读取 `data/archive.db` 的 `archive_image_view`，只返回 `visibility = 'published'` 的作品。
- 可选查询参数：`type=abstract|concrete`、`ratio=four_to_three|4:3|panorama`、`limit=1..1000`。
- 如果 `data/archive.db` 不存在，返回 `503` 和 seed 提示；`works.html` 会显示状态并回退到本地 sample 数据。
- `POST /api/archive/images`：创建新上传作品；请求为 multipart，`metadata` 字段包含 `images` metadata、`assets[]` 和 `square_slices[]`，每个文件字段名为 `asset:{asset_id}`；服务端保存文件到 ignored `assets/uploads/{image_id}/`，写入 `image_assets` / `image_square_slices`，并通过 `archive_image_view` 返回可展示 URL。
- `PATCH /api/archive/images/{id}`：只更新既有 `images` 行的 `title`、`description`、`curatorial_note`、`artist_statement`、`series`、`captured_at`、`content_type`、`display_mode`、`visibility`、`sort_order`，并替换该图片的 `image_taggings` 关系；不会创建图片、不会写入 `image_assets`、不会接收文件。
- `DELETE /api/archive/images/{id}`：只删除 `source_type = 'upload'` 的作品；SQLite 外键级联移除 `image_assets`、`image_square_slices`、`image_taggings` 和 `collection_images`，服务端同时删除 `assets/uploads/{image_id}/` 本地文件夹；内置 sample 作品返回 `403`。
- legacy `POST`/`PATCH` 强制校验 `abstract -> black_white`、`concrete -> color`；Upload Studio 不再调用这些接口。

当前 Phase 2A-2F Workspace 接口：

- `GET|POST /api/folders` 与 `PATCH|DELETE /api/folders/{id}`
- `POST /api/uploads/intents`、`DELETE /api/uploads/{id}` 与 `POST /api/uploads/{id}/complete`
- `GET /api/images?workflow_status=draft`
- `GET /api/images/{id}/readiness`
- `PATCH /api/images/{id}/draft`、`DELETE /api/images/{id}` 与 restore endpoint
- `POST /api/images/{id}/submit`，body 精确包含 `confirmation=submit-for-review`、current `expected_version` 与 UUID `idempotency_key`

Scanner 内部 RPC 不经过浏览器或 `server.py`，只接受 Supabase service-role/secret 身份：

- `scanner_claim_asset_scan(worker_id, lease_seconds)`：领取一个 allowlisted job snapshot 与短期 lease token；并发 worker 使用 `SKIP LOCKED`。
- `scanner_retry_asset_scan(asset_id, lease_token, error_code, retry_after_seconds)`：仅当前未过期 token 可安排有界重试，达到 attempt 上限后 terminal failed。
- `scanner_complete_asset_scan(asset_id, lease_token, result)`：只接受固定字段和固定 outcome/result code，重新锁定并核对 asset 与 Storage object；same-token retry 幂等，旧 token 被拒绝。

前端不应该直接拼对象存储路径；应读取 `archive_image_view.image_url` 或 API 返回的签名 URL。

作品放大鉴赏层应读取同一条 Archive 查询结果，不单独请求原图。字段优先级为：`display` 资产或 `archive_image_view.image_url` -> 必要时 fallback 到 `original_url`；`thumbnail_url` 只用于列表或快速预览，不替代作品展示图。标签建议直接返回 `tag_groups`，前端只做轻量渲染和缺省分组 fallback。

## 权限建议

Supabase 当前规则：

- 公开页面只能读取 `visibility = 'published'` 的图片和集合。
- 作者后台可以读取自己的 `draft/private/published` 图片。
- Workspace 写入只能由 active owner 通过 validated RPC 执行；Admin/Super Admin 还需要 AAL2。
- private bucket 已拆成 `image-originals`、`image-display`、`image-thumbnails`；Draft 读取使用签名 URL，原图不公开。
- authenticated 不能直接 INSERT/UPDATE/DELETE `review_submissions`；Submit RPC 才能创建 submission 并锁定版本。Owner 只可删除尚未登记为 `image_assets` 的临时 Storage object，registered object 留给受控 retention worker。
- Submit transaction 在 image/version/asset/object 锁下重新计算五项 readiness，保存 readiness/asset snapshot，更新 workflow/version，并原子写 notification 和 append-only audit。

## 后续接入顺序

当前进度与后续顺序：

1. 当前已完成本地读取连接：`server.py` 读取 `data/archive.db`，`works.html` / `archive.js` 优先消费 `/api/archive/images`。
2. 当前已完成本地既有作品 metadata/tag 写入连接：`manage.js` 保存 seed 作品时调用 `PATCH /api/archive/images/{id}`。
3. 已完成 `database/product_schema.sql` + Phase 1 RLS/Auth + Phase 2A-2G ordered Workspace migrations 的当前 development boundary。
4. 已完成 owner-scoped signed upload、Folder、Draft edit/list、soft-delete Trash/Restore、双并发 Retry/Cancel/Remove、partial-object cleanup、五项 readiness、idempotent Submit transaction、User Dashboard aggregate、受保护 creator profile/cover，以及独立 trusted scanner 的 leased/retry/clean/flagged/failed 代码与数据库状态机；Dashboard/Trash/creator-profile 真库门禁使用十二个 marker。development scanner 已具备隔离 secret 与 ClamAV 运行条件，production 常驻 Worker、监控与告警仍需交付。
5. `/admin/reviews` 的 scoped Queue/Detail、原子 assignment/start、versioned/idempotent decisions、notification/audit 与 private signed asset 边界已部署 development；rollback-only、双会话并发和真实 disposable 多身份浏览器验收均通过。
6. published-only production-candidate DTO、derivative public delivery、公开 Works 数据源迁移与 Admin+AAL2 Approve and Publish 已接通 development；public creator portfolio 使用独立只读边界，不直接暴露 protected profile DTO。legacy `manage.html` 仍保持独立 SQLite 原型。
7. Phase 4B Admin Users 已部署 development：账户目录、Suspend/Reactivate、Super Admin-only Reviewer/Admin role 管理、session provider intent、CAS/幂等/审计和三层门禁均完成。
8. Phase 5 的项目咨询、通知中心、站内 Inbox、Audit Ledger 和生产发布工具已形成生产候选；当前仍需在 development 或隔离 staging/恢复克隆完成 migration/rollback 验收，不能据此宣称已部署生产。
9. 后续补 scheduled orphan repair、user quota/rate limit、TUS、Withdraw/Escalate/Quarantine 与运营筛选，最后迁移首页精选、真实 AI 分析和仍被产品确认需要的 square slice/tag 能力；正式生产激活还要求域名/TLS、生产 secrets、Storage recovery、干净 release tag 与上线 smoke/观察。
