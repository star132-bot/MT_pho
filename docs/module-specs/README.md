# MT Presence 模块与系统规格

## 文档目的

本目录把 MT Presence 当前代码拆成可独立验收的模块和系统规格。每份文档都说明：

- 功能能解决什么问题，以及当前代码已经支持到什么程度。
- 用户进入功能前必须满足的身份、权限、页面和数据条件。
- 从进入页面到完成操作的完整流程。
- 页面在 loading、empty、error、success、disabled、permission 和冲突场景中的显示方式。
- 用户点击后的可观察效果和最终结果。
- 性能、容量、可靠性、安全性和可维护性要求。
- 异常如何恢复、如何反馈，以及功能明确不处理什么。

文档描述的是当前项目的真实边界。没有实现的能力会标记为“未实现/不属于当前范围”，不能把它当成已有功能交付。

## 模块分类

| 文档 | 模块/系统 | 主要入口 | 当前状态 |
|---|---|---|---|
| [01-authentication-and-security.md](01-authentication-and-security.md) | 认证与安全系统 | `/auth/*`、`/auth/mfa` | 已实现；依赖 Supabase Auth |
| [02-account-profile-and-dashboard.md](02-account-profile-and-dashboard.md) | 账户、个人主页与账户设置 | `/dashboard`、`/settings/account` | 已实现；受保护 |
| [03-public-site-and-navigation.md](03-public-site-and-navigation.md) | 公开站点、导航、页脚与法律页面 | `/`、`/about.html`、`/privacy.html`、`/terms.html` | 已实现 |
| [04-works-archive-and-viewer.md](04-works-archive-and-viewer.md) | Works 档案、作品查看器与 Creator 主页 | `/works.html`、`/work.html`、`/creators/{slug}` | 已实现；只展示 published |
| [05-lightbox-and-inquiry.md](05-lightbox-and-inquiry.md) | Lightbox、选片与联系咨询 | `/lightbox.html`、`/contact.html` | 已实现；询价由服务端持久化 |
| [06-upload-workspace.md](06-upload-workspace.md) | 上传工作台、文件夹、Draft、Trash | `/workspace/images` | 已实现；需要登录 |
| [07-asset-scanner-and-media-pipeline.md](07-asset-scanner-and-media-pipeline.md) | 图片资产管线与可信扫描系统 | Upload API、独立 Scanner | 已实现；Scanner 必须独立运行 |
| [08-review-queue-and-publication.md](08-review-queue-and-publication.md) | Review Queue 与发布系统 | `/admin/reviews` | 已实现；按角色和 AAL2 控制 |
| [09-admin-governance.md](09-admin-governance.md) | Admin Works 与 Admin Users 治理系统 | `/admin/works`、`/admin/users` | 已实现；Admin/Super Admin |
| [10-notifications-and-inbox.md](10-notifications-and-inbox.md) | Notifications 与 Inbox 通信系统 | `/workspace/notifications`、`/inbox` | 已实现；收件人隔离 |
| [11-audit-ledger.md](11-audit-ledger.md) | 审计台账系统 | `/admin/audit` | 已实现；只读安全投影 |
| [12-data-provider-and-api-boundary.md](12-data-provider-and-api-boundary.md) | 数据、Provider、BFF 与 API 边界 | `server.py`、Supabase、SQLite | 已实现；两套数据边界并存 |
| [13-operations-deployment-backup-recovery.md](13-operations-deployment-backup-recovery.md) | 发布、健康检查、备份与恢复运维系统 | `deploy/`、`scripts/` | 候选运维能力；生产激活需单独验收 |

## 通用状态合同

所有用户可见功能必须至少考虑以下状态；不适用时在具体文档说明原因：

1. `Loading`：请求或本地处理进行中，操作控件禁用或显示进度。
2. `Empty`：没有数据时给出原因和唯一合理的下一步，不用假数据填充真实空结果。
3. `Success`：显示可理解的成功反馈，并更新权威状态。
4. `Error`：保留用户可恢复的输入，显示可执行的错误信息，不泄露 token、内部 ID 或 provider 原文。
5. `Conflict`：并发版本冲突时要求重新加载权威记录，不能静默覆盖他人修改。
6. `Permission`：未登录、未验证、恢复会话、AAL1、角色不足和 inactive 状态分别处理。
7. `Boundary`：对超大文件、过长文本、重复提交、非法 URL、过期链接和不支持的扩展行为 fail closed。

## 统一验收原则

- 桌面 1440×900、平板 1024×768、移动 390×844 不出现横向溢出、遮挡或无法操作的控件。
- 所有 mutation 使用同源 CSRF 和 Origin 校验；需要幂等的操作使用 UUID idempotency key。
- 服务端返回稳定错误码和面向用户的消息；浏览器不把 provider secret、access token、Storage key 或内部审计字段写入 DOM/Storage。
- 公开端只读取 published 和允许公开的 derivative；原图、Draft、扫描中或下架记录不可通过公开接口复活。
- 文档里的“性能目标”是验收门槛，不代表本机或生产已经完成压测；实际部署还要记录测量结果。

## 关联权威文档

- 当前代码职责：[项目功能地图](../architecture/project-map.md)
- 目标产品范围：[用户上传与管理员规格](../product/user-upload-admin-spec.md)
- Provider 与安全边界：[Provider Decisions](../architecture/provider-decisions.md)
- 数据模型：[数据库设计](../architecture/database-design.md)
- 运维流程：[生产部署](../operations/production-deployment.md)

## 维护规则

- 新增页面、API、角色、状态或外部依赖时，先更新对应模块规格，再更新 `docs/architecture/project-map.md` 和本索引。
- 规格只记录真实实现和可验收要求；路线图、会议记录和一次性运行日志放到 Operations 或单独记录中。
- 删除功能时同步删除入口、流程、状态和验收标准，不能只在文档中标记过期。
