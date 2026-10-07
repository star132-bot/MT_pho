# 08 Review Queue 与发布系统

## 1. 功能范围与当前能力

Review 系统把用户 Submitted Draft 交给 Reviewer/Admin 审核，保存 checklist、证据、决定和不可变审计；Publication 系统把符合条件的审核结果原子发布到公开 Works 和 Creator profile。两者是同一安全边界的不同阶段。

主要文件：`admin-reviews.html`、`admin-reviews.js`、`server.py` Review handlers、Phase 3/公开交付 migrations 和 `styles.css`。

## 2. 入口与前置条件

| 角色/状态 | 能力 |
|---|---|
| 未登录/普通成员 | 不能进入 Review Queue |
| Reviewer + active + AAL2（按部署策略） | 可查看非本人 waiting/open assigned，claim/start 后审核 |
| Admin/Super Admin + AAL2 | 可看授权历史，决定并可 Approve and publish |
| Super Admin + AAL2 | 在严格条件下可 self-publish 自己 untouched/unassigned Submitted 作品 |
| Recovery/AAL1/self-review | 服务器拒绝，不能通过前端绕过 |

作品必须是当前 Submitted、版本一致、资产当前 clean、证据/rights 完整；Admin 的 original 访问仍受 derivative-only policy 限制。

## 3. 流程

### 3.1 Queue 与 Claim

1. 页面读取 `/api/admin/review-submissions`，按状态、assignment、cursor 显示 queue。
2. 用户点击一项进入 detail/deep link；移动端 Queue/Detail 互斥切换，不需滚过整页。
3. Reviewer 执行 Start/claim；数据库原子锁定 assignment、版本和 lease，其他 Reviewer 看到冲突或无权访问。
4. 页面加载 submitted snapshot、图片 derivative、rights/evidence/history 和 checklist。

### 3.2 决定

1. Reviewer/Admin 按十项政策 checklist 检查；失败项聚焦首个缺失项并用 assertive alert 说明。
2. 选择 Request Changes、Reject 或 Approve；需要原因时强制填写非空理由。
3. mutation 带当前 `lock_version`、CSRF、UUID idempotency；服务端重新检查 self-review、role、AAL、资产和状态。
4. 决定成功后写 notifications 和 append-only audit；页面更新 history、queue status 和下一项。

### 3.3 Publish 与 Super Admin self-publish

- Admin/Super Admin 的 Approve and publish 只有在批准条件、三类 current-policy-clean derivative、版本和权限都满足时才公开。
- Super Admin self-publish 只能选择本人、未领取、未开始审核、Submitted、checklist 完整的作品；批量 UI 只是逐件调用同一 dedicated endpoint，每件独立 CAS/idempotency/audit。
- Publication 原子改变 visibility 和 derivative public flags；original 永远 private。

## 4. 页面状态与结果

- `Queue loading/empty/error`：局部状态和 Retry；不显示未经授权的总数或记录。
- `Claiming`：按钮 busy/disabled；成功显示 assigned/current lock，失败说明已被领取或权限不足。
- `Asset unavailable`：阻止决定或只显示允许的 derivative；不回退到原图公开路径。
- `Checklist incomplete`：Approve/Publish disabled；焦点和提示指向第一项缺失策略。
- `Conflict 409`：显示版本已变化，要求 Reload；保留未提交备注但不自动覆盖。
- `Decision success`：显示新状态、通知/审计完成和返回 Queue；重复点击 replay 首次结果。
- `Batch self-publish`：一项成功移出选择；失败项保留选中并显示独立错误，不能清空成功审计证据。

## 5. 需求规格

### 权限、并发、数据

- 所有读取和 mutation 在 PostgreSQL/RPC 层再次检查 actor、role、AAL、recovery、owner/self-review、submission 状态和版本；UI 隐藏不等于权限。
- Claim/Start、decision、publish 使用原子 CAS、idempotency 和可审计失败记录；同一 key replay 不重复发布。
- Detail DTO 按父记录 ID 绑定后再投影浏览器字段；Storage key、owner UUID、内部备注和 raw provider payload 不进入 DOM。
- 公开发布只暴露 current clean display/thumbnail；任何状态不确定都不发布。

### 性能与体验目标

- Queue 首次列表 p95 ≤ 1.5s；采用 cursor pagination 和 bounded page size，不拉取全库。
- Claim/decision/publish 正常请求目标 p95 ≤ 1s（不含 Storage signed URL）；超时显示未知状态并支持按 idempotency 查询。
- 详情图片先显示 thumbnail/metadata 壳，再按权限加载 derivative；移动端 detail 不遮挡决定操作。
- 审核页面在 1440×1000 与 390×844 都可完成 checklist、对话框确认和焦点操作。

## 6. 异常处理

| 异常 | 用户反馈 | 恢复 |
|---|---|---|
| 未授权/AAL不足 | 登录/MFA 或权限说明 | 进入正确守卫，不暴露记录存在性 |
| 已被他人 claim | “This submission is assigned” | 返回队列或等待 assignment 释放 |
| self-review | “You cannot review your own work” | mutation 服务器拒绝，前端不提供旁路 |
| checklist 不完整 | 首个缺失项提示 | 补充证据或选择 Request Changes |
| 版本冲突 | Reload 当前记录 | 重新检查后再决定 |
| Storage/scan 不一致 | 暂停决定或发布 | 等待当前扫描/重新上传，不能强制批准 |
| provider 失败 | 保留 detail 和输入 | Retry；不显示虚假的已发布状态 |

## 7. 边界与非目标

- Reviewer 不负责用户角色治理、作品 Takedown、密码/MFA 管理或数据库修复。
- 批量操作不创建第二套“批量发布”规则；每件作品必须走同一单件服务端 endpoint。
- 不允许 Admin 查看 original，除非既有明确、独立授权的 Reviewer submission policy；不把原图放入公开发布路径。
- 不实现自动 AI 审稿、自动批准、评论社区或复杂工作流编排。

## 8. 相关实现与验收

- 页面/脚本：`admin-reviews.html`、`admin-reviews.js`。
- 服务：`server.py` 的 review list/detail/assignment/start/decision handlers。
- 验收：`scripts/validate_review_queue_phase3.py`、`scripts/test_review_queue_boundary.py`、`scripts/test_review_queue_database.sql`、`scripts/test_review_queue_concurrency.py`、`scripts/test_review_queue_browser.py`、`scripts/test_review_batch_browser.py`、`scripts/test_public_delivery_boundary.py`。
