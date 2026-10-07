# 03 公开站点、导航、页脚与法律页面

## 1. 功能范围与当前能力

公开站点系统负责 Home、About、Contact、Works 等入口的统一页面壳、Global Header、移动导航、账户入口、Public/Workspace Footer，以及 Privacy/Terms 法律页面。它负责信息架构和导航，不负责具体业务数据写入。

主要文件为 `index.html`、`about.html`、`contact.html`、`works.html`、`lightbox.html`、`privacy.html`、`terms.html`、`global-header.js`、`public-navigation.js`、`site-footer.js` 和 `styles.css`。

## 2. 入口与前置条件

- 匿名用户可访问 Home、Works、About、Contact、Lightbox、Privacy、Terms。
- 已登录用户在同一公开壳内看到 Dashboard、Workspace、Account Settings 和按角色显示的 Review 入口。
- 移动端宽度小于约 760px 时使用菜单按钮；导航必须有 `aria-expanded`、`aria-hidden`、`inert` 和焦点恢复。
- Footer 的账户入口只接受 Header Identity 发出的可信状态；Footer 不自行请求 `/api/me`。

## 3. 页面流程

### 3.1 首屏与身份壳

1. HTML 先绘制品牌、导航骨架和固定尺寸账户容器。
2. `global-header.js` 读取服务端注入的最小 Header Identity；匿名显示 Sign In，active 用户显示 initials/avatar。
3. Avatar 成功 decode 后才 crossfade；请求失败保留 initials，不把身份回退为匿名。
4. `site-footer.js` 根据 `data-footer-variant` 渲染 Public 或 Workspace footer，并监听身份事件更新入口。

### 3.2 桌面与移动导航

1. 桌面显示 MT Presence、Home、Works、About、Lightbox、Contact 和账户入口。
2. 移动端点击菜单后展开主导航；ArrowDown 聚焦首项，Escape 关闭并恢复触发器焦点，外部点击或链接选择关闭。
3. 当前页面使用 `aria-current` 和细下划线表达 active，不通过重复标题或大块胶囊占空间。
4. Review 只由可信角色状态控制；账户菜单保持 Dashboard、Workspace、Account Settings、Sign out 四类主操作。

### 3.3 Footer 与法律页

- Public Footer 提供 Explore、Practice、Account、Contact、Privacy/Terms 等真实入口；Contact 页面不重复 inquiry band。
- Workspace Footer 只提供 Public Works、Contact 和版权，不遮挡内部操作。
- Privacy 说明账户、作品、咨询、Cookie、保留和安全记录边界；Terms 说明注册、作品、账户安全和可接受使用要求。

## 4. 页面状态与交互结果

- `Loading`：身份壳使用固定 initials/骨架，避免导航在请求期间跳动。
- `Anonymous`：所有受保护链接以登录入口或受控提示呈现，不显示空头像菜单。
- `Active`：账户链接、Review 权限入口和 Footer 按角色更新；Sign In 不与头像同时出现。
- `Mobile open`：背景交互被 `inert` 限制，焦点只在导航；关闭后焦点返回菜单按钮。
- `Error`：身份接口临时失败时保持上次已知 active 身份；只有明确 401 才切换匿名。
- `Reduced motion`：关闭滚动过渡、crossfade 等非必要动画，保留内容和操作顺序。
- `Motion paused`：首页 Selected Works 的 Pause motion 按钮暂停作品带，`aria-pressed=true`；再次点击 Resume motion 恢复。系统开启 reduced motion 时自动停止动效并隐藏该按钮。

点击效果：导航链接进入对应规范路径并标记 active；账户头像进入 Dashboard，三点按钮打开账户菜单；Footer 的 Contact CTA 进入真实咨询表单；Privacy/Terms 可从注册和 Footer 到达。

## 5. 需求规格

### 一致性与可访问性

- 桌面 Header 高度约 64px，移动约 56px；账户容器预留固定尺寸。
- 所有可操作项必须有可见 focus、可读 accessible name、键盘等价操作和至少 44px 移动触控目标。
- 页面不允许公开左侧 rail、重复搜索/标题或隐形占位造成横向空白。
- 页面只链接真实路由；历史 Collections 原型不能重新进入主导航。
- Header、Footer、Mobile Nav 和 Account Menu 各自只有一个职责，不复制身份、登出或权限请求逻辑。

### 性能目标

- 静态公开页首屏不依赖 Supabase 才能显示品牌和基本内容。
- Header Identity 请求目标 p95 ≤ 500ms；失败时不阻塞页面主体。
- 导航打开/关闭应在一个交互帧内完成，避免等待网络。
- 首页与 About 静态图片声明文件真实尺寸；滚动作品使用 lazy/async，About 首图保持立即加载。正常公开首页使用随发布版本保存的图文；只有服务端明确启用 development + loopback + `MT_LOCAL_ARCHIVE_PREVIEW=1` 才读取 IndexedDB 的 legacy 首页设置。
- 1440×900、1024×768、390×844 下无布局位移导致的主要按钮不可见。

## 6. 异常处理

| 异常 | 用户反馈/显示 | 恢复 |
|---|---|---|
| 身份请求 401 | 显示 Sign In | 点击后进入安全登录流程 |
| 身份请求 5xx/网络失败 | 保留已有身份或显示 initials | 后续页面事件可重新 hydrate |
| 菜单脚本未加载 | HTML 主导航仍可通过普通链接访问 | 不依赖脚本才能到达核心页面 |
| 公开 API 为空 | 显示真实空态 | 不用草稿或旧缓存伪造 published |
| 视口变窄 | 菜单转移动模式 | 关闭菜单并恢复焦点，避免横向滚动 |
| 语言/字体加载失败 | 使用系统字体和现有文本 | 不能阻塞导航和表单 |

## 7. 边界与非目标

- 不在导航层加入搜索后端、推荐算法、通知读取或复杂业务状态；这些由对应模块负责。
- 不通过 Footer 或 Header 暴露 owner UUID、角色内部字段、token、Storage key 或审计数据。
- 不新增社交媒体、Cookie 同意、支付、会员等级等占位入口，除非另立需求规格。
- Collections/Series 文件可以保留 direct-route 兼容，但不能重新成为产品主流程。

## 8. 相关实现与验收

- 页面与脚本：`index.html`、`about.html`、`contact.html`、`works.html`、`lightbox.html`、`privacy.html`、`terms.html`、`global-header.js`、`public-navigation.js`、`site-footer.js`、`styles.css`。
- 验收：`scripts/validate_product_phase0.py`、`scripts/test_header_identity_boundary.py`、`scripts/validate_interaction_integrity.py`、`scripts/test_public_image_contract.py`、`scripts/test_public_browser.py`。浏览器使用隔离合成数据，性能记录属于本地采样，线上 p95 需独立测量。
