# 12 数据、Provider、BFF 与 API 边界系统

## 1. 功能范围与当前能力

本系统定义浏览器、Python BFF、Supabase Auth/REST/Storage、PostgreSQL RPC、可信 Scanner 和 legacy SQLite 之间的责任边界。它不是一个页面，而是全项目必须遵守的数据流和安全合同。

主要实现：`server.py`、`database/schema.sql`、`database/migrations/`、`data/`、`archive-data.js`、`public-archive.js`、`docs/architecture/provider-decisions.md`。

## 2. 数据分层

| 层 | 责任 | 可以成为何种权威 |
|---|---|---|
| 浏览器状态 | URL、表单、临时 UI、Lightbox/session selection | 只对当前交互权威，不对权限/扫描权威 |
| BFF | Cookie、CSRF、DTO、路由和 provider 编排 | 浏览器唯一业务 API 边界 |
| Supabase Auth | 用户、OAuth、session、MFA factor | 认证与 provider session 权威 |
| PostgreSQL/RPC | Profile、Draft、Review、治理、通信、审计 | 业务状态、RLS、CAS、idempotency 权威 |
| Supabase Storage | private/original/derivative object | 媒体对象和 signed URL 权威 |
| Scanner | 当前政策安全 verdict | clean/flagged/failed/retry 权威 |
| SQLite/IndexedDB/sample | legacy archive/本地 preview 过渡 | 仅 development/preview，不可覆盖生产事实 |

## 3. 请求流程与前置条件

1. 浏览器调用 allowlisted `/api/*`，不会直连带 privileged key 的 Supabase。
2. BFF 校验 method、Content-Type、body size、Origin、CSRF、session/recovery/AAL/role，并规范化输入。
3. BFF 使用 provider access token 调 Auth/REST/RPC，按固定 DTO 投影结果，隐藏 raw provider payload。
4. 涉及状态变化的 RPC 处理 owner/RLS、CAS、idempotency、rate limit 和 append-only audit。
5. 涉及对象的接口重新验证 bucket/path/owner/version/scan 状态，只返回短期 signed derivative URL 或 opaque 状态。
6. 浏览器只根据稳定 HTTP status、error code 和字段错误更新 UI。

## 4. 状态合同

- `401 AUTH_REQUIRED`：没有有效 active session；页面进入登录流程。
- `403`：权限、AAL、recovery、owner 或 policy 不允许；不得用前端隐藏替代服务端拒绝。
- `409`：CAS/version/idempotency/conversation conflict；用户 Reload 后重做。
- `422`：输入字段/业务规则不符合；保留输入并显示字段错误。
- `429`：频控；提示等待，不循环重试。
- `502/503`：provider/依赖不可用；不写入半状态，不回退为 clean/published。
- `200` 空结果：真实空态；不得用旧缓存或 sample 伪造生产数据。
- 公开作品响应必须有 `items` 数组，每项必须有 ID 和 display URL；缺失/损坏字段进入可恢复错误态，不能解释为空列表或回退 original。公开读取共享 12 秒 AbortController 超时，provider 错误不会回退 sample。
- 首页 legacy 设置由服务端的 development、loopback 和显式 preview 开关共同控制；普通公开页面不读取这些私有 IndexedDB 内容。

## 5. 需求规格

### 安全

- privileged Supabase secret 只存在 Scanner/受控运维脚本；Web 只持有 publishable key 和 HttpOnly session。
- 所有公开、账户、工作区、Review、Admin 和通信接口都必须有明确 allowlist；未知 `/api` 路由返回受控错误。
- DTO 不返回密码、token、CSRF、owner UUID、Storage 坐标、原始 provider payload、内部 audit metadata 或未授权原图。
- mutation 输入必须规范化、长度受限、类型受限；数组、cursor、排序、URL、ID 都有白名单。
- BFF 不从浏览器提供的 role、AAL、visibility、scan verdict 或 owner 字段做安全决策。

### 可靠性与性能

- 外部 provider 请求有 timeout、错误映射和取消；浏览器请求支持 latest-wins 或 AbortController。
- BFF 线程、body、分页、上传和导出都有 bounded 限制；不能因单个慢 provider 拖垮全部请求。
- 读接口尽量使用聚合 DTO；浏览器不得遍历全库计算 dashboard、权限或公开状态。
- 关键 mutation 使用幂等 key 和版本 CAS，重试不能重复发布、回复、撤销或审计。

## 6. 异常恢复

| 类别 | 处理原则 |
|---|---|
| provider 超时 | 返回 502/503，保留可重试输入，不伪造成功 |
| provider 返回非预期字段 | 严格 DTO 校验，返回安全 unavailable |
| 数据库冲突 | 返回 409 和当前可重载路径，不静默覆盖 |
| Storage URL 过期 | 重新生成允许的 signed derivative，不暴露 key |
| 本地缓存损坏 | 丢弃缓存并回权威 API；生产不把缓存当事实 |
| 未知异常 | request ID + 通用错误；日志不含 cookie/token/消息正文 |

## 7. 边界与非目标

- 不允许页面绕过 BFF 直接用 service-role key 操作 Supabase。
- 不把 SQLite/IndexedDB 过渡层扩展成生产多写数据库；未来迁移必须有单独数据迁移规格。
- 不增加 GraphQL、消息总线、第二个状态管理或第二套 API client，除非已有边界无法满足并另行批准。
- 不把 provider 的“暂时不可用”解释为数据为空、扫描 clean、邮件已发或 session 已撤销。

## 8. 相关实现与验收

- 入口：`server.py` 的 `do_GET/do_POST/do_PATCH/do_DELETE` 和各 `handle_*`。
- 数据：`database/schema.sql`、`database/migrations/`、`data/archive.db`、`archive-data.js`。
- 验收：`scripts/release_gate.sh`、`scripts/validate_auth_foundation.py`、各模块 boundary/database tests、`scripts/validate_production_deployment.py`。
