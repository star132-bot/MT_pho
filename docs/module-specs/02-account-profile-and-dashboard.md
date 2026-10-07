# 02 账户、个人主页与账户设置

## 1. 功能范围与当前能力

本模块包含三类相关但职责不同的页面：

- `Dashboard`：登录用户看到的个人工作概览和个人资料展示，不等同于公开 Creator 主页。
- `Account Settings`：编辑个人身份、偏好、安全设置、登录身份和会话控制。
- 公开 `Creator` 主页：只展示已发布内容，详见 [04](04-works-archive-and-viewer.md)。

当前实现位于 `dashboard.html`/`dashboard.js`、`account-settings.html`/`account-settings.js`、`creator.html`/`creator.js`，服务端对应 profile、cover、avatar、identities、sessions 和 dashboard handler。

## 2. 入口与前置条件

| 功能 | 入口 | 前置条件 |
|---|---|---|
| Dashboard | `/dashboard` | active、已验证账户；Admin/Super Admin 先满足 AAL2 |
| Account Settings | `/settings/account` | active 会话；recovery session 拒绝 |
| Profile 编辑 | `/settings/account#profile` | 当前用户本人；服务端 owner scope |
| Avatar 上传 | Account Settings Profile | 登录、CSRF、JPG/PNG/WebP、浏览器可处理 |
| Cover 选择 | Dashboard | 登录；候选必须属于当前用户且满足资产/扫描条件 |
| Identity linking | Account Settings > Security | 已登录；provider 已在 Supabase 配置 |
| Session 控制 | Account Settings > Sessions | provider 支持当前会话描述或批量撤销 |

## 3. 功能流程

### 3.1 Dashboard

1. 服务端进入 `/dashboard` 时先检查 session；未登录跳转登录并带安全 `next`。
2. 页面并行读取 `/api/me/profile` 和 `/api/dashboard`，先绘制固定尺寸身份壳，再填充 cover、avatar、身份、Status、Needs Attention、Recent Images、Review Activity、Storage、Drafts。
3. 用户可切换 `Overview` / `My works` tabs；tab 状态为页面内可访问状态，不复制第二份服务器数据。
4. 点击 Edit profile 进入 Account Settings；点击 Upload work 进入 `/workspace/images`；首件已发布作品后，显示公开 Creator profile 入口。
5. Cover chooser 可选择已有 scanner-clean private derivative，或选择本地文件进入同一上传/扫描链路；成功后调用 cover update。

### 3.2 Profile 与偏好

1. 页面按 Identity、Work、Location、About、Links 五组显示十个 creator 字段和 authorship preferences。
2. 用户修改字段，页面进入 dirty 状态；保存时发送规范化 patch 和 CSRF。
3. 服务端 owner-scoped RPC 校验字段长度、格式和可选值，成功后重新读取权威 profile。
4. 页面显示 saved 状态；失败保留用户输入并给出字段或全局错误。

### 3.3 Avatar

1. 用户选择 JPG/PNG/WebP；浏览器中心裁切、解码并重新编码为 512×512 JPEG。
2. 服务端创建 private Storage upload intent；浏览器向 signed URL 上传后调用 complete。
3. 服务端确认 owner、MIME、尺寸和对象状态，再更新 profile avatar；顶栏通过事件同步。
4. Remove 只删除当前用户头像关联和允许删除的 private object，不影响作品资产。

### 3.4 安全设置、身份与会话

1. Security 区域读取 `/api/auth/mfa/status`、`/api/me/identities` 和 `/api/me/sessions`。
2. 普通账户显示 Authenticator On/Off；Admin/Super Admin 显示 Required 且禁用关闭。
3. Link provider 通过 server-side OAuth；Unlink 前服务端检查不会移除最后一种登录方式。
4. Sessions 只显示 provider 返回的当前会话摘要；“Sign out other devices”和“All devices”是显式确认的 provider action。

## 4. 页面状态与用户可见效果

- `Loading`：头像、cover、profile、dashboard aggregate、identities、sessions 各自显示局部加载，不让一个失败阻塞整页。
- `Empty`：没有 Draft、Activity、公开作品或 cover 时显示原因和下一步；不把统计 0 渲染成异常。
- `Dirty`：离开或切换分组前提示未保存；保存按钮 busy 时禁用。
- `Provider unavailable`：MFA/session/quota 信息显示“provider managed/unavailable”，不能猜测或伪造。
- `Avatar fallback`：首帧使用稳定 initials，图片只有 decode 成功后才 crossfade，失败保留 initials。
- `Permission`：恢复会话和 AAL1 不能访问；管理员不满足 AAL2 进入 MFA；非 owner 的 profile/cover/avatar 请求返回受控 403/404。
- `Conflict`：profile 或 cover 版本冲突时要求 Reload 当前记录，不静默覆盖。

用户点击后的结果：保存 profile 后资料文本和 Header Identity 更新；上传头像后 Account、Dashboard、顶栏和菜单一致显示；选择 cover 后 Dashboard 立即更新；链接身份后安全列表增加一项；撤销会话后显示 provider action 结果并重新加载当前摘要。

## 5. 需求规格

### 数据与权限

- 所有 profile、avatar、cover、identity、session 操作按当前用户 owner scope；浏览器不能提交任意 user ID 覆盖目标。
- Profile 字段有明确长度、URL、邮箱/社交链接和枚举校验；空字符串和 null 的含义固定。
- Avatar source 永不公开；只允许 private 512×512 JPEG 进入 profile 关联。
- Cover 只能指向当前用户的合格资产；不能从 published 之外的他人、原图或未 clean 对象选择。
- Dashboard 是聚合读模型；不得在浏览器遍历所有图片自行计算统计。

### 性能与可用性验收目标

- Dashboard 首屏在 profile 与 aggregate 并行请求时，目标 p95 ≤ 1.5s（不含慢的 signed URL provider）；单块失败不应使整页空白。
- Profile 保存反馈目标 ≤ 1s；长请求必须显示 busy，避免重复提交。
- Avatar/cover 图片在 390×844 下保持固定容器，不引起 Header 或布局跳动。
- 列表、表单、对话框支持键盘、焦点恢复和 `prefers-reduced-motion`。

## 6. 异常处理

| 场景 | 反馈 | 恢复策略 |
|---|---|---|
| profile 校验失败 | 字段级错误 | 保留输入，修正后重试 |
| Storage intent 失败 | “照片暂时无法上传” | 不更新头像；允许重新选文件 |
| signed upload 中断 | 项目级上传错误和 Retry | 取消未完成对象，禁止半对象成为头像 |
| provider session 不支持详细列表 | 说明只能显示当前摘要 | 仍允许 provider 支持的批量撤销 |
| 版本冲突 | “资料已在其他页面更新” | Reload 权威记录，再决定是否重改 |
| MFA/identity provider 不可用 | 可重试错误，不改变本地开关 | 保留原安全状态 |
| 账户被停用 | 退出受保护页面 | 重新激活后再登录，不能在页面绕过 |

## 7. 边界与非目标

- 不在 Dashboard 中提供 Admin 治理、Review decision、硬删除、支付、社交关注或公开作品编辑。
- 不伪造远程设备的地理位置、浏览器历史、活跃数量或配额；provider 没提供就显示 unavailable。
- 不把 Dashboard 的私有 Draft/Review 数据泄露到 Creator 公开主页。
- 不为 avatar 单独建立第二套上传/扫描流程；必须复用 Workspace/private Storage contract。

## 8. 相关实现与验收

- 页面：`dashboard.html`、`dashboard.js`、`account-settings.html`、`account-settings.js`、`creator.html`、`creator.js`。
- 接口：`/api/me/profile`、`/api/me/profile/avatar/*`、`/api/me/profile/cover`、`/api/me/identities*`、`/api/me/sessions*`、`/api/dashboard`。
- 验收：`scripts/validate_user_dashboard.py`、`scripts/test_user_dashboard_boundary.py`、`scripts/validate_profile_avatar.py`、`scripts/test_profile_avatar_database.py`、`scripts/test_profile_avatar_browser.py`、`scripts/test_header_identity_boundary.py`、`scripts/test_oauth_identity_boundary.py`。
