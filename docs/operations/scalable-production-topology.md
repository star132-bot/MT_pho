# MT Presence 最小高可用部署与扩展方案

## 1. 文档目标

本文档定义 MT Presence 从单机部署升级为可扩展生产环境时的最低配置、标准配置、网络结构、部署顺序和扩容路径。

这里的“最低配置”指：数据库、图片存储和应用计算完全分离，并且任意一台应用服务器或单个数据库节点停止后，公开网站、登录、上传和图片扫描仍能恢复或继续运行。它不是最低成本的单机方案。

## 2. 结论

### 2.1 最少服务器和计算节点数量

最终生产环境最低购买 **2 台 ECS + 1 套 RDS PostgreSQL 高可用版**：

| 设备 | 数量 | 最低建议配置 | 用途 |
| --- | ---: | --- | --- |
| ECS A | 1 | 4 vCPU / 8 GiB / 100 GiB ESSD | Web、Nginx、图片扫描 Worker |
| ECS B | 1 | 4 vCPU / 8 GiB / 100 GiB ESSD | Web、Nginx、图片扫描 Worker |
| RDS PostgreSQL 高可用版 | 1 套 | 2 vCPU / 8 GiB / 100 GiB ESSD 起步 | 用户、作品元数据、权限、审核和审计 |

数量需要用两种口径理解：

- 阿里云控制台采购：2 台 ECS、1 套 RDS，共 3 项计算资源；
- 实际底层节点：2 个应用节点、1 个数据库主节点、1 个数据库备节点，共至少 4 个计算节点；
- OSS 是托管对象存储，不需要购买或维护图片文件服务器。

两台 ECS 和 RDS 必须：

- 位于同一地域的两个不同可用区；
- 使用相同应用版本和 Web 配置；
- 分别设置唯一的 `MT_SCANNER_ID`；
- 同时连接同一个 RDS PostgreSQL 高可用实例；
- 不保存权威业务数据和用户图片；
- 由 ALB 统一接收公网流量。

一台 ECS 加一个单节点数据库虽然可以运行项目，但任意一个节点故障都会中断业务，不属于企业级高可用部署。当前 Vultr 和 Supabase 可以在迁移期保留为回滚环境，但新旧数据库不能同时接受生产写入。

### 2.2 摄影网站的数据分工

PostgreSQL 不保存 JPEG、PNG、WebP 或 RAW 文件本体，只保存结构化数据：

- 用户、角色、Profile 和外部认证主体映射；
- 作品标题、简介、标签、类别、版权和人物授权；
- 图片所属用户、OSS object key、版本号和 SHA-256；
- 宽高、比例、MIME、文件大小、EXIF 清理状态；
- 上传、扫描、审核、发布、下架和恢复状态；
- 收藏、下载许可、通知、咨询和审计记录。

图片文件保存到 OSS：

- 原图和 RAW：私有桶，只允许签名上传和授权下载；
- 展示图和缩略图：独立 derivative 路径，通过 CDN 分发；
- 头像和封面：独立 profile 路径；
- 未扫描文件：隔离路径，扫描通过前不能公开访问；
- 灾备副本：复制到另一个地域或独立账号的 OSS 桶。

### 2.3 登录、注册和身份认证层

登录系统独立于作品数据库和图片存储。应用数据库只保存内部 `user_id`、业务 Profile 和外部身份映射；密码哈希、OAuth client secret、授权码交换、MFA factor 和 refresh token 由身份提供商管理。

计划支持的用户流程：

- 邮箱注册、邮箱验证、密码登录和退出；
- 忘记密码、重置密码、修改邮箱和安全通知；
- Magic Link 或 Email OTP 作为无密码登录；
- X OAuth 2.0 快捷登录；
- Telegram OIDC/OAuth 快捷登录；
- 一个 MT Presence 用户绑定多个登录方式；
- 查看和撤销登录 Session；
- Admin 和 Super Admin 强制 TOTP MFA/AAL2。

短期最低方案继续使用 Supabase Auth 作为托管身份提供商，不增加 ECS：

- 邮箱密码、Magic Link/OTP、Session 和 TOTP 继续由 Supabase Auth 管理；
- X 使用 Supabase 原生 X OAuth 2.0 provider；
- Telegram 使用其 OIDC Authorization Code + PKCE 流程，通过经过验证的 custom OIDC provider 或服务端 callback 接入；
- 生产邮件使用阿里云 DirectMail 等自定义 SMTP，不使用 Supabase 的测试发信额度；
- 发信使用单独子域名，例如 `auth.mtdo.cn`，并配置 SPF、DKIM 和 DMARC。

RDS 中的业务身份映射至少包含：

```text
users
  id                    MT Presence 内部稳定用户 ID
  status                active / suspended / deleted
  profile fields        展示资料

user_identities
  user_id               关联 users.id
  provider              email / x / telegram
  provider_subject      身份提供商不可变 subject
  email_at_link_time    可选审计快照，不作为唯一合并依据
  linked_at / last_used_at
```

账号绑定规则：

- 登录后必须重新验证当前 Session 才能绑定或解绑身份；
- 不得只因为两个 provider 返回相同邮箱就静默合并账号；
- Telegram 可能没有邮箱，始终以经过验证的 provider subject 作为外部身份键；
- 至少保留一种可用登录方式，不能把用户锁在账号外；
- Provider token 不进入浏览器持久化存储或普通业务表；
- OAuth callback 必须验证 `state`、PKCE、issuer、audience、签名和过期时间；
- X、Telegram 在部分网络环境不可用，因此邮箱登录必须始终作为基础入口。

如果以后不再使用 Supabase Auth，而是在阿里云自托管认证服务，为避免登录系统成为新的单点故障，至少增加 2 台 2C4G Auth ECS 并放在不同可用区。这个阶段的总 ECS 数量将从 2 台增加到 4 台；数据库仍使用同一套 RDS 高可用实例，但认证 schema、角色和凭据必须与业务 schema 隔离。

### 2.4 非服务器托管资源

最低生产方案还必须具备：

| 资源 | 最低数量 | 用途 |
| --- | ---: | --- |
| ALB | 1 | HTTPS、负载均衡、健康检查和故障摘除 |
| RDS PostgreSQL 高可用版 | 1 套 | 独立数据库主备、自动备份和故障切换 |
| OSS 主存储 | 1 套 | 原图、展示图、头像、封面和隔离文件 |
| OSS 灾备存储 | 1 套 | 第二地域或独立账号的图片副本 |
| 身份提供商 | 1 套 | Supabase Auth 起步；管理邮箱、OAuth、Session 和 MFA |
| 事务邮件服务 | 1 套 | 注册验证、找回密码和安全通知 |
| 日志与监控 | 1 套 | 健康检查、错误率、进程重启和磁盘告警 |
| 域名证书 | 1 套 | 覆盖主域名和需要保留的别名域名 |

WAF、Redis、独立消息队列和单独预发布服务器不是最低配置的硬性要求，但应按风险和流量逐步加入。

## 3. 最低部署拓扑

```text
                         用户
                          |
                    阿里云 DNS
                          |
                    ALB + HTTPS
                    /           \
          可用区 A /             \ 可用区 B
                  /               \
          ECS A 4C8G             ECS B 4C8G
          - Nginx                - Nginx
          - Web                  - Web
          - Scanner A            - Scanner B
                  \               /
                   \             /
                    应用服务访问层
              /             |             \
             /              |              \
    托管身份提供商       RDS PostgreSQL       OSS 主图片存储
 Email/X/Telegram/MFA   主节点 <-> 备节点      |        \
          |                                   CDN      灾备 OSS
     DirectMail SMTP
```

这套方案只需要自行维护两台 ECS。数据库由 RDS 管理主备节点，图片容量由 OSS 独立扩展。Web 和 Scanner 同机能够降低初期成本；两个 Scanner 通过数据库租约领取任务，必须使用不同 Worker 标识，避免重复处理。

## 4. 最低服务器配置

### 4.1 两台 ECS 的共同配置

- 规格：4 vCPU、8 GiB 内存；
- 系统盘：100 GiB ESSD；
- 操作系统：项目验证过的长期支持版 Linux；
- 公网 IP：不配置；
- 入站流量：只接受 ALB 和受控运维入口；
- 应用账户：`mtpresence`；
- 扫描账户：`mtpresence-scanner`；
- 常驻服务：Nginx、Web systemd service、ClamAV daemon、Scanner systemd service；
- 临时文件：分别使用受权限保护的 Web 和 Scanner 目录；
- 日志：发送到集中日志服务，不只保留在本机。

4C8G 是 Web 与 ClamAV 同机时的最低建议值。2C4G 可能能够启动，但病毒库加载、图片解码和并发请求会争夺内存，不作为生产采购基线。

### 4.2 不应部署在 ECS 上的内容

- PostgreSQL 数据库进程或数据库文件；
- 用户原图、头像、封面和缩略图的权威副本；
- 唯一一份数据库备份；
- Git 仓库中的明文生产密钥；
- 依赖本机的登录 Session 或任务状态。

## 5. 网络和访问控制

```text
公网 -> 80/443 -> ALB
ALB -> 应用端口 -> ECS A / ECS B
ECS -> PostgreSQL private endpoint -> RDS
ECS -> HTTPS/private endpoint -> OSS
CDN -> HTTPS -> OSS derivative objects
公网 -X-> ECS 应用端口、Scanner、数据库和 ClamAV
```

最低安全要求：

- ECS 不暴露应用端口到公网；
- SSH 只允许固定管理 IP 或受控运维通道；
- Web 使用最小权限数据库角色，不能包含数据库管理员密码和 Scanner secret；
- Scanner 使用独立 secret 和 Unix 身份；
- 两台 ECS 使用相同 Cookie 签名配置，但 Scanner ID 必须不同；
- ALB 健康检查访问 `/healthz`；
- `/readyz` 只允许受信任的内部检查，不公开给匿名用户；
- 域名 A/ALIAS/CNAME 记录最终指向 ALB，不再直接指向某一台 ECS。

## 6. 数据安全最低要求

多一台 ECS 只能提高服务可用性，不能替代数据备份。最低方案必须同时完成：

1. RDS 使用跨可用区高可用版，不使用 Basic 单节点版作为最终生产数据库。
2. RDS 开启自动备份和时间点恢复；每日另存加密 PostgreSQL 逻辑备份及 SHA-256 manifest。
3. 数据库备份只包含元数据，不包含 OSS 图片对象；二者必须分别备份并通过 asset ID/object key 对账。
4. OSS 主桶和灾备桶开启版本控制，备份凭据与应用运行凭据分离。
5. 建议保留 7 个每日、4 个每周和 12 个每月备份。
6. 每月至少把数据库和一个对象恢复到隔离环境一次，确认备份实际可用。
7. 初始目标建议为 RPO 不超过 24 小时；启用 PITR 后再将数据库 RPO 收紧到 15 分钟以内。初始 RTO 建议为 1 至 4 小时。

## 7. 部署步骤

### 阶段 A：准备基础设施

1. 在同一阿里云地域创建 VPC 和两个可用区的交换机。
2. 创建两台 4C8G ECS，分别进入两个可用区。
3. 创建跨可用区 RDS PostgreSQL 高可用版，主备节点分别位于两个可用区。
4. 创建 OSS 私有主存储、derivative 路径和第二地域或独立账号灾备桶。
5. 创建跨可用区 ALB，并将两台 ECS 加入后端服务器组。
6. 配置安全组，禁止 ECS 应用端口和 RDS 直接暴露公网。
7. 申请或上传域名证书，在 ALB 配置 HTTPS。
8. 为 OSS 开启版本控制、复制、生命周期和独立备份凭据。

### 阶段 B：部署应用

1. 使用同一个已审核 Git tag 构建不可变发布包。
2. 先安装到 ECS A，不立即承接生产流量。
3. 安装 Web 和 Scanner systemd unit，并执行运行时 preflight。
4. 设置 ECS A 的唯一 `MT_SCANNER_ID`。
5. 使用同一发布包部署 ECS B，并设置另一个 `MT_SCANNER_ID`。
6. 确认两台 Web 使用相同 `MT_PUBLIC_BASE_URL`、Cookie、RDS endpoint 和 OSS 配置。
7. 分别验证 `/healthz`、内部 `/readyz` 和 Scanner 任务领取。

### 阶段 C：联调与切流

1. 通过 ALB 临时地址执行匿名页面、登录、上传、扫描、审核和发布测试。
2. 停止 ECS A，确认 ALB 自动将流量送入 ECS B。
3. 恢复 ECS A，再停止 ECS B，重复验证。
4. 确认关闭任意一台后 Scanner 仍能领取并完成新任务。
5. 完成数据库和 Storage 独立备份并执行一次隔离恢复。
6. 将 `mtdo.cn` 指向 ALB，保留 `mt6666.cn` 到主域名的重定向。
7. 迁移后的 14 至 30 天保留 Vultr 回滚环境，但停止其生产写入。

## 8. 发布和回滚方式

双节点采用滚动发布：

1. 从 ALB 后端摘除 ECS A。
2. 在 ECS A 安装并验证新版本。
3. 将 ECS A 加回 ALB，观察健康状态。
4. 摘除 ECS B，安装相同的 Git tag。
5. 验证后将 ECS B 加回。

出现应用故障时逐台切换到上一不可变发布版本。数据库变更必须先备份并在隔离克隆验收；数据库回滚不依赖应用 symlink 回滚。

## 9. 后续扩展路径

### 最低企业方案：2 台 ECS + RDS 高可用

- ECS A：Web + Scanner；
- ECS B：Web + Scanner；
- RDS：一个主节点和一个备节点；
- OSS：主图片存储和灾备存储；
- 优点：应用、数据库、图片三层分离，任意单应用节点故障仍可服务；
- 限制：Web 和扫描争夺 CPU/内存，Scanner secret 存在于两台 Web 主机。

### 标准生产方案：4 台 ECS

- 2 台 2C4G Web；
- 2 台 4C8G Scanner Worker；
- Web 与高权限扫描服务完全分离；
- 可分别扩展 Web 和图片处理能力。

### 完整企业方案：5 台以上 ECS

- 2 台 Web；
- 2 台 Scanner Worker；
- 1 台独立 Staging；
- 按实际负载增加 Web 或 Worker；
- 需要时加入 WAF、Redis、消息队列和跨地域数据库灾备。

从 Supabase 迁移到 RDS/OSS 是独立的数据平台迁移项目。当前系统已经把数据库和 Storage 托管在 Supabase，它们并不位于 Vultr Web 服务器上；但系统同时依赖 Supabase Auth、RLS、RPC 和 Storage 签名，因此不能把数据库连接地址直接替换为 RDS。必须迁移 PostgreSQL schema/data、认证边界、RLS/RPC、Storage object key 和签名流程。服务器迁移和数据平台迁移应分两次发布，并在最终切换时停止旧库写入，避免双写分叉。

## 10. 最低方案验收标准

- 两台 ECS 位于不同可用区并由一个 ALB 分流；
- 任意关闭一台 ECS 后，网站、登录和公开 Works 仍可用；
- 任意关闭一台 ECS 后，新上传的图片仍能由另一台 Scanner 处理；
- ECS 不保存权威数据库和用户图片，RDS 与 OSS 均使用私网或受控 endpoint；
- 任意触发一次 RDS 主备切换后，应用能够重新连接数据库；
- 两台服务器没有公开暴露 ClamAV、应用内部端口或管理接口；
- 数据库和 Storage 均存在独立于生产系统的备份；
- 已真实完成一次数据库和对象恢复；
- 域名、HTTPS、Auth redirect 和 `MT_PUBLIC_BASE_URL` 一致；
- 发布可逐台执行，旧版本可以逐台恢复；
- 日志能够识别具体 ECS 和 Scanner ID，并对 5xx、健康检查失败、磁盘和 Worker 停止发送告警。

## 11. 官方能力参考

- [阿里云 RDS 高可用与灾备设计](https://help.aliyun.com/en/rds/product-overview/high-availability-and-disaster-recovery)：高可用版主备、多可用区、自动备份和时间点恢复。
- [阿里云 OSS 产品概览](https://help.aliyun.com/en/oss/user-guide/oss-overview)：对象存储容量扩展、多可用区冗余和跨地域复制。
- [阿里云 OSS 数据复制](https://help.aliyun.com/en/oss/user-guide/data-replication-2/)：同地域复制和跨地域灾备。
- [阿里云 OSS 版本控制](https://help.aliyun.com/en/oss/user-guide/overview-78/)：防止图片被误覆盖或误删除。
- [使用 CDN 加速 OSS](https://help.aliyun.com/en/oss/user-guide/cdn-acceleration)：通过边缘缓存分发展示图和缩略图。
- [Supabase Auth](https://supabase.com/docs/guides/auth)：邮箱、密码、OTP、社交登录、Session 和 MFA 的托管认证能力。
- [Supabase X OAuth 2.0](https://supabase.com/docs/guides/auth/social-login/auth-twitter)：X provider、callback 和 PKCE 接入流程。
- [Telegram Login](https://core.telegram.org/bots/telegram-login)：Telegram Authorization Code、PKCE、ID Token 签名和 claims 校验。
- [阿里云 DirectMail 发信域名](https://help.aliyun.com/en/direct-mail/user-guide/how-to-configure-sending-domain-names)：事务邮件发信域名以及 SPF、DKIM、DMARC 配置。
