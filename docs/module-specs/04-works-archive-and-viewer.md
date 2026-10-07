# 04 Works 档案、作品查看器与 Creator 主页

## 1. 功能范围与当前能力

本模块负责公开作品浏览、搜索和比例筛选、自然比例 masonry、全屏作品查看器、独立作品详情和公开 Creator 主页。公开读模型只允许 `published` 作品和允许公开的 display/thumbnail derivative。

主要文件：`works.html`、`archive.js`、`public-archive.js`、`work.html`/`work-detail.js`、`creator.html`/`creator.js`、`archive-data.js`、`styles.css`。主要接口为 `GET /api/archive/images`、`GET /api/public/creators/{slug}` 和公开作品详情请求。

## 2. 入口与前置条件

- `/works.html`：匿名或登录均可访问；只读取 published DTO。
- `/works.html?work={id}`：打开某个已发布作品的查看器；不存在或非 published 时显示 unavailable/404。
- `/work.html?id={id}`：独立详情布局；数据必须来自同一公开边界。
- `/creators/{public_slug}`：公开 Creator profile；只显示公开身份和 published works。
- Search/Type/Ratio：不需要登录；Add to Lightbox、Inquire、Download 需要认证，按当前代码的 sign-in gate 处理。

## 3. 用户流程

### 3.1 浏览与过滤

1. 页面读取公开 DTO，显示 Type/Ratio 筛选与自然比例画廊；正常状态不显示技术数据来源文案或重复标题/Count，加载和失败状态提供可见提示。
2. 用户输入 Search；260ms debounce 后更新筛选，状态同步到 `?q=`。
3. 用户选择 Type（All/Abstract/Concrete）或 Ratio（Square、Classic、Portrait、Vertical、Landscape、Cinema、Panorama），URL 同步并保留返回可恢复性。
4. `All` 使用协调 masonry；具体 Ratio 使用同组等宽网格；原图不裁切、不拉伸、不加黑边。

### 3.2 查看器

1. 点击卡片或带 `?work=` 的链接，打开沉浸式 Viewer；背景滚动锁定，焦点进入 Viewer。
2. Toolbar 显示序号和 Fit/Actual；舞台承托完整图片，Info 面板显示标题、说明、尺寸、类型、标签、系列和 Related Works。
3. Prev/Next 按稳定 sequence 切换并同步 URL；Escape/关闭恢复原页面焦点和滚动位置。
4. Add to Lightbox、Inquire、Download 通过公开操作 gate；需要登录时保存安全返回位置。

### 3.3 Creator 与详情

1. 从卡片作者名进入 `/creators/{slug}`；接口返回 cover、avatar、公开身份、availability、links 和 published work list。
2. 点击作品进入统一详情/Viewer；Related Works 只能来自同一公开集合。
3. 数据为空时显示真实的 Creator empty/404，不回退到私有 Dashboard 或 Draft。

## 4. 页面状态与效果

- `Loading`：筛选结果和 Viewer 内容显示局部 loading，不重绘已存在卡片造成滚动跳动。
- `Empty`：没有匹配作品时显示筛选可清除的空态；published 为空时不能用 sample 假装线上有内容。
- `Provider error`：公开 provider 失败时显示可见错误和 Retry loading works 按钮，隐藏“无作品”空态；点击重试保留 URL 筛选。12 秒超时、无效 JSON 或损坏 DTO 都进入错误态，生产环境 fail closed。
- `Unavailable`：作品下架、草稿、ID 不存在或 derivative 不可用时不显示原图，并提供返回 Works。
- `Action gate`：匿名点击收藏/询价/下载时提示登录；登录成功回到原作品和操作意图。
- `Actual size`：只允许舞台内滚动查看大图，不突破页面容器或泄露原图地址。
- `Reduced motion`：禁用 gallery reveal、Viewer 动画和自动过渡，保留键盘导航。

操作结果：过滤器改变 URL 和列表；点击卡片打开对应作品；收藏只更新被点卡片/Viewer 状态和计数，不整页刷新；询价把当前 work ID 显式传入 Contact；下载只返回允许公开的 derivative。

## 5. 需求规格

### 数据、媒体与安全

- 公开 DTO 至少包含稳定 id、title、display/thumbnail URL、ratio label、content type、作者公开信息和必要 metadata；禁止 owner UUID、Storage 坐标、原图 descriptor、checksum、审计字段。
- 只接受 published/current-policy-clean 的 display/thumbnail；original 始终 private。
- 公开 API 200 空结果必须显示空态；不得因为 provider 空或错误重新显示旧 Draft、IndexedDB 私有记录或历史样例。
- URL 参数必须白名单化；`work`、`q`、`type`、`ratio` 超长或非法值要安全忽略/归一化。
- 作品卡片、Viewer、详情、Creator 共享同一公开读取层和 Lightbox 事件，不建立第二套缓存来源。

### 性能与交互目标

- 首屏目标：在公开 API 正常时 p95 ≤ 1.5s；图片加载使用合适的 thumbnail/display，避免一次拉取原图。
- Search debounce 约 260ms；输入期间不阻塞滚动，结果顺序使用 latest-wins，旧请求不能覆盖新筛选。
- 公开作品列表请求通过共享 `fetchArchivePayload()` 在 12 秒内取消等待；请求结束清理计时器，Retry 加载中禁用以防重复请求。移动端比例 tabs 可在有界横向滚动条内触达，页面本身不能横向溢出。
- Viewer 打开目标 ≤ 200ms 显示舞台和 metadata 壳；display 图片异步加载，加载失败可关闭或重试。
- 画廊在 1440/1024/390 视口保持自然比例、无横向溢出；键盘 Tab 顺序稳定。

## 6. 异常处理

| 场景 | 用户反馈 | 系统动作 |
|---|---|---|
| API 超时/5xx | “Works 暂时无法加载” | 保留筛选，允许 Retry；生产不启用样例回退 |
| 作品已下架 | “This work is no longer available” | 清除 Viewer deep link 或显示受控 404，不暴露状态细节 |
| 图片 URL 过期 | 图片不可用提示 | 重新请求允许的 signed derivative，不暴露 Storage key |
| 快速连续筛选 | 只显示最后一次结果 | Abort/latest-wins，旧响应丢弃 |
| 下载失败 | Toast + Retry | 不伪称已下载，不提供原图旁路 |
| Lightbox/登录失败 | 局部错误和登录入口 | 不丢失当前 URL/筛选状态 |

## 7. 边界与非目标

- 不在公开 Works 增加上传、排序 Arrange、治理、批量发布或编辑 metadata；这些属于 Workspace/Admin。
- 不公开原图、EXIF 中敏感位置、未审核作品、私有 Creator 字段或任何审计信息。
- 不把历史 Series/Collections 原型重新扩展成新的内容模型；如果未来要恢复，必须另立产品规格。
- 不通过客户端图片名称启发式替代服务端发布和扫描状态；本地 preview fallback 不代表生产事实。

## 8. 相关实现与验收

- 页面：`works.html`、`work.html`、`creator.html`；脚本：`archive.js`、`public-archive.js`、`work-detail.js`、`creator.js`。
- 服务：`server.py` 的 `handle_archive_images`、`handle_public_works_get`、公开 Creator handlers。
- 验收：`scripts/test_public_delivery_boundary.py`、`scripts/test_public_delivery_database.py`、`scripts/validate_public_delivery.py`、`scripts/test_public_interaction_state.js`、`scripts/test_public_browser.py`。
