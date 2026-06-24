# Database Design

## 当前状态

作品档案数据库暂缓接入。当前项目继续使用静态页面、本地图片资源和浏览器 IndexedDB；不要下载 MySQL，也不要在现在执行 `database/schema.sql`。

`server.py` 提供本地静态文件服务，并提供 `GET /api/archive/images` 端点用于从 `data/archive.db` 的 `archive_image_view` 读取已发布作品，以及 `PATCH /api/archive/images/{id}` 端点用于把内部管理页对既有 seed 作品的 metadata 和标签写回 SQLite。Contact 页面使用 `mailto:` 打开访客邮件客户端，不保存本地消息，也不提供消息中心。

当前新增了一个本地 SQLite 验证库，不作为生产后端，也不改变页面数据源：

- `database/local_archive_schema.sql`：SQLite 版本的本地作品档案 schema，用于验证表结构、标签关系和查询视图。
- `scripts/seed_local_archive_db.py`：从 `archive-data.js` 读取 27 张本地 sample 图片，写入 `data/archive.db`。
- `scripts/validate_local_archive_db.py`：创建临时 SQLite 数据库，运行 seed，并验证表/视图、外键、数据量、多版本资产、标签 JSON、比例分类、展示 URL fallback 和本地资源路径。
- `.github/workflows/database.yml`：在 pull request、`main`/`master` push 和手动触发时运行本地数据库验证。
- `server.py`：读取 `data/archive.db` 并通过 `GET /api/archive/images` 返回 `archive_image_view` 中 `visibility = 'published'` 的作品；支持 `type`、`ratio` 和 `limit` 查询参数；`PATCH /api/archive/images/{id}` 更新既有图片的标题、说明、系列、可见性、排序和标签关系。
- `archive.js`：公开 Works 页面启动时优先读取 `/api/archive/images`，失败或无结果时回退到本地 sample/IndexedDB。
- `manage.js`：保存已有 seed 作品时同步调用 `PATCH /api/archive/images/{id}`，写入 `images`、`image_tags` 和 `image_taggings`；上传图和首页设置仍保存到 IndexedDB 过渡层。
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

项目完工后，MT Presence 的数据库可用于保存作者作品档案的服务端版本，替代当前 `archive.js` 中的浏览器 IndexedDB 本地存储。图片数据库只保存图片元数据、分类结果、对象存储路径和分析记录；真实图片文件应放在对象存储中，例如 Supabase Storage、S3 或自建文件服务。

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

当前静态原型在内部 `manage.html` 中用 IndexedDB 模拟这套对象存储模型：每张上传图保存 `imageRecord`、`assets[]` 和 `squareSlices[]`，其中 `assets[]` 字段对齐 `image_assets`，`squareSlices[]` 对齐 `image_square_slices`。内部上传默认写成 `published`，方便作者保存后立刻到公开 `works.html` 检查；作者仍可在 Manage 页把 visibility 改成 `draft`、`private` 或 `archived`，公开页面只读取已发布作品。未来接 API 时，把这些本地对象上传到对象存储并批量写入数据库即可。

## 文件

- `database/schema.sql`：PostgreSQL/Supabase 兼容作品档案 schema，包含表、枚举、索引、更新时间 trigger、比例分类函数和 Archive 视图。
- `database/local_archive_schema.sql`：SQLite 本地验证 schema，字段命名和核心关系对齐目标 schema，但使用 `TEXT` ID 和 SQLite check/index/view 能力。
- `scripts/seed_local_archive_db.py`：本地 seed 脚本；读取 `archive-data.js`，写入本地 sample 图片、三类资产、派生标签、标签关联、`archive-featured` collection 和分析记录。
- `scripts/validate_local_archive_db.py`：本地和 CI 共用的数据库验收脚本；运行 seed 后检查 SQLite integrity/foreign key、核心表和 `archive_image_view`、published 数量、三类资产、URL fallback、标签 JSON、比例 code 和本地图片路径。
- `.github/workflows/database.yml`：数据库检查工作流；安装 Python 3.11 和 Node 20 后执行 `python3 scripts/validate_local_archive_db.py`。
- `archive-upload.js`：当前内部上传的本地处理管线，输出可迁移到 `images`、`image_assets` 和 `image_square_slices` 的对象。
- `manage.js`：当前前端本地模型写入来源；已有 seed 作品的 metadata/tag 保存会同步到本地 SQLite API，上传图、图片资产二进制和首页设置仍保存在 IndexedDB 过渡层；项目完工后再考虑把全部写入逻辑改为生产 API。
- `archive.js`：当前公开 Works 读取模型来源；优先读取本地只读 API 的 published 作品，失败时使用 sample/IndexedDB fallback，写入仍停留在浏览器本地过渡层。
- `server.py`：当前本地静态服务器；提供 `GET /api/archive/images` 作品读取端点和 `PATCH /api/archive/images/{id}` 既有作品 metadata/tag 写入端点，不提供消息 API、上传 API 或图片文件写入 API。

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

当前本地接口：

- `GET /api/archive/images`：读取 `data/archive.db` 的 `archive_image_view`，只返回 `visibility = 'published'` 的作品。
- 可选查询参数：`type=abstract|concrete`、`ratio=four_to_three|4:3|panorama`、`limit=1..1000`。
- 如果 `data/archive.db` 不存在，返回 `503` 和 seed 提示；`works.html` 会显示状态并回退到本地 sample 数据。
- `PATCH /api/archive/images/{id}`：只更新既有 `images` 行的 `title`、`description`、`curatorial_note`、`artist_statement`、`series`、`captured_at`、`content_type`、`display_mode`、`visibility`、`sort_order`，并替换该图片的 `image_taggings` 关系；不会创建图片、不会写入 `image_assets`、不会接收文件。
- `PATCH` 会强制校验 `abstract -> black_white`、`concrete -> color`；`manage.js` 对 seed 作品调用该端点，上传图则继续只保存到 IndexedDB。

后续生产服务端建议提供这些接口：

- `GET /api/images?type=abstract&ratio=four_to_three`
- `POST /api/images/upload-intent`
- `POST /api/images`
- `POST /api/images/:id/analyze`
- `GET /api/collections/homepage-selected`

前端不应该直接拼对象存储路径；应读取 `archive_image_view.image_url` 或 API 返回的签名 URL。

作品放大鉴赏层应读取同一条 Archive 查询结果，不单独请求原图。字段优先级为：`display` 资产或 `archive_image_view.image_url` -> 必要时 fallback 到 `original_url`；`thumbnail_url` 只用于列表或快速预览，不替代作品展示图。标签建议直接返回 `tag_groups`，前端只做轻量渲染和缺省分组 fallback。

## 权限建议

如果使用 Supabase：

- 公开页面只能读取 `visibility = 'published'` 的图片和集合。
- 作者后台可以读取自己的 `draft/private/published` 图片。
- 上传、修改、删除只能由作者或管理员执行。
- 对象存储 bucket 建议拆成 `originals` 和 `public-display`，原图默认不公开，展示图可公开或走签名 URL。

## 后续接入顺序

以下步骤暂缓，等页面、作品展示、上传体验和后台需求稳定后再执行：

1. 当前已完成本地读取连接：`server.py` 读取 `data/archive.db`，`works.html` / `archive.js` 优先消费 `/api/archive/images`。
2. 当前已完成本地既有作品 metadata/tag 写入连接：`manage.js` 保存 seed 作品时调用 `PATCH /api/archive/images/{id}`。
3. 后续接生产时，先执行 `database/schema.sql` 创建表。
4. 建一个上传 API，把当前 `archive.js` / `manage.js` 的上传文件和资产写入改为服务端写入。
5. 把 `sampleItems` 导入 `images`、`image_assets` 和一个 `archive-featured` collection。
6. 把 Archive 页面读取切换到生产 `archive_image_view` 或同形状 API 返回值。
7. 再接真实 AI 视觉模型，替换当前 `classifyContent()` 的文件名关键词逻辑。
