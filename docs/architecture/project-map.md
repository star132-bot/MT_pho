# Project Map

## 维护规则

- 每次新增、删除、移动或修改功能相关代码后，同步更新本文档。
- 按功能/页面归档文件职责，不只按目录罗列。
- 记录真实职责，不写愿景和过期计划。

## 全局结构

- `index.html`：首页入口；承载英文 hero、无限横向精选作品带、四段图文 Statement 和联系作者区域；首页只使用全宽顶部导航，不显示左侧 rail，hero 和 Statement 的主图/文字可由内部管理页写入的首页设置覆盖。
- `works.html`：公开作品档案页；使用与 Home/About/Lightbox/Contact 一致的全宽顶部导航，按 Search、Type/Ratio 文本 tabs、标题/数量/数据状态、全宽 masonry 图片墙的顺序组织内容；公开 UI 不显示 Upload、Review 或 Arrange，Viewer 继续提供 Add to Lightbox、Inquire 和 Download。
- `collections.html` / `collections.js` / `series-data.js`：已从公开导航和运行时依赖移除的历史 Series 原型；当前保留文件仅用于未提交工作区兼容，目标产品不得链接或加载。
- `about.html`：公开 About 页面；使用全站统一顶部导航，用作品图、作者实践说明、工作方法和可合作范围建立专业信息，并进入通用 Contact inquiry。
- `lightbox.html`：访客浏览器本地 Lightbox；使用全站统一顶部导航，展示、移除、清空个人选择，并把所选作品上下文带入 Contact。
- `archive-data.js`：Works Archive 的共享基础数据；保存本地样例作品 ID、路径、尺寸、内容类型和比例分类，供 `archive.js` 与 `manage.js` 用同一 ID 合并人工 metadata。
- `archive-upload.js`：共享浏览器导入管线；读取上传图尺寸、checksum、基础 EXIF，生成 `original` / `display` / `thumbnail` / `square_slice` 资产记录，供 Upload Studio 等内部工具复用。
- `manage.html`：内部 Archive Review 审核中心；作为本地作者 Publish 工作流入口出现在功能侧栏中，用紧凑操作栏和筛选 pill 审核作品 metadata、筛选待处理/未发布/已发布记录、一键发布，以及编辑首页 hero/Statement 图片和文字；Upload 链接统一进入受保护 `/workspace/images`，legacy Archive 非公开读取与 mutation 仅允许 Admin+AAL2。
- `dashboard.html`：受保护 canonical `/dashboard` 的全宽个人资料页；复用统一顶部导航，以可编辑横向摄影 cover、重叠 avatar、profile identity、安静资料列表和明确的 Edit profile/Upload work 动作为首屏，随后提供 Overview/My works tabs，展示服务端聚合 Status、Needs Attention、Recent Images、Review Activity、Storage 与最近可编辑 Draft，并覆盖 loading、empty、permission、error 和 retry；该页不是公开 creator portfolio。
- `upload-studio.html`：受保护 `/workspace/images` 承载的渐进式 Upload Workspace；Loading/空状态只显示 Folder + 主导入区，选中 Draft 后展开编辑器；提供双并发队列、Cancel/Retry/Remove、分组 metadata、900ms 自动/手工保存、冲突 Reload、五项 Submission readiness、确认式 Submit for Review，以及只读 Trash/Restore 分段视图；不含 hard delete、Review decision 或 Publish 控件。
- `admin-reviews.html`：受保护 `/admin/reviews` 与 `/admin/reviews/{submissionId}` 的 Supabase Review Queue/Detail 工作台；以紧凑 status/assignment queue、image-first submitted snapshot、rights/evidence/history inspector、policy checklist 和 decision dialog 承载审核；移动 Detail 提供保留 URL/选中态的 Back to queue，当前只显示 Request Changes、Reject、Approve，不在 public delivery 接通前显示虚假的 Publish 能力。
- `contact.html`：联系作者独立页面；使用全站统一顶部导航，承载英文联系说明、作品图和结构化邮件草稿表单，可接收 Work、Series 或 Lightbox 上下文。
- `auth.html` / `auth.js`：Phase 1 统一用户入口；同一可访问 editorial shell 按 `/auth/sign-in`、`/auth/register`、`/auth/forgot-password`、`/auth/reset-password`、`/auth/verify-email` 的配置呈现字段、loading、invalid/expired、field error、success 与下一步；Forgot 使用防枚举成功文案；Reset/Verify 同时兼容 fragment `token_hash` 和 Supabase 默认 implicit fragment，先把敏感 fragment 读入函数内存并立即清除 URL，再由 same-origin 服务端换成 `HttpOnly` Cookie，禁止 local/session storage；所有 mutation 先获取 HttpOnly double-submit CSRF token，并校验 Origin；登录 200 后仍以 no-store `/api/me` 确认 Cookie，再执行 Admin MFA 或 `/workspace/images` 跳转。
- `mfa.html` / `mfa.js`：Admin TOTP enrollment 与登录 challenge 页面；复用 editorial Auth shell，覆盖 factors loading、首次 QR/手工 secret、已有 factor、6 位验证码、provider error、invalid/expired code、success、sign-out 与移动端布局；发现旧的 unverified TOTP factor 时由受保护 enrollment API 自动重置并生成新的 QR/secret；QR data URI 兼容 `<svg>` 与带 XML declaration 的 Supabase SVG；MFA mutation 同样使用 Origin + CSRF token，所有 token 仍只存在于服务端 HttpOnly session。
- `account-settings.html` / `account-settings.js`：受保护 `/settings/account` 账户页面；复用单一全局顶栏，以紧凑标题栏、sticky 本地导航和连续白色表单面板组织 Profile、Preferences、Security 与 Sessions。Profile 的十个 creator 字段按 Identity、Work、Location、About、Links 五组排列，维护滚动章节同步和 dirty/disabled/saving/error/success 状态，保留请求期间产生的更新输入，以显式安全导航避免成功注销被 dirty prompt 截断，使用 `/api/me/profile` 读写服务端 profile，并通过 provider 支持的 `others` / `all` scope 撤销会话；不伪造头像上传、远程设备列表或位置历史。
- `styles.css`：全站视觉系统和响应式布局；定义 gallery palette、`--ui-*` 与 `--presentation-*` 状态/视觉 token、固定公开顶栏、移动展开菜单、首页图片覆盖过渡、紧凑 Statement、Infinite Marquee Gallery、无公开侧栏的 Works 全宽 masonry、图标式 hover 操作层、沉浸式作品查看器、创作者资料页的横向摄影 cover/重叠头像/安静事实列表与工作区、账户设置连续中性表单、Upload 渐进式布局、Supabase Review Queue/Detail/decision 状态、联系页、统一 focus-visible 和响应式规则。
- `script.js`：首页短程滚动过渡、登录态 Dashboard 入口、IndexedDB 首页设置读取和应用、Statement 标题和每个图文 moment 的渐进显影、锚点点击平滑滚动逻辑；不再维护作品分类或比例筛选状态。
- `public-navigation.js`：公开页与 Dashboard 共用的窄屏顶部导航控制器；在 `760px` 断点同步菜单 open/closed、`aria-expanded`、`aria-hidden` 与 `inert`，支持按钮点击、ArrowDown 首项聚焦、Escape 关闭并恢复触发器焦点、链接选择、焦点离开、外部点击和 viewport 切换；不读取登录状态，也不复制账户菜单或 Sign out 逻辑。
- `public-archive.js`：Series、Lightbox、Contact 共用的公开作品读取层；统一 API/sample/IndexedDB published fallback、数据归一化、比例样式和 `mt-presence-lightbox-v1` 读写，并兼容迁移旧 Saved/Collection keys。
- `contact.js`：结构化咨询表单逻辑；负责必填校验、条件 Budget 字段、Work/Series/Lightbox 上下文读取与移除、`mailto:` 草稿生成、loading 和 toast。
- `archive.js`：公开 Works 逻辑；优先读取 SQLite API，失败时回退 sample/IndexedDB published 作品，处理 Search/Type/Ratio 与 URL 状态、Viewer、Add to Lightbox、Inquire、Download、Related Works 和 hover 操作；Draft 上传不再被兼容提升为 published。
- `collections.js`：历史 Series 索引/详情原型逻辑；文件仍可把 `series-data.js` 的 workIds 与 published archive 合并，但当前公开导航和运行时页面不加载或链接它。
- `lightbox.js`：读取公开作品和 `mt-presence-lightbox-v1`，渲染个人选择、移除/清空、空态和咨询入口。
- `dashboard.js`：并行读取 `/api/me/profile` 与单一 `/api/dashboard` 聚合 DTO，渲染身份、Status/Attention/Recent/Activity/Storage/Drafts 和 Overview/My works 键盘 tabs；通过 `GET/PATCH /api/me/profile/cover` 加载、选择或移除当前 owner 的合格封面并恢复 dialog 焦点；不遍历 `/api/images` 计算统计，不使用浏览器存储。
- `account-menu.js`：公开顶部导航及 Dashboard、Upload、Review、Account 共用的 signed-in identity control；公开页默认显示 Sign In，`/api/me` 成功后替换为进入 `/dashboard` 的 initials 头像和 role-aware menu，失败时保留 Sign In；菜单支持方向键/Home/End/Escape/outside/focus restoration，并通过 CSRF 执行 Sign out。
- `manage.js`：内部 legacy Archive Review 审核逻辑；同步 SQLite metadata/tag，保留 IndexedDB fallback，并维护筛选、checklist、Approve & Publish、Homepage 编辑与离开提示；Homepage dirty signature 只比较可编辑字段，`beforeunload` 只读取既有 dirty 状态，未修改页面不再被派生 `database_shape` 误判。当前不读取 Supabase `review_submissions`。
- `upload-studio.js`：Phase 2A-2G Upload Workspace 客户端；双 worker 上传三类 private asset，900ms 串行 autosave 和手工 Save 共享 `expected_version`，409 保留本地表单；从服务端读取五项 readiness，仅在 pending 时 5 秒轮询；Drafts/Trash 视图分别加载 active/trashed DTO，Trash 卡片只读并提供 Restore 的 loading/error/conflict/permission 状态；IndexedDB 仅为离线只读缓存，浏览器不能写 scan verdict。
- `admin-reviews.js`：Phase 3 Review Queue 客户端；维护 URL/deep-link queue state、移动 Queue/Detail 视图、唯一 queue accessible name、latest-wins list/detail fetch、Reviewer 原子 Start claim、signed preview、Actual size、checklist alert/focus、提交 busy/conflict recovery、CSRF retry、dialog focus restoration 和 Request Changes/Reject/Approve 决定；不把 Storage key 写进 DOM 或浏览器存储。
- `server.py`：Python 标准库本地开发服务器；提供静态文件与 legacy SQLite Archive API；Supabase 边界覆盖 Auth/MFA/Profile/Session、Dashboard、Workspace 与 Review Queue 路由保护；Dashboard 只接受 `get_my_dashboard()` 固定 DTO，creator cover 只接受严格投影后的 owner-scoped current ready scanner-clean display/thumbnail asset，并把 private coordinates 换成短期 signed URL；Review API 对 User/recovery/Admin AAL1 fail closed；legacy Archive 非公开读取与 mutation 继续仅允许 Admin+AAL2。
- `workers/scan_adapters.py`：Phase 2F scanner I/O 边界；当前实现只调用三条 scanner RPC，使用隔离 secret 流式读取 private Storage，拒绝 redirect，限制字节并核对 SHA-256/magic/MIME；ClamAV 使用无凭据最小环境，临时文件为 `0600` 且完成后删除。
- `workers/image_scanner.py`：Phase 2F 独立扫描进程与 CLI；执行单任务或持续轮询，把确定性文件问题落为 failed、恶意命中落为 flagged、依赖/网络问题落为 retry；校验 download/scan/decode/request 总预算不超过 lease，使用每 Worker `0700` 临时目录并启动清理，结构化日志仅允许非敏感字段；不得被 `server.py` 导入或共享 secret。
- `workers/image_probe.py`：无凭据 Pillow 子进程；以 JPEG/PNG/WebP allowlist 完整 decode，处理 EXIF-oriented dimensions、多帧与 decompression bomb，并应用 timeout、CPU/core/NOFILE 及操作系统支持时的内存限制。
- `requirements-scanner.txt` / `.env.worker.example`：为 Python 3.11 hash-lock Pillow scanner 依赖并定义独立的 Supabase secret、ClamAV、租约、下载/扫描/解码超时和资源限制环境变量；真实 `.env.worker` 被 Git 忽略。
- `scripts/configure_development_scanner.py`：development Scanner 本地配置入口；从 Web `.env` 复用 Supabase URL，只通过隐藏输入或进程环境接收 privileged credential，拒绝 publishable/placeholder key 和 secret CLI 参数，以真实空文件扫描校验 ClamAV，保留稳定 Worker ID，并在全部检查通过后原子写入权限 `0600` 的 Git ignored `.env.worker`。
- `scripts/test_configure_development_scanner.py`：secret-free Scanner 配置回归；使用假 current/legacy credential 与假 ClamAV，验证密钥不进入日志、publishable key 和 ClamAV failure fail closed、旧配置不被覆盖、Worker ID 稳定及文件权限为 `0600`。
- `README.md`：GitHub 项目首页说明；记录版本、功能、运行方式、静态浏览和联系页邮件草稿行为。
- `CHANGELOG.md`：版本记录；当前第一版为 `v1.0.0`，`Unreleased` 记录联系作者功能。
- `VERSION`：当前项目版本号。
- `.gitignore`：Git 忽略规则；排除临时源图、截图、本地缓存、本地 skill 目录、环境变量文件和本地运行产物。
- `project-development-guardrails/SKILL.md`：本地企业级项目开发护栏 skill；定义开发前读代码、文档闭环、垂直切片、验收、验证和自审规则。
- `docs/README.md`：项目文档统一索引；定义 Product、Architecture、Design、Operations 分类和维护规则。
- `docs/architecture/database-design.md`：后期数据库接入设计说明；记录作品档案表、上传入库流程、前端字段映射、Archive 查询、权限建议，以及本地 SQLite 作品库验证流程。
- `docs/operations/upload-testing.md`：上传功能联调和手工验证说明；记录启动方式、数据库检查、公开页回读、故障排查和相关 API 示例。
- `docs/operations/review-testing.md`：Phase 3 Review Queue 权限矩阵、local contract、真实 development RLS/Storage/并发，以及已通过的 disposable 多身份浏览器验收说明。
- `docs/operations/enterprise-delivery-workflow.md`：项目统一交付门禁；定义需求进入、UI 参考研究、页面提示词、垂直切片、状态设计、自动化/浏览器/安全验收、发布观察与复盘，并提供可复制的企业级摄影网站主提示词和发布评分表。
- `database/schema.sql`：PostgreSQL/Supabase 兼容数据库预留 schema；当前不作为本地运行库，项目完工后再用于创建作品、资产、比例分类、AI 分析记录、1:1 切片、标签和精选集合。
- `database/product_schema.sql`：Phase 0 目标产品 schema；定义用户/角色、所有权、文件夹、三类图片状态、不可变版本与审核、通知、下架案件和 append-only 审计，并以 `public_works` 统一公开读取源。
- `database/supabase_phase1_auth_rls.sql`：Phase 1 Supabase 权限 baseline；把 `auth.users` 同步为业务 user/profile/default role，为私有业务表启用 RLS，建立 owner/reviewer/admin/AAL2/public Works/Storage 策略，并以 `update_my_profile(jsonb)` 取代通用 profile UPDATE，限制字段、active account 与 Admin AAL2。
- `database/migrations/20260715_workspace_drafts_folders.sql`：Phase 2A transaction-wrapped migration；创建 `upload_intents`、三个 private bucket、system Inbox trigger、Storage delete policy 和 11 个 `workspace_*` RPC；撤销 Folder/Image/Version/Asset/Intent 通用 authenticated 写权限，业务写入只能走 validated RPC。
- `database/migrations/20260716_upload_retry_cancel.sql`：Phase 2B transaction-wrapped migration；为 upload intent 增加 `canceled_at` / `cleanup_status`，提供 owner-scoped cancel 与 cleanup-result RPC，completed intent 禁止取消且重复取消保持幂等。
- `database/migrations/20260716_workspace_draft_compliance.sql`：Phase 2C transaction-wrapped migration；为既有 `image_versions` 合规字段补充数据库约束，扩展 `workspace_draft_json` 与 owner-scoped `workspace_update_draft`，验证 Alt Text、版权年份、人物/财产 release、权利声明、AI 与敏感内容枚举，同时保留 Draft lock 和 authenticated-only RPC 边界。
- `database/migrations/20260716_workspace_draft_versioning.sql`：Phase 2D transaction-wrapped migration；在 Draft DTO 中暴露 `lock_version`，增加 `workspace_update_draft_versioned` 与 `workspace_trash_draft_versioned` 的行锁/CAS 边界，版本不匹配返回 `DRAFT_VERSION_CONFLICT`；撤销 authenticated 对旧 unversioned update/trash RPC 的 execute，只授权新 versioned RPC；删除 Folder 并把 Draft 移入 Inbox 时同步递增 `images.version`。
- `database/migrations/20260716_workspace_folder_integrity.sql`：Phase 2D Folder 归属完整性 migration；以 owner-scoped transaction advisory lock 串行化 Folder 删除与 `images` / `upload_intents` 的 Folder assignment，防止并发写入 soft-deleted Folder；上传完成时若原 Folder 已被并发删除，触发器把记录落入 active Inbox；恢复 Trash Draft 时若原 Folder 已失效，同样回退到 Inbox。
- `database/migrations/20260722_workspace_trash_restore.sql`：Phase 2G owner-scoped Trash read model；拒绝 recovery JWT，仅向 active authenticated owner 返回 soft-deleted editable Draft DTO 并附带 `deleted_at`，撤销 public/anon/service_role execute。
- `database/migrations/20260716_workspace_submit_readiness.sql`：Phase 2E transaction-wrapped migration；新增五项 owner-scoped readiness 与 versioned/idempotent Submit RPC，为 submission 保存 UUID、readiness/asset snapshots，锁定 image version 并保护 submission snapshot，不允许 authenticated 直接写 submission；同一事务更新 workflow/version、创建 notification 与 append-only audit，并禁止 owner 直接删除已登记到 `image_assets` 的 Storage object。
- `database/migrations/20260717_workspace_asset_scanner.sql`：Phase 2F transaction-wrapped migration；创建 inaccessible `asset_scan_jobs` 与 append-only events，自动 enqueue 新 asset，提供仅 service_role 可执行的 SKIP LOCKED claim、token-bound retry/complete RPC，验证真实 Storage object 和观察值，处理租约过期/attempt 上限，并把最终状态投影到 `image_assets` readiness。
- `database/migrations/20260717_review_queue.sql`：Phase 3 transaction-wrapped migration；提供 scoped queue/detail、non-self atomic assignment/start、versioned/idempotent decisions、非空 expected version/immutable result snapshot、notification/audit 与 Admin publish boundary；重写 Reviewer/Admin+AAL2 RLS 和 current-clean private Storage bucket-kind/lifecycle scope，并撤销 direct decision/submission writes/truncate。
- `database/migrations/20260722_user_dashboard.sql`：用户 Dashboard transaction-wrapped read model；authenticated-only `get_my_dashboard()` 调用 active-account guard，在数据库聚合 counts、Changes Requested-first attention、recent work/review activity 与 storage usage，并返回未配置 quota/public delivery 的明确 capability flags。
- `database/migrations/20260722_z_creator_profile.sql`：protected creator profile transaction-wrapped migration；扩展十字段资料合同与 availability enum，以 strict `update_my_profile(jsonb)` 拒绝未知字段/非 HTTPS 或非官方 social host，并提供 owner-scoped current-ready/current-policy-clean cover helper 及 authenticated-only `get_my_profile_cover()` / `set_my_profile_cover(uuid)`；helper 不授予 authenticated，recovery/inactive/Admin AAL1 fail closed。
- `scripts/validate_product_phase0.py`：Phase 0 契约检查；验证目标 schema 核心表/状态/append-only 规则，并检查五个公开页面不再链接 Series/Collections、不包含或预留 public rail、完整加载统一顶栏/账户入口/移动导航，以及 `public-navigation.js` 的 ARIA/inert/键盘合同。
- `scripts/validate_auth_foundation.py`：Phase 1 Auth/Account 契约检查；验证认证与 Account Settings 页面/API、Cookie/CSRF、Profile/Session client、增量部署入口和可访问性钩子，并禁止 token 使用 localStorage/sessionStorage/IndexedDB。
- `scripts/validate_supabase_phase1_rls.py`：Phase 1 数据权限契约检查；验证 auth user trigger、全部私有表 RLS、owner isolation、Reviewer/Admin 角色、Admin AAL2、Profile RPC baseline/增量 migration、Published-only 公开读取、Storage 用户目录与角色禁止直写规则。
- `scripts/validate_workspace_phase2.py`：Phase 2A-2E 静态契约检查；验证 schema/migrations、私有 bucket、Draft/Folder/Submit RPC 权限、autosave/conflict、五项 readiness、idempotent Submit、snapshot/Storage retention、Works 统一公开 shell，以及登录后从账户菜单进入 Workspace 的 destination 和 CI wiring。
- `scripts/test_workspace_phase2_boundary.py`：secret-free loopback fake-provider 集成；除 Folder/upload/Draft/CAS 外，覆盖 active/trashed list、Restore CSRF/重复 404/Folder 回退 Inbox、readiness blocked/pending/ready、Submit、幂等和 submitted lock。
- `scripts/test_workspace_trash_browser.py`：真实 Auth UI + fake provider 浏览器验收；覆盖只读 Trash、Restore、1440/390 无横向溢出与固定头部重叠、截图及 page error。
- `scripts/validate_workspace_asset_scanner.py`：Phase 2F 静态契约检查；验证 job/event 隔离、lease/token/attempt、RPC grant 与 result allowlist、Storage 二次校验、Pillow/ClamAV fail-closed 路径、scanner-only 环境和日志字段白名单。
- `scripts/test_workspace_asset_scanner.py`：secret-free loopback scanner 集成；以真实 Pillow fixture 和 fake ClamAV 覆盖当前 secret key/legacy service-role header、redirect 拒绝、子进程 credential 隔离、JPEG/PNG/WebP/EXIF、多帧/像素限制、clean/failed/flagged/retry、Storage failure、临时文件与敏感日志排除。
- `scripts/validate_review_queue_phase3.py`：Phase 3 静态契约检查；验证 migration transaction、RPC/ACL、completed filter、role-stacking+AAL2、non-self Reviewer scope、current-clean Storage bucket-kind、并发幂等、真实 audit snapshot、发布前 asset/version 状态及 Web/UI/CI/docs wiring；静态检查不替代真实 PostgreSQL apply。
- `scripts/test_review_queue_boundary.py`：secret-free fake-provider HTTP integration；覆盖 Review route/auth/MFA/CSRF、status filter、DTO allowlist、Reviewer cross-assignment、atomic start、stale CAS、decision idempotency 和 Admin publish precheck。
- `scripts/validate_user_dashboard.py` / `scripts/test_user_dashboard_boundary.py`：Dashboard/creator-profile 静态 SQL/UI/API/CI 合同与 secret-free loopback HTTP 集成；覆盖 anonymous/canonical guards、aggregate/profile/cover RPC、十字段 profile、严格 DTO、CSRF cover mutation、合法 review activity、重复 asset 签名缓存、provider 字段清洗、非法 aggregate、跨 owner asset 与 bucket-kind mismatch 拒绝。
- `scripts/test_user_dashboard_database.py`：development-only、rollback-only Dashboard/Trash/creator-profile 真库发布门禁；十二个成功 marker 检查八个函数的 `SECURITY DEFINER`、空 `search_path` 和精确 EXECUTE ACL，其中三个 helper 仅 `postgres` owner 可执行，五个公开 RPC 仅 `postgres + authenticated`；以真实 authenticated JWT claims 覆盖双 owner 聚合隔离、资料字段/社交 URL 约束、current-clean cover eligibility、inactive/recovery/stacked Admin AAL1 拒绝、Admin AAL2 成功及 Trash owner/deleted/workflow 过滤；事务回滚后用独立连接确认固定 fixture UUID 不存在。
- `scripts/test_review_queue_database.sql`：development-only、rollback-only Phase 3 数据库验收；用事务级 advisory lock 和完整 Workspace fixture 真实覆盖 role/AAL/role stacking、self-review、direct RLS、current-scan Storage 生命周期、stale CAS、Approve + Admin Publish 后仍稳定的 replay snapshot、冲突重放、notification/audit，并恢复临时禁用的 scanner insert trigger 后回滚全部数据。
- `scripts/test_review_queue_browser.py`：development-only 真实 disposable Reviewer/Admin 多身份浏览器验收；覆盖 Reviewer A claim、Reviewer B cross-assignment 拒绝、Request Changes、Admin AAL2 Approve、三类 private asset、桌面/移动 responsive、focus/dialog、console/session 与 fixture cleanup，且不持久化测试状态。
- `scripts/test_workspace_asset_scanner_database.sql`：development-only、rollback-only 数据库状态机测试；覆盖三个 disjoint claim、token replay/conflict、retry、lease reclaim、old-token 拒绝和 attempt exhaustion，不保存 verdict。
- `scripts/deploy_supabase_phase1.sh`：Phase 0/1 Supabase 数据库部署入口；执行 Phase 0-3 静态 migration contract 门禁，使用 libpq `PG*` 环境变量避免密码出现在进程参数，fresh database 默认执行 baseline 后按文件名顺序执行 `database/migrations/*.sql`；已有数据库使用 `MT_APPLY_PHASE1_BASELINE=no` 只执行幂等增量 migration；默认拒绝未确认的 production 部署。
- `scripts/test_supabase_phase1_isolation.py`：只读远程集成测试；使用两个已验证开发用户的普通 access token，验证双方只能读取自己的 user/profile/role，以及 `current_authorization` 与身份一致，不使用会绕过 RLS 的 service-role key。
- `scripts/test_supabase_admin_mfa.py`：可逆的真实 Supabase TOTP/AAL2 集成测试；临时复用明确 disposable 的开发用户并恢复其 hash/roles/factors/sessions，验证 Admin+AAL1 denied、真实 TOTP enrollment/verify、Admin+AAL2 allowed 与 non-Admin+AAL2 denied，且不输出凭据、secret 或 token。
- `scripts/test_local_auth_session_refresh.py`：本地 Auth 实时回归；使用 gitignored development Admin 建立独立 AAL1 session，故意破坏 access Cookie 后通过 refresh Cookie 触发轮换，断言 `/api/me` 回写两枚新 Cookie 且 `/auth/mfa` 不发生回登录页的 303；输出只含状态，不打印凭据或 token，并尽力撤销测试 session。
- `scripts/test_auth_security_boundary.py`：无需真实凭据的本地 Auth/Account 安全集成测试；用 loopback fake provider、临时 SQLite/asset fixture 和真实 `MTRequestHandler` 验证缺失/跨源 CSRF、防枚举 Forgot、受限 recovery、密码更新、Workspace/Account 路由门禁、普通用户 Profile 读写与输入归一化、current-only Session 能力、others/all revoke、Admin AAL1 MFA 拒绝，以及 legacy upload 资产隐私，全程不输出 token/password。
- `scripts/test_supabase_deploy_script.py`：无需数据库的部署回归；注入临时 fake `psql`，验证 fresh baseline 与 existing-database migration-only 两种执行顺序，并确认非法 baseline 模式在任何数据库调用前失败。
- `database/migrations/20260714_account_profile_boundary.sql`：已有 Supabase Phase 1 环境的 Account Settings 增量加固；删除通用 profile UPDATE，安装字段 allowlist、active account 与 Admin AAL2 约束的 `update_my_profile(jsonb)` RPC。
- `scripts/provision_development_admin.py`：持久 development Admin provisioning；幂等选择 `.env` 指定或已验证 disposable 身份，随机轮换密码、撤销旧 sessions、授予 Admin、更新开发显示名、写 append-only audit，并以普通 password token 验证 Admin+AAL1 仍无跨用户 scope；凭据只原子写入权限 `0600` 的 gitignored `.env`。
- `database/migrations/20260713_admin_mfa_hardening.sql`：现有 Supabase 环境的幂等权限加固；让 `has_any_role` 同时要求 active account，避免暂停/封禁的特权用户继续获得 Reviewer/Admin RLS scope。
- `docs/architecture/provider-decisions.md`：Phase 1 的认证 provider、Cookie session、服务端 RBAC 与私有对象存储边界。
- 2026-07-13：Supabase development 已实际部署 Phase 0 schema、Phase 1 Auth/RLS 与 inactive privileged user 加固；远程核对 12 张 RLS 表、34 条策略、5 个授权函数完整，匿名只能读取空的 `public_works`，无法读取 `users` 或 `user_roles` 行；两个 disposable 用户的业务初始化/A-B RLS 隔离通过，真实 TOTP 流程进一步验证 Admin+AAL1 denied、Admin+AAL2 allowed、non-Admin+AAL2 denied，临时身份状态已恢复。
- `database/local_archive_schema.sql`：SQLite 本地作品档案验证 schema；对齐目标作品表、资产表、标签表、集合表和 `archive_image_view`，用于在接后端前校验图片 metadata 与标签关系。
- `scripts/validate_local_archive_db.py`：本地 SQLite 作品库验收脚本；创建临时数据库，运行 seed，并检查 schema、外键、核心数据量、多版本资产、Archive view、标签 JSON、比例分类和本地图片路径。
- `.github/workflows/database.yml`：数据库与 Auth/Account/Workspace 安全检查 GitHub Actions workflow；安装锁定 scanner 依赖，在 PR、`main`/`master` push 和手动触发时运行本地 Archive、产品/Auth/RLS/Profile/Phase 2F 契约、受保护浏览器脚本 `node --check`、secret-free Web/scanner 集成测试和 fake-`psql` 部署顺序回归。
- `docs/design/design-system.md`：MT Presence 的组件库选型、设计系统、排版规则、画廊增强方案和后续技术路线。
- `docs/product/user-upload-admin-spec.md`：唯一目标产品规格；明确取消目标 Series，定义用户系统、受保护 Upload Workspace、Drafts/Folders、Submit/Review、删除/下架、Admin Platform、数据模型、API、安全和验收。
- `docs/design/image-sources.md`：记录当前临时图片素材来源、使用规则和替换要求。
- `shots/`：页面验收截图和历史设计快照目录；包含首页、Works、Manage 的调试和对比图，不参与运行时页面加载。
- `assets/art/`：首页主视觉和作品图片资源目录；当前为 `gpt-image-2-all` 生成的临时 AI 视觉样张，正式上线前应替换为 MT 真实作品或确认授权可用的最终生成图。
- `assets/archive/`：作品档案页本地样例图目录；当前 27 张样例下载自 Picsum Photos，用于保证 `works.html` 不依赖运行时外链加载。
- `data/.gitkeep`：保留本地数据目录；`data/*.db` 为本地运行产物并由 `.gitignore` 忽略，当前支持生成 `data/archive.db`，联系作者不再生成消息数据库。
- `data/messages.db`：历史消息数据库产物；当前功能已移除，仅保留为旧运行产物说明，不再被页面或 API 使用。
- `tmp/art-source/`：临时源图目录；由处理脚本读取，不直接被页面引用。
- `scripts/prepare_art_assets.py`：历史/备用本地处理脚本；读取 `tmp/art-source/` 下的源图，裁切、调色并输出到 `assets/art/`；当前页面不依赖该脚本生成的推荐比例逻辑。
- `scripts/seed_local_archive_db.py`：本地 SQLite 作品库 seed 脚本；通过 Node VM 读取 `archive-data.js`，生成 `data/archive.db`，写入 27 张本地 sample 图片、`original/display/thumbnail` 资产、派生标签、`image_taggings`、`archive-featured` collection 和 seed analysis 记录。
- `project-development-guardrails/agents/openai.yaml`：Codex 项目入口配置；定义该 skill 的显示名、简短说明和默认提示词。
- `skills/frontend-aesthetic-reviewer/`：前端审美评审 skill 目录；用于截图、页面审查和设计提示，不参与站点运行时。
- `.claude/settings.local.json`：本地 Claude 配置；仅用于作者本机环境设置，不影响项目页面功能。
- `image.png`：仓库根目录临时图片文件；当前无运行时职责。

## 1. 首页与品牌介绍

### 功能说明

- 展示 MT Presence 的品牌名称、英文核心宣言、大幅摄影背景、Selected Works 作品带、四段图文 Statement 序章和两个主操作按钮。
- 页面入口：`index.html`
- 主要用户操作：点击 `Enter Works` 进入 Works；点击 `View Series` 进入 Series；通过 Current Series 直达当前摄影项目；页面底部联系入口进入 Contact。

### 相关文件

- `index.html`：定义 hero、Selected Works、Current Series、Statement、Contact；hero 主/次 CTA 为 Enter Works / View Series；Current Series 当前链接到 `weather-at-the-threshold`。
- `styles.css`：实现参考图式摄影背景、右侧主标题、斜切下沿、按钮样式、Selected Works 作品带、紧凑双列 Statement 和移动端单列布局；hero 使用非 sticky 双层图片过渡，桌面高度上限约 `92svh`、移动端约 `82svh`，各视口首屏都露出下一段内容。
- `script.js`：启动时读取 IndexedDB `site_settings.homepage`，用 `--home-hero-abstract-image` / `--home-hero-concrete-image` CSS 变量和 `data-home-*` DOM 钩子覆盖首页 hero/Statement 图片与文字；根据 hero 自身的短程滚动进度设置图片和两套文案的分段淡出/淡入变量，并在 hero 接近结束时切换导航栏状态；登录态把首页 Sign In 更新为 Dashboard；用 IntersectionObserver 渐进增强 Statement 显影，未触发动画时内容仍可读；拦截页内锚点点击并扣除 header 高度后执行 ease-in-out 纵向滚动。
- `docs/design/design-system.md`：记录首页的视觉定位、字体、色彩、按钮和布局规则。
- `docs/design/image-sources.md`：记录首页主视觉当前素材来源和替换规则。
- `assets/art/hero-ci-jian.jpg`：首页主视觉临时样张。

### 页面内部结构

- 主视觉：`hero-stage` 桌面高度上限约 `92svh`、移动端约 `82svh`，`hero` 保持普通页面流而非 sticky；滚过主视觉时把 `assets/art/hero-ci-jian.jpg` 黑白抽象风景平滑切到 `assets/art/hero-concrete.jpg` 具体彩色风景，抽象文案和具象文案同步分段淡出/淡入、轻微上移，避免两套大标题叠字；首屏下沿必须露出 Selected Works，按钮不随滚动替换。
- 品牌文案：默认抽象阶段为 `Abstract Field`、`A Quiet Field for Images` 和 `Images are not records of the world...`；默认具象阶段为 `Concrete Field`、`Where Looking Becomes Presence` 和 `Light, weather, and distance settle into form...`；内部 `manage.html` 可覆盖两阶段图片、eyebrow、标题和说明。
- Works：`#works` 在 Statement 前展示 `Works / Selected Works` 标题和 Infinite Marquee Gallery，为后续 Statement 留出视觉加载空间。
- Current Series：`.home-series-feature` 使用一张明确作品、年份、系列标题、synopsis 和 View Series 入口连接公开 Series detail。
- Statement：`#statement` 使用 `.statement-intro` 标题和 `.statement-moments` 四段图文；桌面以两列重复单元提升扫描密度，移动端回到单列；每个 `.statement-moment` 包含 `.statement-media`、`.statement-moment-copy`、`.statement-index` 和一段文案，最终 `.statement-cta` 链接到 `works.html`；内部 `manage.html` 可覆盖 Statement 标题、四段图片和四段文字。
- 按钮：Hero 使用 `Enter Works` / `View Series`；Statement 保留 `Enter Works`；底部联系段使用 `Contact Artist`。
- 状态：IndexedDB `site_settings.homepage` 是当前首页手工配置过渡层，未来可迁移到页面设置表和 `collections.slug = 'homepage-selected'`；滚动进度控制 `--hero-concrete-opacity`、`--hero-copy-shift`、`--hero-copy-abstract-opacity`、`--hero-copy-concrete-opacity`、`--hero-copy-abstract-panel-shift`、`--hero-copy-concrete-panel-shift`、`--hero-title-alpha`、`--hero-statement-alpha`、`--hero-copy-shadow-alpha` 和 `--hero-copy-shadow-blur`；`body.is-scrolled` 在 hero 底部接近 header 后触发导航换肤；Statement 由 `data-statement-section`、`data-statement-moment`、`.is-animating` 和 `.is-visible` 控制渐进显影，但初始透明度保持内容可读。
- 响应式：桌面 Statement 使用两个稳定列轨，移动端图片和文字改为普通流单列，所有段落直接可读；`prefers-reduced-motion` 下关闭 Statement 过渡并直接显示内容。
- 测试：通过浏览器打开页面检查布局、锚点平滑滚动、下滑过渡、Selected Works 在 Statement 前、四段 Statement 图文分别入场、最终 CTA 和联系页跳转。

## 2. 无限横向作品带

### 功能说明

- 作品区展示精选 AI 生成风景图，不再提供分类切换或比例筛选。
- 图片保持原始宽高比，统一行高，自然宽度展示。
- 横向作品带从右向左缓慢连续滚动，第二组重复图片负责无缝循环。
- 悬停作品带时暂停滚动；悬停单张图片时只做轻微放大和透明度过渡。

### 相关文件

- `index.html`：定义 `works` 区域和两组重复的 `.marquee-track` 图片序列。
- `styles.css`：实现 `.marquee-gallery`、`.marquee-track`、`.marquee-item`、`gallery-marquee` 动画、悬停暂停、图片自然比例、移动端高度和 `prefers-reduced-motion` 降级。
- `docs/design/design-system.md`：记录 Infinite Marquee Gallery 规则和不裁切摄影作品的约束。
- `docs/design/image-sources.md`：记录当前 AI 生成图片的模型、日期和临时用途。
- `assets/art/abstract-01.jpg`：AI 生成黑白风景图，1024x1536。
- `assets/art/abstract-02.jpg`：AI 生成黑白风景图，1024x1536。
- `assets/art/abstract-03.jpg`：AI 生成黑白风景竖图，1024x1536。
- `assets/art/hero-concrete.jpg`：AI 生成彩色具象图，当前不参与首页 hero 滚动替换，仅作为素材保留。
- `assets/art/concrete-01.jpg`：AI 生成低饱和彩色风景图，1024x1536。
- `assets/art/concrete-02.jpg`：AI 生成低饱和彩色风景图，1024x1536。
- `assets/art/concrete-03.jpg`：AI 生成低饱和彩色风景竖图，1024x1536。

### 页面内部结构

- 作品带：`.marquee-gallery` 内包含两个 `.marquee-track`，第二个 `aria-hidden="true"`，用于无缝循环。
- 图片展示：`.marquee-item` 统一高度；`img` 使用 `width: auto`、`height: 100%`、`object-fit: contain`，不裁切、不拉伸、不加黑边。
- 表格：无。
- 表单：无。
- 弹窗/抽屉：无。
- 状态：纯 CSS 动画；没有 JS 作品状态。
- API：无运行时远程接口；当前图片为 2026-06-06 通过私有图像生成代理的 `gpt-image-2-all` 模型别名生成后保存到本地。
- 测试：检查作品带连续滚动、悬停暂停、图片无裁切、移动端高度合理、`prefers-reduced-motion` 下可横向手动滚动。

## 3. 智能作品档案页

### 功能说明

- 作品档案页用于公开展示已发布的作者上传图片和本地样例图片。
- 上传入口已迁移到内部 `upload-studio.html`，公开 `works.html` 不再显示 Add Works。
- 档案卡片显示比例使用分类后的标准比例，而不是原始尺寸的细微偏差；例如 `800x850` 会按 `1:1` 展示，但 `Size` 仍显示原始 `800x850`。
- 如果上传图不是 `1:1`，前端会使用 canvas 按短边尺寸自动生成多个 `1:1` 方形切片，切片输出限制到约 1400px 并记录原图 source 坐标；档案页仍按原始比例分类展示，不裁切原图。
- 内容类型分为 `Abstract` 与 `Concrete`。当前静态版本通过文件名关键词做前端启发式分类，并在 `archive.js` 的 `classifyContent()` 中保留未来接入视觉模型的替换点。
- 内部上传图会在浏览器中生成多版本资产：`original` 原图完整保留，`display` 用于前台画廊展示，`thumbnail` 用于未来列表/后台，非方图额外生成 `square_slice`；原始宽高、checksum、基础 EXIF、比例分类、抽象/具体分类、标题、`assets[]` 和 `squareSlices[]` 会通过 multipart 写入本地 `assets/uploads/` 与 SQLite 的 `images` / `image_assets` / `image_square_slices`，同时保存到 IndexedDB 作为浏览器 fallback。
- 抽象图片以黑白展示；具体图片以低饱和彩色展示。
- 页面不再渲染或预留公开左侧 rail；固定全局顶栏之后依次是全宽 Search、可横向滚动的 Type/Ratio 文本 tabs、Works Archive 标题/Count/数据状态和作品区。
- Gallery 提供 Search、Type、Ratio 三组叠加过滤器，并把状态写入 URL；公开页面不提供 Arrange。Type 固定为 All Works/Abstract/Concrete，Ratio 固定为 All Ratios/Square/Classic/Portrait/Vertical/Landscape/Cinema/Panorama，当前项使用细下划线而不是胶囊块。
- 点击作品卡片会打开可由 `?work={id}` 直达的放大鉴赏层；Info 抽屉展示标题、策展说明、Add to Lightbox/Inquire/Download、metadata、标签和 Related Works。
- `All` 模式使用协调的 masonry 图墙，让不同尺寸图片自然错落并保持整体平衡。选择具体比例后切换为比例专用网格，图片按当前比例组等宽缩放并铺满行宽，不裁切、不拉伸、不加黑边。

### 相关文件

- `works.html`：统一顶部导航、Search/Type/Ratio、标题/Count/数据状态、gallery、空态/toast 和带 Info、Add to Lightbox/Inquire/Download/Related Works 的沉浸式 Viewer；公开 UI 不含 Upload、Review、Arrange。
- `archive-data.js`：定义本地样例作品基础数据，`archive.js` 启动时按同 ID 合并 IndexedDB 中保存的 manual metadata。
- `archive-upload.js`：定义上传读取尺寸/EXIF/checksum、`original`/`display`/`thumbnail`/`square_slice` 资产生成、非方图 `1:1` 切片和内容分类，默认建立 Draft，供 `upload-studio.js` 调用。
- `archive.js`：published 读取、叠加搜索/过滤与 URL 同步、Viewer/focus/scroll、Lightbox、Inquiry、Related Works、Download、toast 和 gallery reveal；历史 arrange/upload helper 仍在文件内但公开 DOM 不挂载入口。
- `styles.css`：公开顶栏、无 rail 全宽布局、搜索/文本 tabs、四/三/二/一列 masonry、hover/focus 操作、Viewer/Info、Series/About/Lightbox/Contact、内部工具和响应式规则。
- `docs/architecture/database-design.md`：定义项目完工后可能接入的服务端数据库模型和当前 IndexedDB 字段迁移关系。
- `database/schema.sql`：预留服务端作品档案表结构、索引和 `archive_image_view` 查询视图；当前不执行。
- `assets/archive/`：存放 27 张本地摄影样例图，覆盖 `1:1`、`4:3`、`4:5`、`2:3`、`3:2`、`16:9`、`Panorama`。

### 分类规则

- 比例分类：`1:1`、`4:3`、`4:5`、`2:3`、`3:2`、`16:9`、`Panorama`。
- 示例尺寸：`4000x4000` -> `1:1`；`4000x3000` -> `4:3`；`4000x5000` -> `4:5`；`4000x6000` -> `2:3`；`6000x4000` -> `3:2`；`1600x900` -> `16:9`；`4000x2000` -> `Panorama`。
- 内容分类：`Abstract` 包含 textures、shadows、light patterns、geometry、minimal details；`Concrete` 包含 people、architecture、landscapes、animals、identifiable objects。

### 页面内部结构

- 上传：公开 Works 页面不挂载上传控件；受保护 Upload Studio 的 `input[type=file][multiple]` 为每张图显示读取、压缩、切片、分析、上传、完成或失败状态，三类资产通过 signed URL 写入 private Supabase Storage，完成后创建服务端 Draft。
- 多版本资产：`original` 不压缩并保存原始尺寸/MIME/byte size/checksum/EXIF；`display` 最长边约 2300px、质量约 0.86，用于画廊展示；`thumbnail` 最长边约 640px、质量约 0.78，用于未来后台列表；所有资产使用 `storage_bucket`、`storage_path`、`mime_type`、`byte_size`、`width`、`height`、`checksum_sha256` 字段对齐 `image_assets`。
- 自动切片：非 `1:1` 上传图通过 `createSquareSlices()` 生成方形切片，输出边长限制约 1400px；切片文件作为 `image_assets(kind = 'square_slice')` 保存，`source_x`、`source_y`、`source_size` 和顺序保存在 `squareSlices[]`，对齐 `image_square_slices`。
- 过滤：顶部 Search、Type、Ratio 叠加生效；状态同步到 `?q=`、`?type=`、`?ratio=`，Count 和数据来源状态使用 `aria-live` 更新；桌面筛选区可吸附在 64px 顶栏下方，移动端回到普通流并允许各组横向滚动，公开页面不提供 Arrange。
- Gallery：完整使用内容视口，`>=1180px` 四列、`761-1179px` 三列、`520-760px` 两列、`<520px` 单列；图片保持自然比例、无厚边框/阴影/大圆角，hover 或 focus 才显示品牌角标、Add to Lightbox 和 Download；Lightbox 状态写入 `mt-presence-lightbox-v1`，Draft/Archived 记录不能进入公开列表。
- 作品查看器：`?work={id}` 可直达；Info 抽屉包含展签、metadata、tags、statement、Related Works、Add to Lightbox、Inquire 和 Download；Inquire 使用 `contact.html?source=work&work={id}`。
- 标签可视化：`normalizeWorkDetail()` 优先读取 `title`、`description`、`curatorial_note`、`artist_statement`、`content_type`、`ratio_label`、`original_width`、`original_height`、`captured_at`、`series`、`tags[]`、`tag_groups[]`、`image_url`、`thumbnail_url`、`display_mode`；没有标签数据时按作品标题、类型、比例和 display mode 派生 Subject、Place、Form / Ratio、Mood、Material / Surface、Palette / Tone、Series / Collection 等轻量分组，主体标签覆盖 Landscape、House / Building、Architecture、Animal、Object、Coast / Water、Mountain / Valley、Stone、Surface / Pattern 等内容类别。
- 联系：导航 `Contact` 链接到 `contact.html`。
- 状态：过滤器与 Viewer 使用 URL，可恢复当前搜索和指定作品；Lightbox 使用 `mt-presence-lightbox-v1` 并通过 `mt:lightbox-change` 同步当前页面；鉴赏层继续维护焦点和滚动恢复。

## 4. About、Lightbox 与历史 Series 文件

### 功能说明

- `about.html` 负责作者实践与专业信息；`lightbox.html` 只负责访客当前浏览器中的个人选择，两者都复用统一公开顶部导航且无左侧 rail。
- 页面入口：`about.html`、`lightbox.html`。`collections.html` / `collections.js` / `series-data.js` 是已从公开导航和运行时依赖移除的历史 Series 原型。
- 主要用户操作：进入 Works Viewer、管理 Lightbox，并携带 Work/Lightbox 上下文咨询。

### 相关文件

- `collections.html` / `collections.js` / `series-data.js`：历史 Series 原型文件；当前公开导航、`public-navigation.js` 和运行时页面不得加载或链接。
- `about.html`：Practice、Availability 和 Contact CTA。
- `lightbox.html` / `lightbox.js`：本地选择清单、移除/清空、空态、Works Viewer 和 Contact 入口。
- `public-archive.js`：Lightbox 与 Contact 共享 published archive 读取和 Lightbox key 迁移。
- `styles.css`：定义 `.series-*`、`.about-*`、`.lightbox-*` 和公开页面响应式规则。

### 页面内部结构

- Lightbox：`mt-presence-lightbox-v1` 保存有序 work IDs；首次读取兼容合并旧 Saved/Collection keys；`?source=lightbox` 把清单带入 Contact。
- About：事实型 Practice 与 Availability 内容，不复制 Home 四段 Statement，也不展示虚构经历。
- 状态：API 不可用时显示 sample fallback；空 Lightbox 有单一有效下一步；所有公开页桌面/移动端无横向溢出。

## 5. 公开导航与作者工作台导航

### 功能说明

- Home、Works、About、Lightbox、Contact 和 Dashboard 共用一套固定顶部导航；公开页面不渲染左侧 rail，也不保留 `padding-left`、margin、grid track 或定位宽度。桌面顺序固定为 MT Presence、Home、Works、About、Lightbox、Contact、Sign In/账户身份。
- 当前公开路由通过 `aria-current="page"` 和细下划线标识；导航高度桌面固定 64px、移动端固定 56px。移动端顶栏只保留品牌、Sign In 或账户身份和菜单按钮，主导航在按钮下方展开，不允许链接换行挤压或页面横向溢出。
- 未登录公开页保留 Sign In；`account-menu.js` 成功读取 `/api/me` 后才把它替换为进入 `/dashboard` 的头像和账户菜单。Workspace/Review/Account/Sign out 继续存在于 role-aware 账户菜单，不作为第二套公开导航常驻展示。
- Home 与内部工具的登录态头像统一进入受保护 `/dashboard` 个人资料；资料页的 Edit profile 再进入 `/settings/account#profile`。头像是目的地链接，旁边的账户菜单按钮继续承担 Dashboard/Workspace/Account/Review/Sign out 导航。
- Upload/Review 内部 rail 提供 Dashboard、Works、Upload、Review、Account destinations；Review 按 Admin 权限显示，active 项仅改变当前入口状态。
- 78px rail 只属于 Upload/Review 等内部工作区；不得重新用于 Works、About、Contact、Lightbox 或 Dashboard。
- Lightbox 仍只保存在当前浏览器；Upload/Review/Account 使用服务端账户与权限边界。

### 相关文件

- `index.html` / `works.html` / `about.html` / `contact.html` / `lightbox.html`：共享同一顶部信息架构、Sign In fallback、账户菜单挂载点和移动菜单钩子，桌面/移动端都不包含公开左侧 rail。
- `dashboard.html`：复用同一全局顶部信息架构的 protected personal profile，不显示左侧 rail。
- `public-navigation.js`：只负责公开/资料页移动导航的 open/close、ARIA/inert、键盘和外部关闭行为。
- `account-menu.js`：读取登录状态并在 Sign In 与账户身份之间切换，保留 role-aware destinations 和 CSRF Sign out。
- `upload-studio.html` / `manage.html`：Artist Workspace rail；Review 入口保留权限控制。`account-settings.html` 使用自己的单一全局顶栏与本地章节导航，不再渲染第二条桌面 rail。
- `styles.css`：固定 64/56px 公开 header、桌面文字导航、移动展开菜单、公开页零 rail 宽度和内部工作区 rail 的独立规则。
- `scripts/validate_product_phase0.py`：静态检查五个公开页面不存在 public rail/占位，并都包含统一路由、账户入口、移动触发器和导航脚本；同时检查移动菜单的 ARIA/键盘合同。

### 页面内部结构

- Works/About/Contact：公开观展、作者信息和咨询。
- Lightbox：公开工具入口，显示当前浏览器选择数量。
- Dashboard：受保护个人资料、封面与作品状态总览；不是 public creator portfolio。
- Upload/Review：内部 Draft 导入与发布审核；Works 返回公开档案。
- 响应式：公开页和 Dashboard 在 1440x900、1024x768、390x844 下都应无 rail 占位、无重复导航和横向溢出；菜单链接、头像、按钮、文本与图片不得遮挡。内部工具移动端继续隐藏自己的 rail，页面不保留空白宽度。

## 6. 内部 Archive Review 审核中心

### 功能说明

- 内部作者审核页面，用于检查作品标题、Viewer 文本、标签、资产和 visibility，按 All / Needs review / Unpublished / Published 筛选队列，一键把审核通过的作品发布到公开 `works.html`，并维护首页 hero/Statement 图片和文字。
- 入口：`manage.html`；顶部公开导航不强调，桌面极简 rail 提供 `Review` 入口，供本地作者维护流程使用。
- 编辑字段对齐数据库目标结构：`images.title`、`images.series`、`images.curatorial_note`、`images.description`、`images.artist_statement`、`images.captured_at`、`images.content_type`、`images.display_mode`、`images.visibility`、`images.sort_order`，以及 `image_tags` / `image_taggings` 标签关系。
- 保存已有 seed 作品或上传作品 metadata 时，`manage.js` 会同步写入本地 SQLite 的 `images`、`image_tags` 和 `image_taggings`，同时保留 IndexedDB 作为浏览器 fallback；新图片导入、压缩和文件夹归类由 `upload-studio.html` 负责。公开 `works.html` 优先通过 `/api/archive/images` 读取 SQLite 结果，接口不可用时再按作品 ID 合并 IndexedDB manual metadata；`script.js` 启动时读取 `site_settings.homepage` 覆盖首页图文。

### 相关文件

- `manage.html`：定义审核中心左侧 rail、紧凑 Review 操作栏、审核统计 pill 筛选、Review Queue 列表、右侧 Viewer 信息审核表单、审核 checklist、Approve & Publish、保存当前、保存全部、撤销、删除内容/删除上传图确认弹窗，以及下方首页 hero/Statement 设置区。
- `archive-upload.js`：共享上传管线仍被 Upload Studio 使用，输出可迁移到 `images` / `image_assets` / `image_square_slices` 的本地对象；`manage.html` 不再暴露直接导入控件。
- `manage.js`：读取共享 `archive-data.js` base data 和 IndexedDB 存储；归一化 base data、manual metadata、database shape；生成 `image_tags` 与 `image_taggings`；推导审核状态和 checklist；按 All / Needs review / Unpublished / Published 筛选队列；`Approve & Publish` 先校验标题、Viewer 文本、标签和资产，再把 visibility 写为 `published` 并调用 `PATCH /api/archive/images/{id}` 同步 SQLite metadata/tag 关系；处理 homepage settings 表单同步、Hero 图片预览、保存/撤销、dirty 状态、保存、批量保存、刷新、离开提示和标签键盘编辑。
- `archive-data.js`：提供稳定 sample ID，保证管理页保存的 metadata 能被 `works.html` 同 ID 回读。
- `archive.js`：公开 Works 页面优先读取 SQLite published 记录；接口失败时读取 IndexedDB/sample，只复活明确 `published` 上传图；`draft` 不再因历史兼容逻辑被提升为公开状态。
- `styles.css`：复用全站中性 gallery palette，为内部作者工作台、Homepage 预览编辑器、保存状态、dirty 状态、表单、列表和移动端布局提供规则。

### 页面内部结构

- 审核统计：页面顶部用一行 pill 显示 All records、Needs review、Unpublished、Published 四个筛选按钮和数量；筛选会同步影响左侧 Review Queue，不再使用大统计卡片。
- 左侧 Review Queue：显示本地样例作品和上传作品；列表项显示缩略图、Type、Ratio、Size、Visibility/审核状态，dirty 项显示 Unsaved。
- Upload Studio handoff：`manage.html` 顶部只提供 `upload-studio.html` 入口；创建文件夹、批量上传、压缩、入库和上传后初始编辑都在 Upload Studio 完成。
- Homepage：常驻编辑台维护抽象/具象 hero 的图片、eyebrow、标题和说明，以及 Statement 标题、四张图和四段文案；每个 hero 区域显示当前图片预览和 Image selector；保存到 IndexedDB `site_settings.homepage`，内部记录 `database_shape.collections = ['homepage-selected']` 和 `collection_images` 风格的 image/role/sort_order 映射，方便未来迁移。
- 右侧审核表单：字段顺序贴近 Viewer 显示顺序，显示作品预览、数据库摘要、审核状态和 checklist；表单字段包括 Title、Curatorial Note、Description、Metadata、Tag Groups、Artist Statement、Visibility。
- Approve & Publish：点击后先校验审核 checklist，缺少标题、Viewer 文本、标签或展示资产时显示 inline error 和 toast；通过后把 visibility 改为 `published` 并复用原保存流程写入 SQLite 和 IndexedDB fallback。
- Metadata：`Captured`、`Content Type`、`Display Mode`、`Sort Order` 可编辑；原始尺寸、比例、图片路径、`image_assets` 和 square slice 数据只展示，不在表单中随意修改。
- Tag Groups：表单固定显示 Subject、Place、Form / Ratio、Mood、Material / Surface、Palette / Tone、Series / Collection 七组；默认值与 Works Viewer / SQLite seed 共用同一套派生规则，用户可用逗号或换行编辑标签；保存时写成 `imageRecord.tag_groups`、扁平 `tags`、`image_tags` 与 `image_taggings` 结构，已有 seed 作品和上传图都会同步写入 SQLite `image_tags` / `image_taggings`，并保留 IndexedDB fallback。
- 状态：`dirtyRecordIds` 记录未保存作品，`isHomeDirty` 记录未保存首页设置；Homepage signature 只包含用户可编辑的 hero/statement 字段，不比较由表单派生且形状可能变化的 `database_shape`；`beforeunload` 只读取既有 dirty state，不在离开瞬间重新序列化表单。真实修改仍提示，未修改页面直接离开；保存成功/失败用 toast 和 inline 状态反馈。
- 删除：`Delete Content Data` 清空 manual metadata，并把标签重置为默认派生标签，保留图片资产；`Delete Image Record` 只对上传图启用，本地样例图作为 base data 不允许删除。
- 测试：编辑已有 seed 作品保存后，`PATCH /api/archive/images/{id}` 返回更新后的 SQLite 视图数据；刷新 `works.html` 点击同一作品，Viewer 右侧信息显示更新后的标题、说明、metadata、标签分组和 statement；上传图保存后仍可在 IndexedDB fallback 中刷新恢复；在 manage 页保存首页 hero/Statement 设置后刷新 `index.html`，对应图片和文字显示更新内容。

## 7. Upload Studio 个人上传平台

### 功能说明

- Phase 2A-2G 个人图片上传页面，完成“Folder -> 三类 signed asset -> 服务端 Draft -> trusted scan -> 自动/手工保存 -> authoritative readiness -> idempotent Submit / versioned Trash -> owner-scoped Trash/Restore”的代码与数据库边界；常驻 scanner runtime 仍需单独 provision。
- canonical 页面入口为受保护 `/workspace/images`；未登录跳 Sign In，Admin/Super Admin AAL1 跳 MFA，recovery session 禁止进入。
- Folder 是 owner-scoped 私有整理维度，不自动成为公开 Series 或标签；每个账户有不可重命名/删除的 system Inbox，当前仅支持单层 Folder。
- Draft 允许标题等字段不完整；用户不可编辑 owner、workflow/publication 状态、asset key、version lock 等系统字段。

### 相关文件

- `upload-studio.html`：三栏工作台；支持 Folder、导入队列、完整 Draft metadata、Save/Reload/Trash、五项 readiness、Submit for Review，以及只读 Trash/Restore；没有 hard delete、Review decision、assignment 或 Publish 控件。
- `upload-studio.js`：从 `/api/folders` 与 `/api/images` hydrate；三类 signed upload 后 complete；900ms autosave 与手工 Save 共用串行队列；readiness pending 时定时轮询，dirty/save/conflict/offline/submit 状态禁用不安全操作；确认后发送 current version + UUID key，成功从 Draft list 移除；API 不可用时只读 IndexedDB cache。
- `archive-upload.js`：共享浏览器图片处理管线；负责尺寸、EXIF、checksum 和派生图，本阶段只把 original/display/thumbnail 送入服务端上传协议。
- `server.py`：提供 Folder CRUD/restore、upload intent/complete、Draft list/update/trash/restore、`GET /api/images/{id}/readiness` 与 `POST /api/images/{id}/submit`；Draft update/trash/submit 使用 `expected_version`，Submit 还要求 UUID idempotency key 和 confirmation；服务端清洗 readiness/error/result，不返回 provider debug、asset key 或 token。
- `database/migrations/20260715_workspace_drafts_folders.sql`：实现 server-authoritative PostgreSQL/RLS/RPC 与 private bucket 配置；bucket 分别限制为 50/20/10 MiB，只允许 JPEG/PNG/WebP。
- `database/migrations/20260716_workspace_draft_versioning.sql`：增加 Draft `lock_version`、versioned update/trash RPC、旧 RPC execute 撤销、Folder delete version bump 和 stale-write conflict code。
- `database/migrations/20260716_workspace_folder_integrity.sql`：为 image/upload intent Folder assignment 增加 owner-scoped 串行化守卫，和 Folder soft delete 使用同一事务锁。
- `database/migrations/20260716_workspace_submit_readiness.sql`：服务端五项 readiness、expected-version/UUID-idempotent Submit、immutable version/review/readiness/asset snapshots、notification/audit 原子写入、direct submission mutation revoke 和 registered Storage object retention。
- `database/migrations/20260717_workspace_asset_scanner.sql` 与 `workers/`：服务端不可见 job/event、租约 RPC、private object 内容校验、ClamAV/Pillow verdict 与 scanner-only secret 边界；Web server/browser 无 service-role 凭据。
- `styles.css`：新增 `.upload-studio-*` 三栏工作台、文件夹列表、drop zone、上传卡片、编辑器、readiness、Submit/确认状态和移动端单列降级样式。
- `works.html`：公开作品只读取 published；页面不显示 Upload 或 public rail，登录用户通过账户菜单中的 Workspace destination 进入独立的受保护 Workspace，不把 Draft 暴露到公开作品流。
- `manage.html`：仍是 legacy SQLite Review/Publish 原型；Phase 2E 创建的 Supabase `review_submissions` 由独立 `/admin/reviews` 消费，该页面不与新 Review Queue 混用。

### 页面内部结构

- Folders：服务端默认 Inbox；作者可创建/重命名/软删除普通文件夹；删除非空 Folder 前由 UI 确认并把活动 Draft 移到 Inbox。
- Upload queue：每张图片显示缩略图、Type/Ratio、原图到 display 图的体积变化、上传阶段和进度；点击图片后右侧表单切换到该记录。
- Editor：Work details 编辑 Title、Folder、Captured、Location、Content Category、Caption、Description、Tags；Accessibility/Rights 分组编辑 Alt Text、Copyright Holder/Year、Recognizable People、Model/Property Release、Rights Declaration、AI/Sensitive Disclosure；Model Release 只在 Recognizable People=Yes 时显示。所有字段在 Draft 阶段可不完整；编辑后 900ms 自动保存且保留 Save Draft，二者均不改变 workflow/publication state；Delete 实际调用 versioned soft-delete Trash。
- Readiness/Submit：服务端返回固定顺序的 Work details、Rights & disclosures、Image assets、Security scan、Submission state；`blocked` 展示可修复字段，`pending` 每 5 秒轮询，只有 `ready` 才启用 Submit。提交前 flush 最新 Draft、再次读取 readiness 并确认；成功后该 image workflow 为 submitted、版本锁定并从 Draft list 移除。
- Import：选择或拖入 JPEG/PNG/WebP 后执行读取、压缩/缩略图、checksum、三类 signed upload 和 complete RPC；只有 complete transaction 成功才创建 `images` / `image_versions` / `image_assets`。
- 状态：Folder/Draft 权威数据在 Supabase PostgreSQL，asset 在 private Storage；编辑器呈现 Saving/Saved/Error/Conflict 和 readiness checking/pending/blocked/ready/submitting；409 不覆盖本地输入；IndexedDB 只保存最近成功 hydrate 的只读 cache，离线和 submission in-flight 禁用 mutation。
- 安全：authenticated 通用业务表写权限为 0，direct submission INSERT/UPDATE/DELETE 已撤销；RPC 重新校验 owner、account/AAL、metadata、三类 private assets、Storage object、clean scan、workflow 与 expected version。Submit 事务锁住 image/version/assets/objects，保存 snapshots，更新 workflow/version，并创建 notification/audit；已登记 asset 的 Storage object 不允许 owner 直接删除。
- 测试：Web validator/fake provider 覆盖 Draft/CAS、readiness 三态、Submit、Trash list/Restore/Inbox fallback 和 submitted lock；浏览器覆盖 1440/390 只读 Trash、Restore、溢出、头部遮挡与 page error；scanner validator/loopback provider 覆盖 secret header、leased claim、clean/failed/flagged/retry 与日志脱敏。真实 upload 仍从 `pending` 开始，只有独立 worker 明确完成三个 clean 才启用 Submit；本切片没有 user quota/capacity policy。

## 8. 联系作者

### 功能说明

- 首页联系段和所有公开导航提供 Contact；Work Viewer、Series 和 Lightbox 提供带上下文 inquiry。
- `contact.html` 是独立联系页，首屏直接显示说明、黑白作品图视觉锚点和表单。
- 表单字段：Name、Email、Inquiry Type、Project / Intended Use、Message 必填；Organization、Timeline 可选；Commission/Licensing 条件显示 Budget Range。
- 提交后调用浏览器 `mailto:` 打开给作者邮箱的邮件草稿；成功或失败用 toast 提示，页面不刷新。
- 站点不保存访客联系内容，不提供本地消息中心、回复后台或 `/api/messages`。

### 相关文件

- `index.html`：首页 hero 和联系段的 `Contact Artist` 链接入口。
- `works.html`：档案页导航的 `Contact` 链接入口。
- `contact.html`：结构化表单和 Selected Works 上下文容器。
- `contact.js`：必填校验、条件字段、Work/Series/Lightbox 公开数据摘要、逐项移除、结构化 `mailto:`、loading 和 toast。
- `public-archive.js` / `series-data.js`：Contact 上下文所需的 published works 与 Series 定义。
- `server.py`：静态服务器；拒绝 `/api/` 和 `/data/` 等私有路径。
- `styles.css`：联系页、表单、字段状态、提交 loading spinner、toast 和响应式规则。
- `docs/architecture/database-design.md`：记录联系作者不入库的当前边界，数据库设计仅保留作品档案相关结构。

### 页面内部结构

- 联系页：`contact.html` 左侧说明和黑白作品图，右侧 `.contact-page-form` 表单。
- 表单：`sender_name`、`sender_email`、`inquiry_type`、`organization`、`project_use`、`timeline`、`budget_range`、`message`；字段状态同步 `.is-focused`、`.is-filled`、`.has-error` 和 `aria-invalid`。
- Toast：`[data-contact-toast]` 使用 `role="status"` 和 `aria-live="polite"`，成功/失败共享同一个容器。
- 邮件草稿：包含访客信息、咨询类型、用途、时间、预算、Series 和公开 work ID/title，不把私人信息写入 URL query。
- API：无联系表单 API；`server.py` 对 `/api/` 返回 404 JSON。
- 安全边界：站点不保存访客联系内容；`/data/` 路径不提供静态访问。
- 测试：启动 `python3 server.py --port 8131` 后测试 Contact 表单校验、邮件草稿跳转和 toast。

## 9. Legacy 作品档案与生产数据库边界

### 功能说明

- Phase 2A-2G 已把用户 Folder、Draft、Version、三类 Asset metadata、private Storage、可信扫描、自动保存、乐观并发、readiness、Submit transaction 与 Trash/Restore 接入 Workspace，并提供真实 Dashboard 聚合和受保护 creator profile/editor；Phase 3 Review Queue/Detail/decision 已部署 development 且数据库、并发和真实多身份浏览器验收通过。公开 derivative delivery、Works 数据迁移与 public creator portfolio 仍未接入同一生产链路。
- 当前 `works.html` 优先读取 `server.py` 的本地 SQLite API；当 `data/archive.db` 不存在、API 失败或无 published 数据时，继续使用本地样例图和浏览器 IndexedDB fallback；不需要安装 MySQL，也不需要现在执行 PostgreSQL 目标 schema。
- 当前 `manage.html` 保存 legacy seed/upload 作品 metadata 时仍同步写入 `data/archive.db`；这些 Admin+AAL2 Archive API 仅为旧 Review/public prototype 服务。`upload-studio.html` 已不调用 legacy multipart/PATCH/DELETE API，也不写本地 `assets/uploads/`。
- 本地开发可执行 `python3 scripts/seed_local_archive_db.py` 生成 `data/archive.db`，用于验证图片 metadata、资产表、标签分组、图-标签关联和 collection 设计。
- Phase 3 双会话 race、secret-free fake-provider 和 2026-07-22 真实 disposable Reviewer/Admin 多身份浏览器验收均已通过。后续先实现 published-only DTO 与 derivative public delivery；只有公开 `works.html` 迁移到该数据源后，才向浏览器开放 Admin Approve and Publish。受保护 creator profile/editor 已完成，但 public creator portfolio/delivery 仍需独立、只读、published-only 的交付边界；随后再迁移 sample metadata、首页精选和需要保留的标签/切片能力。
- 图片二进制文件不直接进入关系表；数据库只保存对象存储 bucket/path/url、尺寸、MIME、checksum 和分类元数据。
- 首页精选作品和未来专题作品通过 `collections` 与 `collection_images` 表管理，不再依赖硬编码图片列表。

### 相关文件

- `docs/architecture/database-design.md`：说明后期数据库目标、表职责、上传入库流程、当前前端字段迁移关系、Archive 查询 SQL 和 Supabase 权限建议。
- `database/schema.sql`：预留 `ratio_categories`、`artists`、`images`、`image_assets`、`image_square_slices`、`image_analysis_events`、带 `group_name` 的 `image_tags`、`collections` 等表；包含索引、更新时间 trigger、比例匹配函数和优先 display/fallback original 的 `archive_image_view`，该视图同时输出鉴赏层需要的 `tags` / `tag_groups`。
- `database/local_archive_schema.sql`：SQLite 本地验证 schema；用 `TEXT` 主键和 SQLite 约束/索引/View 表达同一套核心关系，包含 `archive_image_view` 输出 `image_url`、`thumbnail_url`、`tags` 和 `tag_groups`。
- `scripts/seed_local_archive_db.py`：从 `archive-data.js` 读取本地样例，生成 `data/archive.db`；写入 27 条 `images`、81 条 `image_assets`、48 个派生 `image_tags`、278 条 `image_taggings`、`archive-featured` collection 和 27 条 seed analysis 记录。
- `scripts/validate_local_archive_db.py`：本地/CI 共用验收命令；默认创建临时 SQLite 库，调用 seed 脚本后验证 integrity、foreign key、核心表/视图、published 数量、三类资产、URL fallback、标签 JSON、比例 code 覆盖和资源路径存在性。
- `.github/workflows/database.yml`：数据库验收 workflow；安装 Python 3.11 和 Node 20 后执行 `python3 scripts/validate_local_archive_db.py`，覆盖 PR、`main`/`master` push 和手动触发。
- `data/archive.db`：脚本生成的本地 SQLite 作品库；被 `.gitignore` 忽略，不作为源码提交。
- `server.py`：`GET /api/archive/images` 和 Admin+AAL2 legacy mutations 继续服务 SQLite Review/public prototype；Folder、signed upload 与 Draft/Trash 使用独立 `/api/folders`、`/api/uploads/*`、`/api/images*` Supabase 边界。
- `archive.js`：公开 Works 的只读连接层；把 API 行归一化成现有 gallery/viewer item 形状，保留本地 sample/IndexedDB fallback；项目完工后如接生产 API，再把 `saveStoredItem()`、`getStoredItems()` 和上传资产写入迁移到后端。
- `works.html`：新增 `data-archive-data-status` 状态文本，展示数据库加载、只读 API 成功或 fallback 提示。

### 数据流

- 本地 seed：`archive-data.js.sampleItems` -> `scripts/seed_local_archive_db.py` -> `database/local_archive_schema.sql` -> `data/archive.db`；标签按 Subject、Place、Form / Ratio、Mood、Material / Surface、Palette / Tone、Series / Collection 七组确定性派生。
- 本地验收：`python3 scripts/validate_local_archive_db.py` -> 临时 SQLite 库 -> seed -> integrity/foreign key/schema/view/count/assets/tag JSON/ratio/path 检查；CI 通过 `.github/workflows/database.yml` 跑同一命令。
- 本地只读连接：浏览器打开 `works.html` -> `archive.js` 请求 `/api/archive/images` -> `server.py` 查询 `data/archive.db.archive_image_view` 的 published 且有 `image_url` 的记录 -> 前端映射为现有 gallery/viewer item；接口失败时显示 fallback 状态并继续使用本地 sample/IndexedDB。
- 本地 metadata 写入连接：作者在 `manage.html` 编辑已有 seed 作品 -> `manage.js` 调用 `PATCH /api/archive/images/{id}` -> `server.py` 事务更新 `images` 并替换 `image_taggings` -> `works.html` 下次读取 API 时显示新的标题、说明、visibility、sort order 和 tag groups；同一保存仍写 IndexedDB 作为浏览器 fallback。
- Phase 2A 上传：作者进入 `/workspace/images` -> `archive-upload.js` 生成 original/display/thumbnail -> 服务端创建 owner-scoped intent 与三条 signed URL -> 浏览器直传 private Storage -> complete RPC 核对 object metadata 并事务写入 Supabase `images` / `image_versions` / `image_assets` -> `/api/images` 以短期 signed read URL hydrate Draft；IndexedDB 仅缓存成功响应。
- Phase 2D 保存：字段输入停顿 900ms -> 客户端串行 PATCH 并发送当前 `lock_version` 作为 `expected_version` -> versioned RPC 行锁核对并递增 `images.version` -> 服务端直接返回不含 assets 的规范 Draft metadata；若服务器版本已变化则返回 409，保留本地表单并等待用户 Reload。Trash 使用同一 CAS；dirty Draft 会先保存再以最新 version Trash；Folder 删除、Draft 移动和上传 Folder assignment 使用同一 owner transaction lock，删除 Folder 导致 Draft 移入 Inbox 时也递增 version。
- Phase 2G 恢复：用户切换 Trash -> 客户端 GET `workflow_status=trashed` -> owner-scoped RPC 只返回 soft-deleted editable Draft + `deleted_at` -> Restore 通过 CSRF-protected POST 清除 deletion marker、递增 version；原 Folder 无效则事务内回退 Inbox -> 客户端从 Trash 移除并加入 Drafts。
- Phase 2E 提交：客户端 GET 五项 readiness -> pending 时轮询、blocked 时显示安全 field guidance -> ready 后确认并 POST current `expected_version` + UUID key -> RPC 在同一事务锁定当前 image version、保存 review/readiness/asset snapshots、workflow 变 submitted、version +1、写 notification/audit -> 客户端移除 Draft。同 key retry 返回原 submission；submitted 后 Draft update/Trash 被锁定。
- Phase 2F 扫描：asset INSERT 自动 enqueue restricted job -> 独立 worker 通过 service_role-granted RPC + SKIP LOCKED 领取租约 -> private Storage 拒绝 redirect 后流式下载并核对 size/checksum/magic -> 无凭据 ClamAV verdict -> 非恶意文件由隔离 Pillow allowlist 完整解码并核对 EXIF-oriented dimensions -> token-bound complete/retry 更新 job/event/audit 与 `image_assets.scan_status`；依赖不可用、旧 token、不满足当前 policy 或不确定结果都不能 clean。service-role credential 本身仍是广泛高权限，不因 Worker 只调用三条 RPC 而变成 capability-limited key。
- Phase 3 审核：Reviewer/Admin 打开 `/admin/reviews` -> server 以用户 access token 调用 scoped list RPC -> Reviewer 点击不属于自己的公共 Submitted 时先原子 Start/Claim -> detail RPC 只向自己的 open non-self assignment 返回 submitted snapshot 和三类 current-clean private asset -> 决定发送 current lock version + UUID key + checklist/reason/message -> RPC 行锁、CAS、same-payload replay、notification 与 append-only audit 在同一事务完成；所有角色禁止 self-review，Admin/Super Admin 的完整 history 与 publish boundary 始终要求 AAL2。
- 后续处理：derivative worker、EXIF/public metadata 策略、AI 分析、square slice、user quota/rate limit、orphan cleanup 与 TUS 尚未完成；真实 asset 初始 `pending`，不会被 readiness 当成 capacity 或 clean。
- 后续展示：把 approved display/thumbnail 发布到 public delivery，再让公开 Works 只读取 `publication_status = published` 的稳定 DTO；完成前 Review 浏览器只提供 Approve，不承诺公开，原图始终保持 private。
- 后期精选：首页 Selected Works 读取 `collections.slug = 'homepage-selected'` 对应的 `collection_images` 排序结果。

## 10. 用户认证与账户设置

### 功能说明

- 为注册用户提供真实 Supabase Auth 身份、服务端 HttpOnly session、受保护 Workspace 和账户资料/会话管理，不使用浏览器存储模拟认证。
- 入口：`/auth/sign-in`、`/auth/register`、`/auth/forgot-password`、`/auth/reset-password`、`/auth/verify-email`、`/auth/mfa`、`/dashboard`、`/settings/account`。
- 主要用户操作：注册与邮箱验证、登录/退出、找回与重置密码、Admin TOTP、查看受保护个人资料、编辑 creator Profile/Authorship Preferences、查看当前 Session、退出当前/其他/全部设备。

### 相关文件

- `auth.html` / `auth.js`：统一 Auth shell、各认证模式字段和 callback 处理；mutation 使用 same-origin CSRF，敏感 token 仅在函数内存短暂存在并立即清理 URL。
- `mfa.html` / `mfa.js`：Admin TOTP enrollment/challenge/verify 和失败恢复；Admin AAL1 不能进入受保护管理范围。
- `account-settings.html` / `account-settings.js`：无重复全局 rail 的 Account Settings 页面；紧凑标题栏、sticky Profile/Preferences/Security/Sessions 本地导航和连续白色内容面板；五组十字段 creator Profile、Preferences 表单、Security 摘要、current-only Session 列表、确认弹窗、滚动章节同步、dirty/save/error 状态、field error 和 bulk revoke。
- `server.py`：Supabase Auth/PostgREST 代理、access/refresh rotation、CSRF/Origin、recovery grant、strict Profile/cover allowlist、Account/Workspace route guard、Admin role+AAL2 和 Session scope revoke。
- `database/supabase_phase1_auth_rls.sql`：fresh database Auth/RLS/Profile RPC baseline。
- `database/migrations/20260713_admin_mfa_hardening.sql`：已有环境的 inactive privileged user 加固。
- `database/migrations/20260714_account_profile_boundary.sql`：已有环境的 strict owner-only Profile RPC 增量加固。
- `database/migrations/20260722_z_creator_profile.sql`：扩展 creator profile 字段、availability enum 与 owner-scoped cover selector RPC；封面只能来自当前用户 current ready image 的 scanner-clean display/thumbnail asset。
- `scripts/test_auth_security_boundary.py` / `scripts/test_user_dashboard_boundary.py`：loopback fake provider 的 Account 与 creator profile/cover 集成回归，不使用真实凭据或远程账号。
- `scripts/test_supabase_deploy_script.py`：fresh/incremental 部署顺序回归。

### 页面内部结构

- Creator Profile：十个字段分成 Identity（`display_name`、`professional_headline`）、Work（`company`、`availability_status`）、Location（`country_code`、`city`）、About（`bio`）、Links（HTTPS `website_url`、官方 host 的 `instagram_url`、`linkedin_url`）；client、server 和 SQL RPC 使用一致边界，未知字段拒绝。
- Preferences：`preferred_locale`、IANA `timezone`、`copyright_name`、`default_license_preference`；仅写入当前用户的 `user_profiles` 行。
- Security：只读显示 verified email、服务端角色、account status 和当前 AAL；Admin AAL1 跳转 MFA。
- Sessions：Supabase 当前能力只描述当前 session；明确返回 `scope=current_only` 和 capability flags，不伪造全部远程设备；支持 `others` 与 `all` bulk revoke，危险操作经过确认弹窗。
- 页面布局：桌面使用约 236px sticky 本地导航与连续表单面板，Profile fieldset 仅由中性细线分组；760px 以下切换为顶栏下方横向滚动章节页签和单列表单。Identity 的 initials 头像只读展示，不提供未受后端支持的上传入口。
- 状态：页面覆盖 loading、retryable error、field error、dirty、saving、saved、disabled、permission/MFA、recovery restricted 和 signed-out redirect。
- API：`GET/PATCH /api/me/profile`、`GET/PATCH /api/me/profile/cover`、`GET /api/me/sessions`、`DELETE /api/me/sessions/{others|all}`；所有 mutation 要求 JSON、same-origin、CSRF Cookie/header 双提交。Cover response 只返回固定 asset DTO 与短期 signed URL，不返回 bucket/key/owner/scan internals。
- 部署：fresh database 运行完整 baseline；已有数据库设置 `MT_APPLY_PHASE1_BASELINE=no`，只按文件名顺序执行 transaction-wrapped 增量 migrations。
- 测试：CI 静态验证 Auth/RLS/Profile SQL 契约和受保护浏览器脚本语法，并运行 recovery、普通用户 Profile、Admin AAL1、Session revoke、Cookie 清理和部署顺序集成回归。

## 10A. Supabase User Dashboard

### 功能说明

- canonical 入口为受保护 `/dashboard`，旧 `/workspace` 规范化到此页；未登录保留 `next=/dashboard`，recovery session 禁止进入，Admin/Super Admin AAL1 进入 MFA。
- Home、其他公开页与所有内部登录态头像都进入 `/dashboard`；资料页使用明确的 Edit profile 链接进入 `/settings/account#profile`，避免把头像本身变成编辑命令。
- 页面优先回答当前用户需要处理什么：Changes Requested 优先于 processing failure，Recent Images 与 Review Activity 使用服务端排序，浏览器不读取全量 Draft 后自行计算。
- Profile identity 来自 `/api/me/profile`；工作统计来自 authenticated-only `/api/dashboard`。两者都失败关闭，页面提供 retry；账号被限制时显示无重试 permission 状态。
- Profile cover 来自 `GET/PATCH /api/me/profile/cover`：候选按 current image 去重，优先 display、缺失时回退 thumbnail，并只接受当前 owner、non-deleted、ready、current-policy scanner-clean private asset；响应不包含 bucket/key/owner/scan internals。Storage quota 与 public creator delivery 未接通时只返回 unavailable capability。
- 页面复用全局公开顶部导航；200px 横向摄影 cover 是第一视觉信号，112px avatar 与封面底边重叠。桌面主体为 300px 身份/资料侧列和弹性作品/状态主列，资料完整度、职业、可用性、地点、网站和社交链接使用白底细线列表，不使用彩色仪表盘块。

### 相关文件

- `dashboard.html` / `dashboard.js` / `styles.css`：无左侧 rail 的全宽摄影 cover、重叠 avatar、identity/actions、安静资料列表、Overview/My works tabs、状态聚合和桌面/平板/移动响应式个人资料页。
- `public-navigation.js`：Dashboard 与公开页共享的移动全局导航控制器；不处理资料或账户数据。
- `account-menu.js`：公开及内部页面共享 identity/destination/sign-out menu；Review 按 Reviewer/Admin/Super Admin role 显示。
- `server.py`：`/dashboard`、`/api/dashboard` 与 `/api/me/profile/cover` guard，严格 aggregate/cover allowlist、owner-prefixed private asset signing 和 no-store protected assets。
- `database/migrations/20260722_user_dashboard.sql`：owner-scoped aggregate read model；helper 仅 `postgres` owner 可执行，公开 Dashboard RPC 仅 `postgres + authenticated`，不授予 anon/public/service_role 执行权限。
- `database/migrations/20260722_z_creator_profile.sql`：strict creator fields 与 cover read/write boundary；两个 helper 仅 `postgres` owner，三条 exposed profile RPC 仅 `postgres + authenticated`。
- `scripts/validate_user_dashboard.py` / `scripts/test_user_dashboard_boundary.py`：部署/CI 静态门禁和 fake-provider HTTP 边界回归。
- `scripts/test_user_dashboard_database.py`：development 部署后的 rollback-only 真实 PostgreSQL 门禁；十二个成功 marker 验证八个函数的安全元数据/精确 ACL、资料字段、cover owner/current-clean/bucket-kind 边界、身份矩阵、Trash 状态过滤、事务回滚与独立 fixture absence。

### 页面内部结构

- Identity：当前合格作品封面或稳定 fallback、avatar/initials fallback、Display Name/headline/company/location/availability/bio/links/account context，以及 Edit profile 和 Upload work。名称使用编辑式衬线，状态强调只使用深森林绿或必要的 danger 色。
- Cover chooser：dialog 读取最多 24 个按 image 去重的候选，支持选择、移除、loading/empty/error/success、Escape/Cancel 和 trigger focus restoration；PATCH 要求 CSRF，非法或过期候选失败关闭。
- Overview：五项 Status、最多八条 priority attention、最多八张 recent images、最多十条 review activity 与真实 used bytes/file/image 数；空数组分别给一个明确下一步。
- My works：最多十二个 Draft/Changes Requested，固定缩略图尺寸并链接 Workspace；public creator portfolio 未接通时显示能力说明而非虚假公开网格。
- Account menu：ArrowUp/ArrowDown/Home/End 循环，Escape 关闭并恢复 trigger 焦点，点击外部或焦点离开关闭；Sign out 使用 same-origin CSRF 并在失败时聚焦错误。
- 安全与真实性：聚合在 PostgreSQL 完成；浏览器不使用 local/session storage，不看到 storage coordinates，不把 original 当列表预览，不伪造 quota/public delivery。
- 响应式：`<=1179px` 资料侧列收窄、Draft 改两列；`<=760px` cover 降到 152px、avatar 降到 84px，主体改普通单列、状态两列、Draft 单列；`<520px` 主操作改单列。验收视口为 1440x900、1024x768、390x844，必须检查固定顶栏、封面/头像构图、菜单展开、焦点、遮挡和水平溢出。

## 11. Supabase Admin Review Queue

### 功能说明

- 为已提交的 immutable submission snapshot 提供独立的企业级摄影审核工作台，不复用 legacy `manage.html` 或 SQLite visibility。
- canonical 入口为 `/admin/reviews`，deep link 为 `/admin/reviews/{submissionId}`；未登录进入 Sign In，recovery/普通 User 拒绝，Admin/Super Admin AAL1 进入 MFA。
- 纯 Reviewer 只看到未分配的 Submitted queue 与自己的 open assignment；未领取项只使用 thumbnail，打开时必须先原子 Start/Claim，再读取 Original/Display。Admin/Super Admin 达到 AAL2 后可查看完整授权历史。
- 当前浏览器动作是 Request Changes、Reject、Approve；数据库/API 保留 Admin+AAL2-only publish boundary，但公开 Works 仍读 SQLite，因此不在 UI 中显示或宣称真实 Publish。

### 相关文件

- `admin-reviews.html` / `admin-reviews.js`：Queue + Detail、status/assignment filters、deep link、移动 Back to queue、latest-wins fetch、Reviewer claim、Actual size、evidence/history、checklist alert/description、decision confirmation、busy/conflict/retry 与可访问性状态。
- `styles.css`：`.admin-review-*` gallery-white 高密度布局；桌面自然高度/sticky media、12px evidence 与 13px body、1024px 上下折叠、760px Queue/Detail 单视图和 390px 无横向溢出规则。
- `server.py`：保护页面与 Review API，执行 identity/active account/role/AAL/CSRF/JSON/version/idempotency 边界，把 PostgREST/provider 响应投影为不泄露 bucket/key/internal note 的稳定 DTO，并为允许的 asset 生成短时签名 URL。
- `database/migrations/20260717_review_queue.sql`：scoped list/detail、assignment/start/decision RPC，Reviewer/Admin+AAL2 RLS、private Storage 生命周期与 bucket-kind 绑定、CAS、immutable result replay、notification、publication boundary 和 immutable audit。
- `scripts/validate_review_queue_phase3.py` / `scripts/test_review_queue_boundary.py`：静态 SQL/UI/API/CI contract 与 secret-free fake-provider HTTP integration。
- `scripts/test_review_queue_database.sql`：rollback-only development 数据库角色/AAL/RLS/Storage/CAS/幂等/通知/审计验收。
- `scripts/test_review_queue_concurrency.py`：development-only 双会话真实并发验收；用 process-level advisory run lock 和 shared start gate 同步独立 PostgreSQL backend，覆盖 Start/claim 竞争、不同 key decision CAS 竞争、same-key replay 单副作用，并在前置与 `finally` 清理 committed fixture。
- `scripts/test_review_queue_browser.py`：development-only 真实多身份浏览器验收；以 disposable Reviewer A/B 与 Admin AAL2 走 claim、cross-assignment denial、Request Changes、Approve 和三类 private asset 检查，最终关闭 sessions 并清理 fixture。
- `docs/operations/review-testing.md`：本地、真实 development database、双会话并发、RLS/Storage 和已通过的多身份浏览器验收手册。

### 页面内部结构

- Queue header：紧凑标题、可点击 counts、Status 与 Assignment filter、Refresh，不使用 Dashboard 卡片墙。
- Queue list：thumbnail、title、Submission ID 尾段、owner、waiting time、category、rights、assignment 与 status；accessible name 同时包含可区分任务的 title/status/owner/waiting/ID 尾段，分页与选中项同步 URL。
- Review Detail：submitted image 为视觉主角，Inspector 依次显示 copy、rights、asset evidence、readiness、history 与 decision；图片只用签名 URL，Actual size 不裁切原作。
- Mutation：Start 与 decision 在请求中禁用相关控件；409/assignment conflict 保留本地输入并提供 Reload；checklist 首错项的 invalid/description/focus、dialog 首焦点、Escape、关闭后焦点恢复和 alert 宣告都有明确合同。
- 安全：角色叠加不能让 Admin+AAL1 借 Reviewer policy 绕过 MFA；Reviewer 完成/失去 assignment 后 private detail/asset 权限立即失效；same-key/same-payload 返回首次完整结果，不同 payload 冲突。
- 验收状态：migration 已部署 development，rollback-only User/Reviewer/stacked Admin AAL1/Admin AAL2 的 RLS/Storage/CAS/幂等/通知/审计验收通过；六个独立 `psql` 会话完成三组双会话 Start/decision race，每组 backend PID 不同且 fixture 已清理；真实多身份浏览器的 Reviewer A claim、Reviewer B 越权拒绝、Request Changes、Admin AAL2 Approve、private 三变体、responsive/focus/console、session close 与 fixture cleanup 全部通过。当前真实未完成的是 public DTO、derivative delivery、Works migration 与 public creator portfolio/delivery；Escalate/Quarantine/Withdraw、bulk/risk filters 属于后续运营切片。

## 12. 本地企业级开发护栏 Skill

### 功能说明

- 定义本项目使用的企业级开发原则，约束 Codex 在规划、开发、重构、测试和验收时先读代码、明确边界、复用现有体系、拆垂直切片并完成验证。
- 入口：`project-development-guardrails/SKILL.md`
- 主要用途：在后续项目开发时强制维护 `README.md`、`docs/architecture/project-map.md`、`docs/design/design-system.md` 文档闭环；修改记录统一写入 Project Map。

### 相关文件

- `project-development-guardrails/SKILL.md`：本地 skill 主文档；包含硬性护栏、工作流、企业级项目文档契约、功能地图规则、验收标准、验证清单和输出格式。
- `README.md`：由 skill 要求维护项目版本、运行方式、功能清单和项目文件说明。
- `docs/architecture/project-map.md`：由 skill 要求维护项目功能地图和唯一修改记录。
- `docs/design/design-system.md`：由 skill 要求维护布局设计、组件规则、视觉系统、响应式和动效约束。

### 文档内部结构

- 企业级项目文档契约：规定 `README.md`、Project Map、Design System 的用途、更新时机和推荐提示词。
- 开发工作流：从任务大小判断、上下文建立、约束确认、垂直切片、验收标准到实现、验证和自审。
- 验证：要求检查 lint/typecheck/test/build 或项目等价验证，并检查三份核心文档是否与真实代码一致。

## 修改记录

- 2026-07-22：统一 Home、Works、About、Lightbox、Contact 与 protected creator profile 的固定顶部导航，移除公开 rail DOM 和布局占位；新增 `public-navigation.js` 的移动菜单/ARIA/焦点职责，并让 `account-menu.js` 在公开页切换 Sign In 与登录身份。Works 改为 Search、文本 Type/Ratio tabs、标题/Count/数据状态和全宽四/三/二/一列 masonry；Dashboard 改为横向 cover、重叠 avatar、安静资料列表和作品/账户主列，保留原有 Viewer、Lightbox、筛选、账户、封面和服务端状态逻辑。1440x900、1024x768、390x844 浏览器验收均无 rail 占位、重复导航或横向溢出。
- 2026-07-22：把 `/settings/account` 从展示型浅绿 Hero 与粉彩分组改为紧凑设置工作区；移除重复桌面全局 rail，保留共享账户顶栏，新增滚动同步本地导航、连续白色表单面板、只读 initials 头像摘要和明确保存状态，并覆盖 1440、1024、390 响应式验收。
- 2026-07-22：首页移除左侧 public rail，改为完整宽度摄影首屏和顶部导航；同时取消 `150vh/140vh` sticky hero，收敛为桌面上限 `92svh`、移动端 `82svh` 的普通流主视觉，让各视口首屏都露出 Selected Works；缩短作品带高度，Statement 改为桌面双列/移动单列，并让 IntersectionObserver 仅作渐进增强，脚本未运行或尚未触发时内容仍可读。登录态首页入口更新为 Dashboard；1440x900 与 390x844 浏览器截图无横向溢出或空白段。
- 2026-07-22：把 protected User Dashboard 扩展为无左侧 rail 的 full-width personal profile：Home 与内部 workspace 的登录态头像统一进入 `/dashboard`，资料页用 Edit personal information 进入 `/settings/account#profile`；首屏提供 owner-scoped current-clean cover chooser、完整 creator identity 和 Overview/My works。Account editor 新增五组十字段资料合同；`20260722_z_creator_profile.sql`、strict server DTO/signing、CSRF cover mutation、静态/secret-free boundary 和 rollback-only 真库覆盖进入同一发布门禁。此切片只交付受保护个人资料，public creator portfolio/delivery 仍未完成。
- 2026-07-22：完成 Upload Studio Trash/Restore 垂直切片：新增 authenticated owner-scoped trashed Draft read RPC、Drafts/Trash 分段视图、只读删除记录、Restore 全状态和已删除 Folder 回退 Inbox；API fake-provider 回归与 1440/390 浏览器截图/溢出/遮挡/page-error 验收通过，页面不提供 hard delete；同日真实 PostgreSQL owner/state/ACL/回滚验收也已通过。
- 2026-07-22：收紧 Admin Review UI：移动端 Queue/Detail 改为互斥视图，Detail 顶部 Back to queue 保留 deep-link/active selection 并恢复焦点；queue button accessible name 加入 title/status/owner/waiting/UUID 尾段且唯一；Evidence/History/Checklist 提升到 12px、正文到 13px并扩大触控行；checklist 首错项通过 assertive alert 与 `aria-describedby` 关联；桌面 media 保持自然高度/sticky，并用不遮挡内容的 Review decision 跳转动作取代覆盖 checklist 的 floating footer。1440x1000 与 390x844 fake-provider 视觉探针无横向溢出；真实 disposable 多身份浏览器验收也已通过 Reviewer A claim、Reviewer B 越权拒绝、Request Changes、Admin AAL2 Approve、三类 private asset、responsive/focus/console、session close 与 fixture cleanup。
- 2026-07-20：补齐 development Scanner 安全配置与本机运行前置：新增 `configure_development_scanner.py` 及 secret-free 回归，拒绝 publishable/placeholder key 和 secret CLI 参数，以真实空文件扫描校验 ClamAV，并只在成功后原子写入 `0600` 的 `.env.worker`；CI、README 与上传运维手册同步。已创建 Python 3.11/Pillow 12.3.0 隔离 venv，ClamAV 1.5.3 与当日官方签名真实 preflight 通过；远程仍为 3 pending/3 queued/0 leased/0 clean，因服务端 secret 尚未 provision，Worker 未启动。
- 2026-07-20：完成 Phase 3 真实双会话数据库并发门禁：新增 development-only `scripts/test_review_queue_concurrency.py`，以 process-level run lock 与 shared advisory gate 同步六个独立 `psql` 会话，并确保每组竞争使用不同 backend PID；验证双 Reviewer Start/claim 一胜一冲突、不同 key decision 一胜一 CAS 冲突、same-key/same-payload 并发返回同一 immutable result 且 decision/notification/audit 各一，所有 committed fixture 已清理。当时尚未执行的真实 disposable Reviewer/Admin 浏览器验收已于 2026-07-22 通过；本机 Scanner venv/ClamAV 后续同日已就绪，服务端 secret 与 `.env.worker` 仍待 provision，常驻 Scanner 未启动。
- 2026-07-20：Phase 3 migration 已部署 development；修复 decision 虽声明 `expected_lock_version` / `result_snapshot` 却未写入导致重放读取 live state 的缺陷，将两列收紧为非空并在首次 decision insert 中保存完整 immutable result。新增 rollback-only 数据库验收，真实覆盖 role stacking/AAL、自审拒绝、direct RLS/current-scan Storage 生命周期、stale CAS、Approve 后 Admin Publish、跨后续状态稳定重放、冲突重放、notification 与精确 audit before/after，所有 fixture 已回滚；后续已完成双会话 race，并于 2026-07-22 完成真实多身份浏览器验收。
- 2026-07-20：完成 Phase 3 secret-free fake-provider 浏览器验收：1440x1000 Queue/Detail 与 390x844 移动 Detail/decision 均无横向溢出，签名图片正常；required message/checklist 聚焦、确认弹窗 Cancel 首焦点、Escape 关闭和 opener 焦点恢复通过，console/page error 为空。当时尚未执行的真实 disposable Reviewer/Admin 多身份验收已于 2026-07-22 通过。
- 2026-07-20：收紧本地发布门禁与静态文件保护：Supabase 部署入口在执行 migration 前新增 Phase 3 Review Queue contract validation；规范化 URL 后同时保护 `/assets/uploads` 根目录及其子路径，GET/HEAD 均不能退回公开目录列表，并由 Auth boundary integration 覆盖。
- 2026-07-20：完成 Phase 3 Supabase Admin Review Queue 本地垂直切片：新增 protected `/admin/reviews` 与 deep-link Queue/Detail 工作台、status/assignment filters、Reviewer 原子 Start/Claim、submitted snapshot/rights/asset/history inspector、Actual size 和 Request Changes/Reject/Approve；服务端对 User/recovery/Admin AAL1 fail closed，按纯 Reviewer 与 Admin+AAL2 严格投影 DTO/签名资产并执行 CSRF/CAS/idempotency；transaction-wrapped migration 收紧 role-stacking RLS/Storage、bucket-kind/lifecycle、direct ACL，提供 atomic assignment/start、stable same-payload replay、真实 before/after audit、notification 与 Admin-only future publish boundary。浏览器刻意不显示 Approve and Publish，因为 public Works 仍读取 SQLite。静态合同和 secret-free fake-provider 集成进入 CI；后续已完成 development 部署、rollback-only 数据库、双会话并发，以及 2026-07-22 真实多身份浏览器验收。
- 2026-07-20：完成 Account Settings 最终浏览器验收；390px 下用账户页专属单行顶栏覆盖全局双行移动导航，确保固定顶栏实际高度与吸附式 Profile/Preferences/Security/Sessions 目录的 68px 偏移一致，滚动后目录不再被顶栏遮挡；保存响应不再覆盖请求期间的新输入，成功注销可安全越过 dirty prompt，失败时恢复当前设备退出控件，CSRF 初始化失败可在当前页重试且 Session 错误可聚焦宣告，小字号辅助文字达到 WCAG AA；桌面与移动端均无横向溢出，表单 dirty 状态及 Session 确认弹窗焦点恢复通过。
- 2026-07-17：完成并向 development 部署 Phase 2F Trusted Asset Scanner 的代码与数据库状态机：restricted leased job、append-only event、SKIP LOCKED claim、token/idempotent complete、retry/backoff/attempt exhaustion、current-policy readiness 与 Storage metadata/observation 双重校验；独立 Python 3.11 Worker 拒绝 credential redirect，以无凭据 ClamAV/Pillow 子进程执行 SHA-256/magic/MIME/full decode/EXIF/multi-frame/decompression-bomb 检查，并约束 lease budget、私有临时目录与资源上限。loopback integration 与 rollback-only development DB test 均通过；后者真实覆盖 claim/complete/retry/expiry/exhaustion 后完整回滚。远程最终核对 scanner RLS 2/2、通用 table grant 0、service RPC 3/3、client RPC 0、constraints 2、trigger object 3、queued jobs/events 3/3、terminal job 0、invalid prerequisites 0，资产仍为 3 pending。Web server/browser/解析子进程不持有 scanner secret；development 尚未 provision 常驻 ClamAV Worker，所以自动消费未启动，也未伪造 clean。Admin Review Queue 仍是下一生产切片。
- 2026-07-16：完成 Phase 2E Submit Readiness / Submit for Review 垂直切片：数据库以固定五项检查权威计算 metadata、rights/disclosures、三类 asset/Storage、security scan 和 submission state；GET readiness 与 POST submit 使用 owner/session/CSRF 边界，Submit 要求 current `expected_version`、显式确认和 UUID idempotency key；事务创建 immutable image version/review/readiness/asset snapshots，将 workflow 锁到 submitted，并原子写入 notification 与 append-only audit；撤销 direct submission mutation，registered Storage object 不允许 owner 直删。Upload Studio 增加 readiness 状态、pending 轮询、确认 dialog、提交 in-flight 禁用和成功移除 Draft。真实 asset 仍从 `scan_status=pending` 开始，没有可信 scanner 时 Submit 保持 disabled；没有 user quota/capacity policy，legacy `manage.html` 尚未读取 Supabase submission，Admin Review Queue 是下一切片。同轮修复 legacy Review Homepage false-dirty：签名只比较可编辑字段，离站不再重新序列化 clean form。
- 2026-07-16：实现并在 development 部署 Phase 2D Draft Autosave / Optimistic Concurrency 垂直切片：Upload Studio 在字段停顿 900ms 后串行自动保存，同时保留手工 Save，并明确呈现 Saving/Saved/Error/Conflict；Draft DTO 暴露 `lock_version`，PATCH/Trash 发送 `expected_version`，stale mutation 返回 409 且保留本地表单，用户可用 Reload Server Draft 主动加载服务器版本；PATCH 提交后不再二次签名且 response 不含 assets；`20260716_workspace_draft_versioning.sql` 新增 versioned update/trash RPC、撤销旧 RPC authenticated execute，并在 Folder delete 移动 Draft 时递增 image version；`20260716_workspace_folder_integrity.sql` 串行化 Folder 删除与 image/upload-intent assignment。只读核对 versioned RPC authenticated=true、旧 RPC authenticated=false、anon=false、Folder guard trigger=2。该切片当时不含 Submit 或 Trash Restore UI；现已分别由 Phase 2E 与 Phase 2G 补齐，quota 与 production scanner operations 仍在后续。
- 2026-07-16：完成 Phase 2C Draft Compliance Metadata 垂直切片：Upload Studio editor 分为 Work details 与 Accessibility/Rights 两个无卡片分组，新增 Location、Alt Text、Copyright Holder/Year、Recognizable People、条件 Model Release、Property Release、Rights Declaration、AI 与 Sensitive Content Disclosure；`server.py` 扩展 owner-scoped Draft allowlist 和字段错误，upload-complete 仍限制为 core metadata；development 已部署 `20260716_workspace_draft_compliance.sql`，只读核对六个数据库约束完整、RPC 包含新字段、authenticated execute=true、anon execute=false；fake-provider 集成验证 metadata round-trip、非法年份/枚举/布尔值和系统字段拒绝。Submit validation 后续已由 Phase 2E 实现，Review Queue 仍为下一切片。
- 2026-07-16：Home、Works、About、Contact、Lightbox 全部主要公开页统一增加 78px 左侧导航，固定提供 Home/Works/Upload/Lightbox/About 与底部 Contact，并增加静态导航契约防止页面遗漏；移动端继续隐藏 rail、保留顶部导航。修复 `/workspace/images` 把临时 authorization provider 故障误报为 403 的问题：瞬时失败自动重试一次，持续上游失败返回 502，只有明确 inactive account 返回 403；fake-provider 安全集成新增瞬时故障恢复回归。
- 2026-07-16：统一 Works/Upload/Review/Account 的桌面 rail 为 78px；Works 恢复受保护 Upload 入口，内部 rail 收敛为 Works/Upload/Review/Account 顺序。Upload Studio 去掉渐变、浮动三卡和大阴影，空/Loading 状态只显示 Folder + 主导入区，选中 Draft 后渐进展开编辑器；新增 Loading skeleton，避免远程 Folder hydrate 前误显示 `0 folders`；1440x900、390x844 浏览器验收无横向溢出。
- 2026-07-16：完成 Phase 2B Upload Resilience 垂直切片：Upload Studio 改为稳定双并发任务队列，提供 queued/in-flight Cancel、失败 Retry 与失败/取消 Remove；`server.py` 新增 `DELETE /api/uploads/{id}`，通过 owner-scoped RPC 记录取消并调用 Supabase Storage API 清理三类潜在 partial object；development 已部署 `20260716_upload_retry_cancel.sql`，只读核对新增字段存在、两条 RPC 仅 authenticated 可执行且 anon 不可执行。扫描 worker、quota/rate limit、TUS 和 Submit/Review/Publish 保持未实现。
- 2026-07-15：完成 Phase 2A Upload Workspace 第一生产垂直切片：development 部署 `upload_intents`、三类 private Storage bucket、system Inbox、11 个 owner-scoped Workspace RPC；`server.py` 增加 signed upload/Folder/Draft/Trash API，Upload Studio 移除 localStorage 与 legacy Archive 写入，IndexedDB 降为离线只读 cache；静态合同、Auth/Workspace fake-provider 集成、部署顺序回归进入 CI。development 只读验收结果为 RLS=true、private bucket 3/3、authenticated generic writes=0、authenticated RPC=11、anon RPC=0、missing Inbox=0、Storage owner policies=3。

- 2026-07-15：完成 Account Settings 垂直切片闭环：`/settings/account` 提供 Profile、Authorship Preferences、Security 和 current-only Sessions；`server.py` 增加一致的 Profile URL/input boundary，普通用户 owner-only 读写、Admin AAL2 和 recovery route guard、others/all Session revoke；fresh Auth/RLS baseline 与 existing-environment migration 均安装 strict `update_my_profile` RPC；部署脚本支持 `MT_APPLY_PHASE1_BASELINE=no` 增量模式；Auth/RLS 契约、loopback fake-provider 集成和 fake-`psql` 部署顺序测试进入 CI；development 增量部署成功，RPC 存在性与 authenticated/anon/table UPDATE/policy 权限 5/5 只读核对通过。

- 2026-07-14：完成 Phase 1B 第一垂直切片：统一 Auth shell 新增 Forgot/Reset/Verify Email；服务端接入 Supabase recovery/verify/update-user/global-logout，使用短期 recovery grant、HttpOnly session、Origin + CSRF 防护与无 query access log；`/workspace/images` 成为受保护 canonical route，直达 Upload Studio 重定向，legacy Archive 非公开读取/mutation 收紧为 Admin+AAL2，上传目录不再可枚举且仅 Published 派生图公开；新增 secret-free 安全集成测试并更新配置/运维说明。

- 2026-07-13：整理项目文档：根目录仅保留 README/CHANGELOG；产品、设计、架构和运维文档移动到 `docs/`；新增 `docs/README.md`；删除已过期的页面功能设计和重复的上传数据库完成报告；修复全部文档路径。
- 2026-07-13：新增 `docs/product/user-upload-admin-spec.md` 作为唯一目标产品规格；取消目标 Series，定义用户系统、Upload Workspace、Drafts/Folders、Submit/Review、删除/下架、Admin Platform、数据模型、API、安全和验收。
- 2026-07-13：按当时页面方案完成公开站点职责第一阶段：Collections 改为 Series，新增 About、Lightbox；随后目标需求改为用户系统、上传工作台和管理员平台，现有页面代码等待后续切片按最新产品规格调整。

- 2026-06-06：新增首版静态站点、作品分类切换和临时作品图。
- 2026-06-06：新增现位于 `docs/design/design-system.md` 的设计系统文档。
- 2026-06-06：用 Pexels 临时摄影素材替换几何占位图；新增现位于 `docs/design/image-sources.md` 的来源记录和 `scripts/prepare_art_assets.py`。
- 2026-06-06：新增作品比例查看模式；作品图处理改为保留原始比例，避免破坏摄影构图。
- 2026-06-06：补充摄影可信度规则，排除纯纹理、AI 质感和无法解释拍摄对象的图片。
- 2026-06-06：按参考图方向重做首屏为英文全屏摄影 landing page，只保留 `Enter Works` 和 `Contact Artist` 两个主要入口。
- 2026-06-06：比例查看改为 `Auto` 默认模式，根据图片真实宽高自动匹配最佳展示比例。
- 2026-06-06：移除分类切换和比例筛选；作品区改为单排 Infinite Marquee Gallery，图片统一高度、自然宽度、无裁切、无黑边。
- 2026-06-06：用 `gpt-image-2-all` 生成首页主视觉和 6 张精选风景图，更新 `assets/art/metadata.json` 记录生成模型、日期和尺寸。
- 2026-06-14：重设 `styles.css` 全站配色为 neutral gallery palette；同步更新 Design System 色彩规则。
- 2026-06-06：新增首页到作品区的纵向滚动过渡；下滑时 hero 背景轻微缩放/降饱和，文案上移淡出，点击锚点使用自定义 easing。
- 2026-06-06：主页过渡改为 sticky 双层图片覆盖：黑白抽象风景作为底层，彩色具象横幅随下滑从下向上覆盖；降低白色遮罩强度；Selected Works 全部替换为竖向作品图。
- 2026-06-06：新增 `works.html` 智能作品档案页；支持上传图片后本地读取尺寸、按 `1:1`/`4:5`/`2:3`/`3:2`/`16:9`/`Panorama` 分类，按抽象/具体和比例过滤，并用横向图片墙保持原始比例展示。
- 2026-06-06：新增现位于 `docs/architecture/database-design.md` 的数据库设计和 `database/schema.sql`。
- 2026-06-07：合并 Project Map 中分散的修改记录，改为文档末尾统一维护。
- 2026-06-07：确认数据库暂缓接入；当前项目继续使用静态资源和浏览器 IndexedDB，数据库文件仅作为项目完工后的预留方案。
- 2026-06-07：新增 `README.md`、`CHANGELOG.md`、`VERSION` 和 `.gitignore`，准备将当前项目提交为 GitHub 第一版 `v1.0.0`。
- 2026-06-14：移除本地 Messages 页面、`/api/messages`、SQLite 消息存储、SMTP 示例配置和正式数据库消息表预留；Contact 页面改为打开邮件草稿。
- 2026-06-07：新增联系作者独立页面。
- 2026-06-07：Works Archive 新增 Arrange 模式，支持拖拽、移动按钮排序、本地保存顺序和刷新恢复。
- 2026-06-07：首页顺序调整为 Hero、Selected Works、四段图文 Statement、Contact；Statement 每段对应一张图片并分别入场，最终保留 Enter Works CTA、移动端和 reduced-motion 降级。
- 2026-06-08：统一 Works Archive 的圆角、字体角色和单色细线图标；上传入口改为细线工具入口，筛选区和 Count/Arrange 管理区分组，Arrange 卡片改为 4px 编辑态和图标按钮。
- 2026-06-08：更新 `project-development-guardrails/SKILL.md`，把 README、Project Map 和 Design System 纳入开发闭环。
- 2026-06-08：优化首页 hero 抽象到具象滚动转场；缩短 pinned 距离，延长图片 opacity 过渡进度，确认并接入抽象/具象两套 hero 文案分段淡出/淡入，延后导航换肤并补充锚点 header 避让。
- 2026-06-08：新增 Works Archive 上传图片压缩与数据库联动原型；上传时生成 `original`、`display`、`thumbnail` 和 `square_slice` 多版本资产，逐图显示状态，并同步 `image_assets` / `image_square_slices` 设计。
- 2026-06-10：新增 Works Archive 作品放大鉴赏层与标签可视化；普通模式点击卡片打开展签式 dialog，支持 Esc/遮罩/关闭按钮、左右切换、焦点恢复和滚动锁定，Arrange 模式点击不打开；数据库预留 `curatorial_note`、`artist_statement`、`series` 和标签分组字段。
- 2026-06-14：新增内部 Works Viewer 编辑页和共享 `archive-data.js`；`manage.html`/`manage.js` 可编辑 Viewer 右侧 metadata、visibility、sort order 和分组标签并保存到 IndexedDB，`archive.js` 按同 ID 合并 manual metadata 后供 `works.html` Viewer 回读。
- 2026-06-14：将 Add Works 从公开 `works.html` 迁移到内部 `manage.html`，新增共享 `archive-upload.js`；`manage.html` 增加首页 hero/Statement 图片和文字设置，保存到 IndexedDB `site_settings.homepage`，`script.js` 在首页启动时读取并应用。
- 2026-06-14：优化内部维护台信息架构，首页设置改为折叠辅助区，作品列表/编辑区前置；内部上传默认 published，并兼容旧自动 draft 上传，使保存后可在公开 Works 页立即查看。
- 2026-06-14：重做 `manage.html` 内部作者工作台视觉，Homepage 设置改为带 Abstract/Concrete Hero 图片预览、保存状态栏和 Last saved 的常驻编辑台；`works.html` 新增 Works 搜索、Clear Search、搜索空态和 Search/Type/Ratio 叠加过滤，`archive.js` 支持 title/series/说明/标签/tag groups/type/ratio/source 等字段搜索和 vertical/horizontal/panorama 比例关键词。
- 2026-06-14：删除 `manage.html` 顶部、Add Works、Homepage、Viewer Text、Metadata、Tag Groups 和 Delete Operations 中的说明性文案；保留 `Hero Images and Text`、字段、状态和操作控件。
- 2026-06-15：优化 Works Archive 标签体系和放大查看器；Viewer 改为全屏图片详情层，支持 Fit/Actual size 缩放、右侧信息栏和分组标签展示；`archive.js` 与 `scripts/seed_local_archive_db.py` 同步 Subject、Place、Form / Ratio、Mood、Material / Surface、Palette / Tone、Series / Collection 派生规则，seed 后 `data/archive.db` 写入 27 张 sample 图片、81 条资产、48 个派生标签、278 条标签关联和 `archive-featured` 集合。
- 2026-06-15：压缩 Works Archive 顶部 chrome，把搜索、筛选、Count 和 Arrange 改为更薄的 sticky 工具条；`manage.html` / `manage.js` 同步新增七组 Tag Groups 编辑器，保存时写回同一套 `tag_groups` / `tags` / `imageTags` / `imageTaggings` 结构。
- 2026-06-14：新增本地 SQLite 作品库验证层；`database/local_archive_schema.sql` 定义本地 `images` / `image_assets` / `image_tags` / `image_taggings` / `collections` / `collection_images` 和 `archive_image_view`，`scripts/seed_local_archive_db.py` 从 `archive-data.js` 生成 `data/archive.db`，写入 27 张 sample 图片、81 条资产、42 个派生标签、237 条标签关联和 `archive-featured` 集合。
- 2026-06-17：新增数据库验收工作流；`scripts/validate_local_archive_db.py` 默认创建临时 SQLite 库并验证 seed/schema/view/assets/tags/ratio/path，`.github/workflows/database.yml` 在 PR、主分支 push 和手动触发时运行同一命令；同步修正联系作者不再生成 `data/messages.db` 的文档边界。
- 2026-06-17：完成 Works Archive 本地只读数据库连接切片；`server.py` 新增 `GET /api/archive/images` 读取 `data/archive.db.archive_image_view` 的 published 作品，`archive.js` 优先使用该 API 并保留本地 sample/IndexedDB fallback，`works.html` 增加数据库加载状态。
- 2026-06-17：完成 Manage 到本地 SQLite 的 metadata/tag 写入切片；`server.py` 新增 `PATCH /api/archive/images/{id}`，`manage.js` 保存已有 seed 作品时同步写入 `images`、`image_tags` 和 `image_taggings`，上传图和首页设置继续留在 IndexedDB 过渡层。
- 2026-06-17：完成上传图片到 SQLite 数据库的 metadata 连接；`server.py` 新增 `POST /api/archive/images` 创建新上传记录，`manage.js` 修改 `shouldSyncRecordToArchiveApi()` 让上传记录也同步到数据库，新增 `archiveApiCreatePayload()` 函数，`importUploadedFiles()` 在上传时调用 POST API 写入 SQLite 并保留 IndexedDB 作为 fallback。
- 2026-07-03：补齐上传作品资产入库闭环；`manage.js` 的新上传 POST 改为 multipart，随 `metadata` 一起提交 `asset:{asset_id}` 文件字段；`server.py` 解析 multipart、保存文件到 ignored `assets/uploads/{image_id}/`、写入 `image_assets` 和 `image_square_slices`，让 `archive_image_view.image_url` / `thumbnail_url` / `original_url` 对上传作品也可用；`GET /api/archive/images` 默认过滤缺失 `image_url` 的旧坏记录，调试时可传 `include_missing_assets=1`；`.gitignore` 忽略本地上传产物。
- 2026-07-03：新增 Works feed 基础平台操作；`works.html` 增加 Saved rail、Download rail 和 archive toast 钩子，`archive.js` 增加保存/加入集合/下载操作、Saved 过滤和 localStorage 持久化，`styles.css` 增加 hover 操作按钮 active 状态和 toast 样式。
- 2026-07-03：升级作品详情弹层；`works.html` 在 viewer 信息栏增加 Save/Collect/Download 操作和 Related Works 容器，`archive.js` 复用 feed 操作状态并按 Type/Ratio/Series/标签重合推荐相关作品，`styles.css` 增加详情层操作按钮和相关作品列表样式。
- 2026-07-03：新增 Collections 第一切片；`collections.html` / `collections.js` 展示当前浏览器 `mt-presence-collection-works-v1` 中的 Quiet Collection，支持集合内搜索、移除作品、API/sample/IndexedDB fallback 和 toast；首页、Works、Contact 导航补充 Collections 入口。
- 2026-07-03：扩展 Collections 集合切换；`collections.html` 新增 Quiet/Abstract/Concrete 集合卡片，`collections.js` 支持 `activeCollectionSet`、自动 Abstract/Concrete 过滤、集合计数和切换 toast，`styles.css` 增加集合切换卡片响应式样式。
- 2026-06-24：按参考图库截图重做公开 Works 页面外壳和图片 hover 交互；`works.html` 新增左侧 rail、顶部搜索栏、频道/比例 tabs 和 Submit 入口，`archive.js` 的 gallery 卡片增加 hover 暗层、品牌角标、收藏/加号、作者信息和 `View` 浮动按钮，并把 API/sample 作品排在本地 upload fallback 前；`styles.css` 新增紧凑顶部/侧边栏、四列 masonry 图片墙、hover 动效、比例筛选 grid、移动端单列降级和 reduced-motion 降级。
- 2026-06-24：补充上传联调、仓库辅助文件和本地产物职责说明；重复完成报告已在 2026-07-13 文档整理时删除。
- 2026-07-04：新增静态 UI 组件体系增强层；`styles.css` 增加 `--ui-*` token、统一 focus-visible、gallery/collection item reveal、集合 active indicator、Contact 表单状态和 loading spinner；`archive.js` / `collections.js` 在重渲染时设置 `aria-busy` 并注入 `--item-delay`；`contact.js` 同步字段状态和 `aria-invalid`；`works.html` 筛选按钮补初始 `aria-pressed`，各页面样式版本号更新为 `20260704-ui-system-2`。
- 2026-07-04：修正作品查看器和左侧 rail 的黑色占比；`styles.css` 将 `.work-viewer-media` 从大面积黑底改为浅色 gallery surface、细边界和轻阴影，左侧 `archive-rail-button.is-active` 改为低对比品牌色 active 状态；各页面样式版本号更新为 `20260704-ui-system-3`。
- 2026-07-04：重做 Works 点击查看和 hover 操作层；`works.html` 新增 `icon-info`、Info toggle、rail/title 提示和 `20260704-ui-system-4` 样式版本，`archive.js` 新增默认关闭的 Info 抽屉状态、`i` 快捷键、hover Save/Collect/Download 图标按钮 title，`styles.css` 把查看器改为沉浸式全屏图片优先并让信息以右侧抽屉滑出，同时移除卡片 hover 底部文字和大号 Download 文案按钮。
- 2026-07-04：补齐按钮 tooltip 和图片点击语义；`works.html` 把 rail、viewer 和详情操作按钮从原生 `title` 改为 `data-tooltip`，样式版本更新到 `20260704-ui-system-5`；`archive.js` 让 Save/Collect 动态 tooltip 随状态变化，并取消 viewer 图片自身点击切换局部 zoom；`styles.css` 增加统一黑底 tooltip 和 viewer 图片默认指针，让“点击卡片打开全屏查看”与“按钮 hover 显示提示”成为明确规则。
- 2026-07-05：新增 `upload-studio.html` / `upload-studio.js` 文件夹式上传工作台；保留旧 `manage.html` 和公开 `collections.html`，新页面提供 Folders、当前文件夹一键上传、上传队列、点击图片编辑信息、保存/发布到 Works，并把文件夹名写入 `series` 与 `Series / Collection` 标签组；`styles.css` 增加 `.upload-studio-*` 三栏工作台样式，`works.html` 的 `Submit an image` 改指向新上传工作台，`manage.html` 增加入口链接。
- 2026-07-05：将 Works 页面原 Collections/文件夹入口改为 Upload Studio；`works.html` 左侧 rail 文件夹图标和顶部 `Upload Studio` 都跳转 `upload-studio.html`，`upload-studio.html` 新增与 Works 一致的左侧 `archive-rail`，桌面端 header/content 避让 rail，移动端隐藏 rail 并保持单列工作台。
- 2026-07-10：将 `manage.html` 从上传/编辑混合页收敛为 Archive Review 审核中心；新增 Works 同款左侧 rail、审核统计筛选、Review Queue、审核 checklist 和 `Approve & Publish`，直接上传控件移出 Manage 并继续由 `upload-studio.html` 负责；`manage.js` 增加审核状态推导、筛选计数和发布前校验；`styles.css` 增加 `.manage-review-*` 审核工作台样式。
- 2026-07-10：移除普通用户个人工作台 `user-manage.html` / `user-manage.js` 以及 `Your Studio` 入口；左侧 rail 改为 96px 极简短标题导航，只显示 Works、Sets、Upload、Review、Saved、Download 和 Contact；`Legacy Editor` 文案统一改为 `Review Center`。
- 2026-07-10：明确 `Sets` 为 Works 收藏/自动策展集合页，`Upload` 为个人图片上传平台；`upload-studio.html` / `upload-studio.js` 增加当前上传记录 Delete 操作，`server.py` 增加 `DELETE /api/archive/images/{id}`，只允许删除 upload 来源作品并清理 SQLite 级联关系、本地上传文件夹和 IndexedDB fallback。
- 2026-07-10：按素材库页面参考收敛工具页首屏设计；`collections.html`、`upload-studio.html`、`manage.html` 去掉大 hero 标题和说明卡片，改为 18-20px 模块名、紧凑操作栏、横向筛选 pill 和内容优先布局。
