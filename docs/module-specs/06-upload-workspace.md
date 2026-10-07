# 06 上传工作台、文件夹、Draft 与 Trash

## 1. 功能范围与当前能力

Upload Workspace 是创作者的受保护工作区，负责文件夹、批量导入、三类 private asset 上传、Draft metadata、自动保存、提交前 readiness、Submit for Review、Trash/Restore。它不负责审核决定、公开发布或硬删除。

主要文件：`upload-studio.html`、`upload-studio.js`、`archive-upload.js`、`dashboard.js`（复用封面候选链路）；服务端为 folders、uploads、images、readiness、draft mutation handlers。

## 2. 入口与前置条件

- 入口：`/workspace/images`；直接访问 `/upload-studio.html` 应 canonicalize 到该路径。
- 必须是 active、已验证的普通成员或具备允许的工作区身份；recovery session、未验证邮箱、inactive 和未登录拒绝。
- 所有修改需要 CSRF/Origin；每个对象按当前用户 owner scope。
- 浏览器需要支持 File API、图片解码和 signed URL；服务端需要配置 Supabase Storage 和 trusted scanner。

## 3. 使用流程

### 3.1 文件夹

1. 页面先加载 Folder 列表和 Draft 计数；没有文件夹时显示空态和创建入口。
2. 用户创建、重命名、删除或恢复 folder；删除前服务端处理其中 Draft 的约束，不直接丢弃作品。
3. 当前 Folder 决定 Draft 列表和批量 Submit 范围。

### 3.2 Quick Upload

1. 用户选择一个或多个文件；客户端读取尺寸、MIME、checksum、基础 EXIF，生成 original/display/thumbnail/square_slice 资产记录。
2. Quick Upload 可一次声明 content category、版权、release、AI/sensitive disclosure、tags/location、Alt Text 模板，应用到本批 private Draft；这些默认值只在当前 tab 临时记忆。
3. 每个文件进入双并发队列，显示读取、压缩、切片、上传、complete 状态；用户可 Cancel、Retry、Remove。
4. 服务端创建 signed upload intents；浏览器向 private bucket 上传三类资产，完成后创建 Draft。
5. 创建后进入 Draft 编辑器；服务端版本号是唯一权威，IndexedDB 只做离线只读缓存。

### 3.3 Draft 编辑、Ready 与提交

1. 用户编辑标题、说明、版权、release、content type、tags、location、Alt Text 等字段。
2. 900ms debounce 自动保存，也可手工 Save；请求带 `expected_version`。
3. 页面读取五项 server-authoritative readiness；pending 时最多按策略轮询，不在浏览器自行写 scan verdict。
4. 只有 Ready Draft 可显示 Submit for Review；确认后逐件重新读取最新 readiness 并幂等提交。
5. 提交成功后 Draft 进入 Submitted/Review Queue；失败/Blocked/Pending 项仍留在列表并标出原因。

### 3.4 Trash

- Draft soft-delete 进入 Trash；Restore 恢复 owner scope 的可编辑 Draft。
- 当前范围不提供 hard delete；对象清理由取消上传和服务端生命周期策略处理。

## 4. 页面状态与结果

- `Loading`：Folder、Draft、上传队列、readiness 分区独立显示 loading；不能因为一个图片失败让整批消失。
- `Empty`：无 Folder、无 Draft、空 Trash 分别提供对应下一步。
- `Queue progress`：每个文件有明确阶段、进度、取消/重试；上传中禁用重复 complete。
- `Draft dirty`：显示 Unsaved；离开时提示；保存中按钮 disabled。
- `Pending/Blocked`：显示服务器 readiness 检查项、预计下一步和 Retry/Reload；不能显示“可以提交”。
- `409 Conflict`：保留本地表单，显示另一会话已修改，用户选择 Reload 权威版本或重新编辑。
- `Success`：上传完成显示 Draft；保存显示时间/状态；提交后进入 Review queue link；Restore 回到原 Folder。

点击结果：Cancel 取消当前 upload intent 并尽力清理对象；Retry 只重试失败项；Remove 从当前队列移除未提交项；Submit 不会把整个 Folder 无条件提交，只有当时重新验证 Ready 的项成功。

## 5. 需求规格

### 数据与安全

- 原图、display、thumbnail、square slice 都是 private Storage asset；对象 metadata 与数据库 image/version 必须一致。
- 每个 mutation 必须 owner scoped、CSRF protected、幂等或具备版本 CAS；客户端不可信的 `folder_id`、`image_id`、scan verdict 必须重新验证。
- 文件允许类型为 JPG/PNG/WebP；尺寸、字节数、像素数、文件名、EXIF 和请求体设上限。
- 取消、失败和过期 intent 必须清理孤儿对象或进入可审计待清理状态，不能让它们出现在公开列表。
- 批量声明只作为默认值，不改变每张图服务端的最终政策和 readiness。

### 性能与容量目标

- 上传队列最多两路并发（当前实现），单图处理不阻塞 UI；大图处理应在 Web Worker/受控任务中执行。
- 自动保存 debounce 约 900ms，连续输入不产生请求风暴；p95 保存响应目标 ≤ 1s。
- readiness 轮询有上限和退避，页面不可因永久 pending 无限请求。
- 单批文件数、总字节数、每文件像素和 metadata 长度均有明确限制；接近上限时提前提示。
- 移动端队列和编辑器可滚动，操作按钮不会被固定 footer 或键盘遮挡。

## 6. 异常处理

| 异常 | 用户反馈 | 恢复 |
|---|---|---|
| 文件类型/尺寸不合规 | 在对应文件项显示具体原因 | 移除该项，其他项继续 |
| signed URL 过期 | 上传失败和 Retry | 重新申请 intent，不复用过期 URL |
| scanner retry | Pending/Retry 状态 | 由 worker 按 lease 重试，用户不能手工标 clean |
| autosave 409 | Conflict banner | Reload 权威版本后重编辑 |
| readiness blocked | 列出未通过检查 | 修改字段/等待扫描后重新读取 |
| provider 5xx | 全局错误但保留本地输入 | 指数退避/手工 Retry |
| 浏览器关闭 | 未完成队列标记 interrupted | 重新进入后只恢复安全的服务端 Draft，不恢复伪造进度 |

## 7. 边界与非目标

- 不在 Upload Workspace 放置 Review decision、Approve、Publish、Takedown、Restore publication 或 Admin 用户管理按钮。
- 不提供硬删除、任意 Storage 浏览、原图公开链接、浏览器端扫描结果写入和跨账户移动 Draft。
- 不把 IndexedDB 当作生产数据库；离线缓存不能改变服务器状态。
- 不引入另一套上传 SDK、状态管理或 metadata schema；复用 `archive-upload.js`、BFF 和既有 Storage contract。

## 8. 相关实现与验收

- 页面/脚本：`upload-studio.html`、`upload-studio.js`、`archive-upload.js`。
- 接口：`/api/folders`、`/api/images`、`/api/uploads/intents`、`/api/uploads/{id}`、`/api/images/{id}/readiness`、`/api/images/{id}/submit`。
- 验收：`scripts/validate_workspace_phase2.py`、`scripts/test_workspace_phase2_boundary.py`、`scripts/validate_workspace_asset_scanner.py`、`scripts/test_workspace_asset_scanner.py`、`scripts/test_workspace_trash_browser.py`、`scripts/test_manage_production_release.py`。
