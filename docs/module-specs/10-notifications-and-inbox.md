# 10 Notifications 与 Inbox 通信系统

## 1. 功能范围与当前能力

通信系统分为：

- Notifications：当前账户的系统通知、未读计数、筛选、标记已读。
- Inbox：作为 inquiry recipient 的会话列表、详情、已读、回复、Close/Reopen。
- Guest delivery fallback：没有配置 outbound provider 时，真实显示 manual email/copy，不伪称发送成功。

主要文件：`notifications.html`/`notifications.js`、`inbox.html`/`inbox.js`、`server.py` 通信 handlers、`20260723_d_communications_audit.sql`。

## 2. 前置条件与权限

- Notifications 需要 active、已登录账户；只返回 recipient-isolated DTO。
- Inbox 需要 active recipient 身份；用户只能读取自己所属 conversation 和 messages。
- 回复、Close/Reopen、mark read 需要 CSRF/Origin、conversation version 和 idempotency key。
- Guest inquiry 可以创建会话，但匿名 response 不包含 recipient 或 conversation 内部 ID；收件人查看需要登录。

## 3. 使用流程

### 3.1 Notifications

1. 页面加载 `/api/notifications/unread-count` 和 cursor 列表。
2. 用户按 unread/all 本地筛选，点击一条可跳到 allowlisted 站内 href。
3. 点击单条或全部 mark read；服务端以 recipient scope 更新，成功后同步计数。
4. 翻页使用 object cursor 和 bounded page size；刷新不丢当前筛选。

### 3.2 Inbox

1. 页面加载 conversation 列表，支持本地 search、status filter、cursor pagination。
2. 选择会话后读取 detail、participants、works、messages；打开时按规则 mark read。
3. 回复框在 open 状态可用；提交前检查非空、长度和当前 version，成功后追加 message、通知并更新 version。
4. Close/Reopen 由确认式状态按钮执行；关闭后回复框禁用，Reopen 后恢复。
5. 409 version conflict 显示 Reload；Reload 后重新加载 detail，不覆盖他人回复。

## 4. 页面状态与用户效果

- `Loading`：列表、详情和消息区域独立显示加载。
- `Empty`：无通知/无会话/无搜索结果分别提供清除筛选或等待提示。
- `Unread`：有明确视觉和 accessible state；标记已读后计数下降。
- `Closed`：状态、输入框 placeholder、发送按钮和说明一致，禁止回复。
- `Provider unavailable`：访客邮件状态显示 manual email/copy；不显示“sent”。
- `Conflict`：保留用户未提交的回复文本，提供 Reload；重新读取后由用户决定是否发送。
- `Permission`：跨 recipient ID 统一返回不可用/403，不暴露存在性。

最终效果：收件人看到隔离的会话和通知；回复形成版本递增的 message；Close/Reopen 改变会话状态；每项动作有可追踪通知/审计，但不向浏览器暴露 raw payload。

## 5. 需求规格

### 数据与隐私

- Notification DTO 固定为 `id,type,title,message,created_at,read_at,href`；href 只能是 allowlisted 站内路径。
- Inbox DTO 不返回 raw provider payload、recipient ID、无关 participant 数据、token、IP 或 Storage 坐标。
- conversation version 是并发控制权威；同一 idempotency key 重放返回首个不可变结果。
- Reply/Close/Reopen 必须 owner/recipient isolated；不能通过 URL 改写 recipient。
- 未配置邮件 provider 时，服务端记录 `provider_unavailable`，客户端提供手动操作，不改变事实状态。

### 性能与容量目标

- 通知/会话列表首屏 p95 ≤ 1s，单页 bounded（建议 ≤50 条），消息详情按需加载。
- 回复/状态 mutation 目标 p95 ≤ 1s；超时显示状态未知并可安全重试。
- 长消息、搜索词、分页 cursor、单会话 message 数量和通知批量 mark 数有上限。
- 390×844 下列表与详情使用可切换单视图，回复区不被键盘遮挡。

## 6. 异常处理

| 异常 | 用户反馈 | 恢复 |
|---|---|---|
| 401/403 | 进入登录或显示不可用 | 不重试敏感请求 |
| 404/跨 recipient | 统一“conversation unavailable” | 返回列表，不暴露 ID |
| 409 version | “Conversation changed” | Reload 后再回复/改状态 |
| 429 | 等待提示 | 保留草稿，不重复发送 |
| provider outage | manual fallback | conversation 仍可读写并保留真实状态 |
| cursor 失效 | 重新从第一页加载 | 保留筛选，提示列表已刷新 |

## 7. 边界与非目标

- 不实现群聊、外部 IM 同步、自动分配销售、邮件营销、附件上传或富文本 HTML。
- 不把 Notifications 变成通用 event bus；每种通知类型必须有固定文案、href 和 recipient policy。
- 不允许已关闭会话继续回复；重开必须是显式授权动作。
- 不声称任何 provider 邮件已经发送，除非服务端有明确成功结果。

## 8. 相关实现与验收

- 页面/脚本：`notifications.html`、`notifications.js`、`inbox.html`、`inbox.js`。
- 服务：`server.py` 通信 handlers；migration `database/migrations/20260723_d_communications_audit.sql`。
- 验收：`scripts/validate_communications_audit.py`、`scripts/test_communications_audit_boundary.py`、`scripts/test_communications_audit_database.py`、`scripts/test_public_delivery_database.py`。
