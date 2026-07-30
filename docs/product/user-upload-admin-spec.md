# MT Presence 用户、图片上传工作台与管理员平台功能设计

## 1. 文档定位与优先级

- 文档类型：产品功能规格、页面职责设计、权限设计、数据与 API 边界、开发验收标准。
- 设计语言：本文档使用中文；页面可见 UI、代码、数据库字段、API、事件名和开发注释使用英文。
- 需求优先级：本文档是用户系统、上传工作台和管理员平台的唯一主规格；需求冲突时以本文为准。
- 明确取消：目标产品不需要公开 `Series` 功能；`collections.html`、`collections.js`、`series-data.js` 在后续实施中应从导航和运行时移除，不在本轮文档阶段直接删除代码。
- 当前实现基线（2026-07-29）：Supabase Auth/Account、owner-scoped Upload Workspace、Quick Upload 共享声明、多 Draft readiness 批量提交、Draft autosave/CAS、Trash/Restore、trusted asset scanner、protected creator profile/Dashboard、Admin Review Queue/Detail/decision，以及 published-only Works/public creator delivery 已实现。Quick Upload 与批量 Submit 只编排既有 per-Draft API，不能绕过 private storage、scanner、readiness、CAS 或审核。Reviewer 只能处理 non-self assignment 且只能 Request Changes、Reject 或 Approve；常规 assignment/start/decision 对所有角色继续禁止 self-review。Admin/Super Admin 必须达到 AAL2 才可执行 Approve and publish；另有独立的 Super Admin self-publish 例外，只允许本人未分配、未开始审核的 Submitted submission，经完整 checklist、CAS、幂等、readiness 与 current-policy-clean 三资产校验后发布，并写专用 immutable audit。Super Admin 可显式多选 eligible 自有作品并一次确认十项 checklist，但客户端逐件重新读取 Detail、逐件调用 dedicated endpoint，成功和失败独立。发布事务只把 display/thumbnail 切为 public，并立即通过 strict DTO 出现在 Works 与 `/creators/{public_slug}`。MT Web API 浏览器 DTO 不包含 original、owner UUID、显式 Storage bucket/key、review evidence 或 private GPS/EXIF；权威空数据或 provider 错误不回退 SQLite/sample/IndexedDB。Supabase signed URL 与匿名交付 RPC 的 provider locator 仍可能包含当前公开衍生图 object path；若业务要求隐藏该 locator，后续必须采用 owner-independent opaque public path 或 server-only credential + image-byte proxy。rollback-only 数据库、双会话并发、无密钥 HTTP 与真实多身份浏览器门禁覆盖上述边界。

## 2. 产品目标

产品围绕三条业务线组织：

1. `User System`：注册、登录、用户身份、会话、个人资料、权限和账号状态。
2. `Upload Workspace`：用户上传图片、编辑文案、保存草稿、使用文件夹、提交审核、删除和下架自己的作品。
3. `Admin Platform`：管理员审核图片、处理合规风险、查看全部图片信息、管理用户、下架内容并保留完整审计记录。

最终核心流程：

```text
Register / Sign in
  -> Upload Workspace
  -> Import images
  -> Save Draft
  -> Edit copy and rights information
  -> Submit for Review
  -> Admin Review
  -> Approve and Publish / Request Changes / Reject
  -> Public Works
  -> User or Admin Unpublish
```

## 3. 非目标

- 不建设公开摄影 Series、Collections 或社交 feed。
- 不建设在线支付、作品销售、订阅、评论、点赞或关注系统。
- 不让普通用户直接操作数据库、对象存储路径或其他用户的图片。
- 不允许上传完成后绕过审核直接公开。
- 不承诺系统可以“绝对确保合法”；系统提供材料声明、自动检测、人工复核、下架和审计能力，最终法律判断仍需依据运营政策和必要的专业法律意见。
- 不使用 localStorage、IndexedDB 或隐藏导航来模拟生产权限。

## 4. 用户角色与权限

### 4.1 `Visitor`

- 浏览公开 Works、About、Contact。
- 查看已发布图片和公开 metadata。
- 不能进入 Upload Workspace 或 Admin Platform。

### 4.2 `User`

- 注册、登录、验证邮箱、维护个人资料。
- 上传图片并管理自己拥有的图片、文件夹和草稿。
- 编辑自己的 Draft 或 Changes Requested 作品。
- 提交审核、撤回尚未开始的审核申请。
- 删除自己的 Draft；下架自己的 Published 作品。
- 查看自己的审核结果、原因和操作历史。
- 不能查看其他用户的 Draft、内部审核信息或私人文件。

### 4.3 `Reviewer`

- 查看分配给自己或公共队列中的 Submitted 图片。
- 查看审核所需图片资产、公开 metadata、权利声明和历史版本。
- 执行 `Start Review`、`Request Changes`、`Reject`、`Approve`。
- 不能管理用户角色、系统配置或删除审计记录。
- 不应静默修改用户的创作文案；需要修改时使用 Request Changes。

### 4.4 `Admin`

- 拥有 Reviewer 权限。
- 查看全部图片和全部用户的运营信息。
- Publish、Unpublish、Takedown、Quarantine、Restore。
- 管理用户状态、上传配额和内容限制。
- 查看审核历史、操作日志和下架记录。
- 不能删除或修改审计日志。

### 4.5 `Super Admin`

- 管理 Reviewer/Admin 角色。
- 管理审核政策、系统配额和高风险配置。
- 处理账号彻底删除、法律保留和数据导出。
- 所有高风险操作必须二次确认并记录审计事件。

### 4.6 权限矩阵

| Action | Visitor | User | Reviewer | Admin | Super Admin |
| --- | --- | --- | --- | --- | --- |
| View published works | Yes | Yes | Yes | Yes | Yes |
| Upload image | No | Own | No | Own | Own |
| Edit draft copy | No | Own | No | Any with reason | Any with reason |
| Submit review | No | Own | No | Any | Any |
| Review submitted image | No | No | Assigned/queue | Any | Any |
| Publish image | No | No | Optional by policy | Yes | Yes |
| Unpublish own image | No | Own | No | Any | Any |
| Takedown for policy/legal reason | No | No | Recommend | Yes | Yes |
| View all private images | No | No | Review scope | Yes | Yes |
| Manage users | No | No | No | Limited | Full |
| Manage roles | No | No | No | No | Yes |
| View audit logs | No | Own activity | Review scope | Yes | Yes |

所有服务端接口都必须重新验证权限；前端隐藏按钮只是交互处理，不是权限控制。

## 5. 目标页面地图

### 5.1 公开站点

| Page | Route | 职责 |
| --- | --- | --- |
| `Home` | `/index.html` | 品牌和精选公开作品入口 |
| `Works` | `/works.html` | 浏览所有 Published 图片 |
| `About` | `/about.html` | 作者或平台介绍 |
| `Contact` | `/contact.html` | 联系与业务咨询 |
| `Sign In` | `/auth/sign-in` | 登录入口 |
| `Create Account` | `/auth/register` | 用户注册 |

公开导航建议：`Works / About / Contact / Sign In`。登录后 Sign In 替换为 initials 头像，点击进入受保护 `/dashboard` personal profile；内部页面同样以头像进入个人资料，再用资料页的 Edit personal information 进入 `/settings/account#profile`。相邻独立菜单按钮进入 `Dashboard`、`Workspace`、`Account Settings` 和有权限时的 `Review`。

### 5.2 用户工作区

| Page | Route | 职责 |
| --- | --- | --- |
| `Personal Profile / Dashboard` | `/dashboard` | 无左侧 rail 的受保护封面/身份资料、Overview/My works 和用户作品状态；`/workspace` 规范化到此路由 |
| `Upload Workspace` | `/workspace/images` | 上传、文件夹、草稿、图片信息编辑 |
| `Image Editor` | `/workspace/images/{id}` | 单张图片完整文案和权利信息 |
| `Notifications` | `/workspace/notifications` | 审核、失败和下架通知 |
| `Account Settings` | `/settings/account` | 五组十字段 creator 资料、偏好、安全、会话和账号操作 |

当前静态阶段可以继续使用 `upload-studio.html` 作为 Upload Workspace 原型，但生产实现应使用受保护路由。

### 5.3 管理员平台

| Page | Route | 职责 |
| --- | --- | --- |
| `Admin Dashboard` | `/admin` | 待审核、风险、失败和运营指标 |
| `Review Queue` | `/admin/reviews` | 审核队列、领取任务、批量分配 |
| `Review Detail` | `/admin/reviews/{submissionId}` | 单张图片合规审核与决策 |
| `All Images` | `/admin/images` | 查看全部图片、状态、资产和所有者 |
| `Image Detail` | `/admin/images/{imageId}` | 完整 metadata、资产、版本和审核历史 |
| `Users` | `/admin/users` | 用户搜索、状态、配额和风险管理 |
| `User Detail` | `/admin/users/{userId}` | 用户资料、图片、审核和管理历史 |
| `Audit Log` | `/admin/audit` | 不可变操作日志和导出 |
| `Policy Settings` | `/admin/settings/policies` | Super Admin 管理审核规则和限制 |

当前 `manage.html` 可作为 Review Detail/All Images 的原型基础，但必须拆分职责，不能继续把首页编辑混在图片审核后面。

## 6. 图片状态模型

图片不能只使用一个 `visibility` 字段表达所有状态。生产模型至少拆成三条独立状态：

### 6.1 `processing_status`

```text
pending -> uploading -> processing -> ready
                  \-> failed
                  \-> canceled
```

- 描述文件和派生资产是否完整。
- `ready` 只表示资产可编辑，不表示通过审核或公开。

### 6.2 `workflow_status`

```text
draft -> submitted -> in_review -> approved
                     |           \-> rejected
                     \-> changes_requested -> draft

submitted -> draft  (only when review has not started)
```

- `draft`：用户可编辑。
- `submitted`：等待管理员领取，用户主要字段锁定。
- `in_review`：审核进行中。
- `changes_requested`：退回用户修改，必须保留原因。
- `rejected`：当前版本拒绝，不可直接公开。
- `approved`：审核通过，可由系统或 Admin 发布。

### 6.3 `publication_status`

```text
never_published -> published -> unpublished
                             \-> quarantined
unpublished -> published  (requires policy-defined re-review)
* -> archived -> deleted
```

- 公开 Works 只读取 `publication_status = published`。
- 用户主动下架进入 `unpublished`。
- 管理员政策/法律下架进入 `quarantined` 或 `unpublished`，必须带 reason code。
- `deleted` 默认是软删除状态；真正物理删除由保留策略异步执行。

### 6.4 当前字段迁移

当前 `images.visibility` 映射建议：

| Current visibility | workflow_status | publication_status |
| --- | --- | --- |
| `draft` | `draft` | `never_published` |
| `private` | `draft` | `unpublished` |
| `published` | `approved` | `published` |
| `archived` | 保留原审核状态 | `archived` |

迁移完成前，禁止同时由 `visibility` 和新字段分别驱动公开查询，避免同一图片出现两个可写状态源。

## 7. 用户系统详细设计

### 7.1 注册

字段：

- `Email`：required，唯一，规范化为 lowercase。
- `Password`：required；服务端执行强度检查。
- `Display Name`：required。
- `Terms Acceptance`：required，记录 policy version 和 timestamp。
- `Marketing Consent`：optional，与 Terms 分开。

流程：

```text
Submit registration
  -> rate limit and validation
  -> create pending user
  -> send verification email
  -> verify token
  -> activate account
  -> create profile and default Inbox folder
  -> enter Workspace
```

状态：loading、duplicate email、invalid fields、email sent、expired token、resend cooldown、success。

### 7.2 登录

- Email + Password。
- `Remember this device` 使用受控 refresh session，不在 localStorage 存 access token。
- 登录失败使用统一提示，避免枚举账号。
- Admin/Super Admin 强制 MFA；普通 User 建议支持 MFA。
- 账号 suspended/banned 时拒绝登录并显示可联系支持的原因类别。

### 7.3 密码与会话

- Forgot Password 使用一次性、短期、可撤销 token。
- 修改密码后可选择注销其他设备。
- Account Settings 显示 active sessions：device、browser、approximate location、last active。
- 用户可以 revoke 单个或全部其他 session。
- 高风险操作需要 recent authentication：修改邮箱、删除账号、管理员角色变更。

### 7.4 用户资料

- `display_name`
- `avatar_url`
- `professional_headline`
- `company`
- `availability_status`：`open`、`limited`、`unavailable`
- `bio`
- `website_url`
- `instagram_url`
- `linkedin_url`
- `country_code`
- `city`
- `preferred_locale`
- `timezone`
- `copyright_name`
- `default_license_preference`
- `cover_asset_id`

受保护 Profile editor 的十个 creator fields 按 Identity、Work、Location、About、Links 分组；`avatar_url`、偏好与 `cover_asset_id` 不伪装成同一表单字段。`website_url` 只接受 HTTPS，Instagram/LinkedIn 还必须使用对应官方 host。

Cover chooser 只允许选择或移除当前 owner 的 current、non-deleted、ready image 资产，每张 image 优先 current-policy scanner-clean private display、缺失时回退 clean thumbnail。`GET/PATCH /api/me/profile/cover` 只返回固定 DTO 与可用时的短期 signed URL；不能返回 bucket/key/owner/scan internals，mutation 要求 CSRF，并拒绝 recovery、inactive、Admin/Super Admin AAL1、跨 owner 与 bucket-kind mismatch。若数据库保存已提交但即时预览签名失败，PATCH 返回 HTTP 200 `{cover:null,saved:true}`，UI 明确显示保存成功但预览暂不可用，不得引导用户重复提交。

公开 Works 与 `/creators/{public_slug}` 只读取独立的 published-only public creator DTO。公开 cover 也必须来自当前作品、current-policy clean、精确 object 匹配的 public display/thumbnail；protected `/api/me/profile*` 不得复用为 public delivery。

### 7.5 账号状态

```text
pending_verification -> active -> suspended -> active
                               \-> banned
active -> deletion_requested -> deleted
```

- suspended：暂时禁止上传和提交，可保留登录查看通知。
- banned：禁止登录和公开内容；是否下架全部作品由 Admin 明确操作。
- deletion_requested：进入冷静期，停止新上传；到期后按数据保留政策处理。

### 7.6 用户系统验收标准

- 未验证邮箱不能上传或提交审核。
- 用户 A 无法读取、修改、移动、提交或删除用户 B 的私有图片。
- Admin 页面对非管理员返回服务端 `403`，不是只重定向前端。
- 密码、session token、verification token 不写入日志或浏览器 localStorage。
- 登录、密码重置、邮箱验证有速率限制和安全审计。

## 8. Upload Workspace 详细设计

### 8.1 页面目标

为登录用户提供完整的个人图片生产工作台：上传资产、组织文件夹、编辑文案、保存草稿、提交审核、查看结果、删除和下架。

### 8.2 桌面布局

```text
Top command bar
  [Import Images] [New Folder] [Submit Selected] [Search] [Account]

Left: Folders and saved views
  Inbox
  Drafts
  Submitted
  Changes Requested
  Published
  Unpublished
  Trash
  Custom folders...

Center: Image library / upload queue
  cards or dense rows
  batch selection
  status and progress

Right: Metadata inspector
  preview
  copy fields
  rights fields
  validation
  Save Draft / Submit for Review
```

移动端使用普通页面流：顶部状态 tabs、图片列表、点击进入独立 Image Editor；不把桌面三栏强行压缩成窄屏三栏。

### 8.3 导入与上传

支持：

- Drag and drop。
- File picker，多文件选择。
- JPG、PNG、WebP；未来需要时增加 TIFF/HEIC 服务端转码。
- 单文件和单用户配额限制由服务端返回，不硬编码在前端。
- 每张图片独立任务，一个失败不阻塞其他任务。

单张任务阶段：

```text
Queued
Reading metadata
Hashing
Uploading original
Generating display
Generating thumbnail
Scanning file
Saving draft
Ready
```

失败提供明确原因和 `Retry`；上传中提供 `Cancel`；完成后提供 `Open Draft`。

### 8.4 文件校验与资产生成

- 客户端初步检查 extension、reported MIME、尺寸和大小。
- 服务端必须重新检查 magic bytes、解码能力、像素数量和 MIME。
- checksum 用于当前用户范围的重复文件提醒；跨用户不能泄露“其他用户已上传此图片”。
- 保存 `original`、`display`、`thumbnail`；方形切片只有真实业务使用时才保留。
- 原图默认私有；公开页面读取 display/CDN URL。
- 对公开 metadata 采用 EXIF allowlist；GPS 默认不公开。
- 文件安全扫描未完成前不能进入 Submit。

### 8.5 草稿箱

`Drafts` 是系统 saved view，不是普通文件夹。

功能：

- 上传成功自动创建 Draft。
- 文案输入 debounce autosave，同时显示 `Saving / Saved / Save failed`。
- 保留手动 `Save Draft`，用于明确提交当前编辑。
- 支持未完成字段；只有 Submit 才执行完整审核前校验。
- 刷新、换设备和重新登录后草稿仍存在于服务端。
- 记录最后编辑时间和最后编辑者。
- 保留有限版本历史，至少能够查看审核提交时的 immutable snapshot。

离开页面时：

- 已成功 autosave：直接离开。
- 保存中：等待或提示。
- 保存失败：明确提示未同步内容，不显示虚假 Saved。

### 8.6 文件夹系统

文件夹用于用户内部组织，不影响公开分类和审核结果。

功能：

- 默认 `Inbox`，不可删除。
- 创建、重命名、移动、删除 custom folder。
- 首版支持单层 custom folders；需要嵌套时最大深度建议为 3。
- 图片可以存在于一个 folder；Saved views 通过状态动态生成。
- 批量移动图片到 folder。
- 删除非空 folder 时必须选择：Move to Inbox 或 Move to Trash。
- Folder 名只写入 `folders.name`，不自动写入图片 tags、title 或公开 metadata。
- Folder 删除为软删除，保留短期恢复窗口。

### 8.7 图片文案编辑

#### Core Copy

- `Title`：Submit 前 required，最大长度明确。
- `Caption`：optional，公开短说明。
- `Description`：optional，完整作品说明。
- `Alt Text`：Submit 前 required，用于无障碍，不与 Caption 自动共用。
- `Tags`：optional，数量和单项长度限制。
- `Content Category`：required，由受控选项选择。

#### Capture Information

- `Captured At`：optional。
- `Location Name`：optional。
- `GPS Visibility`：默认 private；不得因 EXIF 自动公开精确坐标。
- `Camera / Lens / Exposure`：从 EXIF 读取，用户决定是否公开。

#### Rights and Compliance

- `Copyright Holder`：required，默认来自 profile。
- `Copyright Year`：required 或从 captured date 推导后确认。
- `License Availability`：optional。
- `Contains Recognizable People`：required yes/no。
- `Model Release Status`：条件字段。
- `Property Release Status`：条件字段。
- `I own or control the required rights`：Submit 前 required declaration。
- `AI Generated / AI Edited Disclosure`：required 选择；不能依赖自动识别代替用户声明。
- `Sensitive Content Disclosure`：required 选择。

#### System Fields

以下字段只读：original filename、dimensions、ratio、checksum、asset state、upload time、owner、workflow status、publication status、review state。

### 8.8 Submit for Review

Submit 前校验：

- processing_status = ready。
- Title、Alt Text、Category 完成。
- Rights declaration 完成。
- 条件 release 字段完成。
- 没有 unresolved upload/scan error。
- 用户账号 active 且未超出 submission limit。

Submit 后：

- 创建 immutable submission snapshot。
- workflow_status -> submitted。
- 用户编辑受控字段锁定。
- 生成 activity event 和 notification。
- 管理员 Review Queue 增加任务。

用户可以在管理员尚未 `Start Review` 前撤回，撤回生成新审计事件并回到 Draft。

当前 Phase 2E-Phase 3 实现边界：

- `GET /api/images/{imageId}/readiness` 由服务端固定返回 Work details、Rights & disclosures、Image assets、Security scan、Submission state 五项检查；客户端只展示/轮询结果，不能替代提交事务内的再次校验。
- `POST /api/images/{imageId}/submit` 要求显式 `submit-for-review` confirmation、current `expected_version` 和 UUID `idempotency_key`；同 key retry 返回首次成功结果，stale version 返回 conflict。
- Quick Upload 允许一次填写本批 content category（或 filename auto-classification）、copyright、release、rights、AI/sensitive disclosure、tags/location 与 Alt Text template，再选择多文件；每张图片仍创建独立 Draft/version/assets，默认值随 Draft 保存且只在当前 tab 非权威记忆。
- `Check & submit ready` 对当前 Folder 每张 Draft 重新读取 readiness，只把明确 Ready 的记录纳入一次确认；之后逐件调用同一 versioned/idempotent Submit API，成功项移除，Pending、Blocked 和失败项保留。
- 成功事务锁定当前 `image_versions`，创建带 readiness/asset snapshot 的 `review_submissions`，更新 `images.workflow_status/version`，并写入 notification 与 append-only audit。authenticated 不能直接创建/改写/删除 submission，owner 不能直删已登记为 asset 的 Storage object。
- Upload Studio 展示 blocked/pending/ready/checking/error/submitting，pending 时轮询，提交前保存并再次检查，确认后提交，成功后从 Draft list 移除；submitted 后 Draft update/Trash 拒绝。
- 当前真实上传的三个 asset 均从 `scan_status=pending` 开始；INSERT 自动 enqueue restricted job，独立 worker 以 SKIP LOCKED lease 领取，校验 private Storage bytes/checksum/magic，ClamAV clean 后再由 Pillow 完整解码并核对 EXIF-oriented dimensions。只有三个 token-bound completion 都为 `clean` 才能启用 Submit；malware 为 flagged，确定性损坏为 failed，依赖/网络不确定性 retry 且绝不 clean。
- Browser、普通 authenticated user 与 `server.py` 都不能读写 scan job/event 或 verdict，也不持有 Supabase secret/service-role key。Phase 2F 不实现或宣称 user quota/submission capacity。
- `/admin/reviews` 与 `/admin/reviews/{submissionId}` 已通过服务端 DTO 接入 Supabase submission snapshot，支持 status/assignment queue、原子 claim/start、submitted-version Detail、checklist，以及 Request Changes/Reject/Approve；Reviewer 的 detail/private asset 权限只在自己的 open non-self assignment 内有效，Admin/Super Admin 仍要求 AAL2。常规 mutation 都拒绝 self-review；仅 `review_super_admin_self_publish` 允许 Super Admin 对本人 untouched/unassigned Submitted 作品执行显式、可确认、可审计的发布。
- Super Admin+AAL2 可以显式选择多个 eligible 自有 Submitted 作品并一次确认全部十项 policy checklist；客户端必须逐件重新读取 Detail、逐件使用最新 lock version 和独立 idempotency key 调用 dedicated self-publish endpoint，成功项与失败项不能互相覆盖。该快捷入口不是普通 bulk approval，也不扩大 Admin/Reviewer 权限。
- 决定 mutation 要求 current `expected_version`、UUID idempotency key 和 action-specific fields；same-key/same-payload 返回首次完整结果，same-key/different-payload、stale version 或 reviewer conflict 必须拒绝，历史 decision 与 audit 不可覆盖。
- Admin/Super Admin 在 AAL2 下可以从浏览器执行 `approve_and_publish`，立即进入 Supabase published-only DTO、公开 Works 与 creator profile；Reviewer 仍不能 publish。Withdraw、Escalate、Quarantine 和风险/批量筛选仍是后续切片；legacy `manage.html` 保持独立 SQLite 原型。

### 8.9 删除、回收站与下架

#### Delete Draft

- 用户可把自己的 Draft 移到 Trash。
- Trash 默认保留 30 天，具体天数由 policy 配置。
- 保留期内可 Restore。
- 永久删除需要二次确认和 recent authentication；有 legal hold 时禁止。

#### Delete Submitted/In Review

- 不能直接永久删除。
- 用户先 Withdraw；审核已开始时需要取消请求或联系管理员。
- 所有 submission/review 历史保留。

#### Unpublish Published Work

- 用户可以执行 `Unpublish`，立即从公开 Works 移除。
- Unpublish 不删除原始资产、metadata、审核记录或历史公开时间。
- 再次发布默认需要重新提交审核，除非内容和资产完全未变化且 policy 允许快速恢复。

#### Admin Takedown

- Admin 选择 reason code：copyright、privacy、illegal_content、policy_violation、security、user_request、other。
- 高风险内容可先 Quarantine，再调查。
- 用户收到可公开的原因和申诉方式；内部备注不直接暴露。
- Takedown、Restore 和证据引用全部写入 audit log。

### 8.10 Upload Workspace 状态

- Loading：folder skeleton、image list skeleton、editor placeholder。
- Empty Inbox：显示 Import Images。
- Empty Drafts：显示 Go to Inbox / Import Images。
- Processing：逐图进度。
- Partial Failure：成功与失败分离，支持只重试失败项。
- Offline：显示只读或未同步状态，不把浏览器本地数据当成已提交。
- Permission Denied：账号 suspended 或 quota exceeded 时禁用 Import，并说明原因。
- Changes Requested：醒目显示管理员原因、需修改字段和 Resubmit。
- Trash：显示 remaining days 和 Restore。

### 8.11 Upload Workspace 验收标准

- 上传完成只产生 Draft，公开 Works 不可见。
- Draft 文案刷新后仍能从服务端恢复。
- Folder 操作不修改公开 tags 或审核状态。
- 用户不能编辑 Submitted/In Review snapshot。
- Submit 失败时保留 Draft 和错误信息。
- 用户下架后公开 API 立即不再返回该图片。
- Delete/Unpublish/Takedown 的语义和按钮文案严格区分。
- 桌面三栏和移动端独立 Editor 都无重叠、溢出或操作遮挡。

## 9. 用户 Dashboard

### 页面目标

先建立当前用户的受保护 creator identity，再让用户快速知道“需要我做什么”，而不是重复展示全部图片网格。

### 页面内容

- Cover + Identity：当前合格作品封面或 fallback、avatar/initials、creator details、Edit personal information、Upload work。
- Profile facts：completion、availability、professional/company、location/timezone、website/social，以稳定六项事实区呈现。
- Status summary：Drafts、Submitted、Changes Requested、Published、Unpublished。
- `Needs Attention`：上传失败、Changes Requested、账号/配额问题。
- Recent Images：最近编辑的 6-10 张。
- Review Activity：Submitted、Review started、Approved、Rejected、Takedown。
- Storage Usage：已用空间、文件数和配额。
- Primary CTA：`Import Images`。

### 状态与验收

- 统计来自服务端聚合，不能在浏览器遍历全部图片计算。
- Changes Requested 永远优先于普通 recent activity。
- 空账号只显示 Import Images 和基础账号完成提示。
- Dashboard 不承担图片完整编辑。
- Dashboard 不显示左侧 rail，Overview/My works 使用 keyboard-accessible tabs；桌面事实区稳定 3x2，窄屏逐步降为 2 列/1 列，不允许横向溢出。
- 当前实现通过 authenticated-only `get_my_dashboard()` 聚合工作状态，通过 protected `/api/me/profile` 与 `/api/me/profile/cover` 读取 identity/cover；浏览器只读取稳定 DTO 和短期签名 display/thumbnail。尚未配置的 storage quota 显示 unavailable；public delivery capability 按真实 published count 显示公开主页入口或 no-published-works 状态，不能伪造数字或链接。

## 10. Admin Platform 详细设计

### 10.1 Admin Dashboard

#### 页面目标

显示审核压力、风险和系统异常，帮助管理员决定下一步动作。

#### 指标

- Awaiting Review。
- In Review。
- Oldest Waiting Time。
- Changes Requested。
- Rejected Today。
- Published Today。
- Quarantined。
- Processing/Scan Failures。
- Suspended Users。

所有指标都可以点击进入带对应 filter 的列表；不做无操作价值的装饰图表。

### 10.2 Review Queue

#### 列表字段

- Thumbnail。
- Submission ID。
- Image title / original filename。
- User。
- Submitted at / waiting time。
- Content category。
- Automated flags count/severity。
- Rights declaration summary。
- Assigned reviewer。
- Review status。

#### 筛选和排序

- Unassigned / Assigned to me / All。
- Risk severity。
- Submitted date。
- Waiting time。
- User/account risk。
- File scan state。
- Content category。
- Has releases / missing releases。

#### 队列动作

- `Assign to Me`。
- Admin 批量分配 reviewer。
- 仅低风险、明确规则允许的项目可批量 Approve；首版建议不做批量 Approve。
- Reviewer 打开详情时原子领取任务，避免两人同时覆盖决定。

### 10.3 Review Detail

#### 页面布局

```text
Top: submission identity / timer / assigned reviewer / status

Left: large image preview
  fit / actual size
  asset variants
  EXIF and dimensions

Right: review inspector
  user copy
  rights declarations
  automated flags
  policy checklist
  prior review history
  decision actions
```

#### 审核信息

- Original/display/thumbnail 是否完整。
- Magic MIME、decode、dimensions、checksum、scan result。
- Title、Caption、Description、Alt Text、Tags。
- Owner、account age、prior violations。
- Copyright declaration。
- People/property/release status。
- AI disclosure。
- Automated moderation flags 和 model/version/confidence。
- Previous versions、previous rejection、takedown history。

#### 审核 Checklist

Checklist 由 policy version 管理，至少覆盖：

- 文件安全和可正确解码。
- 用户权利声明完整。
- 可识别人物与隐私风险。
- 未成年人相关风险。
- 暴力、色情、仇恨、违法内容风险。
- 受保护地点、私人财产或 release 风险。
- 商标、艺术品、第三方版权风险。
- 误导性编辑或 AI disclosure。
- Title/Description/Tags 是否包含攻击、欺诈或非法信息。
- 公开 GPS/EXIF 是否泄露敏感信息。

系统只能辅助识别风险；自动模型不能成为高风险拒绝或法律结论的唯一依据。

#### 审核动作

- `Approve`：审核通过，不一定立即公开。
- `Approve and Publish`：Admin 权限，事务内完成审核决定与发布。
- `Request Changes`：选择 reason codes、填写面向用户的说明和需修改字段。
- `Reject`：选择 reason codes、用户说明、内部备注。
- `Escalate`：进入高级管理员/法律复核，不对用户给出未确认结论。
- `Quarantine`：紧急隐藏高风险内容。

动作必须要求：

- checklist 完成。
- decision reason。
- 当前 reviewer identity。
- submission version 未被替换。
- 防止重复提交的 idempotency key。

### 10.4 All Images

#### 页面目标

查看系统内全部图片的运营和技术信息，不局限于待审核队列。

#### 表格字段

- Thumbnail。
- Image ID。
- Title。
- Owner user/email。
- Folder。
- Processing status。
- Workflow status。
- Publication status。
- Review decision。
- Asset count / scan state。
- Uploaded / updated / published time。
- Assigned reviewer。
- Flags。

#### 功能

- Search：ID、title、filename、email、display name、checksum（Admin only）。
- Filters：所有状态、owner、reviewer、risk、日期、asset state。
- Sort：uploaded、updated、waiting time、published。
- 打开 Image Detail。
- 导出当前筛选 metadata；导出不包含原始资产 URL 或敏感 EXIF，除非拥有额外权限。
- 批量 Unpublish/Archive 需要原因、确认和审计；不提供批量物理删除。

### 10.5 Admin Image Detail

- Public preview 与原始资产 preview 分开。
- 展示全部 metadata、用户文案、system fields、资产列表、checksum、scan、EXIF allowlist。
- 展示 workflow timeline、publication timeline、review decisions、versions、notifications、takedowns。
- Admin override 必须填写 reason，并保留 before/after diff。
- 用户创作文案默认只读；管理员修正系统字段与要求用户修改文案应使用不同动作。

### 10.6 Users

#### 列表字段

- User ID、email、display name。
- Account status / email verified / MFA。
- Role。
- Image counts by status。
- Storage usage / quota。
- Violation count。
- Created / last active。

#### 用户管理动作

- Suspend / Unsuspend。
- Ban，需高风险确认。
- Change quota。
- Require password reset。
- Revoke sessions。
- View user's images and review history。
- Role management 只允许 Super Admin。
- Impersonation 默认不实现；如未来实现必须明显提示并完整审计。

### 10.7 Audit Log

记录：

- actor user/admin ID、role。
- action。
- target type/ID。
- timestamp。
- request ID。
- IP/user agent 的受控安全记录。
- reason code / internal note reference。
- before/after structured diff。
- policy version。
- result success/failure。

规则：

- 普通业务接口不能 update/delete audit rows。
- 敏感值、密码、token、原图 signed URL 不写入日志。
- 支持按 actor、target、action、date、request ID 筛选。
- 导出操作本身也必须记录。

### 10.8 Admin Platform 验收标准

- 非管理员访问任何 `/admin/*` 或 admin API 都返回 `403`。
- 两名 reviewer 不能无提示地覆盖同一 submission decision。
- 每次 Approve/Reject/Unpublish/Takedown 都有 reviewer/admin、reason、timestamp、policy version。
- Published 图片被 Quarantine 后公开 API 立即不可见。
- Admin 可以从任意图片看到完整 workflow 和 publication history。
- Admin 不能删除 audit log。
- 管理员表格在桌面可扫描；移动端使用详情优先布局，不压缩全部列。

## 11. 用户与管理员协作

### 11.1 通知事件

| Event | Recipient | UI message |
| --- | --- | --- |
| Draft saved | User | `Draft saved` |
| Upload failed | User | `Upload failed` + retry reason |
| Submitted | User | `Submitted for review` |
| Review assigned | Reviewer | Queue/task update |
| Review started | User | `Review in progress` |
| Changes requested | User | Reason + affected fields |
| Rejected | User | Reason + appeal/support path |
| Approved | User | `Approved` |
| Published | User | Public URL |
| User unpublish | User | `Removed from public Works` |
| Admin takedown | User + Admin | Policy reason and case reference |

### 11.2 并发和版本

- 图片保存使用 `version` 或 `updated_at` optimistic concurrency。
- Submission 指向 immutable `image_version_id`。
- 用户修改 Changes Requested 图片会创建新 version，不覆盖被审核的 snapshot。
- Admin decision 提交时校验 submission version 和当前 assignment。
- 发生冲突时显示 Reload/Compare，不静默 last-write-wins。

## 12. 数据模型

### 12.1 用户与权限

#### `users`

- `id`
- `email`
- `email_verified_at`
- `account_status`
- `created_at` / `updated_at` / `last_active_at`
- 密码由 Auth provider 或专用 credential 表管理，不放业务 profile 表。

#### `user_profiles`

- `user_id`
- `display_name`
- `avatar_url`
- `bio`
- `website_url`
- `timezone` / `preferred_locale`
- `copyright_name`
- public field flags。

#### `roles` / `user_roles`

- `role_code`: user/reviewer/admin/super_admin。
- role assignment actor、reason、created_at。

#### `user_sessions`

建议由 Auth provider 管理；业务侧只保存必要的 session security event，不保存明文 token。

### 12.2 图片与工作区

#### `folders`

- `id`
- `owner_user_id`
- `parent_id` nullable
- `name`
- `sort_order`
- `is_system`
- `deleted_at`

#### `images`

- `id`
- `owner_user_id`
- `folder_id`
- `current_version_id`
- `processing_status`
- `workflow_status`
- `publication_status`
- `published_at` / `unpublished_at`
- `deleted_at`
- `created_at` / `updated_at`

#### `image_versions`

- `id`
- `image_id`
- `version_number`
- title/caption/description/alt_text/tags/category。
- capture/public EXIF fields。
- rights/release/AI/sensitive disclosures。
- `created_by_user_id`
- `created_at`
- immutable after submission。

#### `image_assets`

沿用当前 original/display/thumbnail 思路，补充：

- `owner_user_id` 或通过 image 关联所有权。
- `scan_status` / `scan_result_code`。
- `scan_completed_at` / `scan_policy_version`。
- `storage_visibility`。
- `deleted_at`。

#### `asset_scan_jobs` / `asset_scan_events`

- 每个 active asset 一条 restricted job；保存不可变 asset/object snapshot、queued/leased/retry/terminal 状态、attempt、available time、短期 lease token 与 scanner/engine/result metadata。
- claim 使用 `FOR UPDATE SKIP LOCKED`；complete/retry 必须匹配未过期 token，same-token replay 幂等，旧 token 不得覆盖新 worker。
- events append-only，记录 queued/claimed/lease-expired/retry/clean/flagged/failed，不保存 object key、secret、恶意签名或面向用户的原始 provider error。
- anon/authenticated/service_role 均无 scanner 表级访问；三条 scanner RPC 只授予 service_role，当前 Worker 也只调用这三条 RPC，Web API 不代理它们。secret/service-role credential 本身仍是可绕过 RLS 的广泛高权限凭据，不能把 RPC-only 实现误认为 credential-level 限权。

#### `upload_sessions` / `upload_items`

- 多图上传批次、客户端 task、上传 intent、进度、错误和 retry 状态。
- 服务端完成前不得只依赖浏览器 task 数组。

### 12.3 审核与合规

#### `review_submissions`

- `id`
- `image_id`
- `image_version_id`
- `submitted_by_user_id`
- `status`
- `assigned_reviewer_id`
- `submitted_at` / `review_started_at` / `completed_at`
- `policy_version`
- `lock_version`
- `idempotency_key`
- `readiness_snapshot`
- `asset_snapshot`

`image_version_id`、提交身份/时间、policy、idempotency key 与两个 snapshot 在创建后不可改写；review status/assignment 的后续合法状态转换不能覆盖原始提交证据。

#### `review_decisions`

- `submission_id`
- `reviewer_id`
- `decision`
- `reason_codes[]`
- `user_message`
- `internal_note`
- `checklist_result`
- `created_at`

Decision 使用 append-only，不覆盖历史决定。

#### `moderation_flags`

- 来源：automated/manual/user_report/legal_request。
- category、severity、confidence、model/version、status。
- 自动 flag 与最终人工 decision 分开保存。

#### `release_documents`

- image/version 关联。
- type：model/property/other。
- encrypted/private object storage key。
- verification status。
- 公开 API 永远不返回 release 文件地址。

#### `takedown_cases`

- image、requester、reason、evidence reference、status、assigned admin、resolution。
- 支持 legal hold。

#### `notifications`

- recipient、type、payload reference、read_at、created_at。
- payload 不复制敏感审核内部备注。

#### `audit_logs`

- append-only actor/action/target/diff/reason/request/policy metadata。

### 12.4 当前数据库缺口

当前 schema 有 `artists`、`images`、assets、tags、collections，但缺少：

- 真实 users/auth ownership。
- roles/RBAC。
- folders 表。
- 独立 processing/workflow/publication 状态。
- image versions 和 immutable submission snapshot。
- review submissions/decisions。
- moderation flags、release documents、takedown cases。
- notifications 和 immutable audit logs。

因此不能只在当前 `images` 表增加几个字符串字段就声称用户/管理员系统完成。

## 13. API 设计

所有 API 使用英文 JSON 字段、稳定错误码和服务端权限校验。

### 13.1 Auth / User

```text
POST   /api/auth/register
POST   /api/auth/sign-in
POST   /api/auth/sign-out
POST   /api/auth/verify-email
POST   /api/auth/forgot-password
POST   /api/auth/reset-password
GET    /api/me
PATCH  /api/me/profile
GET    /api/me/sessions
DELETE /api/me/sessions/{sessionId}
```

如使用 Supabase/Auth0 等 provider，前端可以调用 provider SDK，但业务 API 仍必须验证 provider token 并映射内部 user/roles。

### 13.2 Folders

```text
GET    /api/folders
POST   /api/folders
PATCH  /api/folders/{folderId}
DELETE /api/folders/{folderId}
POST   /api/folders/{folderId}/restore
```

Delete 必须明确 non-empty policy，不允许级联永久删除全部图片。

### 13.3 Upload and Images

```text
POST   /api/uploads/intents
POST   /api/uploads/{uploadId}/complete
GET    /api/images?folder=&workflow_status=&publication_status=&q=&cursor=
GET    /api/images/{imageId}
GET    /api/images/{imageId}/readiness
PATCH  /api/images/{imageId}/draft
POST   /api/images/{imageId}/submit
POST   /api/images/{imageId}/withdraw
POST   /api/images/{imageId}/unpublish
DELETE /api/images/{imageId}
POST   /api/images/{imageId}/restore
```

生产上传建议使用短期 signed upload intent 直传对象存储；complete API 验证对象、checksum、MIME 和所有权后才创建 ready Draft。

### 13.4 Admin Review

```text
GET    /api/admin/dashboard
GET    /api/admin/review-submissions
GET    /api/admin/review-submissions/{submissionId}
POST   /api/admin/review-submissions/{submissionId}/assign
POST   /api/admin/review-submissions/{submissionId}/start
POST   /api/admin/review-submissions/{submissionId}/request-changes
POST   /api/admin/review-submissions/{submissionId}/reject
POST   /api/admin/review-submissions/{submissionId}/approve
POST   /api/admin/review-submissions/{submissionId}/approve-and-publish
```

当前 Phase 3 本地边界已实现上述 queue/detail/assign/start/decision routes；list 使用 `status` / `assignment` / bounded `limit` / `offset`，所有 mutation 要求 same-origin CSRF。纯 Reviewer 只能处理自己的 open assignment 且不能 publish；Admin/Super Admin 的完整范围和浏览器 `approve-and-publish` 都要求 AAL2。发布成功后，作品立即进入 strict public DTO、Works 与 creator profile。

### 13.5 Admin Images and Users

```text
GET    /api/admin/images
GET    /api/admin/images/{imageId}
POST   /api/admin/images/{imageId}/unpublish
POST   /api/admin/images/{imageId}/quarantine
POST   /api/admin/images/{imageId}/restore
GET    /api/admin/users
GET    /api/admin/users/{userId}
POST   /api/admin/users/{userId}/suspend
POST   /api/admin/users/{userId}/unsuspend
POST   /api/admin/users/{userId}/ban
POST   /api/admin/users/{userId}/revoke-sessions
GET    /api/admin/audit-logs
```

高风险 POST 必须支持 idempotency key，并要求 reason code。

### 13.6 错误结构

```json
{
  "error": {
    "code": "REVIEW_VALIDATION_FAILED",
    "message": "This image cannot be submitted yet.",
    "field_errors": {
      "alt_text": "Alt text is required."
    },
    "request_id": "req_..."
  }
}
```

前端显示用户可理解的 message；详细堆栈只记录在服务端受控日志。

## 14. 安全、隐私与合规要求

### 14.1 身份和权限

- 生产环境使用成熟 Auth provider 或经过审计的认证实现。
- Cookie session 使用 `HttpOnly`、`Secure`、`SameSite`。
- Admin 强制 MFA 和短 session。
- RBAC 在服务端执行；图片查询附加 owner/role 条件。
- 管理员导出和原图访问使用额外权限。

### 14.2 上传安全

- 不信任客户端 MIME、文件名、尺寸或 EXIF。
- 检查 magic bytes、完整解码、decompression bomb 和超大像素。
- 执行恶意文件扫描。
- 原始文件名不直接作为对象存储路径。
- signed URL 短期有效并绑定操作。
- display/thumbnail 由受控处理管线生成。
- 处理失败的原图保持 private/quarantined。

### 14.3 内容与隐私

- 用户提交 rights declaration 和 release status。
- 精确 GPS 默认不公开。
- release documents 单独加密存储。
- 自动审核结果对普通用户只展示必要结论，不暴露可被绕过的安全细节。
- 未成年人、违法内容、版权投诉等高风险项目支持 escalation 和 legal hold。
- 用户删除请求不能覆盖法定保留或未完成的 takedown case。

### 14.4 Web 安全

- 防止 XSS：所有用户文案输出 escape/sanitize。
- 防止 CSRF：cookie session 的 mutation API 使用 CSRF 保护。
- Rate limit：注册、登录、重置、上传 intent、提交审核、管理员决定。
- Security headers：CSP、frame ancestors、content type options、referrer policy。
- 不把内部备注、release URL、原图私有 URL返回公开 API。

## 15. 页面与功能协调

### 15.1 用户上传流程

```text
Sign In
  -> Workspace Dashboard
  -> Import Images
  -> Upload Sessions
  -> Draft in Inbox
  -> Move to Folder
  -> Edit Copy / Rights
  -> Submit
  -> Notification: In Review
  -> Approved and Published
  -> Public Works
```

### 15.2 Changes Requested

```text
Admin Request Changes
  -> user notification
  -> Changes Requested saved view
  -> open exact fields/reasons
  -> edit creates new image version
  -> resubmit creates new submission
  -> old review remains immutable
```

### 15.3 用户下架

```text
Published image
  -> User clicks Unpublish
  -> confirmation
  -> publication_status = unpublished
  -> public cache purge
  -> Works no longer returns image
  -> audit + user activity event
```

### 15.4 管理员下架

```text
Report / automated flag / admin discovery
  -> Quarantine when urgent
  -> create takedown case
  -> record evidence and reason
  -> notify user
  -> resolve: restore / remain unpublished / ban user
  -> immutable audit trail
```

## 16. UI 与交互规范

### 16.1 Upload Workspace

- 安静、密集、工作导向，不使用营销 Hero。
- 页面首屏直接显示 folders、upload queue/library、editor。
- Upload 使用 upload icon；New Folder 使用 folder-plus icon；Delete 使用 trash icon；Unpublish 使用 eye-off icon。
- Delete 与 Unpublish 不能用同一图标或同一文案。
- 状态使用 text + icon，不只用颜色。
- 图片卡片尺寸稳定，进度和状态变化不能导致列表跳动。
- 三栏不嵌套装饰卡片；panel 用分割线和 surface 区分。

### 16.2 Admin Platform

- Dashboard 只显示可操作指标。
- Review Queue 和 All Images 使用表格/紧凑列表，支持 sticky header、筛选、排序和 cursor pagination。
- Review Detail 以图片为主、审核 inspector 为辅。
- 高风险动作使用明确 dialog，显示目标、影响、reason 和不可逆性。
- Request Changes 面向用户的 message 与 internal note 分开。
- 权限不足时隐藏动作并由 API 返回 403；不能只显示 disabled 后允许直接请求。

### 16.3 通用状态

- Loading：局部 skeleton。
- Empty：一个明确下一步。
- Error：错误对象、可重试动作、request ID。
- Success：inline 状态或低干扰 toast。
- Disabled：解释缺失条件。
- Dirty：明确 autosave 状态。
- Conflict：Reload / Compare，不覆盖他人修改。
- Permission：显示账号或角色边界，不泄露目标数据存在与否。

## 17. 英文开发和产品术语

| Use | Meaning |
| --- | --- |
| `Upload Workspace` | 用户图片工作台 |
| `Import Images` | 选择/拖入文件 |
| `Drafts` | 草稿 saved view |
| `Save Draft` | 保存但不提交 |
| `Submit for Review` | 提交审核 |
| `Changes Requested` | 退回修改 |
| `Review Queue` | 待审核队列 |
| `Approve` | 审核通过 |
| `Approve and Publish` | 审核并公开 |
| `Reject` | 当前 submission 拒绝 |
| `Unpublish` | 下架但保留记录 |
| `Move to Trash` | 用户软删除 |
| `Delete Permanently` | 保留期后物理删除 |
| `Quarantine` | 紧急隔离 |
| `Takedown` | 政策/法律下架流程 |
| `All Images` | 管理员全量图片库 |
| `Audit Log` | 不可变操作日志 |

禁止继续使用：

- `Series`、`Sets`、`Collections` 作为目标产品页面。
- `Mark Published` 出现在 Upload Workspace。
- 用 `Delete` 表达下架。
- 用 `visibility` 同时表达处理、审核、公开和删除状态。
- 用 `Manage` 作为含义不清的管理员页面标题。

## 18. 推荐技术边界

### 18.1 当前原型可复用

- `archive-upload.js` 的尺寸、checksum、display/thumbnail 生成思路。
- `upload-studio.html/js` 的 folder/queue/editor 交互原型。
- `manage.html/js` 的 review list、metadata editor、checklist 和 publish 原型。
- `server.py` 和 SQLite 用于本地数据模型验证。
- `database/schema.sql` 的 PostgreSQL/Supabase 方向。

### 18.2 生产必须补齐

- Auth provider。
- PostgreSQL ownership/RBAC/RLS 或等价服务端权限。
- 对象存储和 signed upload/download。
- 后台 worker：资产生成、安全扫描、metadata 提取。
- Review submission/decision/audit 数据模型。
- 通知服务。
- 管理员 MFA、session 和审计。

SQLite + 静态页面适合本地原型，不适合作为多用户生产系统。

## 19. 分阶段开发计划

### Phase 0：移除冲突职责与建立 schema

- 从目标导航移除 Series/Collections。
- 冻结当前浏览器本地用户状态写入。
- 设计 users、folders、image states、versions、submissions、reviews、audit migrations。
- 明确 Auth 和对象存储 provider。

验收：数据模型评审通过；所有状态只有一个服务端写入源。

### Phase 1：用户系统与受保护 Workspace

- Register、Verify Email、Sign In、Sign Out、Forgot/Reset Password。
- `/api/me`、profile、account status、session boundary。
- Workspace route protection 和 owner permission tests。
- Admin MFA 与 role guard 基础。

验收：用户 A/B 数据隔离；非 Admin 无法访问 admin API。

### Phase 2：Upload Workspace + Drafts + Folders

- Upload intent、multi-file queue、asset processing、retry/cancel。
- 服务端 Draft、autosave、editor。
- Folder CRUD、Inbox、Drafts、Trash。
- Duplicate detection、quota、scan state。
- Phase 2F 代码与数据库已完成：leased scan jobs、private object integrity、无凭据 ClamAV/Pillow subprocess、retry/attempt exhaustion、append-only events 与 current-policy readiness projection；常驻 Worker 部署和监控属于生产运行工作。
- Phase 2G 已完成：owner-scoped Trash read model、Drafts/Trash 分段视图、versioned Restore 和原 Folder 失效时回退 Inbox；fake-provider、桌面/移动浏览器与 rollback-only 真库验收均通过。

验收：刷新/换设备可恢复 Draft；Folder 不影响公开 metadata；Draft 不公开。

### Phase 3：Submit + Review Queue

- 已完成 Phase 2E：server-authoritative readiness、immutable image version/submission snapshots、expected-version + UUID idempotency、notification/audit transaction 和 Upload Studio Submit UI。
- 已完成并向 development 部署 Supabase Review Queue、status/assignment filter、atomic assignment/start、image-first Review Detail、checklist，以及 Request Changes、Reject、Approve；Reviewer 与 Admin+AAL2 使用不同的最小权限范围。
- 决定采用 current-version compare-and-swap、same-payload immutable result replay、immutable decision、Review notification 和 append-only audit；migration 已部署 development，rollback-only 数据库验收、三组双会话并发 race、secret-free fake-provider 桌面/移动浏览器，以及 2026-07-22 真实 disposable Reviewer/Admin 多身份浏览器验收均已通过。真实流程覆盖 Reviewer A claim、Reviewer B cross-assignment denial、Request Changes、Admin AAL2 Approve、private 三变体、responsive/focus/console、session close 与 fixture cleanup。
- `approve_and_publish` 已作为 Admin/Super Admin+AAL2 浏览器能力开放，并接入 Supabase public DTO、derivative delivery、公开 Works 与 creator profile；Reviewer 不显示该动作，普通 Approve 也不会公开作品。
- Escalate、Quarantine、Withdraw、普通批量审批/批量分配、风险/日期/类别/release filters 与生产 SLA/通知投递保留给后续切片；现有 batch self-publish 仅是 Super Admin 自有 eligible 作品对 dedicated per-item endpoint 的受限编排。

验收：审核历史不可覆盖；并发 reviewer 不冲突；只有 approved/published 进入 Works。

### Phase 4：All Images + Users + Unpublish/Takedown

- Admin All Images/Image Detail。
- Users/User Detail、suspend/ban/session revoke/quota。
- 用户 Unpublish；Trash/Restore 已由 Phase 2G 完成。
- Admin Quarantine/Takedown/Restore。
- Audit Log。

验收：下架后公开 API 和缓存立即失效；所有高风险操作可审计。

### Phase 5：生产安全与运营

- 文件安全 Worker 的代码与数据库边界已由 Phase 2F 完成；继续补常驻运行/告警、EXIF privacy、release storage、signature freshness monitoring 与受控 rescan 运维。
- Rate limits、security headers、CSRF、CSP。
- Monitoring、alerts、backup、retention、data export/delete。
- E2E、accessibility、load、security tests。

验收：权限、安全、备份恢复、审计导出和高风险内容处置演练通过。

## 20. 测试策略

### 20.1 Unit

- 权限 policy。
- 状态转换。
- Submit validation。
- folder delete/move policy。
- mail/notification payload。
- public EXIF allowlist。

### 20.2 API Integration

- User A/B ownership isolation。
- Reviewer assignment concurrency。
- idempotent review decision。
- publish/unpublish transaction。
- upload complete verification。
- audit row creation。

### 20.3 E2E

```text
Register -> verify -> upload -> save draft -> submit
Reviewer -> request changes
User -> edit -> resubmit
Admin -> approve and publish
Visitor -> view in Works
User -> unpublish
Visitor -> no longer sees work
```

### 20.4 Security

- Horizontal privilege escalation。
- Admin route access。
- CSRF/XSS。
- malicious file and MIME spoofing。
- signed URL expiry。
- rate limit。
- session revoke。
- sensitive field leakage。

### 20.5 Responsive and Accessibility

- Desktop 1440x1000。
- Mobile 390x844。
- Keyboard complete upload metadata and review decision。
- Focus order、dialog focus trap、labels、errors、status live regions。
- 图片 alt text 编辑和公开输出验证。

## 21. 全局完成标准

- 公开产品不包含 Series/Collections 页面或导航。
- 用户系统拥有真实服务端 session 和 ownership，不依赖浏览器存储模拟。
- Upload Workspace 支持上传、草稿、文案、文件夹、提交、删除和下架。
- Draft 永远不会直接出现在公开 Works。
- 管理员可以审核和查看全部图片信息，并管理用户和下架内容。
- Review decision、Publish、Unpublish、Takedown、用户状态变更全部可审计。
- 自动检测不被描述为绝对法律判断；高风险项目有人工作业和 escalation。
- 所有用户可见功能覆盖 loading、empty、error、success、disabled、permission、conflict 状态。
- lint/typecheck/test/build、数据库 migration、API integration、桌面/移动端 E2E 和安全测试全部通过。
