# MT Presence Documentation

本文档目录是项目文档的统一入口。根目录只保留通用的 `README.md` 和 `CHANGELOG.md`。

## 阅读顺序

1. [目标产品规格](product/user-upload-admin-spec.md)：最新、最高优先级需求；定义用户系统、图片上传工作台和管理员审核平台，并明确目标产品不需要 Series。
2. [Provider Decisions](architecture/provider-decisions.md)：Phase 0 选定 Supabase Auth/Storage，并定义 Cookie session、服务端权限与私有资产边界。
3. [项目功能地图](architecture/project-map.md)：记录当前代码真实实现、文件职责和修改历史。
4. [数据库设计](architecture/database-design.md)：当前 Supabase Workspace、legacy SQLite 公开/Review 层和后续生产迁移边界。
5. [设计系统](design/design-system.md)：视觉、组件、响应式和交互规则。
6. [上传测试](operations/upload-testing.md)：Phase 2A-2F signed Upload、private Draft、Folder、Trash、readiness/Submit 与 trusted scanner 验收步骤。
7. [审核队列测试](operations/review-testing.md)：Phase 3 Reviewer/Admin 权限矩阵、队列/详情/决定验收、开发部署与数据库发布门禁。
8. [公开交付测试](operations/public-delivery-testing.md)：Admin 发布到匿名 Works/creator profile 的 DTO、Storage、回滚数据库与撤销窗口门禁。
9. [企业级交付工作流](operations/enterprise-delivery-workflow.md)：规定提示词、阶段门禁、设计/开发、安全、发布验收与发布评分。
10. [图片来源](design/image-sources.md)：临时图片来源、授权和正式替换要求。

## 文档分类

### Product

- `product/user-upload-admin-spec.md`：目标产品唯一主规格。需求冲突时以此为准。

### Architecture

- `architecture/project-map.md`：当前代码功能地图。每次修改页面、模块、API、状态或测试后同步更新。
- `architecture/database-design.md`：数据模型、资产版本、Archive API 和生产迁移方向。
- `architecture/provider-decisions.md`：Supabase Auth/Storage 选择与应用安全边界。

### Design

- `design/design-system.md`：页面布局、组件、视觉 token、动效和响应式规则。
- `design/image-sources.md`：图片素材来源及使用边界。

### Operations

- `operations/upload-testing.md`：本地上传与数据库联调手册。
- `operations/review-testing.md`：Supabase Admin Review Queue 的权限、并发、幂等、浏览器和开发数据库验收手册。
- `operations/public-delivery-testing.md`：published-only Works/creator、anonymous derivative signing、权威空态和 development rollback 验收手册。
- `operations/enterprise-delivery-workflow.md`：所有 Web、产品、工程和发布任务必须遵循的企业级交付流程与主提示词。

## 根目录文档

- `../README.md`：项目简介、运行方式和文件入口。
- `../CHANGELOG.md`：版本变化记录。

## 维护规则

- 不新增“完成报告”“临时方案”“第二份产品规格”等重复文档。
- 目标需求写入 Product 主规格；当前代码职责写入 Project Map；视觉规则写入 Design System；运行步骤写入 Operations。
- 过期内容直接更新权威文档，不通过追加新文件保留冲突版本。
- 文档中的文件路径必须真实存在。
