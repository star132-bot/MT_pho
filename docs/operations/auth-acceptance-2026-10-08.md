# 邮箱与 Google 认证验收 — 2026-10-08

## 范围与环境

- 本轮仅处理 SMTP 邮箱注册和 Google OAuth 账号闭环；按用户要求搁置异地备份。
- 生产入口：`https://mtdo.cn`，认证 provider：Supabase Auth。
- 开始时生产运行 `v1.6.1`（`f4effff3c2ac4f0606a1e6338fdaf4e0d0a4f1ae`）。
- 邮箱验收仅创建一个随机临时邮箱/测试身份，走网站公开认证 API；未运行生产 fixture/数据库验收，未修改真实用户。
- 本文不保存邮箱、密码、OTP、cookies、tokens 或 SMTP 密钥。

## 根因与修复

1. 之前的收信脚本只接受 `hydra:member` 对象，而邮箱 API 也会返回 JSON 数组，可能把已收到邮件误判为收信超时；注册后立即重发还会触发正常发送冷却。此次兼容两种形状，邮件发送间隔至少 70 秒，找回邮件排除已读取的注册邮件 ID。
2. 应用注册接口把上游 SMTP 500/504 映射成 400 字段/注册失败；重发接口对同类错误仍返回 202 假成功。修复为注册、重发、找回统一返回脱敏 `AUTH_EMAIL_UNAVAILABLE`，提供明确重试反馈。
3. 未验证邮箱的密码登录被误报为密码错误。现在兼容 provider 的 `error_code`/`code`，返回 `EMAIL_NOT_VERIFIED` 并启用已有重发入口。
4. OAuth 取消后丢失目标页面，且 `next` 允许控制字符/路径编码绕过。现在在服务端和浏览器校验，回调失败保留安全目标页面，阻止 `/auth`、`/api`、站外和响应头注入目的地。
5. 最终自审发现浏览器校验还需检查最终规范化路径（编码 `?/#` 与 dot-segment 组合），同时保留合法 `%25` 查询；补齐独立浏览器导航回归并纳入 release gate。
6. 真实浏览器账号页出现 `0 METHODS`。`clean_auth_identities` 错把 Supabase 的 provider `id` 优先当作管理身份 UUID，丢弃非 UUID 的 Google subject。现在优先使用 canonical `identity_id`，兼容旧式仅有 UUID `id` 的响应；显式无效 canonical ID 不回退。回归 fixture 改为真实双字段形状。[Supabase 身份模型源码](https://github.com/supabase/auth/blob/master/internal/models/identity.go)

## 生产邮箱验收

时间：2026-10-08 15:00–15:03（Asia/Shanghai），运行版本 `v1.6.1`。

| 步骤 | 实际结果 |
|---|---|
| 网站注册 | 201 `verification_required` |
| 收到注册邮件 | 8 位 OTP，约 9.7 秒 |
| 遵守冷却后重发 | 202，并收到新的邮件，约 9.7 秒 |
| 邮箱 OTP 验证 | 200，`/api/me` 返回已登录用户 |
| OTP 重放 | 400 `EMAIL_CODE_INVALID` |
| 退出及匿名访问 | 退出 200；`/api/me` 401 |
| 原密码登录/退出 | 均 200 |
| 请求找回 | 202，收到独立 recovery 邮件，约 9.7 秒 |
| 验证 recovery/重置密码 | 均 200 |
| 新密码登录、确认会话、退出 | 均 200 |
| 测试身份/临时邮箱清理 | Supabase 删除 200、临时邮箱删除 204；私密状态文件已移除 |

以上证明此次生产邮件闭环成功；三个邮件样本不作为 p95、容量或长期投递 SLA 的证据。`SMTP_*` 网站配置服务于站内联系发信，账号邮件由 Supabase 配置控制，不能仅靠本地 SMTP 登录成功判断账号邮件可用。[Supabase SMTP 文档](https://supabase.com/docs/guides/auth/auth-smtp)

### 发布后的第二轮

2026-10-08 15:12–15:15，在生产 `v1.6.2` 再次以新临时身份执行整条流程，上表所有步骤再次成功。注册、重发、找回收信分别约 9.8 / 10.0 / 9.9 秒；第二个测试身份和邮箱均已删除，私密状态已清理。`v1.6.3` 仅补前端导航边界与回归，邮箱服务端代码沿用此已验收版本。

## 代码回归

- `scripts/test_auth_security_boundary.py`：通过邮件 12 个 5xx、三个 429、防枚举身份错误、两种未确认邮箱错误格式、17 个恶意跳转边界；Google fixture 完成 PKCE → profile/受保护页 → 退出 → 再次登录，取消后保留目标页面；既有 CSRF/recovery/MFA 测试全部通过。
- `scripts/test_oauth_identity_boundary.py`：通过。
- `scripts/validate_auth_foundation.py`：通过。
- `auth.js` 语法及独立导航边界验证：通过。
- `scripts/test_auth_destination.js`：21 个恶意跳转、六个合法目的地、正常路径归一化通过，覆盖最终路径解析绕过和百分号查询保留。
- 完整 `bash scripts/release_gate.sh`：通过；日志为本机 `/tmp/mt-auth-release-gate.log`。此次无数据库变更，不运行连接生产主库的数据库 fixture gate。
- 包含浏览器导航新回归的完整 release gate 再次通过：`/tmp/mt-auth-release-gate-v163.log`。
- canonical 身份修复后的完整 release gate：通过，`/tmp/mt-auth-release-gate-v164.log`；身份测试使用真实 provider subject + canonical UUID 形状，所有兼容/拒绝/列表/解绑/隐私断言通过。

## Google 真实账号检查与用户验收

代理检查：网站 Google provider 已启用，真实 Chrome 无痕窗口从网站入口跳到 Google 登录页，provider callback 指向本生产 Supabase，应用回调指向 `https://mtdo.cn/auth/oauth/callback`，目标为 `/settings/account`。

`v1.6.4` 激活后刷新真实已有账号的 Account Settings，Linked accounts 从错误 `0 METHODS` 恢复为 `1 METHOD: Google`，最后一种身份的移除按钮为 disabled/Keep；profile 与受保护账号设置均可用。这是代理采集的真实 Google 身份展示与业务账号会话证据。

用户人工验收：2026-10-08，用户随后明确确认“登录和注册修改密码我都测试过了，完全 ok”。按用户人工验收结论，本轮认证修复收口；已确认的人工测试项目为登录、注册、修改密码。Google 的逐次 callback code、退出/重登用户 ID 追踪未由代理采集，本文仅记录上述实际证据和用户反馈。

新用户业务数据由现有数据库触发器建立，回调采用服务端 PKCE 兑换并校验可信用户。[Supabase Google 文档](https://supabase.com/docs/guides/auth/social-login/auth-google)

## 发布记录

- `v1.6.2`：commit `7fd0661150c33a90bdfc5f0d4a3c9f9d6f7c80d0`，archive SHA-256 `19fbd5122d0bde9a278b381840bc02d11756f015510833c0b21ae1efec77319f`；main/tag 已推送，版本已安装并激活。
- 重启后的首次立即 smoke 遇到暂时 liveness 失败；随后 public/loopback health 均 200，readiness 为 ready、Supabase available，完整 HTTPS smoke 重跑全部通过，Web/Scanner active。
- `v1.6.3`：补齐浏览器导航边界，已构建并推送 commit/tag，未激活；浏览器随后的真实身份列表检查发现第六项兼容问题。
- `v1.6.4`：commit `6470571ca6810f1f9de5f7bb4b862fe99e1ee91f`，archive SHA-256 `28f4759a376f7ba3b98649ec3c67ceb9918aafaae71848f928e2b108941ae251`；main/tag 已推送，已安装并激活，previous 为 `v1.6.2`。
- `v1.6.4` Web/Scanner 均 active；完整 HTTPS smoke 验证 liveness、provider readiness、安全头、公开作品、私有路径隔离、匿名受保护页面及 CSRF Cookie，全部通过。生产 Supabase settings 200，Google/email enabled，signup 可用，email auto-confirm disabled。
- 本轮无数据库迁移或认证 provider 配置修改。
