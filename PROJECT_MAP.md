# Project Map

## 维护规则

- 每次新增、删除、移动或修改功能相关代码后，同步更新本文档。
- 按功能/页面归档文件职责，不只按目录罗列。
- 记录真实职责，不写愿景和过期计划。

## 全局结构

- `index.html`：首页入口；承载英文首页、statement、无限横向精选作品带、联系作者四个区域。
- `works.html`：作者作品档案页；承载上传入口、自动分类结果、类型/比例过滤器和横向图片墙。
- `styles.css`：全站视觉系统和响应式布局；定义色彩、字体、间距、按钮、导航、双层首页图片覆盖过渡、Infinite Marquee Gallery 和移动端规则。
- `script.js`：首页滚动过渡和锚点点击平滑滚动逻辑；不再维护作品分类或比例筛选状态。
- `archive.js`：作品档案页数据、上传读取尺寸、比例分类、抽象/具体分类、IndexedDB 本地存储、过滤和横向图片墙渲染逻辑。
- `README.md`：GitHub 项目首页说明；记录版本、功能、运行方式和当前静态前端状态。
- `CHANGELOG.md`：版本记录；当前第一版为 `v1.0.0`。
- `VERSION`：当前项目版本号。
- `.gitignore`：Git 忽略规则；排除临时源图、截图、本地缓存、本地 skill 目录和环境变量文件。
- `DATABASE_DESIGN.md`：作品档案数据库后期接入设计说明；当前暂缓启用，仅记录表职责、上传入库流程、前端字段映射、Archive 查询和权限建议。
- `database/schema.sql`：PostgreSQL/Supabase 兼容数据库预留 schema；当前不执行，项目完工后再用于创建作品、资产、比例分类、AI 分析记录、1:1 切片、标签和精选集合。
- `DESIGN_SYSTEM.md`：MT 此间的组件库选型、设计系统、排版规则、画廊增强方案和后续技术路线。
- `IMAGE_SOURCES.md`：记录当前临时图片素材来源、使用规则和替换要求。
- `assets/art/`：首页主视觉和作品图片资源目录；当前为 `gpt-image-2-all` 生成的临时 AI 视觉样张，正式上线前应替换为 MT 真实作品或确认授权可用的最终生成图。
- `assets/archive/`：作品档案页本地样例图目录；当前 25 张样例下载自 Picsum Photos，用于保证 `works.html` 不依赖运行时外链加载。
- `tmp/art-source/`：临时源图目录；由处理脚本读取，不直接被页面引用。
- `scripts/prepare_art_assets.py`：历史/备用本地处理脚本；读取 `tmp/art-source/` 下的源图，裁切、调色并输出到 `assets/art/`；当前页面不依赖该脚本生成的推荐比例逻辑。

## 1. 首页与品牌介绍

### 功能说明

- 展示 MT CIJIAN 的品牌名称、英文核心宣言、大幅摄影背景和两个主操作按钮。
- 页面入口：`index.html`
- 主要用户操作：点击 `Enter Works` 进入 `works.html` 作品档案页；点击 `Contact Artist` 打开邮件客户端。

### 相关文件

- `index.html`：定义 `hero`、`statement`、`contact` 区域的 HTML 结构和英文文案。
- `styles.css`：实现参考图式全屏摄影背景、右侧主标题、斜切下沿、按钮样式、移动端布局，以及下滑时彩色具象图覆盖黑白抽象图的纵向过渡。
- `script.js`：根据首屏滚动进度设置 hero 双图覆盖比例、缩放、文案上移淡出、遮罩淡化变量；拦截页内锚点点击并执行 ease-in-out 纵向滚动。
- `DESIGN_SYSTEM.md`：记录首页的视觉定位、字体、色彩、按钮和布局规则。
- `IMAGE_SOURCES.md`：记录首页主视觉当前素材来源和替换规则。
- `assets/art/hero-ci-jian.jpg`：首页主视觉临时样张。

### 页面内部结构

- 主视觉：`hero-stage` 提供 165vh 的 sticky 过渡舞台；`hero` 固定在视口顶部完成过渡。底层使用 `assets/art/hero-ci-jian.jpg` 黑白抽象风景，覆盖层使用 `assets/art/hero-concrete.jpg` 彩色具象风景。
- 品牌文案：英文标题 `A QUIET FIELD FOR IMAGES` 和短 statement。
- 按钮：`Enter Works` 链接到 `works.html`；`Contact Artist` 使用 `mailto:contact@mt-cijian.com`。
- 状态：纯静态内容，无远程加载状态；滚动进度控制 `--hero-cover-progress` 等 CSS 变量和 `body.is-scrolled` class。
- 测试：通过浏览器打开页面检查布局、锚点平滑滚动、下滑过渡和邮件链接。

## 2. 无限横向作品带

### 功能说明

- 作品区展示精选 AI 生成风景图，不再提供分类切换或比例筛选。
- 图片保持原始宽高比，统一行高，自然宽度展示。
- 横向作品带从右向左缓慢连续滚动，第二组重复图片负责无缝循环。
- 悬停作品带时暂停滚动；悬停单张图片时只做轻微放大和透明度过渡。

### 相关文件

- `index.html`：定义 `works` 区域和两组重复的 `.marquee-track` 图片序列。
- `styles.css`：实现 `.marquee-gallery`、`.marquee-track`、`.marquee-item`、`gallery-marquee` 动画、悬停暂停、图片自然比例、移动端高度和 `prefers-reduced-motion` 降级。
- `DESIGN_SYSTEM.md`：记录 Infinite Marquee Gallery 规则和不裁切摄影作品的约束。
- `IMAGE_SOURCES.md`：记录当前 AI 生成图片的模型、日期和临时用途。
- `assets/art/abstract-01.jpg`：AI 生成黑白风景图，1024x1536。
- `assets/art/abstract-02.jpg`：AI 生成黑白风景图，1024x1536。
- `assets/art/abstract-03.jpg`：AI 生成黑白风景竖图，1024x1536。
- `assets/art/hero-concrete.jpg`：AI 生成彩色具象首页覆盖图，1672x941。
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

- 作品档案页用于展示作者上传的图片和本地样例图片。
- 上传图片后，前端读取原始宽高并自动匹配最近的预定义比例分类。
- 档案卡片显示比例使用分类后的标准比例，而不是原始尺寸的细微偏差；例如 `800x850` 会按 `1:1` 展示，但 `Size` 仍显示原始 `800x850`。
- 如果上传图不是 `1:1`，前端会使用 canvas 按短边尺寸自动生成多个 `1:1` 方形切片并保存；档案页仍显示原图原始比例，不裁切原图。
- 内容类型分为 `Abstract` 与 `Concrete`。当前静态版本通过文件名关键词做前端启发式分类，并在 `archive.js` 的 `classifyContent()` 中保留未来接入视觉模型的替换点。
- 上传图的文件 blob、原始宽高、比例分类、抽象/具体分类、标题和 `1:1` 切片信息会保存到浏览器 IndexedDB；刷新页面后会恢复。数据库接入已暂缓，项目完工后再考虑把同一数据结构保存到服务端数据库。
- 抽象图片以黑白展示；具体图片以低饱和彩色展示。
- Gallery 提供 Type 与 Ratio 两组过滤器。
- `All` 模式使用协调的 masonry 图墙，让不同尺寸图片自然错落并保持整体平衡。选择具体比例后切换为比例专用网格，图片按当前比例组等宽缩放并铺满行宽，不裁切、不拉伸、不加黑边。

### 相关文件

- `works.html`：定义作品档案页 HTML、上传控件、过滤器和 gallery 挂载点。
- `archive.js`：定义本地样例数据、比例分类表、IndexedDB 存储、上传读取尺寸、非方图 `1:1` 切片、内容分类、过滤器状态和渲染函数。
- `styles.css`：定义档案页 header、上传区、sticky 过滤器、All 模式 masonry 图墙、比例筛选 grid 和移动端规则。
- `DATABASE_DESIGN.md`：定义项目完工后可能接入的服务端数据库模型和当前 IndexedDB 字段迁移关系。
- `database/schema.sql`：预留服务端作品档案表结构、索引和 `archive_image_view` 查询视图；当前不执行。
- `assets/archive/`：存放 25 张本地摄影样例图，覆盖 `1:1`、`4:5`、`2:3`、`3:2`、`16:9`、`Panorama`。

### 分类规则

- 比例分类：`1:1`、`4:5`、`2:3`、`3:2`、`16:9`、`Panorama`。
- 示例尺寸：`4000x4000` -> `1:1`；`4000x5000` -> `4:5`；`4000x6000` -> `2:3`；`6000x4000` -> `3:2`；`1600x900` -> `16:9`；`4000x2000` -> `Panorama`。
- 内容分类：`Abstract` 包含 textures、shadows、light patterns、geometry、minimal details；`Concrete` 包含 people、architecture、landscapes、animals、identifiable objects。

### 页面内部结构

- 上传：`input[type=file][multiple]` 支持多图上传，上传文件只在浏览器本地读取并写入 IndexedDB，不会上传到服务器。
- 自动切片：非 `1:1` 上传图通过 `createSquareSlices()` 生成方形切片；切片保存在 IndexedDB，页面展示仍使用原图 `src`。
- 过滤：`button[data-filter-type]` 和 `button[data-filter-ratio]` 控制当前列表。
- Gallery：`All` 模式下 `.archive-gallery` 使用 CSS columns/masonry，让不同尺寸图片协调排列。每个 `.archive-image-frame` 使用分类后的标准比例作为展示比例，图片在框内 `object-fit: contain`。比例筛选模式下 `.archive-gallery.is-ratio-filtered` 使用 CSS grid 填满行宽。
- 状态：当前过滤器状态保存在 `activeType` 与 `activeRatio`；上传图保存到 IndexedDB，渲染时恢复为 object URL。

## 4. 作品档案数据库预留

### 功能说明

- 数据库设计暂缓接入，当前只作为项目完工后的后期方案。
- 当前 `works.html` 继续使用本地样例图和浏览器 IndexedDB；不需要安装 MySQL，也不需要现在执行 SQL。
- 后期数据库可用于承接 `works.html` 的作者上传作品、比例分类、抽象/具体分类、黑白/彩色展示模式和 `1:1` 自动切片。
- 图片二进制文件不直接进入关系表；数据库只保存对象存储 bucket/path/url、尺寸、MIME、checksum 和分类元数据。
- 首页精选作品和未来专题作品通过 `collections` 与 `collection_images` 表管理，不再依赖硬编码图片列表。

### 相关文件

- `DATABASE_DESIGN.md`：说明后期数据库目标、表职责、上传入库流程、当前前端字段迁移关系、Archive 查询 SQL 和 Supabase 权限建议。
- `database/schema.sql`：预留 `ratio_categories`、`artists`、`images`、`image_assets`、`image_square_slices`、`image_analysis_events`、`image_tags`、`collections` 等表；包含索引、更新时间 trigger、比例匹配函数和 `archive_image_view`。
- `archive.js`：当前本地 IndexedDB 字段是数据库首版模型的来源；项目完工后如接 API，再把 `saveStoredItem()`、`getStoredItems()` 和 `sampleItems` 迁移到后端查询。

### 数据流

- 后期上传：读取真实宽高和 EXIF -> 上传原图到对象存储 -> 使用 `closest_ratio_category(width, height)` 匹配比例 -> 调用 AI 视觉分析得到 `abstract` 或 `concrete` -> 写入 `images` 和 `image_assets`。
- 后期展示：Archive 页面读取 `archive_image_view`；`original_width`/`original_height` 显示真实尺寸，`display_aspect_ratio` 用于前端展示比例。
- 后期切片：非 `1:1` 图片生成方形切片后，切片文件写入 `image_assets(kind = 'square_slice')`，切片位置和顺序写入 `image_square_slices`。
- 后期精选：首页 Selected Works 读取 `collections.slug = 'homepage-selected'` 对应的 `collection_images` 排序结果。

## 修改记录

- 2026-06-06：新增首版静态站点、作品分类切换和临时作品图。
- 2026-06-06：新增 `DESIGN_SYSTEM.md`，记录组件库选型、艺术站点排版 UI 规范和后续画廊增强方案。
- 2026-06-06：用 Pexels 临时摄影素材替换几何占位图；新增 `IMAGE_SOURCES.md` 和 `scripts/prepare_art_assets.py`。
- 2026-06-06：新增作品比例查看模式；作品图处理改为保留原始比例，避免破坏摄影构图。
- 2026-06-06：补充摄影可信度规则，排除纯纹理、AI 质感和无法解释拍摄对象的图片。
- 2026-06-06：按参考图方向重做首屏为英文全屏摄影 landing page，只保留 `Enter Works` 和 `Contact Artist` 两个主要入口。
- 2026-06-06：比例查看改为 `Auto` 默认模式，根据图片真实宽高自动匹配最佳展示比例。
- 2026-06-06：移除分类切换和比例筛选；作品区改为单排 Infinite Marquee Gallery，图片统一高度、自然宽度、无裁切、无黑边。
- 2026-06-06：用 `gpt-image-2-all` 生成首页主视觉和 6 张精选风景图，更新 `assets/art/metadata.json` 记录生成模型、日期和尺寸。
- 2026-06-06：新增首页到作品区的纵向滚动过渡；下滑时 hero 背景轻微缩放/降饱和，文案上移淡出，点击锚点使用自定义 easing。
- 2026-06-06：主页过渡改为 sticky 双层图片覆盖：黑白抽象风景作为底层，彩色具象横幅随下滑从下向上覆盖；降低白色遮罩强度；Selected Works 全部替换为竖向作品图。
- 2026-06-06：新增 `works.html` 智能作品档案页；支持上传图片后本地读取尺寸、按 `1:1`/`4:5`/`2:3`/`3:2`/`16:9`/`Panorama` 分类，按抽象/具体和比例过滤，并用横向图片墙保持原始比例展示。
- 2026-06-06：新增 `DATABASE_DESIGN.md` 和 `database/schema.sql`，完成作品档案数据库首版设计。
- 2026-06-07：合并 `PROJECT_MAP.md` 中分散的修改记录，改为文档末尾统一维护。
- 2026-06-07：确认数据库暂缓接入；当前项目继续使用静态资源和浏览器 IndexedDB，数据库文件仅作为项目完工后的预留方案。
- 2026-06-07：新增 `README.md`、`CHANGELOG.md`、`VERSION` 和 `.gitignore`，准备将当前项目提交为 GitHub 第一版 `v1.0.0`。
