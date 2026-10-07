# MT Presence Documentation

本文档目录是项目文档的统一入口。根目录只保留通用的 `README.md` 和 `CHANGELOG.md`。

项目已有生产部署，主域名为 `https://mtdo.cn`；域名迁移和 2026-09-17 完整恢复记录可证明历史部署与备份状态。当前本地变更是否已上线须核对具体 release，本轮优化代码尚未发布。所有会创建 fixture 的 rollback-only 数据库验收均为 development-only；发布前只能在 development 或隔离的 staging/生产恢复克隆执行，不能连接生产主库。

## 阅读顺序

1. [目标产品规格](product/user-upload-admin-spec.md)：最新、最高优先级需求；定义用户系统、图片上传工作台和管理员审核平台，并明确目标产品不需要 Series。
2. [Provider Decisions](architecture/provider-decisions.md)：Phase 0 选定 Supabase Auth/Storage，并定义 Cookie session、服务端权限与私有资产边界。
3. [项目功能地图](architecture/project-map.md)：记录当前代码真实实现、文件职责和修改历史。
4. [数据库设计](architecture/database-design.md)：当前 development Supabase 边界、legacy SQLite 过渡层和生产候选数据模型。
5. [设计系统](design/design-system.md)：视觉、组件、响应式和交互规则。
6. [上传测试](operations/upload-testing.md)：Phase 2A-2F signed Upload、private Draft、Folder、Trash、readiness/Submit 与 trusted scanner 验收步骤。
7. [审核队列测试](operations/review-testing.md)：Phase 3 Reviewer/Admin 权限矩阵、队列/详情/决定验收、开发部署与数据库发布门禁。
8. [公开交付测试](operations/public-delivery-testing.md)：Admin 发布到匿名 Works/creator profile 的 DTO、Storage、回滚数据库与撤销窗口门禁。
9. [企业级交付工作流](operations/enterprise-delivery-workflow.md)：规定提示词、阶段门禁、设计/开发、安全、发布验收与发布评分。
10. [生产部署](operations/production-deployment.md)：发布门禁、备份、迁移、TLS、不可变版本、激活、验收、回滚和首小时观察。
11. [域名迁移](operations/domain-migration.md)：权威 DNS、双域名 TLS、Nginx canonical redirect、应用 origin、Supabase 回调、验证和回滚手册。
12. [最小高可用部署与扩展方案](operations/scalable-production-topology.md)：两台应用 ECS、RDS PostgreSQL 主备、OSS 图片存储、邮箱/X/Telegram 身份认证的最低拓扑、迁移顺序和故障验收。
13. [图片来源](design/image-sources.md)：临时图片来源、授权和正式替换要求。
14. [模块与系统规格](module-specs/README.md)：按认证、账户、公开展示、上传、扫描、审核、治理、通信、审计、数据边界和运维拆分的当前功能规格。
15. [网站优化流程](operations/website-optimization-process.md)：本轮有限优化清单、实施结果、公开页面性能、异常恢复、隔离验收和生产证据。

## 文档分类

### Product

- `product/user-upload-admin-spec.md`：目标产品唯一主规格。需求冲突时以此为准。

### Architecture

- `architecture/project-map.md`：当前代码功能地图。每次修改页面、模块、API、状态或测试后同步更新。
- `architecture/database-design.md`：development 数据模型、资产版本、Archive API 和生产候选迁移边界。
- `architecture/provider-decisions.md`：Supabase Auth/Storage 选择与应用安全边界。

### Design

- `design/design-system.md`：页面布局、组件、视觉 token、动效和响应式规则。
- `design/image-sources.md`：图片素材来源及使用边界。

### Operations

- `operations/upload-testing.md`：本地上传与数据库联调手册。
- `operations/review-testing.md`：Supabase Admin Review Queue 的权限、并发、幂等、浏览器和开发数据库验收手册。
- `operations/public-delivery-testing.md`：published-only Works/creator、anonymous derivative signing、权威空态和 development rollback 验收手册。
- `operations/production-deployment.md`：现有生产服务的发布手册，覆盖 secrets 分离、staging/恢复克隆验收、数据库与 Storage 恢复、release gate、systemd/Nginx/TLS、不可变发布、验证与回滚。
- `operations/domain-migration.md`：生产域名切换手册；覆盖 registrar/权威 DNS 分离、缓存诊断、双域名证书、Nginx 主域/别名/退役域名、应用 origin、Supabase Auth 和回滚。
- `operations/scalable-production-topology.md`：生产环境从单机升级到应用、身份认证、数据库、图片存储分层的权威方案；定义双 ECS、托管 Auth/DirectMail、RDS 主备、OSS/CDN、最低规格、滚动发布和恢复门禁。
- `operations/enterprise-delivery-workflow.md`：所有 Web、产品、工程和发布任务必须遵循的企业级交付流程与主提示词。
- `operations/website-optimization-process.md`：网站优化阶段、当前执行切片、验收命令和回滚规则。

### Module Specifications

- `module-specs/README.md`：模块规格索引、通用状态合同、统一验收原则和维护规则。
- `module-specs/01-authentication-and-security.md`：注册、邮箱验证、登录、OAuth、恢复、MFA、CSRF、Cookie 和会话。
- `module-specs/02-account-profile-and-dashboard.md`：Dashboard、Profile、Avatar、Cover、身份绑定、偏好和会话控制。
- `module-specs/03-public-site-and-navigation.md`：公开页面壳、Global Header、移动导航、Footer、Privacy 和 Terms。
- `module-specs/04-works-archive-and-viewer.md`：Works、搜索/比例筛选、Viewer、独立详情和 Creator 主页。
- `module-specs/05-lightbox-and-inquiry.md`：收藏、选片、Contact inquiry、幂等和手动邮件 fallback。
- `module-specs/06-upload-workspace.md`：Folder、Quick Upload、Draft、自动保存、readiness、Submit、Trash/Restore。
- `module-specs/07-asset-scanner-and-media-pipeline.md`：多版本资产、可信 Scanner、ClamAV、Pillow、lease 和 verdict。
- `module-specs/08-review-queue-and-publication.md`：Reviewer/Admin Review、checklist、决定、发布和 Super Admin self-publish。
- `module-specs/09-admin-governance.md`：Admin Works Takedown/Restore、Admin Users 状态与角色治理。
- `module-specs/10-notifications-and-inbox.md`：通知、未读状态、Inbox 会话、回复、Close/Reopen。
- `module-specs/11-audit-ledger.md`：安全审计列表、详情、过滤和有界 CSV 导出。
- `module-specs/12-data-provider-and-api-boundary.md`：BFF、Supabase、SQLite、Storage、Scanner 和 API 错误边界。
- `module-specs/13-operations-deployment-backup-recovery.md`：发布、健康、备份、告警、恢复和回滚。

## 根目录文档

- `../README.md`：项目简介、运行方式和文件入口。
- `../CHANGELOG.md`：版本变化记录。

## 维护规则

- 不新增“完成报告”“临时方案”“第二份产品规格”等重复文档。
- 目标需求写入 Product 主规格；当前代码职责写入 Project Map；视觉规则写入 Design System；运行步骤写入 Operations。
- 过期内容直接更新权威文档，不通过追加新文件保留冲突版本。
- 文档中的文件路径必须真实存在。
