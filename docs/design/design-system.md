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

## AI 辅助设计工作流（强制）

每次新增、改版或美化页面前，必须先为当前页面编写一份具体、可验收的英文 UI design prompt，再开始修改代码。不能只使用 “make it beautiful” 一类空泛提示。

提示词必须包含：

- 页面目标、主要用户和首要任务。
- 视觉方向、品牌气质、排版、色彩、密度和图片角色。
- 页面布局、信息层级和关键组件。
- loading、empty、error、success、disabled、permission、dirty、conflict 等相关状态。
- desktop 与 mobile 行为、键盘操作、focus、文字溢出和可访问性要求。
- 明确的 `Avoid` 清单，防止 generic AI/SaaS UI、过度圆角、渐变、玻璃拟态、装饰性卡片和无意义动效。
- 与当前页面相关的验收标准。

每次执行 Web 页面任务还必须：

1. 先读取本设计系统、产品规格和相邻页面实现。
2. 使用真实产品 UI 样本进行有目的的参考研究；优先研究对应组件和完整流程，不照搬单张概念图。
3. 在实现前向用户展示或概括本次使用的 UI design prompt。
4. 实现后检查桌面与移动端视口，并验证 hover、focus、active、empty、error 等相关状态。
5. 同步更新项目功能地图，并说明未完成或无法验证的部分。

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

### 2026-07-04 静态组件体系增强

当前仓库仍不引入 React、Next.js、Tailwind、shadcn/ui 或 Radix UI 运行时依赖。本轮优化把这些体系里的可执行方法迁移到静态站：

- `styles.css` 增加 `--ui-*` token：统一 focus ring、圆角、缓动曲线和动效时长。
- Works / Collections 的图片项渲染时由 JS 注入 `--item-delay`，配合 CSS 做轻量 stagger reveal；筛选和集合切换不再是生硬 DOM 替换。
- `archive-gallery` / `collection-gallery` 在重渲染时设置 `aria-busy`，筛选按钮和集合按钮用 `aria-pressed` 表达状态。
- Upload Studio 使用 Folders 作为私有整理系统：文件夹不是公开收藏页，不自动成为 Series 或标签；Inbox 是不可重命名/删除的 system folder。
- Contact 表单用 `.is-focused`、`.is-filled`、`.has-error` 和 `aria-invalid` 表达交互状态；提交按钮有 loading spinner。
- 全站交互控件统一 `focus-visible`，保证键盘操作时可见但不破坏摄影页面的低声量视觉。

后续如果迁移到 Next.js，可把这些 token 和状态命名直接映射到 Tailwind theme、shadcn/ui variants 和 Radix state attributes。

### 2026-07-04 Viewer 和 Rail 修正

作品查看器不使用大面积黑色影棚底。参考馆藏/摄影作品页的处理方式，图片区域使用 gallery white / stone surface，黑色只用于文字和少量 hover/active 强调：

- `.work-viewer-media` 使用浅色 gallery surface、细分割线和低透明阴影承托作品。
- 图片自身用浅边框和轻阴影聚焦，不让背景比作品更抢眼。
- 左侧 `archive-rail-button.is-active` 不再使用黑色块，改为轻色底、品牌酒红图标和细内边界。
- 详情层默认是全屏图片优先，不显示右侧信息栏；`Info` 图标打开展签、metadata、tags 和 related works 抽屉；图片本身的点击不再切换局部 zoom，避免把“全屏查看”误做成“单图放大”。
- 作品卡片 hover 只显示 `MT` 角标和 Save / Collect / Download 图标按钮；不再显示底部标题说明和大号 Download 文案按钮，避免遮挡图片。
- 图标按钮必须有 `aria-label` 和 `data-tooltip`，鼠标 hover 或键盘 focus 时显示统一黑底提示；不要只依赖浏览器原生 `title`。

Rail 功能设计方向：

- Works：当前作品档案入口，保持主入口 active。
- Manage：内部 Archive Review 审核入口，后续应加权限/内部模式提示，避免公开访客误入。
- Sets：进入 `collections.html`，只负责浏览当前浏览器保存/策展的作品集合，不承担上传或审核。
- Upload Studio：个人上传入口，提供文件夹、上传队列、点击图片编辑 Draft、保存，以及 Drafts/Trash 分段视图；Trash 卡片只读并只提供 Restore，不提供 hard delete 或 Publish。
- Draft editor 使用无卡片的 Work details 与 Accessibility/Rights 分组；Alt Text 和长文案跨两列，版权/枚举字段维持双列，Recognizable People=Yes 时才显示 Model Release。桌面 editor 可独立纵向滚动，1180px 以下回到普通页面流，移动端严格单列。字段编辑停顿 900ms 后自动保存，同时保留明确的手工 Save 命令。
- Download Visible：下载当前筛选视图第一张作品；后续可升级为打开下载设置菜单。
- Saved：切换只看已保存作品，保留 `aria-pressed` 状态。
- Notifications：建议改成“Activity / Sync status”，展示上传、保存、数据库同步和失败重试状态。
- Avatar：进入联系作者或作者信息；如果未来有登录态，可改成 account menu。
- More：建议改为更多菜单，放入 Help、Keyboard shortcuts、Display density、About archive 等低频项。

### Upload Queue

- 队列卡片使用固定缩略图轨道、弹性信息轨道和稳定的独立操作区；卡片主区域负责选中 Draft，Cancel/Retry/Remove 图标按钮不嵌套在主按钮内。
- Reading、Processing、Uploading、Canceling、Failed、Canceled 和 Draft ready 保持同一外框尺寸，以左侧细状态线、进度条和两行内消息表达变化，禁止状态切换导致列表跳动。
- 运行中任务显示 Cancel；失败任务显示 Retry 与 Remove；取消任务显示 Retry 与 Remove。图标按钮必须有 `aria-label` 和 tooltip，点击范围固定，不用文字胶囊挤占图片信息。
- 桌面端操作区靠右，移动端移动到信息区下方并保持按钮尺寸；长文件名省略，状态消息最多两行，不覆盖缩略图或后续卡片。
- 同一文件夹仍有排队、失败或取消任务时禁止删除该文件夹，先完成或移除任务，避免 Retry 指向失效 Folder。

### Upload Workspace

- 页面使用 gallery white 工作面与细分隔线，不使用渐变背景、三个并列浮卡或大面积阴影。Folder 是窄导航列，导入/队列是主工作区，Draft editor 只在存在选中记录时展开。
- 初始远程 hydrate 必须显示 `Loading folders`、Loading state 和骨架，不得先渲染 `0 folders` / Ready 造成假空态。
- 空状态保持 Folder + 导入区两列，队列空提示控制在紧凑高度；有 Draft 时桌面展开三列，1180px 以下 editor 移到下一行，760px 以下严格单列。
- Import Images 是页面主命令；Choose files 是 dropzone 内的同一 file input 入口。两者状态同步，Loading/离线时都必须 disabled。
- 面板靠边界、留白和层级区分，不做卡片套卡片；统计使用同一条分隔栏，不使用两个独立统计卡。
- Drafts/Trash 使用稳定分段控件；Trash 仅展示标题、缩略图、移入时间和图标 Restore 命令，并完整呈现 loading、empty、error/retry、restoring、success、conflict 与 permission 状态。恢复时原 Folder 已删除则回退 Inbox。

### Draft Save and Conflict

- 自动保存采用 900ms debounce，多个 mutation 必须串行；保存请求期间继续输入不能丢失，当前请求完成后应继续保存较新的表单 revision。
- 手工 Save 始终保留，与自动保存共用同一校验、串行队列和 `expected_version` 协议，不能形成两套结果不同的保存逻辑。
- 状态文本使用稳定占位并通过 `aria-live` 低声量报告 Saving、Saved、Error 和 Conflict；颜色只作为辅助，不能取代可读文字，也不能因文案变化让 editor toolbar 跳动。
- Saving 时 Save 与 Trash 禁用，避免并发 mutation；普通失败显示 Error 并保留 dirty 表单，作者可再次 Save，不能把离线缓存失败误报为服务端保存失败。
- Conflict 表示 HTTP 409 乐观并发冲突：停止自动保存、保持全部本地输入、不自动合并或覆盖，同时禁用 Save 与 Trash；显示带 retry 图标的 `Reload Server Draft`，由作者明确触发后才用最新服务器 Draft 替换表单。
- `Reload Server Draft` 只在 Conflict 中出现，不作为常驻主按钮；桌面与移动端都必须与 Save/status 保持稳定间距，长状态文案可换行但不得覆盖输入区或操作按钮。
- Draft PATCH 成功只更新 metadata 状态，现有预览图保持不变；保存状态不依赖再次获取 signed asset URL，避免写入已成功却显示 Error。

### Admin Review Queue

- Review Queue 是高密度编辑工作台，不使用 Dashboard 卡片墙。顶部只保留紧凑标题、可操作 queue counts、Assignment filter 和 Refresh；统计必须能直接改变队列。
- 桌面采用稳定的 Queue + Detail 结构：队列保持窄而可扫描，详情以提交图片为视觉主角，右侧 inspector 用细分隔线组织 Copy、Rights、Evidence、History 和 Decision；图片始终 `object-fit: contain`，Actual size 只改变查看方式，不裁切作品。
- 列表至少显示作品名、Submission ID 尾段、作者、等待时间、category、rights、assignment 和状态；每个 queue button 的 accessible name 必须同时包含 title/status/owner/waiting/ID 尾段并保持唯一。长文件名与用户文案必须换行或省略，不能挤压状态和缩略图。
- Reviewer 打开可领取的 Submitted 项时先执行原子 Start/Claim，再加载 Original/Display；未领取队列只暴露 thumbnail。Admin+AAL2 可以查看完整历史，但角色叠加不能绕过 MFA。
- Decision 使用完整 checklist、reason 和 user message；提交期间所有相关控件 disabled，冲突保留当前输入并提供 Reload。确认 dialog 首焦点放在 Cancel，关闭后恢复触发控件；未完成 checklist 必须把首个失败 checkbox 标记为 invalid、用 `aria-describedby` 关联 assertive `role="alert"`，同时把焦点移到该项。
- Request Changes、Reject 和 Approve 是当前浏览器动作；在 Supabase public DTO、derivative delivery 和公开 Works 数据源接通前，不显示会虚假承诺公开结果的 Approve and Publish。
- 1024px 以下 Queue 与 Detail 改为上下布局；760px 以下隐藏桌面 rail、使用 68px 单行顶栏，Queue/Detail 为互斥视图。Detail 顶部必须提供 44px 以上 `Back to queue`，返回时保留 deep-link 与选中项、把焦点交还 active row，重新点选无需滚过完整详情即可恢复 Detail。
- Loading、empty、error、permission、busy、success、conflict 都使用固定布局和可读文字；状态颜色只作为辅助。Evidence/History/Checklist 不低于 12px，Inspector 与表单正文不低于 13px，checkbox 行和关键触控动作不低于 44px。

### User Dashboard And Account Menu

- Dashboard 是已登录摄影作者的受保护个人资料，不是营销 Hero、通用统计卡片墙或 public creator portfolio。页面使用全宽顶部导航且不显示左侧 rail；第一视口用真实摄影 cover、avatar/initials、名称/headline/location/availability/bio/links/account context 和 Edit personal information、Upload work 两个明确动作建立身份。
- Overview 依次呈现服务端聚合 Status、Changes Requested 优先的 Needs Attention、Recent Images、Review Activity 与 Storage；My works 只列最近可编辑 Draft。页面允许用 charcoal、forest、teal、rust 与浅色面组织身份事实，但不得退化成单一色相或卡片套卡片；重复 Draft 可以使用不超过 8px 的边框卡片。
- Status 数字来自单一 aggregate DTO；loading、空账号、provider error、permission denied 和 retry 都保留稳定尺寸。未实现的 storage quota/public portfolio 用明确 unavailable 文案，不显示虚假进度条、剩余容量或公开作品入口。
- Dashboard cover chooser 只显示当前 owner 的 non-deleted、ready image，并按 image 去重、优先 current-policy scanner-clean display、缺失时回退 clean thumbnail。候选和当前 cover 只加载服务端短期 signed URL，不能读取 original、Storage key 或跨 owner asset；无候选时使用稳定摄影 fallback。Dialog 支持 loading/empty/error/success、Remove current cover、Escape/Cancel 和 trigger focus restoration。
- Dashboard 提供 Overview/My works tablist，ArrowLeft/ArrowRight/Home/End 可切换并同步 `aria-selected`、`tabindex` 与 panel visibility；移动端把统计改为两列、内容改为单列，不允许横向溢出。
- Account Settings 的 Profile 表单使用 Identity、Work、Location、About、Links 五个并列清晰的 fieldset，每组使用克制而不同的浅色边界/底色，十个字段在桌面稳定两列、窄屏单列；不留下大块无意义空白，也不把 fieldset 放进装饰卡片。
- Home 登录态与内部 Dashboard、Upload、Review、Account 顶栏共用 initials profile avatar；点击头像直接进入 `/dashboard` personal profile，再由 Edit personal information 进入 `/settings/account#profile`。内部顶栏在头像旁提供独立账户菜单按钮，菜单显示当前身份、Dashboard、Workspace、Account Settings、权限允许时的 Review 和 Sign out；ArrowUp/ArrowDown/Home/End 导航，Escape 关闭并恢复菜单按钮焦点，点击外部或焦点离开时关闭。
- Avatar menu 最大 8px 圆角，不使用阴影堆叠或彩色身份 chip；Sign out 通过 same-origin CSRF 执行，失败留在当前页并把可读错误聚焦宣告。

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

- Gallery white 背景：`#ffffff`
- 主文字：`#111111`
- 次文字：`#62666d`
- 低对比分割线：`rgba(17, 17, 17, 0.12)`
- 冷中性面板：`#f5f6f7`
- 深蓝灰强调：`#2f5f7f`
- 深中性暗色区：`#171b20`
- 主内容表面：`#ffffff`

规则：

- 页面背景必须接近纯白现代摄影画廊：以 `#fff`、冷中性浅灰和细线为主，不能偏淡黄色、奶油黄或旧纸色。
- 页面不能变成单一冷灰，需要通过图片、黑白强对比、细线层级和少量深蓝灰强调建立品牌温度。
- 强调色只用于标签、强调、hover/focus/error/dirty 等局部状态，不大面积铺满。
- 图片区域不加复杂边框和卡片阴影，避免破坏作品气质。

### 布局

首页：

- 桌面：整屏摄影背景，右侧/偏右放置主标题、短文案和两个入口按钮。
- 移动端：整屏摄影背景，文案靠下显示，按钮全宽排列。
- 首屏只保留两个主要入口：`Enter Works` 和 `Contact Artist`。
- 首屏下沿可使用斜切过渡，参考摄影社区 landing page 的大图构图，但不照搬 cookie 弹窗或多按钮营销结构。
- 首页 hero 使用普通流内的短图片覆盖转场：桌面 `hero-stage` 高度上限约 `92svh`，移动端约 `82svh`；不能使用超过一个视口的 sticky/pinned 空滚动，各视口首屏下沿必须露出 Selected Works。
- 首屏导航延迟换肤：hero 转场期间保持透明或极轻微顶部渐变，只用浅色文字、轻微 text-shadow 保证可读性；等 hero 底部接近 header、Selected Works 即将进入时再切换为浅色实底，不在滚动早期遮挡摄影图。
- Hero 文案随图片切换交替，但不改变按钮和布局：抽象阶段使用 `Abstract Field`、`A Quiet Field for Images`、`Images are not records of the world...`；具象阶段使用 `Concrete Field`、`Where Looking Becomes Presence`、`Light, weather, and distance settle into form...`。两套大标题不能以 50/50 方式叠字，应使用分段 opacity 和轻微位移：抽象文案先安静淡出，具象文案再淡入。按钮保持原位，过渡结束时应隐约感觉下一段内容即将出现。

Statement：

- Statement 是进入作品前的安静序章，不做营销长页面。
- 首页顺序为 Hero、Selected Works、Statement、Contact。Selected Works 先出现，用作品带给 Statement 留出呼吸空间。
- Statement 使用 `Statement`、`MT Presence` 标题和四个图文 moment；每个 moment 一张 `assets/art/` 图片、一段文案和 `01`-`04` 编号。
- 桌面四个 moment 使用两个稳定列轨，每个单元内部图片在上、文字在下；移动端改为严格单列普通流。图片统一稳定比例，动态内容不能推动相邻单元跳动。
- 每个 moment 进入视口时图片和文字只做轻微纵向显影；IntersectionObserver 是渐进增强，未触发前仍需保持可读透明度。动画保持 700-1000ms，不使用弹跳、旋转、粒子或装饰光效。
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
- Works 和工具页不再使用“大标题 + 说明 + 内容”的通用模板。除首页外，页面首屏必须优先呈现紧凑操作栏、搜索/筛选、结果网格或工作队列；标题只作为 18-20px 模块标签出现。
- Works 顶部按素材库/图库索引组织：导航、Search/Type/Ratio 筛选、Count/Arrange 管理动作和作品网格。公开 Works 页不显示 Add Works，不再提供 `Your Studio` / `user-manage.html` 入口；上传入口进入 `upload-studio.html`。
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

功能侧栏：

- 桌面端 `archive-rail` 统一使用 78px 极简短标题侧栏。入口只包含 icon 和一个短标题，不放说明句、不放常驻分组标题。
- Home 不显示左侧 public rail，使用全宽摄影首屏和顶部 Works/About/Contact/Lightbox/Account 导航；Works、About、Contact、Lightbox 继续使用同一 public rail，顺序固定为 Home、Works、Upload、Lightbox、About，Contact 固定在底部。
- 作者工作区使用 Dashboard、Works、Upload、Review、Account，Review 按权限显示；`/dashboard` 是登录后的 canonical personal profile/overview 且保持无左侧 rail，公开 rail 的 Upload 始终进入受保护 `/workspace/images`，不直接暴露 Draft 数据。
- 侧栏 active 状态使用轻色底、细边界和品牌色，不使用大面积黑块；所有入口保持 8px 圆角、细线、低对比 hover。
- 移动端隐藏侧栏，顶部导航保留主要入口；不要为了塞满功能把窄屏顶栏做成过多小字按钮。
- 不再添加 `Your Studio` 或 `user-manage.html`；账户与云端 Draft 统一进入现有受保护 Upload/Account 边界。

内部管理页：

- `manage.html` 是 Archive Review 审核中心，不是公开展示页，也不是普通 SaaS 后台；应保持 fine art photography 的安静、克制、纸面感和较高信息密度。
- 页面使用 neutral gallery palette，避免淡黄色、奶油黄、旧纸黄、大面积彩色背景、厚重卡片、大阴影和蓝紫渐变。
- 顶部保留 `MT Artist Workspace` 和紧凑 workflow 导航；桌面端使用与 Works / Upload Studio 一致的 78px 短标题侧栏。主体按紧凑 Review 操作栏、筛选 pill、Review Queue、Viewer editor、Homepage settings 组织。
- Manage 不再承载直接图片导入；上传、压缩、文件夹归类和上传后的初始编辑都在 `upload-studio.html` 完成，Manage 只提供入口链接。
- 审核区必须可扫描：顶部用一行 pill 显示 All records、Needs review、Unpublished、Published 数量；左侧列表显示缩略图、visibility 和审核状态；右侧表单显示 checklist，并提供 `Approve & Publish`。
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

- 用于内部作者维护；顶部公开导航不强调，桌面极简 rail 可提供 `Review` 入口，但不能把审核字段混入公开 Works 作品浏览界面。
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
