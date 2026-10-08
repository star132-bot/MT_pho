# 01 认证与安全系统

## 1. 功能范围与当前能力

认证系统负责注册、邮箱验证、密码登录、Google/Apple OAuth、登出、忘记密码、重置密码、恢复会话、TOTP MFA、CSRF、Origin 和会话 Cookie。它是所有受保护模块的共同前置条件。

当前实现位于 `auth.html`/`auth.js`、`mfa.html`/`mfa.js` 和 `server.py` 的 `handle_auth_*`、OAuth、MFA 处理器。身份验证由 Supabase Auth 执行，MT Presence 通过 BFF 只向浏览器投影最小身份状态。

## 2. 入口与前置条件

| 能力 | 页面/接口 | 前置条件 |
|---|---|---|
| 注册 | `/auth/register`、`POST /api/auth/register` | 未登录；邮箱、密码、确认密码、显示名和 Terms 同意有效 |
| 邮箱验证 | `/auth/verify-email`、`POST /api/auth/verify-email-code` | 拥有待验证邮箱和未过期 8 位验证码，或兼容旧 token link |
| 登录 | `/auth/sign-in`、`POST /api/auth/sign-in` | 账户存在、密码正确、邮箱已验证、账户状态 active |
| OAuth | `/api/auth/oauth/{provider}`、`/auth/oauth/callback` | Supabase 中已配置 provider 和精确 redirect URL |
| 找回密码 | `/auth/forgot-password`、`POST /api/auth/forgot-password` | 输入格式正确；成功文案不得暴露账户是否存在 |
| 重置密码 | `/auth/reset-password`、`POST /api/auth/reset-password` | 有有效 recovery link/OTP 形成的受限 recovery session |
| MFA 登录 | `/auth/mfa`、`POST /api/auth/mfa/challenge`、`/verify` | 登录已建立 AAL1，会话存在已验证 TOTP factor |
| MFA 设置 | Account Settings 或 `/auth/mfa` | 普通 active 用户可 enrollment；Admin/Super Admin 由角色策略强制 |
| 登出 | 顶栏账户菜单、`POST /api/auth/sign-out` | 当前会话存在；CSRF/Origin 有效 |

所有 mutation 必须使用同源 `GET /api/auth/csrf` 获得的 double-submit token，并携带 same-origin Origin。浏览器禁止把 access/refresh token 放进 localStorage、sessionStorage 或 URL。

## 3. 标准流程

### 3.1 注册与验证

1. 用户打开注册页，填写标准化邮箱、12–128 字符密码、确认密码、显示名并同意 Terms/Privacy。
2. 客户端做字段校验，服务端再次校验并执行注册频控。
3. Supabase 创建账户后返回 `verification_required`；页面切到验证码状态，邮箱只在当前流程内保存。
4. 用户输入 8 位邮箱验证码；服务端用 `type=email` 验证，并把 provider session 换成 HttpOnly Cookie。
5. 服务端核对返回邮箱身份，成功后显示 verified/signed-in，并按安全 `next` 跳转；没有安全 `next` 时进入 `/works.html`。

### 3.2 密码、OAuth 与 MFA 登录

1. 用户提交邮箱/密码，或点击 Google/Apple。
2. BFF 验证 provider 返回的用户、邮箱验证状态和 `current_authorization`；inactive、恢复会话或权限不足不得进入 Workspace。
3. 若用户有已验证 TOTP，登录先进入 `/auth/mfa`；否则建立普通会话。
4. MFA challenge 创建后，用户输入 6 位验证码；验证成功才提升到 AAL2，并继续原来的安全 `next`。
5. OAuth callback 的 code、state、PKCE verifier 只在服务端短期使用；错误统一回到登录页的可解释状态，并保留已校验的目标页面供重试。

### 3.3 恢复与重置

1. 用户提交邮箱，页面始终显示不泄露账户存在性的成功文案。
2. 用户输入 recovery OTP 或打开兼容链接；服务端建立短时、受限的 recovery session。
3. recovery session 只能访问 recovery status 和 reset password；访问 Dashboard、Account、Workspace、Review、通信和治理接口必须拒绝。
4. 新密码符合策略后更新 provider 密码、结束受限会话并提示重新登录。

## 4. 页面与反馈状态

- `Loading`：提交按钮显示进行中并阻止重复提交；OAuth 跳转期间保留当前页面反馈。
- `Field error`：错误贴近字段，服务端返回 `AUTH_VALIDATION_FAILED` 时保留其他输入。
- `Invalid/expired`：验证码、链接或 MFA 过期显示“已失效/请重新请求”，提供重新发送或返回登录入口。
- `Rate limited`：显示等待提示，不暴露剩余账户数量；注册、验证、恢复分别限流。
- `Provider unavailable`：显示暂时不可用和稍后重试；不能显示上游响应、密钥或 URL。
- `Email unavailable`：注册、重发、找回遇到邮件 provider 5xx/网络失败时统一返回 `AUTH_EMAIL_UNAVAILABLE`（502；上游 503 保持 503），显示一分钟后重试；重发不得显示发送成功，表单保留输入。正常发送后的重发须等待 provider 的发送冷却窗口；429 提示等待并使用已发送的最新验证码。
- `Unverified email`：密码登录识别 provider 的 `email_not_confirmed`，返回 `EMAIL_NOT_VERIFIED`，显示验证邮件重发入口，不创建登录会话。
- `Permission`：未登录受保护页面 303 到带安全 `next` 的登录页；AAL1/Admin 不足跳 MFA 或返回受控 403。
- `Success`：注册显示“验证码已发送”，验证显示“身份已验证”，登录显示目标页面，登出清空身份并回公开页。

## 5. 用户操作效果与最终结果

- 点击“Sign in”成功：获得 HttpOnly access/refresh Cookie，顶栏从 Sign In 变为 initials/avatar，受保护页面可访问。
- 点击“Verify”成功：账户的 email_confirmed 状态变为真，当前浏览器成为已验证会话。
- 点击 OAuth：浏览器跳转 provider；取消时回到登录页并显示可重试状态。
- 点击“Forgot password”：无论账户是否存在都显示同一成功文案；有效邮箱会收到验证码。
- 点击 MFA“Verify”：AAL 从 `aal1` 提升为 `aal2`，Admin Review/Governance 才能继续。
- 点击“Sign out”：撤销/清理当前应用 Cookie，身份组件回到匿名状态；任何旧页面请求按 401 处理。

## 6. 需求规格

### 安全与正确性

- Cookie 必须 `HttpOnly`；生产必须 `Secure`，合理设置 `SameSite` 和过期时间。
- 登录后服务端必须再次向 provider 验证用户和账户状态，不能只相信浏览器字段。
- recovery session、AAL1、inactive、未验证邮箱和角色不足必须在服务端 fail closed。
- OAuth 必须使用 server-side PKCE/state；provider token 不得进入浏览器存储、日志、截图或审计记录。
- OAuth 和密码登录的 `next` 拒绝控制字符、编码绕过、站外/反斜杠路径和解码规范化后进入 `/auth`、`/api` 的路径；取消或失败后重试继续原安全页面。
- 错误响应使用稳定 code、用户消息和可选字段错误；不返回是否存在某个邮箱的差异信息。
- 同一 mutation 重试不能造成重复身份、重复链接或重复审计动作。
- Linked accounts 必须以 provider 返回的 `identity_id` UUID 识别身份；`id` 是 provider subject，不能把 Google subject 当 UUID 校验后静默丢弃。对旧式只含 UUID `id` 的响应保留兼容；显式无效 `identity_id` 拒绝，不退回其他身份 ID。浏览器 DTO 仅提供 canonical ID/provider/email/timestamps，不暴露 provider subject 或原始 metadata。

### 性能与容量验收目标

- 本地/生产登录页首屏不依赖受保护 API 才能绘制基本表单。
- BFF 自身校验在正常 provider 响应下目标 p95 ≤ 500ms；provider 超时必须有明确上限并返回可重试错误。
- 验证码和 MFA 输入只接受固定长度字符，单次请求体和尝试次数有上限。
- 页面在 390×844 下验证码、MFA、错误提示和按钮不被键盘或底部内容遮挡。

## 7. 异常处理与恢复

| 异常 | 用户反馈 | 系统动作 |
|---|---|---|
| 密码/验证码错误 | “邮箱或密码不正确”或“验证码无效/已过期” | 不透露账户细节；记录限流计数 |
| provider 5xx/网络失败 | “服务暂时不可用，请稍后重试” | 不写入半会话；保留表单可重试 |
| CSRF/Origin 失败 | “请求已过期，请刷新后重试” | 拒绝 mutation，重新获取 CSRF |
| session refresh 失败 | “会话已过期，请重新登录” | 清理应用 Cookie，返回登录 |
| OAuth state/PKCE 不匹配 | “登录链接无效，请重新开始” | 丢弃 callback，不创建会话 |
| MFA factor 未完成 | “验证器设置未完成，请重新开始” | 重置未验证 factor，不把 secret 再次泄露 |
| 账户 inactive | “此账户暂时无法访问 Workspace” | 不建立可用工作区会话 |

## 8. 边界与非目标

- 不在 Web 进程自建密码哈希、邮箱投递、OAuth provider 或 TOTP 算法；这些由 Supabase Auth/标准库负责。
- 不提供短信登录、无密码 magic link 主流程、社交账号合并策略或管理员代替用户重置密码。
- 不在浏览器保存凭据，不从活动时间推断 MFA、session 数量或账户配额。
- `collections.html` 等历史页面不是认证入口；所有新受保护页面必须复用同一认证守卫。

## 9. 相关实现与验收

- 页面：`auth.html`、`auth.js`、`mfa.html`、`mfa.js`。
- 服务：`server.py` 的认证、OAuth、MFA 和 session helpers。
- 关键接口：`/api/auth/*`、`/api/me`、`/api/admin/access-check`。
- 验收：`scripts/validate_auth_foundation.py`、`scripts/test_auth_security_boundary.py`、`scripts/test_local_auth_session_refresh.py`、`scripts/test_supabase_admin_mfa.py`。
- 浏览器导航边界：`scripts/test_auth_destination.js`，随 release gate 运行；合法百分号查询和 query/fragment 保留，编码分隔符与 dot-segment 组合不进入认证/API 页面。
- 2026-10-08：生产临时邮箱完成注册/重发收信、OTP 验证及重放拒绝、密码登录/退出、找回/重置和新密码登录；收信约 10 秒（单次验收样本，不代表 p95/SLA）。Google fixture 覆盖 profile、受保护页、退出/重复登录；真实账号验收须由用户完成 Google 登录授权，结果记录于 `docs/operations/auth-acceptance-2026-10-08.md`。
