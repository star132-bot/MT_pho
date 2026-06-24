# MT Presence Design System

## 设计定位

MT Presence is not an admin product or a conventional marketing page. The page should feel like an editorial entry into a fine art photography practice: restrained, image-led, and quiet.

核心气质：

- 克制：少装饰，少动效，少色彩。
- 沉静：文字行距舒展，图片占据主要注意力。
- 收藏感：页面像画册、展厅、作品档案，而不是电商列表。
- 可持续：未来增加作品详情、系列、购买咨询、展览信息时，组件结构仍然稳定。
- 全英文：当前站点所有可见 UI 和文案必须使用英文。

摄影可信度：

- 所有作品图必须能被摄影机拍到。
- 抽象来自真实对象与观看方式，不来自纹理素材或生成质感。
- 不把临时图库素材或 AI 图表述为 MT 正式作品。
- 上传系统后续应支持作者指定作品比例、裁切点和展示说明。

## 当前首版组件策略

当前项目是静态站点，没有 React/Vue/Next 依赖。首版先使用自建轻量组件系统：

- `site-header`：品牌与导航。
- `hero`：主视觉、品牌名、核心宣言、主按钮。
- `button`：统一按钮样式。
- `about-section`：品牌介绍长文案。
- `marquee-gallery`：精选作品无限横向滚动带。
- `marquee-item`：单张作品展示容器，统一高度、自然宽度。
- `ui-icon`：作品档案页功能图标，使用单色细线 SVG symbol。
- `archive-controls`：作品档案页索引区，内部拆分浏览用 `archive-filter-bar` 和管理用 `archive-toolbar`。
- `archive-arrange-actions`：作品档案页排序入口、保存和退出操作。
- `archive-icon-button`：Arrange 模式中的拖动、上移和下移图标按钮。
- `archive-gallery`：作者作品横向多行档案墙。
- `contact-section`：联系作者。
- `contact-page`：联系作者独立页面和表单。
- `manage-workspace`：内部作者维护工作区，当前用于 Works Viewer metadata 编辑。
- `site-footer`：页脚。

这样做的原因：

- 首版只有一个页面和一个精选作品带，不需要重型组件库。
- 艺术站点的视觉质量主要来自排版、图片比例、留白和节奏，不来自复杂 UI 控件。
- 未来如果升级为多页面或 CMS，再引入框架和组件库。

## 推荐技术选型

### 1. 静态首版

适合当前阶段。

- HTML + CSS + 原生 JavaScript
- CSS custom properties 管理颜色、间距和字体
- 原生锚点导航
- 原生锚点导航和少量滚动过渡脚本

当前项目采用这个方案。

### 2. 作品数量增加后的无框架增强

适合继续保持静态站点，但需要更好的画廊体验。

- PhotoSwipe：响应式图片画廊和 lightbox。
- lightGallery：图片、视频、缩略图、缩放、移动端手势更完整。
- SimpleLightbox：轻量图片 lightbox，适合需求很简单时使用。

建议优先级：

1. PhotoSwipe：更适合克制的艺术图片展示。
2. lightGallery：适合作品数量大、需要缩略图、缩放、视频时。
3. SimpleLightbox：适合只要点击放大图时。

### 3. React/Next 阶段

适合以后加入作品详情页、收藏咨询表单、CMS、预约、购买意向、后台管理。

推荐组合：

- Next.js 或 Astro：站点框架。
- Tailwind CSS：设计 token 和响应式排版。
- Radix UI：无样式、可访问的基础交互组件。
- shadcn/ui：把组件代码复制进项目，形成自有组件库。
- React Photo Album：响应式照片墙。
- Yet Another React Lightbox：React lightbox。
- Motion for React：少量进入、切换、浮现动效。

不建议首选：

- Ant Design：更像后台系统，艺术站点会显得工具化。
- MUI：产品应用感较强，容易带出模板感。
- 大量炫技动效库：会抢作品注意力。

### 4. 艺术/创意组件灵感库

这些库适合找灵感，但要非常克制地用：

- React Bits：动效和视觉组件丰富，可参考图片过渡、文字浮现。
- Cult UI：shadcn 生态的动画组件集合，可挑极少量低声量组件。
- Magic UI：视觉效果很多，只适合选少量纹理、渐显、进度或镜头类组件。
- Aceternity UI：更适合创意落地页，当前项目只能借鉴，不建议直接大量使用。

使用规则：

- 只允许增强观看体验，不允许喧宾夺主。
- 禁止使用粒子、霓虹、过度发光、强渐变、装饰球体等效果。
- 每个页面最多一个主要动效模式。
- 动效必须支持 `prefers-reduced-motion`。

### 5. 当前项目对 Magic UI / Aceternity UI 的使用边界

- 当前仓库是静态 HTML、CSS、原生 JavaScript，不引入 React、Next.js、Tailwind 或 shadcn 作为运行时依赖。
- Magic UI 和 Aceternity UI 只作为视觉和交互参考来源，不直接安装到当前项目。
- 当前阶段采用“手写实现，参考质感”的策略：保留现有页面结构和自建样式系统，只吸收局部效果。

适合参考的方向：

- Magic UI：`Marquee` 的节奏、`BlurFade` 的低声量显现、`Progressive Blur` 的信息层渐隐。
- Aceternity UI：图片详情层的聚焦方式、标签或说明卡片的组织方式、少量文字 reveal 过渡。

不适合当前项目直接照搬的方向：

- 强 hero 特效、粒子、光束、glow、流星、装饰背景层。
- 带明显 SaaS 或创意 landing page 模板感的大块卡片和高饱和渐变。
- 依赖 React 组件状态机才能成立的复杂交互外壳。

当前推荐做法：

- 首页继续保持自建 hero、Statement 和作品带。
- `Works Archive` 的作品放大鉴赏层、标签可视化、状态显隐动画，可参考这两个库的节奏后手写实现。
- 如果后续迁移到 Next.js + Tailwind，再评估正式接入 Magic UI 或 Aceternity UI。

## UI 排版规则

### 字体

- 中文正文优先使用宋体或衬线字体，形成画册感。
- 英文小标题使用无衬线字体，作为信息标签。
- 不使用负字距。
- 不随视口宽度线性缩放正文字号。

当前建议：

- 品牌名：衬线，大字号，低字重。
- 正文：17-23px，行高 1.8-2。
- 导航和按钮：13-14px，无衬线。
- 小标签：12px，无衬线。

### 色彩

当前色彩系统：

- Gallery white 背景：`#f6f6f3`
- 主文字：`#171716`
- 次文字：`#66645f`
- 低对比分割线：`rgba(23, 23, 22, 0.13)`
- 浅石灰面板：`#ecebe6`
- 深酒红强调：`#5f2f29`
- 深褐灰暗色区：`#2d2521`
- 主内容表面：`#ffffff`

规则：

- 页面背景应接近现代摄影画廊的 gallery white / stone white，不能偏淡黄色、奶油黄或旧纸色。
- 页面不能变成单一冷灰，需要一点深酒红和深褐灰作为品牌温度。
- 暖色只用于标签、强调、hover/focus/error/dirty 等局部状态，不大面积铺满。
- 图片区域不加复杂边框和卡片阴影，避免破坏作品气质。

### 布局

首页：

- 桌面：整屏摄影背景，右侧/偏右放置主标题、短文案和两个入口按钮。
- 移动端：整屏摄影背景，文案靠下显示，按钮全宽排列。
- 首屏只保留两个主要入口：`Enter Works` 和 `Contact Artist`。
- 首屏下沿可使用斜切过渡，参考摄影社区 landing page 的大图构图，但不照搬 cookie 弹窗或多按钮营销结构。
- 首页 hero 使用短 pinned 图片覆盖转场：桌面 `hero-stage` 约 `150vh`，移动端约 `140vh`；抽象黑白图到具体彩色图的 opacity 过渡覆盖大部分 pinned 滚动，并在结束后尽快释放到 Selected Works，不能让用户在完整具象图上空滚很久。
- 首屏导航延迟换肤：hero 转场期间保持透明或极轻微顶部渐变，只用浅色文字、轻微 text-shadow 保证可读性；等 hero-stage 接近释放、Selected Works 即将进入时再切换为浅色实底，不在滚动早期遮挡摄影图。
- Hero 文案随图片切换交替，但不改变按钮和布局：抽象阶段使用 `Abstract Field`、`A Quiet Field for Images`、`Images are not records of the world...`；具象阶段使用 `Concrete Field`、`Where Looking Becomes Presence`、`Light, weather, and distance settle into form...`。两套大标题不能以 50/50 方式叠字，应使用分段 opacity 和轻微位移：抽象文案先安静淡出，具象文案再淡入。按钮保持原位，过渡结束时应隐约感觉下一段内容即将出现。

Statement：

- Statement 是进入作品前的安静序章，不做营销长页面。
- 首页顺序为 Hero、Selected Works、Statement、Contact。Selected Works 先出现，用作品带给 Statement 留出呼吸空间。
- Statement 使用 `Statement`、`MT Presence` 标题和四个图文 moment；每个 moment 一张 `assets/art/` 图片、一段文案和 `01`-`04` 编号。
- 桌面每个 moment 使用图片/文字两栏，偶数段左右反排，形成观看节奏；移动端改为图片在上、文字在下的普通流。
- 每个 moment 进入视口时图片横向轻推入场，文字延迟淡入上浮；CTA 在段落标题可见后出现。动画保持 700-1000ms，不使用弹跳、旋转、粒子或装饰光效。
- `prefers-reduced-motion` 下关闭显影动画，标题、图片、文字和 CTA 默认完整可读。

作品：

- 顶部只保留 `Selected Works` 标题，不提供比例筛选和分类筛选。
- 作品以 curated horizontal gallery 展示精选图，像 museum wall，而不是社交媒体网格。
- 图片必须保留原始宽高比，不强制固定宽高，不裁切，不拉伸，不加黑边。
- 行内图片统一高度，宽度按原始比例自然变化。
- 横向作品带从右向左缓慢无缝循环；最后一张离开视口后第一张应自然接上。
- 悬停作品带时可暂停滚动；悬停单张图只允许轻微 zoom/fade，避免抢作品注意力。
- 当前作品数量较少时使用单排 Infinite Marquee Gallery；Selected Works 当前只展示竖向照片。作品超过 12 张后可考虑做三排交错方向 marquee。

档案页：

- `Enter Works` 进入独立作品档案页，而不是在首页展开复杂筛选器。
- 档案页用于作者上传和管理作品展示，应更安静、信息密度更高。
- 上传图片后读取原始尺寸并自动分类到 `1:1`、`4:3`、`4:5`、`2:3`、`3:2`、`16:9`、`Panorama`。
- 展示比例使用分类后的标准比例，不使用原始尺寸中的微小偏差；原始宽高只作为 metadata 显示和数据库记录。
- 上传图不是 `1:1` 时，应自动生成 `1:1` 方形切片用于后续归档/发布工作；展示层仍保持原图比例，不裁切用户看到的原图。
- 抽象/具体分类当前静态版可用启发式分类，后续应接视觉模型；抽象图以黑白呈现，具体图以低饱和彩色呈现。
- 静态版本用浏览器 IndexedDB 保存上传图、原始宽高、比例分类、抽象/具体分类、多版本资产和 `1:1` 切片；后续有后端时迁移到对象存储 + `images` / `image_assets` / `image_square_slices`。
- 上传图片压缩采用多版本资产思路：`original` 不压缩、不改尺寸，只归档；`display` 最长边约 2300px、质量约 0.86，用于 Works Archive 和前台展示；`thumbnail` 最长边约 640px、质量约 0.78，用于列表和后台快速预览；`square_slice` 输出边长限制约 1400px，并记录原图 source 坐标。
- 上传状态必须逐图显示读取中、压缩中、切片中、分析中、保存中、完成或失败；多图上传时一个失败不能影响其他图片继续保存。
- 前台作品图优先使用 `display` 版本；没有 `display` 时才 fallback 到 `original`。`thumbnail` 不能替代作品展示图。
- Gallery 在 `All` 模式使用协调的 masonry 图墙，让不同尺寸图片自然错落并保持整体平衡。选择具体比例时切换为比例专用网格，按该比例组缩放图片并铺满行宽。不裁切、不拉伸、不加黑边。
- Works 顶部按三层组织：导航；`Works Archive` 标题和简短说明；Search/Type/Ratio 筛选与 Count/Arrange 管理动作。公开 Works 页不显示 Add Works，上传入口只放在内部 `manage.html`。
- 过滤器包含 Search、Type 和 Ratio，放在 `archive-filter-bar` 中，像档案索引而不是后台 toolbar；搜索输入使用小字号 label、细线输入框和轻量 Clear Search 按钮。
- Search、Type、Ratio 必须叠加生效；搜索匹配 title、series、description、curatorial note、artist statement、tags、tag groups、content type/type、ratio/ratio label、source/original filename，并支持 `1:1`、`4:3`、`4:5`、`2:3`、`3:2`、`16:9`、`panorama`、`vertical`、`horizontal` 等比例关键词。
- 搜索结果数量必须通过 Count 更新并使用 `aria-live`；无结果时显示 `No works match this search.`，移动端筛选区不能横向溢出。
- Count、Arrange、Save Order 和 Done 放在 `archive-toolbar` 中，与筛选视觉分组，避免把浏览行为和管理行为挤在一起。
- 排列功能只在用户点击 Arrange 后出现卡片级控件；桌面支持拖拽，所有设备都保留上/下箭头移动按钮和 Save Order，避免依赖触控拖拽。
- 作品图片默认不加圆角；Arrange 模式下卡片允许 4px 细边框和图片 2px 圆角，用来提示正在编辑，退出后恢复无框展示。
- 内部 Add Works、Arrange、Save Order、Done、拖动柄和上/下移动使用单色细线图标，尺寸保持 16-18px，图标按钮必须保留 `aria-label`。
- 作品放大鉴赏层和标签可视化已作为 Works Archive 的核心浏览入口：普通模式点击作品打开，Arrange 模式点击不打开；动效只使用低声量 fade、slight scale 和 blur reveal，保持当前静态站结构，不引入 Magic UI / Aceternity UI 运行时依赖。
- 鉴赏层桌面使用两栏式：左侧大图优先占面积，右侧是展签式信息；平板和手机改为上下结构，首屏优先看到作品本身。
- 鉴赏层图片优先使用 `display` 资产或 `archive_image_view.image_url`，没有 display 时才 fallback 到 original；图片始终 `object-fit: contain`，不裁切、不拉伸、不加黑边。
- 鉴赏层信息区可显示标题、策展说明、Type、Ratio、Size、Captured、Display、Series、Artist Statement/Description 和标签分组；标题用衬线，metadata 和标签用小号无衬线。
- 标签分组服务作品理解，不做彩色 chip 墙；推荐使用 Subject、Mood、Material / Surface、Palette / Tone、Technique、Series / Collection、Place 等细线分组，标签以轻量行内文字和小点分隔。
- 鉴赏层必须支持 Esc、遮罩、关闭按钮、左右按钮和 ArrowLeft/ArrowRight；打开后锁定背景滚动、焦点进入 dialog，关闭后恢复触发卡片焦点；`prefers-reduced-motion` 下取消 blur/scale 转场。

内部管理页：

- `manage.html` 是内部作者工作台，不是公开展示页，也不是普通 SaaS 后台；应保持 fine art photography 的安静、克制、纸面感和较高信息密度。
- 页面使用 neutral gallery palette，避免淡黄色、奶油黄、旧纸黄、大面积彩色背景、厚重卡片、大阴影和蓝紫渐变。
- 顶部保留 `MT Presence` 品牌以及 `Works / Messages` 导航；主体按 Import、Homepage、Works list、Viewer editor 组织。
- Homepage 设置必须作为内容维护模块展示：Abstract Hero、Concrete Hero、Statement / Homepage text；每个 Hero 区域包含当前图片预览、Image selector、Eyebrow、Title、Statement。
- 保存状态要明确但克制：Saved、Unsaved changes、Last saved time、Save Current、Save All、Revert；修改字段后立即显示未保存状态，保存/失败用 inline 状态和 toast 反馈。
- 表单字段宽度、间距、label、输入框和 textarea 对齐统一；分区之间用细线和留白，不使用卡片套卡片。
- 切换作品、刷新或离开页面前如有未保存修改，需要提示；保存逻辑继续使用 IndexedDB 过渡层，不能做刷新后丢失的假保存。

联系：

- 暗色整段区域。
- 首页联系段只保留一个明确动作：进入 `Contact Artist` 页面。
- 联系页首屏直接呈现表单，不做营销型落地页；左侧用简短说明和黑白作品图作为安静的视觉锚点，右侧放表单。
- 字段只保留 Name、Email、Subject、Note；Email 和 Note 必填。
- 提交时生成邮件草稿，不保存本地消息，不提供 inbox 或回复后台。
- 成功或失败用淡入淡出的 toast，不刷新页面。

## 组件规范

### Button

- 用于明确动作。
- 高度固定在 42-48px，圆角保持 4-6px。
- 主按钮黑底浅字。
- 次按钮透明底黑字。
- 移动端宽度 100%。

### Marquee Gallery

- 用于展示精选作品，不用于筛选、分类或密集信息浏览。
- `.marquee-gallery` 负责裁掉视口外内容，不能给图片加卡片背景或黑色承托框。
- `.marquee-track` 至少重复两组相同图片序列，使用线性动画完成无缝循环。
- `.marquee-item` 统一高度；图片 `height: 100%`、`width: auto`、`object-fit: contain`。
- 图片之间保留清晰间距，呈现 museum wall 的观看节奏。
- 支持 `prefers-reduced-motion`：关闭自动 marquee，允许横向手动滚动。

### Archive Gallery

- 用于展示作者上传图片和精选样例图。
- Type 过滤：`All`、`Abstract`、`Concrete`。
- Ratio 过滤：`All`、`1:1`、`4:3`、`4:5`、`2:3`、`3:2`、`16:9`、`Panorama`。
- 图片原始比例优先，metadata 辅助理解，不作为裁切依据。
- 档案卡片不使用厚重边框和阴影；图片下方只放作品标题、Type 和 Ratio。
- 作品标题使用衬线字体，metadata 使用 11px 左右无衬线小字。
- Arrange 模式下每张卡片显示序号、六点拖拽手柄、上/下移动图标；未保存时显示明确状态，保存后刷新应保持顺序。
- 移动端降低图片行高，保留横向优先的多行排列；过滤器不 sticky，避免遮挡内容。

### Work Viewer

- 用于 Works Archive 的作品放大鉴赏，不是商品详情页、后台 drawer 或普通图库 lightbox。
- 桌面布局为大图 + 信息展签，信息区宽度不能挤压图片；移动端为大图在上、信息在下，关闭和左右切换按钮始终可见。
- 大图保持原始比例，优先 `display` 资产，不默认请求原图。
- Metadata 使用细线、留白和小号档案字体，不使用密集表格线或厚卡片。
- 标签按组展示，小标题对读屏器可读；标签本身不使用高饱和彩色背景。
- 打开/关闭转场控制在 220ms-420ms；`prefers-reduced-motion` 下直接显示。

### Works Viewer Editor

- 用于内部作者维护，不加入公开导航，不改变公开 Works 页面视觉。
- 桌面布局优先露出 Add Works、Homepage 内容维护台、左侧作品列表和右侧当前作品表单；Homepage 区保持紧凑，避免把作品维护工作区压到首屏之外。左侧可 sticky，移动端改为横向可滚动列表加单列表单。
- Add Works 只出现在内部页面，上传状态必须显示读取、压缩、切片、保存、完成或失败。
- Homepage 设置区用于维护首页抽象/具象 hero 图片和文案、Statement 标题、四段图片和文字；使用克制的常驻编辑台和小型图片预览，不做营销式预览大卡。
- 表单顺序必须贴近 Viewer 信息栏：Series、Title、Curatorial Note、Description、Metadata、Tag Groups、Artist Statement、Visibility。
- Dirty 状态要在列表项和表单状态区明确显示；保存当前、保存全部、撤销当前都使用现有 `.button` 样式，不引入新按钮体系。
- 标签编辑保持文本输入密度，Enter 在标签 textarea 中插入分隔符，Shift+Enter 保留换行；保存后仍输出分组结构，不渲染成彩色 chip 编辑器。
- 原始尺寸、比例、图片路径、`image_assets` 和 square slice 数据是只读 base data；编辑页可以展示但不做普通可编辑字段。
- 删除上传图必须与清空内容数据区分；本地样例作为 base data 不能从编辑页删除，只能清空 manual metadata。

### Contact CTA

- 保持短文案。
- 主操作进入独立联系页。
- 联系页表单使用少量阴影和半透明浅色背景；移动端单列显示，不遮挡或挤压表单字段。
- 表单提交按钮沿用 `.button-primary`，生成邮件草稿时 disabled，成功和失败都显示 toast。
- 后续如果增加微信、Instagram、小红书，只作为次级链接，不抢主按钮。

## 后续引入组件库的触发条件

满足任一条件再引入框架和组件库：

- 作品超过 20 件，需要详情页、系列页或筛选。
- 需要 lightbox、缩略图、键盘切换、图片预加载。
- 需要 CMS 或后台维护作品。
- 需要联系表单、预约、询价、收藏意向提交。
- 需要多语言。
- 需要 SEO 级作品详情页。

推荐下一阶段方案：

```text
Astro + Tailwind CSS + PhotoSwipe
```

如果需要复杂交互：

```text
Next.js + Tailwind CSS + Radix UI + shadcn/ui + React Photo Album + Yet Another React Lightbox
```

## 参考来源

- Radix UI: https://www.radix-ui.com/primitives/docs
- shadcn/ui: https://ui.shadcn.com/docs
- PhotoSwipe: https://photoswipe.com/
- lightGallery: https://www.lightgalleryjs.com/
- React Photo Album: https://react-photo-album.com/documentation
- Yet Another React Lightbox: https://yet-another-react-lightbox.com/documentation
- Tailwind CSS: https://tailwindcss.com/docs
- Motion for React: https://motion.dev/react
- Lenis: https://lenis.darkroom.engineering/
- React Bits: https://www.reactbits.dev/
- Cult UI: https://www.cult-ui.com/docs
- Magic UI: https://magicui.design/docs/components
