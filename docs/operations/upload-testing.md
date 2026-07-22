# Phase 2A-2F Upload Workspace 验收

## 当前边界

`/workspace/images` 已使用 Supabase 作为 Folder、Draft 和图片资产的权威来源：

1. 浏览器生成 `original`、`display`、`thumbnail` 资产与 SHA-256。
2. `POST /api/uploads/intents` 校验 Folder、文件类型、大小、尺寸和 checksum，并生成 owner-namespaced Storage key。
3. 服务端使用当前 HttpOnly session 向 Supabase Storage 创建短期 signed upload URL；access token 不返回浏览器。
4. 浏览器直接 `PUT` 三类资产到 private bucket。
5. `POST /api/uploads/{id}/complete` 核对 Storage object 后，在一个 RPC 中创建 `images`、`image_versions`、`image_assets` Draft。
6. Folder 与 Draft 后续读写都走服务端 API；IndexedDB 仅保存最近成功读取的离线只读 cache。
7. 浏览器最多并发处理两个任务；每个任务独立支持 Cancel、Retry 和 Remove。
8. 取消 upload intent 后，服务端通过 Storage API 清理三类可能已上传对象，并把结果记录为 `complete` 或 `failed`。
9. `GET /api/images/{id}/readiness` 权威返回 Work details、Rights & disclosures、Image assets、Security scan、Submission state 五项检查；客户端只展示和轮询。
10. `POST /api/images/{id}/submit` 使用 current `expected_version`、UUID idempotency key 和显式确认；事务锁定 image version，保存 review/readiness/asset snapshots，更新 workflow/version，并写 notification/audit。
11. authenticated 不能直接 mutation `review_submissions`；owner 不能直接删除已经登记到 `image_assets` 的 Storage object，未完成 intent 的临时对象仍可通过受控取消清理。
12. `image_assets` INSERT 自动建立 restricted scan job；独立 worker 通过仅授予 service_role 的 scanner RPC 领取 lease，流式核对 private object，并在无凭据子进程中执行 ClamAV/Pillow，token-bound complete/retry 最终更新 scan status、event、notification 与 audit。

当前不包含 Admin Review Queue/Detail/decision、Publish、scheduled orphan repair、TUS/断点续传、user quota/rate limit 或 Trash 恢复页面。真实上传资产从 `scan_status=pending` 开始，trusted scanner 按当前策略明确写入三个 `clean` 前 Submit 必须 disabled；这不是 quota/capacity 限制。Phase 2F 代码和数据库已部署，但 development 尚未配置常驻 scanner secret/ClamAV Worker，所以现有三个任务保持 `queued`、资产保持 `pending`。浏览器上传 Retry 仍是明确的用户操作，scanner 基础设施失败则使用独立的有界后台 retry。`manage.html` 和公开 Works 仍属于 legacy SQLite Review 原型，不读取 Supabase `review_submissions`。

## 自动验证

在仓库根目录运行：

```bash
python3 -m pip install --require-hashes -r requirements-scanner.txt
python3 scripts/validate_product_phase0.py
python3 scripts/validate_auth_foundation.py
python3 scripts/validate_supabase_phase1_rls.py
python3 scripts/validate_workspace_phase2.py
python3 scripts/validate_workspace_asset_scanner.py
python3 scripts/test_auth_security_boundary.py
python3 scripts/test_workspace_phase2_boundary.py
python3 scripts/test_workspace_asset_scanner.py
python3 scripts/test_supabase_deploy_script.py
node --check upload-studio.js
```

`test_workspace_phase2_boundary.py` 使用本地 fake Auth/REST/Storage provider，不读取真实凭据，覆盖：

- anonymous Folder 读取拒绝；
- owner Folder hydrate/create/rename；
- upload intent 严格校验与三类 signed destination；
- cancel confirmation、三类 owner-namespaced partial object cleanup 与 cleanup result；
- complete 后 private Draft signed preview；
- publication/workflow 等系统字段拒绝；
- Trash confirmation；
- readiness blocked/pending/ready 与固定五项安全 response shape；
- Submit missing CSRF、stale expected version、DRAFT_NOT_READY、安全 details 清洗和严格 success allowlist；
- UUID same-key idempotency、immutable snapshot、submitted update/Trash lock 与 Draft list 移除；
- Admin AAL1 拒绝；
- response 不泄露 session token。

`test_workspace_asset_scanner.py` 使用 loopback fake REST/Storage provider、真实 Pillow fixture 和 fake ClamAV，不读取真实 secret，覆盖：

- current `sb_secret_` 仅使用 `apikey`，legacy service-role JWT 使用 `apikey` + Bearer；两者均不带 Cookie/CSRF；
- HTTP redirect 在携带 credential 前被拒绝，ClamAV/Pillow 子进程不继承 Supabase/PG credential；
- 有效 JPEG/PNG/WebP clean、EXIF orientation、多帧/像素上限、损坏 decode failed、checksum mismatch failed、malware flagged；
- ClamAV transient 与 Storage 503 进入 retry，Storage 404 明确 failed；
- 私有临时目录不会保留已完成文件，object key、lease token、恶意签名与 secret 不进入 stdout/stderr。

## 开发库部署

已有 Phase 1 baseline 的开发库只运行 ordered migrations：

```bash
set -a
source .env
set +a
MT_APPLY_PHASE1_BASELINE=no MT_DEPLOY_ENVIRONMENT=development bash scripts/deploy_supabase_phase1.sh
```

不要对 existing database 重放非幂等 `product_schema.sql` baseline。Production 还需要显式 `MT_ALLOW_PRODUCTION=yes`，且必须经过 release approval。

部署后至少确认：

- `public.upload_intents` 已启用 RLS；
- `image-originals` / `image-display` / `image-thumbnails` 均为 private；
- bucket size limit 分别为 50/20/10 MiB，MIME allowlist 为 JPEG/PNG/WebP；
- authenticated 对 `folders`、`images`、`image_versions`、`image_assets`、`upload_intents` 没有通用 INSERT/UPDATE/DELETE；
- `workspace_get_submit_readiness` 与 `workspace_submit_draft_versioned` 仅授予 authenticated，anon/public 不可执行；
- authenticated 不可直接 INSERT/UPDATE/DELETE `review_submissions`，locked version 与 review snapshot immutability trigger 存在；
- `asset_scan_jobs` / `asset_scan_events` 启用 RLS，anon/authenticated/service_role 无表权限；
- 三条 `scanner_*` RPC 只授予 service_role，anon/authenticated/public 不可执行；claim 使用 SKIP LOCKED，completion 校验 token、lease、asset snapshot 与 Storage object；
- cancel/cleanup 两个新增 RPC 不向响应泄露 intended asset keys；
- 每个业务用户有一个 active system Inbox；
- Storage owner insert/select/delete policies 均存在，且 owner delete policy 排除已登记到 `image_assets` 的对象。

development 至少有三个 queued job 时，可运行真实数据库状态机测试。它会在单个事务内验证 disjoint claim、same-token idempotency/conflict、旧 token 拒绝、lease reclaim 和 attempt exhaustion，最后固定执行 `ROLLBACK`，不会保存 verdict：

```bash
/opt/homebrew/opt/libpq/bin/psql --set ON_ERROR_STOP=1 --file scripts/test_workspace_asset_scanner_database.sql
```

## Trusted scanner 运行

Scanner 与 Web server 必须使用不同环境。使用 Python 3.11 创建 scanner venv；`server.py` 只加载 publishable key，`.env.worker` 只供 worker 使用并保持 Git ignored。secret/service-role credential 本身仍可绕过 RLS 并访问广泛的服务端能力；“当前 Worker 只调用三个 scanner RPC”不是 credential-level 限权，因此必须隔离、轮换并禁止进入 Web/解码子进程。

```bash
python3 -m venv .venv-scanner
.venv-scanner/bin/python -m pip install --require-hashes -r requirements-scanner.txt
python3 scripts/configure_development_scanner.py
set -a
source .env.worker
set +a
.venv-scanner/bin/python workers/image_scanner.py --once
```

`configure_development_scanner.py` 从 `.env` 继承 `SUPABASE_URL`，通过隐藏输入读取 current `sb_secret_` key；非交互环境只从进程环境读取 current secret 或 legacy service-role JWT，不提供会进入 shell history/process arguments 的 secret 参数。脚本会用空文件执行真实 ClamAV preflight，保留已有稳定 Worker ID，并在全部检查通过后才以原子替换和 `0600` 权限写入 Git ignored `.env.worker`。失败不会覆盖上一份有效配置，也不会输出 credential。

连续运行使用：

```bash
.venv-scanner/bin/python workers/image_scanner.py --poll-seconds 5
```

运行前确认：

- `SUPABASE_URL` 指向 development project；优先配置 current `SUPABASE_SECRET_KEY`，仅在兼容旧项目时使用 `SUPABASE_SERVICE_ROLE_KEY`；
- `MT_SCANNER_ID` 是稳定、非敏感 worker 标识；租约必须 30-900 秒；
- `MT_SCANNER_CLAMAV_COMMAND` 指向可用 `clamdscan --fdpass --no-summary` 或等价受控命令；使用 `clamdscan` 时 ClamD 正在运行，所有模式的签名数据库持续更新；
- 下载、像素、最长边、HTTP/download/scan/decode timeout 与 decode memory 维持 `.env.worker.example` 的 fail-closed 上限；下载 + 扫描 + 解码 + 三次 provider request + 30 秒余量必须不大于 lease；
- private temp root 及每个 worker 子目录必须为 `0700`，任务文件为 `0600`；启动会清理同目录的遗留 `mt-scan-*.bin`；
- Provider redirect 一律拒绝；ClamAV 使用最小环境，Pillow 在 `-I` 无凭据子进程中运行并应用 timeout、CPU/core/NOFILE 以及操作系统支持时的内存上限；生产仍应配合无出站网络的容器/进程隔离；
- Worker 日志只包含 asset/image UUID、kind、attempt、outcome、稳定 result code 和耗时，不包含 object path、lease token、scanner signature 或 credential。

ClamAV/Pillow startup preflight 失败时 Worker 不得启动；Provider、Storage 或扫描依赖在任务期间失败时必须保留租约失败证据并安排 retry。任何情况下都不能使用“跳过病毒扫描”的 development clean fallback。

## 手工浏览器验收

### 1. 启动服务器

`.env` 中配置 development Supabase URL、publishable key 和 PostgreSQL连接变量，然后运行：

```bash
python3 server.py --port 8131
```

打开 `http://127.0.0.1:8131/workspace/images`。直接访问 `/upload-studio.html` 应 303 到 canonical Workspace route。

### 2. 验证路由与会话

- 未登录：跳转 `/auth/sign-in?next=/workspace/images`。
- recovery session：只能进入 Reset Password，不得进入 Workspace。
- active 普通用户：允许进入。
- Admin/Super Admin AAL1：跳转 `/auth/mfa?next=/workspace/images`。
- Admin/Super Admin AAL2：允许进入。

### 3. 验证 Folder

1. 首次进入必须看到不可重命名/删除的 Inbox。
2. 创建普通 Folder，刷新页面后仍存在。
3. 重命名 Folder，重复名称应返回 conflict。
4. 删除空 Folder 应从 active list 消失。
5. 删除非空 Folder 时确认 move-to-Inbox；其中的活动 Draft 必须迁入 Inbox。
6. Folder 仍有排队、失败或取消任务时，删除操作必须被阻止并提示先完成或 Remove。

### 4. 验证上传与 Draft

1. 选择 JPEG、PNG 或 WebP；不支持的 MIME 应在 intent 前被拒绝。
2. 观察 Reading、Compressing、Slicing、Analyzing、Uploading、Draft ready 状态，队列布局不得跳动。
3. Network 中应出现一个 upload intent、三个 signed Storage `PUT`、一个 complete 请求。
4. signed Storage 请求不得携带应用 session cookie 或 Supabase access token。
5. complete 成功后刷新，Draft 必须从 `/api/images` 恢复；预览 URL 应为短期 signed URL，不是 public object URL。
6. 清空 Title 并 Save Draft，刷新后 Title 输入仍为空，列表仅用 `Untitled Work` 作为显示占位。
7. 修改 Folder、Captured、Content Category、Caption、Description、Tags 并保存；刷新后值保持。
8. Workspace 没有 Visibility、Review decision 或 Publish 控件；选中 Draft 后应看到五项 Submission readiness 和 Submit for Review。
9. 同时选择至少三张图片：任意时刻最多两个任务进入处理/上传，第三个保持 Queued 且卡片尺寸不变化。
10. Queued 或 Uploading 状态点击 Cancel：任务进入 Canceling/Canceled，已创建 intent 时出现一个 `DELETE /api/uploads/{id}`；响应不得包含 asset keys。
11. 人为制造 signed `PUT` 失败：卡片必须显示 Failed、Retry 和 Remove。Retry 成功后只保留一个可编辑 Draft；Remove 释放本地预览并移除任务。

### 5. 验证 Readiness 与 Submit

1. 保持 Title/Alt Text/Rights 等必填信息不完整：readiness 应为 Blocked，列表显示对应字段，不允许 Submit。
2. 补齐 Work details 与 Rights/disclosures：真实上传资产仍为 `scan_status=pending`，readiness 应仅保留 Security scan Pending，页面每 5 秒轮询且 Submit 继续 disabled。
3. 不要通过浏览器或普通 authenticated token 把 scan 改为 `clean`。启动独立 worker，确认它领取三个 asset job；有效文件依次产生 clean event，页面继续轮询而不需要刷新。
4. 三个 job 都明确 clean 后 readiness 应为 Ready；点击 Submit 先保存最新 Draft、重新检查并打开确认 dialog，Cancel 不改变状态。任一 flagged/failed 时 readiness 必须 Blocked，且不能由 owner 绕过。
5. 确认后 Network request body 必须精确包含 `confirmation=submit-for-review`、当前 `expected_version` 与 UUID `idempotency_key`；成功返回 201，并从当前 Draft list 移除。
6. 重发同一 idempotency key 不得创建第二条 submission；stale `expected_version` 返回 409。submitted image 的 Draft PATCH 和 Move to Trash 返回 423。
7. Submit response 只包含公开 submission/image 状态，不得包含 asset key、owner、internal note、provider debug、session token 或完整 snapshot。
8. 当前没有 user quota/capacity check；不要把 readiness pending/blocked 文案解释为 quota。

### 6. 验证 Trash 与离线 cache

1. Move to Trash 必须先确认；成功后 active Draft list 不再显示该记录。
2. 浏览器 Trash restore UI 尚未实现，不应伪装为 hard delete。
3. 在线成功载入后断开网络并刷新：允许展示 IndexedDB 最近 cache。
4. 离线状态下 Import、Folder mutation、Draft form 和 Trash 必须禁用；不得把本地 mutation 当成已同步。
5. signed preview URL 可能在离线 cache 中过期；metadata 仍可读，图片不可用不代表 cache 可写。

## Workspace API

```text
GET    /api/folders
POST   /api/folders
PATCH  /api/folders/{id}
DELETE /api/folders/{id}
POST   /api/folders/{id}/restore

POST   /api/uploads/intents
DELETE /api/uploads/{id}
POST   /api/uploads/{id}/complete

GET    /api/images?workflow_status=draft
GET    /api/images/{id}/readiness
PATCH  /api/images/{id}/draft
POST   /api/images/{id}/submit
DELETE /api/images/{id}
POST   /api/images/{id}/restore
```

所有 mutation 要求 same-origin CSRF token。所有接口要求 active account；Admin/Super Admin 还要求 AAL2。Draft patch 只允许编辑 core copy、Folder、Alt Text、copyright、release、rights、AI 和 sensitive disclosure 字段，不允许 owner/workflow/publication/asset/system lock 字段。

Submit body 必须精确是 `{"confirmation":"submit-for-review","expected_version":N,"idempotency_key":"<uuid>"}`。Readiness 与 Submit 都由数据库重新验证 owner、当前 version、editable workflow、完整 private assets/Storage objects 和 scan state；浏览器显示 Ready 不能绕过服务端检查。

取消请求 body 必须是 `{"confirmation":"cancel-upload"}`。completed intent 返回 conflict；重复取消保持幂等。Storage cleanup 暂时失败时 API 返回 `202` 与 `cleanup_status=failed`，用户可再次 Cancel/Retry 触发清理重试，页面不得宣称对象已经删除。

## 故障排查

### `AUTH_NOT_CONFIGURED`

服务器进程未加载 `SUPABASE_URL` 或 `SUPABASE_PUBLISHABLE_KEY`。确认 `.env` 已 source 后重启服务器。

### `MFA_REQUIRED`

当前身份具有 Admin/Super Admin role，但 JWT 仍为 AAL1。进入 `/auth/mfa` 完成 TOTP challenge，再返回 Workspace。

### `UPLOAD_ASSETS_INCOMPLETE`

至少一个 private Storage object 缺失，或 object 的 owner、bucket、key、MIME、size 与 intent 不一致。检查三个 signed `PUT` 的 response，不能跳过失败项直接 complete。

### Storage `400` / `413`

检查 MIME 是否为 JPEG/PNG/WebP，以及 original/display/thumbnail 是否分别小于 50/20/10 MiB。当前切片没有 TUS，大文件和断点续传留待后续。

### 离线时无法保存

这是预期行为。IndexedDB 是只读 cache，不是 mutation queue。恢复网络并刷新 server-authoritative data 后再编辑。

### `DRAFT_NOT_READY`

查看 response 中已清洗的五项 readiness。修复 Work details/Rights 字段后，真实资产在 worker 完成前显示 Security scan Pending；检查 scanner 进程、ClamAV health、service_role-granted scanner RPC 和 retry event，不要把普通用户权限扩大为 scan writer。当前没有 quota policy，不能用修改 quota 绕过。

### Scanner `scanner_startup_failed`

检查 `.env.worker` 是否独立提供 `SUPABASE_URL`、secret/service-role key、`MT_SCANNER_ID` 与 `MT_SCANNER_CLAMAV_COMMAND`，并确认 Pillow 依赖和 ClamAV daemon/signatures 可用。日志只给稳定 code，不会输出 credential 或 ClamAV signature。

### Scanner 持续 `scan_retried`

按 result code 区分 provider/Storage timeout、ClamAV unavailable/timeout 与 completion failure。修复基础设施后等待 `available_at` 再领取；不要手工把数据库改成 clean。达到 max attempts 会 terminal failed 并阻止 Submit，需要受控运营处理或后续重扫策略，不能重置 token 绕过。

### Draft 不出现在 `manage.html` 或 `works.html`

Editable Draft 与成功 submitted record 都不会进入 legacy `manage.html` 或公开 Works。Phase 2E 已创建 Supabase submission，但 Admin Review Queue/decision/Publish 与 public delivery 尚未接入；不要用 legacy `/api/archive/images` 复制记录来绕过工作流。

### Review Center 未修改却提示离开

打开 `manage.html` 后不做任何编辑，点击 Upload/Works 应直接离开；修改一个 Homepage 可编辑字段后离开才应出现浏览器提示，Cancel 后输入仍保留，Save/Revert 后提示消失。dirty signature 不比较派生 `database_shape`，`beforeunload` 也不应在离开时重新序列化表单。
