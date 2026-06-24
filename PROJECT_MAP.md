# Project Map

## 维护规则

- 每次新增、删除、移动或修改功能相关代码后，同步更新本文档。
- 按功能/页面归档文件职责，不只按目录罗列。
- 记录真实职责，不写愿景和过期计划。

## 全局结构

- `index.html`：首页入口；承载英文首页、无限横向精选作品带、四段图文 Statement 序章、联系作者四个区域；`Contact Artist` 链接进入 `contact.html`；hero 和 Statement 的主图/文字可由内部管理页写入的首页设置覆盖。
- `works.html`：公开作品档案页；承载 SVG 功能图标、数据库加载状态、搜索输入、类型/比例过滤器、作品顺序排列控件、横向图片墙和作品放大鉴赏层；不再暴露 Add Works 上传入口；导航中的 `Contact` 链接进入 `contact.html`。
- `archive-data.js`：Works Archive 的共享基础数据；保存本地样例作品 ID、路径、尺寸、内容类型和比例分类，供 `archive.js` 与 `manage.js` 用同一 ID 合并人工 metadata。
- `archive-upload.js`：共享浏览器导入管线；读取上传图尺寸、checksum、基础 EXIF，生成 `original` / `display` / `thumbnail` / `square_slice` 资产记录，供内部管理页复用。
- `manage.html`：内部 Works 维护页；不加入公开导航，用于上传作品、维护作品放大鉴赏层右侧信息栏，以及编辑首页 hero/Statement 图片和文字。
- `contact.html`：联系作者独立页面；承载英文联系说明、黑白作品图视觉锚点和邮件草稿表单。
- `styles.css`：全站视觉系统和响应式布局；定义 neutral gallery palette 色彩 token、字体、间距、按钮、导航、SVG 图标、双层首页图片覆盖过渡、四段图文 Statement、Infinite Marquee Gallery、作品档案筛选/管理分组、作品放大鉴赏层、联系页和移动端规则。
- `script.js`：首页滚动过渡、IndexedDB 首页设置读取和应用、Statement 标题和每个图文 moment 的入场显影、锚点点击平滑滚动逻辑；不再维护作品分类或比例筛选状态。
- `contact.js`：联系作者页面表单逻辑；负责前端校验、生成 `mailto:` 邮件草稿、提交中状态和 toast 成功/失败反馈。
- `archive.js`：公开作品档案页逻辑；优先读取 `/api/archive/images` 本地 SQLite 只读接口，失败时回退本地样例和 IndexedDB 中 `published` 作品，合并 base/manual metadata，处理搜索、Type/Ratio 叠加过滤、作品放大鉴赏层、标签视图模型、作品顺序排列和横向图片墙渲染。
- `manage.js`：内部 Works 维护页逻辑；调用 `archive-upload.js` 导入作品；把 base data、manual metadata 和 database shape 分层归一化；维护 `images` 字段、`image_tags` / `image_taggings` 标签关系；保存已有 seed 作品时调用 `PATCH /api/archive/images/{id}` 同步 SQLite，上传新图片时调用 `POST /api/archive/images` 创建新记录并同步到 SQLite，同时保留 IndexedDB 作为浏览器 fallback；维护 Homepage hero 预览、dirty 状态、保存当前、保存全部、撤销、删除上传图和离开提示。
- `server.py`：Python 标准库本地开发服务器；提供静态文件服务、`GET /api/archive/images` 本地 SQLite Archive API、`POST /api/archive/images` 上传图片创建 API 和 `PATCH /api/archive/images/{id}` 既有作品 metadata/tag 写入 API，拒绝其它 `/api/` 和私有运行目录的直接访问。
- `README.md`：GitHub 项目首页说明；记录版本、功能、运行方式、静态浏览和联系页邮件草稿行为。
- `CHANGELOG.md`：版本记录；当前第一版为 `v1.0.0`，`Unreleased` 记录联系作者功能。
- `VERSION`：当前项目版本号。
- `.gitignore`：Git 忽略规则；排除临时源图、截图、本地缓存、本地 skill 目录、环境变量文件和本地运行产物。
- `project-development-guardrails/SKILL.md`：本地企业级项目开发护栏 skill；定义开发前读代码、文档闭环、垂直切片、验收、验证和自审规则。
- `DATABASE_DESIGN.md`：后期数据库接入设计说明；记录作品档案表、上传入库流程、前端字段映射、Archive 查询、权限建议，以及本地 SQLite 作品库验证流程。
- `database/schema.sql`：PostgreSQL/Supabase 兼容数据库预留 schema；当前不作为本地运行库，项目完工后再用于创建作品、资产、比例分类、AI 分析记录、1:1 切片、标签和精选集合。
- `database/local_archive_schema.sql`：SQLite 本地作品档案验证 schema；对齐目标作品表、资产表、标签表、集合表和 `archive_image_view`，用于在接后端前校验图片 metadata 与标签关系。
- `scripts/validate_local_archive_db.py`：本地 SQLite 作品库验收脚本；创建临时数据库，运行 seed，并检查 schema、外键、核心数据量、多版本资产、Archive view、标签 JSON、比例分类和本地图片路径。
- `.github/workflows/database.yml`：数据库检查 GitHub Actions workflow；在 PR、`main`/`master` push 和手动触发时运行本地数据库验收脚本。
- `DESIGN_SYSTEM.md`：MT Presence 的组件库选型、设计系统、排版规则、画廊增强方案和后续技术路线。
- `IMAGE_SOURCES.md`：记录当前临时图片素材来源、使用规则和替换要求。
- `assets/art/`：首页主视觉和作品图片资源目录；当前为 `gpt-image-2-all` 生成的临时 AI 视觉样张，正式上线前应替换为 MT 真实作品或确认授权可用的最终生成图。
- `assets/archive/`：作品档案页本地样例图目录；当前 27 张样例下载自 Picsum Photos，用于保证 `works.html` 不依赖运行时外链加载。
- `data/.gitkeep`：保留本地数据目录；`data/*.db` 为本地运行产物并由 `.gitignore` 忽略，当前支持生成 `data/archive.db`，联系作者不再生成消息数据库。
- `tmp/art-source/`：临时源图目录；由处理脚本读取，不直接被页面引用。
- `scripts/prepare_art_assets.py`：历史/备用本地处理脚本；读取 `tmp/art-source/` 下的源图，裁切、调色并输出到 `assets/art/`；当前页面不依赖该脚本生成的推荐比例逻辑。
- `scripts/seed_local_archive_db.py`：本地 SQLite 作品库 seed 脚本；通过 Node VM 读取 `archive-data.js`，生成 `data/archive.db`，写入 27 张本地 sample 图片、`original/display/thumbnail` 资产、派生标签、`image_taggings`、`archive-featured` collection 和 seed analysis 记录。

## 1. 首页与品牌介绍

### 功能说明

- 展示 MT Presence 的品牌名称、英文核心宣言、大幅摄影背景、Selected Works 作品带、四段图文 Statement 序章和两个主操作按钮。
- 页面入口：`index.html`
- 主要用户操作：点击 `Enter Works` 进入 `works.html` 作品档案页；点击 `Contact Artist` 进入 `contact.html` 联系页。

### 相关文件

- `index.html`：定义 `hero`、`works`、`statement`、`contact` 区域的 HTML 结构和默认英文文案；hero 内含抽象/具象两套带 `data-home-hero-*` 钩子的文案层，随图片转场交替；`Works / Selected Works` 位于 Statement 前；Statement 使用四个带 `data-home-statement-*` 钩子的 `statement-moment`，每段一张图、一段文案和编号，最后保留 `Enter Works` CTA。
- `styles.css`：实现参考图式全屏摄影背景、右侧主标题、斜切下沿、按钮样式、Selected Works 作品带、Statement 四段图文交错布局和移动端布局；hero 使用短 pinned 双层图片过渡，桌面约 `150vh`、移动端约 `140vh`。
- `script.js`：启动时读取 IndexedDB `site_settings.homepage`，用 `--home-hero-abstract-image` / `--home-hero-concrete-image` CSS 变量和 `data-home-*` DOM 钩子覆盖首页 hero/Statement 图片与文字；根据首屏滚动进度设置 `--hero-concrete-opacity` 和 hero 文案区的位移、透明度、墨色、阴影变量，让抽象到具象的图片与两套标题/说明同步分段淡出/淡入，并在 hero-stage 接近释放时切换导航栏滚动状态；用 IntersectionObserver 触发 Statement 标题和每个 `statement-moment` 的入场显影；拦截页内锚点点击并扣除 header 高度后执行 ease-in-out 纵向滚动。
- `DESIGN_SYSTEM.md`：记录首页的视觉定位、字体、色彩、按钮和布局规则。
- `IMAGE_SOURCES.md`：记录首页主视觉当前素材来源和替换规则。
- `assets/art/hero-ci-jian.jpg`：首页主视觉临时样张。

### 页面内部结构

- 主视觉：`hero-stage` 桌面高度约 `150vh`、移动端约 `140vh`，`hero` sticky 固定首屏；前约 62% pinned 滚动进度把 `assets/art/hero-ci-jian.jpg` 黑白抽象风景平滑切到 `assets/art/hero-concrete.jpg` 具体彩色风景，抽象文案和具象文案同步分段淡出/淡入、轻微上移、增强墨色并收敛浅色 glow，避免两套大标题叠字；切换完成后尽快释放到 Selected Works；按钮不随滚动替换。
- 品牌文案：默认抽象阶段为 `Abstract Field`、`A Quiet Field for Images` 和 `Images are not records of the world...`；默认具象阶段为 `Concrete Field`、`Where Looking Becomes Presence` 和 `Light, weather, and distance settle into form...`；内部 `manage.html` 可覆盖两阶段图片、eyebrow、标题和说明。
- Works：`#works` 在 Statement 前展示 `Works / Selected Works` 标题和 Infinite Marquee Gallery，为后续 Statement 留出视觉加载空间。
- Statement：`#statement` 使用 `.statement-intro` 标题和 `.statement-moments` 四段图文；每个 `.statement-moment` 包含 `.statement-media`、`.statement-moment-copy`、`.statement-index` 和一段文案，最终 `.statement-cta` 链接到 `works.html`；内部 `manage.html` 可覆盖 Statement 标题、四段图片和四段文字。
- 按钮：`Enter Works` 链接到 `works.html`；`Contact Artist` 链接到 `contact.html`。
- 状态：IndexedDB `site_settings.homepage` 是当前首页手工配置过渡层，未来可迁移到页面设置表和 `collections.slug = 'homepage-selected'`；滚动进度控制 `--hero-concrete-opacity`、`--hero-copy-shift`、`--hero-copy-abstract-opacity`、`--hero-copy-concrete-opacity`、`--hero-copy-abstract-panel-shift`、`--hero-copy-concrete-panel-shift`、`--hero-title-alpha`、`--hero-statement-alpha`、`--hero-copy-shadow-alpha` 和 `--hero-copy-shadow-blur`；`body.is-scrolled` 等 hero-stage 底部接近视口释放点后才触发导航换肤；Statement 由 `data-statement-section`、`data-statement-moment`、`.is-animating` 和 `.is-visible` 控制标题、CTA 和每段图文入场显影。
- 响应式：桌面 Statement 使用图文两栏交错排列；移动端图片和文字改为普通流布局，所有段落直接可读；`prefers-reduced-motion` 下关闭 Statement 过渡并直接显示内容。
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
- `DESIGN_SYSTEM.md`：记录 Infinite Marquee Gallery 规则和不裁切摄影作品的约束。
- `IMAGE_SOURCES.md`：记录当前 AI 生成图片的模型、日期和临时用途。
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
- 上传入口已迁移到内部 `manage.html`，公开 `works.html` 不再显示 Add Works。
- 档案卡片显示比例使用分类后的标准比例，而不是原始尺寸的细微偏差；例如 `800x850` 会按 `1:1` 展示，但 `Size` 仍显示原始 `800x850`。
- 如果上传图不是 `1:1`，前端会使用 canvas 按短边尺寸自动生成多个 `1:1` 方形切片，切片输出限制到约 1400px 并记录原图 source 坐标；档案页仍按原始比例分类展示，不裁切原图。
- 内容类型分为 `Abstract` 与 `Concrete`。当前静态版本通过文件名关键词做前端启发式分类，并在 `archive.js` 的 `classifyContent()` 中保留未来接入视觉模型的替换点。
- 内部上传图会在浏览器中生成多版本资产：`original` 原图完整保留，`display` 用于前台画廊展示，`thumbnail` 用于未来列表/后台，非方图额外生成 `square_slice`；原始宽高、checksum、基础 EXIF、比例分类、抽象/具体分类、标题、`assets[]` 和 `squareSlices[]` 会保存到 IndexedDB。数据库接入已暂缓，项目完工后再把同一数据结构迁移到对象存储 + `images` / `image_assets` / `image_square_slices`。
- 抽象图片以黑白展示；具体图片以低饱和彩色展示。
- Gallery 提供 Search、Type 与 Ratio 三组叠加过滤器。
- Gallery 提供 Arrange 模式，可通过拖拽或上/下移动图标按钮调整当前视图中的作品顺序，并保存到本地。
- 点击普通浏览模式下的作品卡片会打开作品放大鉴赏层；鉴赏层优先展示 `display` 版本图片，右侧或下方展示标题、策展说明、Type/Ratio/Size/Captured/Display metadata、系列信息和轻量分组标签。
- `All` 模式使用协调的 masonry 图墙，让不同尺寸图片自然错落并保持整体平衡。选择具体比例后切换为比例专用网格，图片按当前比例组等宽缩放并铺满行宽，不裁切、不拉伸、不加黑边。

### 相关文件

- `works.html`：定义公开作品档案页 HTML、单色细线 SVG symbol、`archive-filter-bar` 浏览筛选区、带 label 的 Works 搜索输入和 Clear Search 按钮、`archive-toolbar` Count/Arrange 管理区、gallery 挂载点、搜索空态和 `role="dialog"` 的作品放大鉴赏层骨架。
- `archive-data.js`：定义本地样例作品基础数据，`archive.js` 启动时按同 ID 合并 IndexedDB 中保存的 manual metadata。
- `archive-upload.js`：定义上传读取尺寸/EXIF/checksum、`original`/`display`/`thumbnail`/`square_slice` 资产生成、非方图 `1:1` 切片和内容分类，供内部 `manage.js` 调用。
- `archive.js`：定义比例分类表、IndexedDB 读取、仅 published 记录过滤、搜索文本归一化、比例关键词匹配、过滤器状态、作品详情视图模型、标签分组归一化、dialog 打开/关闭/上一张/下一张/焦点恢复、排列状态、顺序保存、图标按钮渲染和 gallery 渲染函数。
- `styles.css`：定义中性 gallery palette、档案页 header、搜索/Type/Ratio 筛选索引、Count/Arrange 管理区、图标按钮、Arrange 编辑态卡片、All 模式 masonry 图墙、比例筛选 grid、作品放大鉴赏层两栏/移动端上下布局、标签可视化、内部管理台和移动端规则。
- `DATABASE_DESIGN.md`：定义项目完工后可能接入的服务端数据库模型和当前 IndexedDB 字段迁移关系。
- `database/schema.sql`：预留服务端作品档案表结构、索引和 `archive_image_view` 查询视图；当前不执行。
- `assets/archive/`：存放 27 张本地摄影样例图，覆盖 `1:1`、`4:3`、`4:5`、`2:3`、`3:2`、`16:9`、`Panorama`。

### 分类规则

- 比例分类：`1:1`、`4:3`、`4:5`、`2:3`、`3:2`、`16:9`、`Panorama`。
- 示例尺寸：`4000x4000` -> `1:1`；`4000x3000` -> `4:3`；`4000x5000` -> `4:5`；`4000x6000` -> `2:3`；`6000x4000` -> `3:2`；`1600x900` -> `16:9`；`4000x2000` -> `Panorama`。
- 内容分类：`Abstract` 包含 textures、shadows、light patterns、geometry、minimal details；`Concrete` 包含 people、architecture、landscapes、animals、identifiable objects。

### 页面内部结构

- 上传：`input[type=file][multiple]` 支持多图上传，每张图独立显示读取、压缩、切片、分析、保存、完成或失败状态；当前只在浏览器本地生成资产并写入 IndexedDB，不会上传到服务器。
- 多版本资产：`original` 不压缩并保存原始尺寸/MIME/byte size/checksum/EXIF；`display` 最长边约 2300px、质量约 0.86，用于画廊展示；`thumbnail` 最长边约 640px、质量约 0.78，用于未来后台列表；所有资产使用 `storage_bucket`、`storage_path`、`mime_type`、`byte_size`、`width`、`height`、`checksum_sha256` 字段对齐 `image_assets`。
- 自动切片：非 `1:1` 上传图通过 `createSquareSlices()` 生成方形切片，输出边长限制约 1400px；切片文件作为 `image_assets(kind = 'square_slice')` 保存，`source_x`、`source_y`、`source_size` 和顺序保存在 `squareSlices[]`，对齐 `image_square_slices`。
- 过滤：`archive-filter-bar` 内的 `input[data-archive-search]`、`button[data-filter-type]` 和 `button[data-filter-ratio]` 控制当前列表；搜索匹配 title、series、description、curatorial note、artist statement、tags、tag groups、content type、ratio label/code、source/original filename，并支持 `1:1`、`4:3`、`4:5`、`2:3`、`3:2`、`16:9`、`panorama`、`vertical`、`horizontal` 等比例关键词；搜索、Type、Ratio 可同时生效，Count 使用 `aria-live` 更新，空结果显示 `No works match this search.`。
- 排列：`archive-toolbar` 内的 `button[data-arrange-toggle]` 进入排列模式；卡片可拖拽，也可用图标按钮 `button[data-move-offset]` 按当前筛选视图上移/下移；`button[data-save-order]` 保存顺序；`button[data-arrange-done]` 退出排列模式。
- Gallery：`All` 模式下 `.archive-gallery` 使用 CSS columns/masonry，让不同尺寸图片协调排列。每个 `.archive-image-frame` 使用分类后的标准比例作为展示比例，图片在框内 `object-fit: contain`；上传图优先使用 `display` asset 的 object URL，没有 `display` 时 fallback 到 `original`；默认作品图片无圆角，Arrange 模式才给卡片 4px 细边框和图片 2px 圆角提示编辑态。比例筛选模式下 `.archive-gallery.is-ratio-filtered` 使用 CSS grid 填满行宽。
- 作品鉴赏层：`[data-work-viewer]` 包含遮罩、`role="dialog"` 的全屏 `.work-viewer-dialog`、大图区域和右侧信息区；普通模式下点击卡片或按 Enter/Space 打开，Esc、遮罩和关闭按钮关闭，左右按钮或 ArrowLeft/ArrowRight 按当前筛选顺序切换。缩放按钮和图片点击可在 Fit 与 Actual size 之间切换，Actual size 下图片区域独立滚动。打开时锁定页面滚动并把焦点移入 dialog，关闭后恢复滚动位置和触发卡片焦点。Arrange 模式下点击卡片不会打开鉴赏层。
- 标签可视化：`normalizeWorkDetail()` 优先读取 `title`、`description`、`curatorial_note`、`artist_statement`、`content_type`、`ratio_label`、`original_width`、`original_height`、`captured_at`、`series`、`tags[]`、`tag_groups[]`、`image_url`、`thumbnail_url`、`display_mode`；没有标签数据时按作品标题、类型、比例和 display mode 派生 Subject、Place、Form / Ratio、Mood、Material / Surface、Palette / Tone、Series / Collection 等轻量分组，主体标签覆盖 Landscape、House / Building、Architecture、Animal、Object、Coast / Water、Mountain / Valley、Stone、Surface / Pattern 等内容类别。
- 联系：导航 `Contact` 链接到 `contact.html`。
- 状态：当前过滤器状态保存在 `activeSearch`、`activeType` 与 `activeRatio`；鉴赏层状态保存在 `viewerCurrentId`、`viewerTriggerElement`、`viewerScrollY`；排列状态保存在 `isArrangeMode`、`hasOrderChanges` 和 `sortOrder`；上传任务状态保存在 `uploadTasks` 并渲染到 `[data-upload-status-list]`；已保存顺序写入 `localStorage`，上传图的 `sortOrder` 同步到 IndexedDB；上传图保存到 IndexedDB，渲染时恢复 display/original object URL。

## 4. 内部 Works Viewer 编辑页

### 功能说明

- 内部作者维护页面，用于导入作品、编辑 `works.html` 点击图片后放大鉴赏层右侧 `.work-viewer-info` 显示的数据，并维护首页 hero/Statement 图片和文字。
- 入口：`manage.html`，不加入公开导航。
- 编辑字段对齐数据库目标结构：`images.title`、`images.series`、`images.curatorial_note`、`images.description`、`images.artist_statement`、`images.captured_at`、`images.content_type`、`images.display_mode`、`images.visibility`、`images.sort_order`，以及 `image_tags` / `image_taggings` 标签关系。
- 保存已有 seed 作品时，`manage.js` 会同步写入本地 SQLite 的 `images`、`image_tags` 和 `image_taggings`，同时保留 IndexedDB 作为浏览器 fallback；上传图、图片资产二进制和首页设置仍写入 IndexedDB 过渡层。公开 `works.html` 优先通过 `/api/archive/images` 读取 SQLite 结果，接口不可用时再按作品 ID 合并 IndexedDB manual metadata；`script.js` 启动时读取 `site_settings.homepage` 覆盖首页图文。

### 相关文件

- `manage.html`：定义 Add Works 导入区、常驻首页 hero/Statement 编辑台、Abstract/Concrete Hero 图片预览、保存状态栏、左侧 Works 列表、右侧 Viewer 信息编辑表单、保存当前、保存全部、撤销、删除内容和删除上传图确认弹窗。
- `archive-upload.js`：内部导入区调用的共享上传管线，输出可迁移到 `images` / `image_assets` / `image_square_slices` 的本地对象。
- `manage.js`：读取共享 `archive-data.js` base data 和 IndexedDB 存储；归一化 base data、manual metadata、database shape；生成 `image_tags` 与 `image_taggings`；保存已有 seed 作品时调用 `PATCH /api/archive/images/{id}` 同步 SQLite metadata/tag 关系；处理 Add Works 导入、homepage settings 表单同步、Hero 图片预览、保存/撤销、dirty 状态、保存、批量保存、刷新、离开提示和标签键盘编辑。
- `archive-data.js`：提供稳定 sample ID，保证管理页保存的 metadata 能被 `works.html` 同 ID 回读。
- `archive.js`：公开 Works 页面优先读取 `/api/archive/images` 的 SQLite published 记录；接口失败时读取 IndexedDB 保存记录，把 sample manual metadata 合并到本地样例，只把 `published` 上传图复活到 Archive 列表；兼容旧自动 `draft` 上传并按未人工设置 visibility 的 published 记录读取；Viewer 继续通过 `normalizeWorkDetail()` 和 `renderWorkViewer()` 渲染。
- `styles.css`：复用全站中性 gallery palette，为内部作者工作台、Homepage 预览编辑器、保存状态、dirty 状态、表单、列表和移动端布局提供规则。

### 页面内部结构

- 左侧列表：显示全部本地样例作品和上传作品；列表项显示缩略图、Type、Ratio、Size、Visibility/Content 状态，dirty 项显示 Unsaved。
- Add Works：内部导入区接受多图上传，生成 `original`、`display`、`thumbnail`、必要的 `square_slice`，默认 `visibility = published`，保存后可立即在公开 Works 页检查；作者手动改为 `draft`、`private` 或 `archived` 后公开页隐藏。
- Homepage：常驻编辑台维护抽象/具象 hero 的图片、eyebrow、标题和说明，以及 Statement 标题、四张图和四段文案；每个 hero 区域显示当前图片预览和 Image selector；保存到 IndexedDB `site_settings.homepage`，内部记录 `database_shape.collections = ['homepage-selected']` 和 `collection_images` 风格的 image/role/sort_order 映射，方便未来迁移。
- 右侧表单：字段顺序贴近 Viewer 显示顺序，依次为 Series、Title、Curatorial Note、Description、Metadata、Tag Groups、Artist Statement、Visibility。
- Metadata：`Captured`、`Content Type`、`Display Mode`、`Sort Order` 可编辑；原始尺寸、比例、图片路径、`image_assets` 和 square slice 数据只展示，不在表单中随意修改。
- Tag Groups：表单固定显示 Subject、Place、Form / Ratio、Mood、Material / Surface、Palette / Tone、Series / Collection 七组；默认值与 Works Viewer / SQLite seed 共用同一套派生规则，用户可用逗号或换行编辑标签；保存时写成 `imageRecord.tag_groups`、扁平 `tags`、`image_tags` 与 `image_taggings` 结构，已有 seed 作品同步写入 SQLite `image_tags` / `image_taggings`，上传图继续保存到 IndexedDB。
- 状态：`dirtyRecordIds` 记录未保存作品，`isHomeDirty` 记录未保存首页设置；保存栏显示 Saved、Unsaved changes、Last saved time、Save Current、Save All 和 Revert；切换作品前把当前表单同步到内存并在存在未保存修改时提示；刷新或离开页面前提示未保存修改；保存成功/失败用 toast 和 inline 状态反馈；SQLite 不可用时已有 seed 作品仍可保存到 IndexedDB fallback。
- 删除：`Delete Content Data` 清空 manual metadata，并把标签重置为默认派生标签，保留图片资产；`Delete Image Record` 只对上传图启用，本地样例图作为 base data 不允许删除。
- 测试：编辑已有 seed 作品保存后，`PATCH /api/archive/images/{id}` 返回更新后的 SQLite 视图数据；刷新 `works.html` 点击同一作品，Viewer 右侧信息显示更新后的标题、说明、metadata、标签分组和 statement；上传图保存后仍可在 IndexedDB fallback 中刷新恢复；在 manage 页保存首页 hero/Statement 设置后刷新 `index.html`，对应图片和文字显示更新内容。

## 5. 联系作者

### 功能说明

- 首页首屏、首页联系段和作品档案页导航都提供 `Contact Artist` / `Contact` 入口，并跳转到 `contact.html`。
- `contact.html` 是独立联系页，首屏直接显示说明、黑白作品图视觉锚点和表单。
- 表单字段：Name 可选，Email 必填，Subject 可选，Note 必填。
- 提交后调用浏览器 `mailto:` 打开给作者邮箱的邮件草稿；成功或失败用 toast 提示，页面不刷新。
- 站点不保存访客联系内容，不提供本地消息中心、回复后台或 `/api/messages`。

### 相关文件

- `index.html`：首页 hero 和联系段的 `Contact Artist` 链接入口。
- `works.html`：档案页导航的 `Contact` 链接入口。
- `contact.html`：联系作者页面结构，包含说明、视觉图和表单。
- `contact.js`：表单校验、`mailto:` 邮件草稿生成和 toast 反馈。
- `server.py`：静态服务器；拒绝 `/api/` 和 `/data/` 等私有路径。
- `styles.css`：联系页、表单、toast 和响应式规则。
- `DATABASE_DESIGN.md`：记录联系作者不入库的当前边界，数据库设计仅保留作品档案相关结构。

### 页面内部结构

- 联系页：`contact.html` 左侧说明和黑白作品图，右侧 `.contact-page-form` 表单。
- 表单：`sender_name`、`sender_email`、`subject`、`message`；页面标签显示为 Note，`contact.js` 前端校验邮箱格式和必填字段。
- Toast：`[data-contact-toast]` 使用 `role="status"` 和 `aria-live="polite"`，成功/失败共享同一个容器。
- 邮件草稿：`contact.js` 使用固定作者邮箱生成 `mailto:` URL，把访客邮箱和 Note 放入邮件正文。
- API：无联系表单 API；`server.py` 对 `/api/` 返回 404 JSON。
- 安全边界：站点不保存访客联系内容；`/data/` 路径不提供静态访问。
- 测试：启动 `python3 server.py --port 8131` 后测试 Contact 表单校验、邮件草稿跳转和 toast。

## 6. 作品档案数据库预留

### 功能说明

- 作品档案生产数据库设计暂缓接入；当前只把本地 SQLite 作为开发验证和既有 seed metadata/tag 写入层。
- 当前 `works.html` 优先读取 `server.py` 的本地 SQLite API；当 `data/archive.db` 不存在、API 失败或无 published 数据时，继续使用本地样例图和浏览器 IndexedDB fallback；不需要安装 MySQL，也不需要现在执行 PostgreSQL 目标 schema。
- 当前 `manage.html` 保存已有 seed 作品时会同步写入 `data/archive.db` 的 `images`、`image_tags` 和 `image_taggings`；上传图片、图片资产二进制和首页设置仍保存在 IndexedDB 过渡层。
- 本地开发可执行 `python3 scripts/seed_local_archive_db.py` 生成 `data/archive.db`，用于验证图片 metadata、资产表、标签分组、图-标签关联和 collection 设计。
- 后期数据库可用于承接 `works.html` 的作者上传作品、比例分类、抽象/具体分类、黑白/彩色展示模式、作品鉴赏层 metadata、标签分组和 `1:1` 自动切片。
- 图片二进制文件不直接进入关系表；数据库只保存对象存储 bucket/path/url、尺寸、MIME、checksum 和分类元数据。
- 首页精选作品和未来专题作品通过 `collections` 与 `collection_images` 表管理，不再依赖硬编码图片列表。

### 相关文件

- `DATABASE_DESIGN.md`：说明后期数据库目标、表职责、上传入库流程、当前前端字段迁移关系、Archive 查询 SQL 和 Supabase 权限建议。
- `database/schema.sql`：预留 `ratio_categories`、`artists`、`images`、`image_assets`、`image_square_slices`、`image_analysis_events`、带 `group_name` 的 `image_tags`、`collections` 等表；包含索引、更新时间 trigger、比例匹配函数和优先 display/fallback original 的 `archive_image_view`，该视图同时输出鉴赏层需要的 `tags` / `tag_groups`。
- `database/local_archive_schema.sql`：SQLite 本地验证 schema；用 `TEXT` 主键和 SQLite 约束/索引/View 表达同一套核心关系，包含 `archive_image_view` 输出 `image_url`、`thumbnail_url`、`tags` 和 `tag_groups`。
- `scripts/seed_local_archive_db.py`：从 `archive-data.js` 读取本地样例，生成 `data/archive.db`；写入 27 条 `images`、81 条 `image_assets`、48 个派生 `image_tags`、278 条 `image_taggings`、`archive-featured` collection 和 27 条 seed analysis 记录。
- `scripts/validate_local_archive_db.py`：本地/CI 共用验收命令；默认创建临时 SQLite 库，调用 seed 脚本后验证 integrity、foreign key、核心表/视图、published 数量、三类资产、URL fallback、标签 JSON、比例 code 覆盖和资源路径存在性。
- `.github/workflows/database.yml`：数据库验收 workflow；安装 Python 3.11 和 Node 20 后执行 `python3 scripts/validate_local_archive_db.py`，覆盖 PR、`main`/`master` push 和手动触发。
- `data/archive.db`：脚本生成的本地 SQLite 作品库；被 `.gitignore` 忽略，不作为源码提交。
- `server.py`：`GET /api/archive/images` 从 `archive_image_view` 读取 published 作品，支持 `type`、`ratio` 和 `limit`，并在数据库缺失时返回可恢复的 503 JSON；`PATCH /api/archive/images/{id}` 更新既有 `images` metadata 并替换该图片的 `image_taggings`。
- `archive.js`：公开 Works 的只读连接层；把 API 行归一化成现有 gallery/viewer item 形状，保留本地 sample/IndexedDB fallback；项目完工后如接生产 API，再把 `saveStoredItem()`、`getStoredItems()` 和上传资产写入迁移到后端。
- `works.html`：新增 `data-archive-data-status` 状态文本，展示数据库加载、只读 API 成功或 fallback 提示。

### 数据流

- 本地 seed：`archive-data.js.sampleItems` -> `scripts/seed_local_archive_db.py` -> `database/local_archive_schema.sql` -> `data/archive.db`；标签按 Subject、Place、Form / Ratio、Mood、Material / Surface、Palette / Tone、Series / Collection 七组确定性派生。
- 本地验收：`python3 scripts/validate_local_archive_db.py` -> 临时 SQLite 库 -> seed -> integrity/foreign key/schema/view/count/assets/tag JSON/ratio/path 检查；CI 通过 `.github/workflows/database.yml` 跑同一命令。
- 本地只读连接：浏览器打开 `works.html` -> `archive.js` 请求 `/api/archive/images` -> `server.py` 查询 `data/archive.db.archive_image_view` 的 published 记录 -> 前端映射为现有 gallery/viewer item；接口失败时显示 fallback 状态并继续使用本地 sample/IndexedDB。
- 本地 metadata 写入连接：作者在 `manage.html` 编辑已有 seed 作品 -> `manage.js` 调用 `PATCH /api/archive/images/{id}` -> `server.py` 事务更新 `images` 并替换 `image_taggings` -> `works.html` 下次读取 API 时显示新的标题、说明、visibility、sort order 和 tag groups；同一保存仍写 IndexedDB 作为浏览器 fallback。
- 后期上传：读取真实宽高、EXIF、MIME、byte size、checksum -> 上传原图到对象存储 -> 使用 `closest_ratio_category(width, height)` 匹配比例 -> 调用 AI 视觉分析得到 `abstract` 或 `concrete` -> 写入 `images` 主记录和 `image_assets(kind = 'original')`。
- 后期多版本资产：生成 `display` 和 `thumbnail`，写入 `image_assets(kind = 'display'/'thumbnail', source_asset_id = original_asset.id)`；非 `1:1` 图片生成方形切片后，切片文件写入 `image_assets(kind = 'square_slice')`，切片位置和顺序写入 `image_square_slices`。
- 后期展示：Archive 页面读取 `archive_image_view.image_url`，优先 display URL、缺失时 fallback original URL；用 `display_aspect_ratio` 控制前端比例框，继续保持原图不裁切；作品鉴赏层读取同一视图的 `curatorial_note`、`artist_statement`、`series`、`tags` 和 `tag_groups`。
- 后期精选：首页 Selected Works 读取 `collections.slug = 'homepage-selected'` 对应的 `collection_images` 排序结果。

## 7. 本地企业级开发护栏 Skill

### 功能说明

- 定义本项目使用的企业级开发原则，约束 Codex 在规划、开发、重构、测试和验收时先读代码、明确边界、复用现有体系、拆垂直切片并完成验证。
- 入口：`project-development-guardrails/SKILL.md`
- 主要用途：在后续项目开发时强制维护 `README.md`、`PROJECT_MAP.md`、`DESIGN_SYSTEM.md` 三份核心文档闭环；其中修改记录统一写入 `PROJECT_MAP.md`。

### 相关文件

- `project-development-guardrails/SKILL.md`：本地 skill 主文档；包含硬性护栏、工作流、企业级项目文档契约、功能地图规则、验收标准、验证清单和输出格式。
- `README.md`：由 skill 要求维护项目版本、运行方式、功能清单和项目文件说明。
- `PROJECT_MAP.md`：由 skill 要求维护项目功能地图和唯一修改记录。
- `DESIGN_SYSTEM.md`：由 skill 要求维护布局设计、组件规则、视觉系统、响应式和动效约束。

### 文档内部结构

- 企业级项目文档契约：规定 `README.md`、`PROJECT_MAP.md`、`DESIGN_SYSTEM.md` 的用途、更新时机和推荐提示词。
- 开发工作流：从任务大小判断、上下文建立、约束确认、垂直切片、验收标准到实现、验证和自审。
- 验证：要求检查 lint/typecheck/test/build 或项目等价验证，并检查三份核心文档是否与真实代码一致。

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
- 2026-06-14：重设 `styles.css` 全站配色为 neutral gallery palette，去除旧纸黄/奶油黄背景；同步更新 `DESIGN_SYSTEM.md` 色彩规则。
- 2026-06-06：新增首页到作品区的纵向滚动过渡；下滑时 hero 背景轻微缩放/降饱和，文案上移淡出，点击锚点使用自定义 easing。
- 2026-06-06：主页过渡改为 sticky 双层图片覆盖：黑白抽象风景作为底层，彩色具象横幅随下滑从下向上覆盖；降低白色遮罩强度；Selected Works 全部替换为竖向作品图。
- 2026-06-06：新增 `works.html` 智能作品档案页；支持上传图片后本地读取尺寸、按 `1:1`/`4:5`/`2:3`/`3:2`/`16:9`/`Panorama` 分类，按抽象/具体和比例过滤，并用横向图片墙保持原始比例展示。
- 2026-06-06：新增 `DATABASE_DESIGN.md` 和 `database/schema.sql`，完成作品档案数据库首版设计。
- 2026-06-07：合并 `PROJECT_MAP.md` 中分散的修改记录，改为文档末尾统一维护。
- 2026-06-07：确认数据库暂缓接入；当前项目继续使用静态资源和浏览器 IndexedDB，数据库文件仅作为项目完工后的预留方案。
- 2026-06-07：新增 `README.md`、`CHANGELOG.md`、`VERSION` 和 `.gitignore`，准备将当前项目提交为 GitHub 第一版 `v1.0.0`。
- 2026-06-14：移除本地 Messages 页面、`/api/messages`、SQLite 消息存储、SMTP 示例配置和正式数据库消息表预留；Contact 页面改为打开邮件草稿。
- 2026-06-07：新增联系作者独立页面。
- 2026-06-07：Works Archive 新增 Arrange 模式，支持拖拽、移动按钮排序、本地保存顺序和刷新恢复。
- 2026-06-07：首页顺序调整为 Hero、Selected Works、四段图文 Statement、Contact；Statement 每段对应一张图片并分别入场，最终保留 Enter Works CTA、移动端和 reduced-motion 降级。
- 2026-06-08：统一 Works Archive 的圆角、字体角色和单色细线图标；上传入口改为细线工具入口，筛选区和 Count/Arrange 管理区分组，Arrange 卡片改为 4px 编辑态和图标按钮。
- 2026-06-08：更新 `project-development-guardrails/SKILL.md`，新增企业级项目文档契约，将 `README.md` 版本/运行说明、`PROJECT_MAP.md` 功能地图/修改记录、`DESIGN_SYSTEM.md` 布局设计/组件规则纳入开发闭环。
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
- 2026-06-17：完成上传图片到 SQLite 数据库的完整连接；`server.py` 新增 `POST /api/archive/images` 创建新上传记录，`manage.js` 修改 `shouldSyncRecordToArchiveApi()` 让上传记录也同步到数据库，新增 `archiveApiCreatePayload()` 函数，`importUploadedFiles()` 在上传时调用 POST API 写入 SQLite 并保留 IndexedDB 作为 fallback；上传的图片现在会同时保存到本地数据库和浏览器存储，公开 Works 页面可以读取到上传的作品。
