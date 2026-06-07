# MT 此间 Design System

## 设计定位

MT CIJIAN is not an admin product or a conventional marketing page. The page should feel like an editorial entry into a fine art photography practice: restrained, image-led, and quiet.

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
- `archive-controls`：作品档案页过滤器。
- `archive-gallery`：作者作品横向多行档案墙。
- `contact-section`：联系作者。
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

- 纸色背景：`#f6f2eb`
- 主文字：`#1b1a17`
- 次文字：`#706a60`
- 暗色区：`#241f19`
- 暖色强调：`#7b2f22`
- 面板底色：`#e8e0d2`

规则：

- 页面不能变成单一黑白灰，需要一点暖色作为品牌温度。
- 暖色只用于标签、强调或局部状态，不大面积铺满。
- 图片区域不加复杂边框和卡片阴影，避免破坏作品气质。

### 布局

首页：

- 桌面：整屏摄影背景，右侧/偏右放置主标题、短文案和两个入口按钮。
- 移动端：整屏摄影背景，文案靠下显示，按钮全宽排列。
- 首屏只保留两个主要入口：`Enter Works` 和 `Contact Artist`。
- 首屏下沿可使用斜切过渡，参考摄影社区 landing page 的大图构图，但不照搬 cookie 弹窗或多按钮营销结构。
- 下滑或点击 `Enter Works` 时使用 smooth vertical scroll transition：hero 在过渡舞台里保持 sticky/pinned，不应过早离开视口；黑白抽象 hero 底图保持震撼摄影感，彩色具象风景图从下向上覆盖上一张图，同时展示“抽象黑白”和“具体彩色”的关系。文案轻微上移和 fade，白色遮罩必须克制，动效必须有 easing 且不能突兀。

关于：

- 左侧标题，右侧长文案。
- 行高舒展，不做卡片。

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
- 上传图片后读取原始尺寸并自动分类到 `1:1`、`4:5`、`2:3`、`3:2`、`16:9`、`Panorama`。
- 展示比例使用分类后的标准比例，不使用原始尺寸中的微小偏差；原始宽高只作为 metadata 显示和数据库记录。
- 上传图不是 `1:1` 时，应自动生成 `1:1` 方形切片用于后续归档/发布工作；展示层仍保持原图比例，不裁切用户看到的原图。
- 抽象/具体分类当前静态版可用启发式分类，后续应接视觉模型；抽象图以黑白呈现，具体图以低饱和彩色呈现。
- 静态版本用浏览器 IndexedDB 保存上传图、原始宽高、比例分类、抽象/具体分类和 `1:1` 切片；后续有后端时迁移到服务端数据库。
- Gallery 在 `All` 模式使用协调的 masonry 图墙，让不同尺寸图片自然错落并保持整体平衡。选择具体比例时切换为比例专用网格，按该比例组缩放图片并铺满行宽。不裁切、不拉伸、不加黑边。
- 过滤器只保留 Type 和 Ratio 两组，避免把页面做成后台系统。

联系：

- 暗色整段区域。
- 只保留一个明确动作：发送邮件。

## 组件规范

### Button

- 用于明确动作。
- 高度固定为 48px。
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
- Ratio 过滤：`All`、`1:1`、`4:5`、`2:3`、`3:2`、`16:9`、`Panorama`。
- 图片原始比例优先，metadata 辅助理解，不作为裁切依据。
- 档案卡片不使用厚重边框和阴影；图片下方只放标题、类型、比例和尺寸。
- 移动端降低图片行高，保留横向优先的多行排列；过滤器不 sticky，避免遮挡内容。

### Contact CTA

- 保持短文案。
- 主操作只有邮件联系。
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
