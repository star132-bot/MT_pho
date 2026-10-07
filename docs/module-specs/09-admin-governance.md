# 09 Admin Works 与 Admin Users 治理系统

## 1. 功能范围与当前能力

Admin Governance 分成两个工作台：

- Admin Works：查看全量作品状态、证据和治理历史，执行带原因的 Takedown/Restore。
- Admin Users：查看账户目录、状态、角色和安全摘要；Admin 可 suspend/reactivate，Super Admin 才能管理 Reviewer/Admin 角色，并可记录 session revocation provider intent。

主要文件：`admin-works.html`/`admin-works.js`、`admin-users.html`/`admin-users.js`、`server.py` admin handlers、Phase 4A/4B migrations。

## 2. 入口、前置条件与权限

- `/admin/works`、`/admin/users` 只允许 active Admin/Super Admin + AAL2；recovery session、AAL1、普通成员和 inactive 拒绝。
- Admin Works 的公开状态操作需要目标作品存在、版本匹配、合法原因和当前资产/发布政策通过。
- Admin Users 的状态操作不能治理自己、system identity、不可降级的基线角色或最后一个 active non-system Super Admin。
- 角色变化只允许 Super Admin；session revoke 返回 provider action intent，不声称 provider 会话已经关闭。

## 3. 使用流程

### 3.1 Admin Works

1. 页面加载状态计数、搜索、排序和 cursor 分页；用户可通过 `?work=` 深链打开详情。
2. Detail 显示 current/history version、latest review、submission、decision、governance action 和审计摘要；只显示允许的 derivative preview。
3. Published 作品点击 Takedown，填写用户可见原因和内部备注，确认后提交 CAS/idempotency mutation。
4. Taken down 作品点击 Restore；服务端重新核验 active owner、approved/current locked version、三类 clean assets、scan job 和 Storage object 精确一致。
5. 成功后更新状态、creator notification、takedown case 和 audit；失败保留详情并显示错误。

### 3.2 Admin Users

1. 页面显示 account state counts，支持搜索、role/status filter、sort、cursor pagination。
2. 用户详情显示身份、profile、安全状态、角色、会话意图和历史；缺失的 provider 数据显示 unavailable。
3. Admin 选择 Suspend/Reactivate；Super Admin 选择 Grant/Revoke Reviewer/Admin；session revocation 需显式确认。
4. 所有 mutation 带当前 user version、CSRF、UUID idempotency；409 时要求 Reload。

## 4. 页面状态与结果

- `Permission denied`：统一受保护跳转/MFA/403；不显示目标是否存在的敏感差异。
- `List empty`：说明筛选条件无结果，并提供清除筛选；不把权限不足当成空列表。
- `Detail loading/error`：右侧 inspector 独立加载；列表可继续使用。
- `Mutation busy`：禁用重复按钮，确认对话框显示 action、原因要求和影响。
- `Conflict`：显示记录已变更，禁用继续 mutation，提供 Reload。
- `Success`：状态计数、列表行、详情、通知和审计反馈同步；session revoke 显示 provider_action_required。

点击 Takedown 的最终效果是公开 derivative 不再可见，original 仍 private；Restore 只有所有当前门禁再次通过才恢复公开。Suspend 成功后账户访问受限；角色变化立即影响后续权限；revoke 只是记录需由 provider 完成的动作。

## 5. 需求规格

### 治理与审计

- PostgreSQL RPC 是权威权限与状态边界；BFF 不能通过拼接参数绕过 actor/AAL/role/CAS。
- 每次成功或失败治理动作写 append-only audit；metadata 仅保留 allowlisted action/reason、错误码、版本和 policy，不记录密码、token、内部备注或用户消息全文。
- Admin Works 禁止 original descriptor、Storage coordinates、checksum 和 owner UUID 投影浏览器。
- Admin Users 对 MFA、active session count、quota 只能显示 provider-managed/unavailable，不能从角色或活动时间推断。
- 所有列表有 bounded page size、白名单 sort/filter、稳定 cursor 和最大搜索长度。

### 性能与可靠性目标

- 列表首屏 p95 ≤ 1.5s；详情 p95 ≤ 1.5s（不含 signed preview）；分页不读取全量表。
- 治理 mutation 目标 p95 ≤ 1s；超时必须能用 idempotency key 查询，不重复执行。
- 移动端 390×844 使用 Inventory/Detail 单视图切换，操作栏不被详情内容遮挡。
- 关键操作前后都显示版本、状态和结果，避免管理员误以为 provider 会话或公开对象已完成变化。

## 6. 异常处理

| 异常 | 反馈 | 处理 |
|---|---|---|
| AAL/MFA/recovery 不满足 | 跳 `/auth/mfa` 或受控 403 | 不加载敏感详情 |
| 目标不存在/无权 | 统一 unavailable/not found | 不创建攻击者可控审计目标 |
| CAS 冲突 | “Record changed elsewhere” | Reload 后重做判断 |
| 原因为空/非法 | 字段级错误 | 不发送 mutation |
| Restore asset 不 clean | 显示缺失门禁 | 保持 taken down |
| provider revoke 未完成 | 明确 provider action required | 写 intent/notification，不谎称会话已关闭 |
| 最后 Super Admin/系统账户保护 | 解释不可执行 | 保持原状态 |

## 7. 边界与非目标

- 不在 Admin Works/Users 实现数据库 shell、直接 SQL、Storage 任意浏览、密码查看或手工改审计。
- 不允许 Admin 自己提升为 Super Admin，不允许删除最后的安全主体，不允许治理 system identity。
- 不把“记录 provider intent”扩展成应用自行管理 Supabase session；必须等待 provider 权威结果。
- 不增加批量 Takedown、批量角色授予等高风险功能，除非另有逐项审计和回滚规格。

## 8. 相关实现与验收

- 页面/脚本：`admin-works.html`、`admin-works.js`、`admin-users.html`、`admin-users.js`。
- 服务：`server.py` 的 Admin Works/Users handlers；migrations `20260723_admin_works_governance.sql`、`20260723_b_admin_user_governance.sql`。
- 验收：`scripts/validate_admin_works.py`、`scripts/test_admin_works_boundary.py`、`scripts/test_admin_works_database.py`、`scripts/validate_admin_users.py`、`scripts/test_admin_users_boundary.py`、`scripts/test_admin_users_database.py`。
