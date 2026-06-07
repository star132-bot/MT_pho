# Database Design

## 当前状态

数据库暂缓接入。当前项目继续使用静态页面、本地图片资源和浏览器 IndexedDB；不要下载 MySQL，也不要在现在执行 `database/schema.sql`。这份文档只作为项目完工后接入 PostgreSQL/Supabase 的后期设计备忘。

## 目标

项目完工后，MT CIJIAN 的数据库可用于保存作者作品档案的服务端版本，替代当前 `archive.js` 中的浏览器 IndexedDB 本地存储。数据库只保存图片元数据、分类结果、对象存储路径和分析记录；真实图片文件应放在对象存储中，例如 Supabase Storage、S3 或自建文件服务。

核心要求：

- 保存图片真实原始尺寸，不能因为展示需要改写原始宽高。
- 上传后根据原始尺寸自动匹配最近的比例分类：`1:1`、`4:5`、`2:3`、`3:2`、`16:9`、`Panorama`。
- 展示比例使用分类后的标准比例，所以 `800x850` 会保存为原始 `800x850`，但展示时可按 `1:1` 显示。
- 抽象作品保存为 `abstract` 并使用 `black_white` 展示模式；具象作品保存为 `concrete` 并使用 `color` 展示模式。
- 非 `1:1` 上传图保留原图，同时记录自动生成的 `1:1` 切片。
- 支持 Archive 页面按 Type 和 Ratio 过滤，也支持首页精选作品集合。

## 文件

- `database/schema.sql`：PostgreSQL/Supabase 兼容 schema，包含表、枚举、索引、更新时间 trigger、比例分类函数和 Archive 视图。
- `archive.js`：当前前端本地模型来源；项目完工后再考虑把上传和读取逻辑改为调用 API。

## 数据表

### `ratio_categories`

比例分类字典表。这里不用前端文案直接做主键，而使用稳定 code：

| code | label | display ratio |
| --- | --- | --- |
| `one_to_one` | `1:1` | 1 / 1 |
| `four_to_five` | `4:5` | 4 / 5 |
| `two_to_three` | `2:3` | 2 / 3 |
| `three_to_two` | `3:2` | 3 / 2 |
| `sixteen_to_nine` | `16:9` | 16 / 9 |
| `panorama` | `Panorama` | 2 / 1 |

`closest_ratio_category(width, height)` 会根据真实宽高返回最接近的分类 code。

### `artists`

作者表。当前站点只有 MT CIJIAN 一个作者，但保留该表可以支持后续多作者或后台账号绑定。

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
- `mime_type`
- `byte_size`
- `width`
- `height`
- `checksum_sha256`

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

标签系统，后续可用于主题、地点、系列、材质、颜色等搜索。

### `collections` / `collection_images`

作品集合。首页 Selected Works 或未来专题都应该用集合表达，不要硬编码图片列表。

典型集合：

- `homepage-selected`
- `archive-featured`
- `black-white-landscape`

## 上传入库流程

1. 前端或后端读取图片真实尺寸、文件大小、MIME 类型和 EXIF。
2. 原图上传到对象存储，写入 `image_assets(kind = 'original')`。
3. 调用 `closest_ratio_category(width, height)` 得到 `ratio_category_code`。
4. 调用视觉模型分析图片内容，判断 `abstract` 或 `concrete`。
5. 根据内容类型设置展示模式：`abstract -> black_white`，`concrete -> color`。
6. 插入 `images` 主记录，保存原始尺寸、比例分类、AI 结果和可见性。
7. 如需要网页优化图或缩略图，写入 `image_assets(kind = 'display'/'thumbnail')`。
8. 如果图片不是 `1:1`，生成若干方形切片；每个切片写入 `image_assets(kind = 'square_slice')` 和 `image_square_slices`。
9. 写入一条 `image_analysis_events`，保留本次 AI 分析原始结果。

## 前端字段映射

当前 `archive.js` 的 IndexedDB 结构可以这样迁移：

| 当前字段 | 数据库位置 |
| --- | --- |
| `id` | `images.id` |
| `title` | `images.title` |
| `src` | `archive_image_view.image_url` |
| `width` | `images.original_width` |
| `height` | `images.original_height` |
| `ratio` | `ratio_categories.label` / `images.ratio_category_code` |
| `type` | `images.content_type` |
| `source` | `images.source_type` |
| `createdAt` | `images.created_at` 或 `images.uploaded_at` |
| `squareSliceCount` | `archive_image_view.square_slice_count` |
| `squareSlices` | `image_square_slices` + `image_assets(kind = 'square_slice')` |
| `blob` | 对象存储文件 + `image_assets(kind = 'original')` |

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

筛选 `4:5` 作品：

```sql
SELECT *
FROM public.archive_image_view
WHERE visibility = 'published'
  AND ratio_category_code = 'four_to_five'
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

建议后续服务端提供这些接口：

- `GET /api/images?type=abstract&ratio=four_to_five`
- `POST /api/images/upload-intent`
- `POST /api/images`
- `POST /api/images/:id/analyze`
- `GET /api/collections/homepage-selected`

前端不应该直接拼对象存储路径；应读取 `archive_image_view.image_url` 或 API 返回的签名 URL。

## 权限建议

如果使用 Supabase：

- 公开页面只能读取 `visibility = 'published'` 的图片和集合。
- 作者后台可以读取自己的 `draft/private/published` 图片。
- 上传、修改、删除只能由作者或管理员执行。
- 对象存储 bucket 建议拆成 `originals` 和 `public-display`，原图默认不公开，展示图可公开或走签名 URL。

## 后续接入顺序

以下步骤暂缓，等页面、作品展示、上传体验和后台需求稳定后再执行：

1. 先执行 `database/schema.sql` 创建表。
2. 建一个上传 API，把当前 `archive.js` 的本地 IndexedDB 写入改为服务端写入。
3. 把 `sampleItems` 导入 `images`、`image_assets` 和一个 `archive-featured` collection。
4. 把 Archive 页面读取改成 `archive_image_view` 或 API 返回值。
5. 再接真实 AI 视觉模型，替换当前 `classifyContent()` 的文件名关键词逻辑。
