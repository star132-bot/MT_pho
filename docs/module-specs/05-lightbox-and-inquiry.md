# 05 Lightbox、选片与联系咨询系统

## 1. 功能范围与当前能力

本系统把公开浏览转成可控咨询：Lightbox 保存浏览器中的长期收藏；Inquiry Selection 保存当前会话中准备询价的子集；Contact 表单把明确选择提交为服务端持久化 inquiry/conversation。两种选择必须严格分离。

主要文件：`lightbox.html`、`lightbox.js`、`contact.html`、`contact.js`、`public-archive.js`、`inbox.js`；主要接口为 `POST /api/inquiries` 以及后续 Notifications/Inbox 接口。

## 2. 入口与前置条件

- Works/Viewer/Creator 上的 Add to Lightbox：公开页面可见，但当前操作要求登录。
- `/lightbox.html`：可打开；长期收藏来自当前浏览器 key `mt-presence-lightbox-v1`。
- Contact：匿名和登录用户都可提交，必须通过字段校验、honeypot、CSRF/Origin（若为 mutation）和速率限制。
- 询价选片：只能选择当前公开、已加载、仍有效的作品 ID；不可手工提交任意 UUID 作为作品。
- 选中的 Work/Series 上下文通过 `source`、重复 `work` 参数或受控字段传入。

## 3. 使用流程

### 3.1 收藏与选片

1. 用户在 Works/Viewer 点击 Add to Lightbox；成功后按钮、卡片和数量即时更新，并广播 `mt:lightbox-change`。
2. Lightbox 加载长期收藏，显示移除、清空和本次 Inquiry Selection 工具栏。
3. 用户只勾选本次要询问的作品；选择保存于 sessionStorage `mt-presence-inquiry-selection-v1`，默认 0 selected。
4. 移除长期收藏时同步剪除当前选择中已不存在的 ID；跨标签页通过 `storage`，bfcache 恢复通过 `pageshow` 对齐。
5. 点击 Inquire 只把显式选中 IDs 传给 Contact；没有选择时提供唯一的“先选择作品”下一步。

### 3.2 Contact inquiry

1. Contact 读取 `source=work|lightbox|series` 和明确选中的 published work IDs，展示上下文摘要。
2. 用户填写姓名、邮箱、项目类型、预算（条件字段）、时间、消息和同意项；honeypot 对真人不可见。
3. 客户端校验后获取 CSRF，生成 UUID idempotency key，提交 `POST /api/inquiries`。
4. 服务端再次验证字段、发布作品关联、频控和匿名/登录身份，写入 inquiry/conversation/notification/audit 数据。
5. 成功显示 opaque reference/status；匿名且没有 outbound provider 时明确提示 manual email fallback，不声称邮件已发送。

## 4. 页面状态与操作结果

- `Empty Lightbox`：显示“还没有保存作品”和进入 Works 的入口，不显示空选择器噪音。
- `Loading/Error`：加载显示状态提示；公开 API 超时或失败时显示错误和 Retry loading saved works，隐藏空收藏文案，保留本地已保存 ID。成功重试后重新渲染收藏。
- `Selection 0`：Contact 按钮禁用或提示先选作品；不得自动把全部收藏当作询价对象。
- `Saving`：收藏按钮防重复点击；Contact 提交按钮 busy，保留输入。
- `Validation error`：字段级错误；预算等条件字段仅在对应类型出现。
- `Success`：显示 reference/status、下一步和可复制信息；清理本次 selection，但不清空长期 Lightbox，除非用户明确操作。
- `Duplicate/replay`：同一 idempotency key 返回首次不可变结果，页面显示已有 reference，不创建重复 inquiry。
- `Provider unavailable`：显示手动邮件地址/复制操作和真实状态；不能伪造 sent。

点击收藏的即时效果是单个按钮更新，不重新请求整个档案；点击提交后的最终结果是服务端可追踪 inquiry，收件人可在 Inbox 看到 conversation（登录收件人场景）。

## 5. 需求规格

### 数据与隐私

- 浏览器 Lightbox 只保存公开作品 ID/必要展示数据；不得保存访问 token、原图 URL 或私有字段。
- 服务端只接受当时 published 且属于允许公开集合的作品关联；已下架作品在提交前重新校验并从 selection 移除或返回可解释错误。
- 匿名 response 只返回 opaque reference/status/created_at/replayed/selected count；不返回 recipient、owner、conversation UUID 或原始 payload。
- Inquiry 内容、邮箱和选中作品按隐私保留策略存储；前端不把完整消息写入 URL、analytics 或日志。
- `source=lightbox` 无 work 时必须保持为空；不能隐式提交全部收藏。

### 性能与容量目标

- Lightbox 本地读写不阻塞页面；大于合理收藏数量时采用分页/分批渲染，避免一次性生成巨大 DOM。
- 收藏点击目标 ≤ 150ms 给出视觉反馈；网络请求失败可在原位置回滚。
- Contact 提交目标 p95 ≤ 1s（不含邮件 provider）；超时必须保持可重试且使用同一/新 idempotency 策略明确区分。
- 输入字段、消息长度、选中 ID 数量、请求体大小和频率都设上限；超限前端提示，服务端最终拒绝。

## 6. 异常处理

| 异常 | 用户反馈 | 恢复 |
|---|---|---|
| 作品已下架 | 从选择中移除并说明 | 返回 Works 重新选择 |
| CSRF 过期 | “页面已过期，请重试” | 自动刷新 token 后最多重试一次 |
| 429 频控 | 等待/稍后重试提示 | 不清空表单，不重复发送 |
| 网络超时 | “状态未知，请勿重复提交” | 用 idempotency key 查询/重试 |
| provider 邮件不可用 | 显示 manual mailto/copy | inquiry 仍保留，状态标记 provider_unavailable |
| localStorage/sessionStorage 禁止访问或写入额度不足 | 读取安全降为无可读收藏/选片，写入失败显示局部 Toast | 已保存且仍可读的旧 ID 保留；失败不能伪报保存成功或再次执行可能失败的补偿写入；Contact 通用咨询仍可使用 |

## 7. 边界与非目标

- 不实现购物车、支付、报价、自动排期、CRM 同步、群发营销邮件或社交收藏云同步。
- Lightbox 不是账户云端收藏；清除浏览器数据不承诺跨设备保留。
- 不允许通过 Contact 直接上传附件、访问私有原图或绕过登录取得下载权限。
- 不在前端猜测 provider 是否已发邮件；只有服务端状态或明确 manual fallback 才能显示。

## 8. 相关实现与验收

- 页面/脚本：`lightbox.html`、`lightbox.js`、`contact.html`、`contact.js`、`public-archive.js`。
- 服务：`server.py` 的 inquiry、notification 和 inbox handlers；数据库 migration `20260723_d_communications_audit.sql`。
- 验收：`scripts/test_public_interaction_state.js`、`scripts/test_public_browser.py`、`scripts/test_public_delivery_boundary.py`、`scripts/test_communications_audit_boundary.py`、`scripts/test_communications_audit_database.py`。
