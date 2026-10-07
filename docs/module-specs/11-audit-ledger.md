# 11 审计台账系统

## 1. 功能范围与当前能力

审计台账记录敏感的认证、治理、审核、通信和发布动作，提供 Admin 受保护的列表、详情、筛选和有界 CSV 导出。它是不可变证据读取系统，不是业务数据编辑器。

主要文件：`admin-audit.html`、`admin-audit.js`、`admin-audit.css`、`server.py` audit handlers，以及通信、Review、Admin Works/Users migrations 中的 append-only audit 表和 RPC。

## 2. 入口与前置条件

- 入口：`/admin/audit`、`GET /api/admin/audit-logs`、`GET /api/admin/audit-logs/{id}`、`POST /api/admin/audit-logs/export`。
- 只有 active Admin/Super Admin + AAL2 可访问；Reviewer、普通成员、AAL1、recovery session 和 inactive 拒绝。
- 列表过滤支持 actor/request/date 等 allowlisted 字段；导出必须再次做权限、范围和大小检查。
- 审计记录只读；任何修正只能通过产生新审计事件，不能 UPDATE/DELETE 旧证据。

## 3. 使用流程

1. 管理员进入页面，列表区域加载最近审计事件；桌面使用 inventory/inspector，移动端使用单视图切换。
2. 选择 action、actor、request、日期范围或对象类别过滤；服务端使用 bounded cursor 分页。
3. 点击一条记录，详情显示安全投影：时间、动作、结果、错误码、版本、policy 和必要父对象关联。
4. 点击 Export，确认当前过滤范围；服务端生成有界 CSV，跳过 raw payload、邮箱、token、Storage 坐标、IP 等禁止字段。
5. 导出成功显示下载结果和记录数量；超限或无权限时不生成部分文件。

## 4. 页面状态与操作结果

- `Loading`：列表和详情独立显示；不会因一条详情失败清空列表。
- `Empty`：明确显示“当前过滤无记录”，提供清除过滤。
- `Forbidden`：统一权限/MFA 反馈，不显示 audit 是否存在的敏感差异。
- `Malformed filter`：忽略或拒绝非法字段、超长文本和过大日期范围。
- `Export busy`：防止重复导出；成功后显示有限行数和文件状态。
- `Export failed`：显示可重试错误，不提供半截 CSV 或 raw provider 错误。

最终结果是管理员可以回答“谁在什么时间以什么角色对什么版本做了什么动作、结果如何”，但不能通过台账读取私密业务正文。

## 5. 需求规格

### 不可变与最小披露

- Audit insert-only；成功和失败动作都可记录，但不存在对象的攻击者控制目标不能创建虚假关联。
- metadata 只允许白名单字段：action、reason code、error code、version、policy、request/idempotency 关联等。
- 列表、详情、导出共享同一安全 DTO 投影；不能因为 CSV 导出绕过页面字段限制。
- 查询过滤、排序、分页和导出行数全部 bounded，避免任意全表导出。
- 审计页面不得显示密码、access/refresh token、CSRF、IP、完整邮箱、用户消息正文、Storage signed URL 或原图 descriptor。

### 性能与容量目标

- 列表首屏 p95 ≤ 1.5s，单页建议 ≤50 条；详情 p95 ≤1s。
- 导出在有界范围内 p95 ≤5s；超过行数/字节限制时提前拒绝并给出调整范围提示。
- 索引覆盖时间、action、actor/request 关联和 created_at；游标分页不使用无限 offset。
- 移动端 390×844 可查看详情字段，不需要横向滚动完整表格。

## 6. 异常处理

| 异常 | 反馈 | 恢复 |
|---|---|---|
| AAL/角色不足 | MFA/权限提示 | 返回安全入口 |
| 日期/字段非法 | 字段错误 | 修正过滤器 |
| Cursor 过期 | “列表已更新，请重新加载” | 从第一页开始 |
| 导出超限 | 说明缩小时间或筛选范围 | 不生成部分文件 |
| DB/provider 故障 | 可重试错误 | 不返回 raw SQL/provider 内容 |
| 记录缺少父对象 | 显示安全 unavailable | 保留事件本身，不拼接猜测对象 |

## 7. 边界与非目标

- 不提供审计记录编辑、删除、恢复、批量清理或用户可见的完整内部备注。
- 不把 Audit Ledger 做成日志搜索平台、SIEM、实时告警中心或业务报表系统。
- 不从审计记录推断当前用户、会话或配额状态；当前状态由对应权威模块读取。

## 8. 相关实现与验收

- 页面/脚本：`admin-audit.html`、`admin-audit.js`、`admin-audit.css`。
- 服务：`server.py` 的 audit list/detail/export handlers；通信与治理 migrations 的 audit contracts。
- 验收：`scripts/validate_communications_audit.py`、`scripts/test_communications_audit_boundary.py`、`scripts/test_admin_works_database.py`、`scripts/test_admin_users_database.py`。
