# Database Design

## 当前状态

Phase 2A-2F 已把账户 owner-scoped Folder、Upload Intent、Draft、Version、Asset metadata、可靠取消/清理、private Supabase Storage、权威 readiness、Submit transaction 与可信 asset scanner 接入当前 development boundary。公开 Works 与 legacy Review Center 仍使用本地 SQLite/sample；不要下载 MySQL，也不要执行历史 `database/schema.sql` 作为当前 production baseline。

`server.py` 同时维护两条明确分离的边界：`/api/folders`、`/api/uploads/*`、`/api/images*` 是 Supabase Workspace/Submit；`/api/archive/images*` 是 Admin+AAL2 legacy SQLite Review/public prototype。Upload Studio 只使用前者；`manage.html` 尚未读取 Supabase `review_submissions`。Contact 页面使用 `mailto:`，不保存本地消息。

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

## 目标

当前 Supabase 已保存私人 Draft，并能权威计算 readiness、创建 immutable submission snapshots 和锁定 submitted workflow；剩余目标是把 Admin Review Queue/decision、Publish、公开 Works、sample/import 和首页精选迁移到同一 production boundary。关系数据库保存 metadata、状态和对象 key，真实图片文件保存在 Supabase Storage。

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

当前 Upload Studio 在浏览器生成 `original`、`display`、`thumbnail`，服务端创建 `{auth.uid}/{image_id}/{kind}.{ext}` signed destination，浏览器直传 private Storage，再由 complete RPC 创建 Draft/version/asset rows。Folder/Draft/readiness/Submit 以 PostgreSQL 为 authority，IndexedDB 只缓存最近成功响应。上传永远不会直接 published；成功 Submit 只进入 `submitted`，Admin Review/Publish 尚未接入。真实 asset 初始 `scan_status=pending`，Phase 2F 独立 worker 通过仅授予 service_role 的 leased RPC 读取并验证 private object，只有三个资产都以当前 policy 明确 `clean` 才允许 Submit；当前没有 user quota/capacity policy。Trash 是 soft delete，restore RPC/API 已有而页面待实现。

## 文件

- `database/schema.sql`：PostgreSQL/Supabase 兼容作品档案 schema，包含表、枚举、索引、更新时间 trigger、比例分类函数和 Archive 视图。
- `database/local_archive_schema.sql`：SQLite 本地验证 schema，字段命名和核心关系对齐目标 schema，但使用 `TEXT` ID 和 SQLite check/index/view 能力。
- `scripts/seed_local_archive_db.py`：本地 seed 脚本；读取 `archive-data.js`，写入本地 sample 图片、三类资产、派生标签、标签关联、`archive-featured` collection 和分析记录。
- `scripts/validate_local_archive_db.py`：本地和 CI 共用的数据库验收脚本；运行 seed 后检查 SQLite integrity/foreign key、核心表和 `archive_image_view`、published 数量、三类资产、URL fallback、标签 JSON、比例 code 和本地图片路径。
- `.github/workflows/database.yml`：数据库检查工作流；安装 Python 3.11 和 Node 20 后执行 `python3 scripts/validate_local_archive_db.py`。
- `archive-upload.js`：当前内部上传的本地处理管线，输出可迁移到 `images`、`image_assets` 和 `image_square_slices` 的对象。
- `upload-studio.js`：当前个人 Draft/Submit 客户端；signed upload、Folder、Draft、readiness、Submit、Trash 走 Supabase API，IndexedDB 仅为离线只读 cache。
- `manage.js`：当前 legacy Review Center metadata 写入来源；已有 seed 作品保存到本地 SQLite，首页设置保存在 IndexedDB；尚未读取 Supabase `review_submissions`。
- `archive.js`：当前公开 Works 读取模型来源；优先读取本地只读 API 的 published 作品，失败时使用 sample/IndexedDB fallback，写入仍停留在浏览器本地过渡层。
- `server.py`：本地静态服务器；除 legacy Archive API 外，提供受保护的 Supabase Folder/upload/Draft/readiness/Submit 边界，对 readiness/error/submission response 做 allowlist 清洗；不提供消息 API。
- `database/migrations/20260716_workspace_submit_readiness.sql`：Phase 2E 增量；增加 submission UUID/readiness/asset snapshots 和 immutability guards，安装五项 readiness 与 versioned Submit RPC，收紧 submission table/Storage delete 权限，并把 workflow、notification、audit 写入同一事务。
- `database/migrations/20260717_workspace_asset_scanner.sql`：Phase 2F 增量；新增 restricted leased jobs、append-only events、INSERT enqueue trigger、SKIP LOCKED claim、token-bound retry/complete、attempt exhaustion、Storage object/观察值校验、scan notification/audit，并只向 service_role 授予三条 RPC 的 EXECUTE。
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
3. 已完成 `database/product_schema.sql` + Phase 1 RLS/Auth + Phase 2A-2F ordered Workspace migrations 的当前 development boundary。
4. 已完成 owner-scoped signed upload、Folder、Draft edit/list、soft-delete Trash、双并发 Retry/Cancel/Remove、partial-object cleanup、五项 readiness、idempotent Submit transaction，以及独立 trusted scanner 的 leased/retry/clean/flagged/failed 代码与数据库状态机；development 常驻 Worker 仍需 provision scanner secret 与 ClamAV 后才会自动消费当前 queued jobs。
5. 下一步把 legacy `manage.html` 拆出的 Admin Review Queue/Detail 接到 Supabase `review_submissions`，让真实 submitted record 可以被领取、查看和决策。
6. 后续补 scheduled orphan repair、user quota/rate limit 与 TUS，再实现 Review decisions/Publish 和 published-only production DTO/public delivery。
7. 最后迁移 `sampleItems`、首页精选、真实 AI 分析与仍被产品确认需要的 square slice/tag 能力。
