# MT Presence 服务器生产化审计与优化任务

你现在负责对 MT Presence 的目标服务器进行一次完整、谨慎、可回滚的生产化审计与优化。

这不是单纯“把项目跑起来”的任务。目标是确认服务器、应用、数据库、对象存储、图片扫描器、反向代理、TLS、备份、监控和发布流程具备正式上线条件，并在不破坏现有服务和数据的前提下补齐缺口。

## 1. 项目信息

本地项目目录：

`/Users/starfeld/Web_MT`

必须优先阅读：

- `/Users/starfeld/Web_MT/README.md`
- `/Users/starfeld/Web_MT/CHANGELOG.md`
- `/Users/starfeld/Web_MT/docs/architecture/project-map.md`
- `/Users/starfeld/Web_MT/docs/architecture/database-design.md`
- `/Users/starfeld/Web_MT/docs/architecture/provider-decisions.md`
- `/Users/starfeld/Web_MT/docs/operations/production-deployment.md`
- `/Users/starfeld/Web_MT/docs/operations/upload-testing.md`
- `/Users/starfeld/Web_MT/docs/operations/review-testing.md`
- `/Users/starfeld/Web_MT/docs/operations/public-delivery-testing.md`
- `/Users/starfeld/Web_MT/scripts/release_gate.sh`
- `/Users/starfeld/Web_MT/scripts/database_acceptance_gate.sh`
- `/Users/starfeld/Web_MT/scripts/production_preflight.py`
- `/Users/starfeld/Web_MT/scripts/verify_production.py`
- `/Users/starfeld/Web_MT/scripts/build_production_release.sh`
- `/Users/starfeld/Web_MT/scripts/manage_production_release.py`
- `/Users/starfeld/Web_MT/scripts/backup_production_database.sh`
- `/Users/starfeld/Web_MT/scripts/verify_production_backup.sh`
- `/Users/starfeld/Web_MT/deploy/`

当前已知状态：

- Git 最新标签为 `v1.2.3`。
- 公开 UI、登录账户、上传、扫描、Review、发布、Admin Works、Admin Users、Inbox、Notifications 和 Audit Ledger 的代码已经存在。
- 本地 `scripts/release_gate.sh` 已通过，但这不代表远程服务器已经部署正确。
- README 与 `VERSION` 可能仍显示 `1.0.0`，需要核对发布元数据是否漂移。
- Phase 5 communications/audit migration 及其非生产 rollback-only 验收仍可能是生产提升门禁。
- 生产常驻 Scanner、监控、告警、正式域名/TLS、对象存储恢复策略可能尚未完成。
- 不得假设服务器已经是生产环境，也不得假设它还是空服务器；先用证据确认。

## 2. 任务结果

最终需要交付：

1. 服务器现状审计报告。
2. 风险分级清单：Blocker / High / Medium / Low。
3. 每个问题的证据、影响、建议和回滚方式。
4. 经用户批准后完成的实际优化。
5. 发布前、发布中、发布后的验证记录。
6. 一份可以重复执行的运维检查清单。
7. 明确说明哪些内容仍未完成，不能用“基本完成”掩盖缺口。

## 3. 最高优先级安全规则

必须遵守：

- 默认把远程服务器视为正在承载真实数据的生产服务器。
- 第一阶段只允许只读检查，不要立即修改系统。
- 在不知道服务器地址、SSH 用户、域名和环境属性时，不要猜测目标。
- 使用已有 SSH Key；不要要求用户把 root 密码或私钥明文发到聊天中。
- 不要把密码、Token、Cookie、Supabase secret、数据库密码、签名 URL 或完整环境变量输出到终端、日志、截图或报告。
- 不要执行 `cat /etc/mt-presence/*.env` 或其他会暴露 secret 的命令。
- 可以验证变量是否存在、文件权限和变量名称，但不得输出变量值。
- 不要把 secret 放进命令参数、Git、shell history、构建产物或临时报告。
- 禁止执行 `git reset --hard`、`rm -rf`、清空数据库、删除 Storage bucket 或直接覆盖 active release。
- 禁止在生产主库运行 fixture-writing、rollback-only、并发竞争或破坏性数据库测试。
- “测试最后会 ROLLBACK”不构成在生产数据库执行测试的许可。
- 不要在未验证 SSH Key 第二会话可用前禁用密码登录。
- 不要在未验证新 Nginx 配置前 reload。
- 不要在没有数据库备份和恢复方案前运行生产迁移。
- 不要在没有可用上一版本和回滚命令前激活新版本。
- 不要在未获用户明确批准前重启生产 Web、Scanner、Nginx、PostgreSQL 或主机。
- 不要擅自修改 DNS、防火墙、证书、系统用户、自动更新策略或云服务设置。
- 所有会造成短暂中断、外部状态变化、费用变化或权限变化的操作，执行前必须列出影响并请求确认。

## 4. 工作方式

将任务拆为五个阶段，不得跳级。

### 阶段 A：只读审计

只收集事实，不修改远程状态。

完成后先向用户提交审计结果和变更计划，再进入下一阶段。

### 阶段 B：备份与候选环境

创建并验证备份，在 development、staging 或隔离恢复克隆上验证迁移和恢复。

不得把生产主库当测试环境。

### 阶段 C：准备生产候选发布

在本地通过 release gate，生成干净、带标签、校验和固定的发布包。服务器只安装，不直接编辑 active release。

### 阶段 D：经批准后激活

只有全部门禁通过并获得用户明确批准，才允许迁移生产数据库、切换 release symlink、重启服务和 reload Nginx。

### 阶段 E：上线观察

完成只读生产 smoke test，观察日志和指标，保留上一版本，确认无回滚条件后再结束。

## 5. 阶段 A：本地代码与发布状态审计

先在 `/Users/starfeld/Web_MT` 检查：

- `git status --short --branch`
- 当前 commit、远程分支和 tag
- 当前 commit 是否有精确 release tag
- 工作树是否干净
- `README.md`、`VERSION`、Git tag 和发布包版本是否一致
- `.env`、`.env.worker`、SQLite、截图、浏览器状态、私钥是否被 Git 忽略
- `dist/` 是否来自当前 tag，而不是旧构建
- 生产包是否排除 `.git`、`.env`、`.env.worker`、测试截图、本地数据库和临时文件
- `deploy/` 中 systemd 与 Nginx 模板是否仍包含未替换 marker
- 功能地图和部署文档是否与当前文件职责一致

运行：

```bash
bash scripts/release_gate.sh
```

记录完整结果。失败时先定位，不得绕过或删除测试。

不要仅因为 release gate 通过就宣称生产可用，因为它不替代真实数据库、浏览器和服务器验收。

## 6. 阶段 A：远程服务器只读清点

只有获得正确 SSH 目标后才连接服务器。

只读确认：

### 6.1 主机基础状态

- Linux 发行版和内核版本
- 主机时区和时间同步状态
- CPU、内存、Swap、磁盘容量和 inode
- 当前 load average
- 是否存在磁盘、内存或进程压力
- 最近是否发生 OOM Kill
- 重启时间和 uptime
- 安全更新是否长期积压
- 仅记录必要信息，不输出与项目无关的用户隐私

建议检查工具：

- `uname -a`
- `/etc/os-release`
- `uptime`
- `free -h`
- `df -h`
- `df -i`
- `timedatectl status`
- `systemctl --failed`
- 只读 `journalctl` 查询

### 6.2 网络与开放端口

确认：

- 对公网只开放必要端口，通常为 SSH、HTTP、HTTPS
- Web 应用只监听 loopback
- `/readyz` 不经 Nginx 对匿名公网开放
- Nginx 是唯一公网 Web 入口
- 没有意外暴露 Python 开发服务器端口、PostgreSQL、ClamD、调试端口或管理端口
- 云安全组和主机防火墙规则一致

禁止在审计阶段直接修改防火墙。

### 6.3 服务和进程

检查：

- `mt-presence.service`
- `mt-presence-scanner.service`
- `mt-presence-healthcheck.timer`
- Nginx
- ClamAV/ClamD
- 时间同步服务

记录：

- active / failed 状态
- restart count
- 启动时间
- 主进程用户
- 是否以 root 运行
- 是否频繁重启
- 是否存在 zombie 或重复实例
- systemd sandbox 配置是否生效

只看 `systemctl status`、`systemctl show` 和安全日志摘要，不打印 Environment 中的 secret。

### 6.4 目录和权限

核对：

```text
/opt/mt-presence/current
/opt/mt-presence/previous
/opt/mt-presence/releases/
/etc/mt-presence/web.env
/etc/mt-presence/scanner.env
/etc/mt-presence/database.env
/var/lib/mt-presence/
/var/lib/mt-presence-scanner/
```

目标权限：

- Web 与 Scanner 使用不同的无登录系统用户
- Web 不读取 scanner/database secret
- Scanner 不读取 web/database env
- `web.env` 通常为 `0640 root:mtpresence`
- `scanner.env` 通常为 `0640 root:mtpresence-scanner`
- `database.env` 为 `0600 root:root`
- Scanner 临时目录只能由 Scanner 用户读写
- release 内容不可由运行时用户任意修改
- `current` 与 `previous` 必须指向明确 release

不要读取环境文件的值。可以通过受控脚本或变量名称白名单验证存在性。

## 7. Web 运行时配置审计

验证以下配置存在且语义正确，但不要输出 secret 值：

- `MT_RUNTIME_ENVIRONMENT=production`
- `MT_COOKIE_SECURE=1`
- `MT_TRUST_PROXY=1`
- `MT_MAX_REQUEST_THREADS` 在合理范围，例如 4–128
- `MT_PUBLIC_BASE_URL` 是无凭据、无 query 的 HTTPS 正式域名
- 生产环境禁用 local archive preview
- Web 进程只使用 Supabase publishable key
- Web 环境不得出现 `PGPASSWORD`
- Web 环境不得出现 `SUPABASE_SECRET_KEY`
- Web 环境不得出现 `SUPABASE_SERVICE_ROLE_KEY`
- inquiry rate limit 必须是有界值
- Cookie 的 Secure、HttpOnly、SameSite 与域名策略正确
- 受保护响应使用正确 Cache-Control
- 错误响应不暴露 traceback、SQL、Storage key、内部对象或 secret

使用现有：

```bash
python3 scripts/production_preflight.py
```

如果服务器上的 release 不包含该脚本，记录为部署完整性问题，不要从未知来源临时下载脚本。

## 8. Scanner 生产运行审计

Scanner 是正式上线的关键门禁。

确认：

- Scanner 与 Web 是不同 Unix 用户和不同环境文件
- Scanner 独占 Supabase privileged credential
- Web、Nginx 和浏览器永远拿不到 Scanner credential
- `MT_SCANNER_ID` 合法且稳定
- `MT_SCANNER_TEMP_DIR` 位于 `/var/lib/mt-presence-scanner` 下
- 临时目录权限为 `0700` 或等价最小权限
- ClamAV 签名为近期版本
- ClamD 正在运行且健康
- systemd 隔离环境中默认使用 `clamdscan --stream --no-summary`
- 禁止在 hardened production namespace 使用 `--fdpass`
- 扫描失败必须 fail closed，不能把不确定结果标记为 clean
- 队列没有持续增长、长期 lease、无限重试或大量 failed
- Scanner 日志不包含 token、signed URL、Storage key 和用户隐私
- Scanner restart policy 不形成高速重启循环

建立指标：

- queue depth
- oldest queued age
- claimed/leased count
- clean/flagged/failed rate
- retry/expiry rate
- Scanner restart count
- ClamAV signature age
- 单图扫描时长

生产 Scanner、队列监控和告警未真实验证前，不得宣布上传发布流程正式可用。

## 9. Nginx 与 TLS 审计

只读检查当前启用配置，禁止直接覆盖。

确认：

- 所有 `__DOMAIN__` 等模板 marker 已替换
- `nginx -t` 能通过
- 证书域名与正式域名一致
- 证书链完整
- 证书未临近过期
- 自动续期 timer 有效
- 只允许现代 TLS，至少 TLS 1.2/1.3
- HTTP 自动跳转 HTTPS
- HSTS 只有在 HTTPS、子域和回滚策略确认后才启用或扩大
- Nginx 只代理到 loopback Web 进程
- `/healthz` 可以供外部监控读取
- `/readyz` 只允许可信本机或运维网络访问
- 上传请求体大小与项目允许的最大图片一致
- 读取、连接和上游 timeout 与上传/扫描职责匹配
- 查询字符串、Cookie、Authorization、密码和表单正文不进入日志
- 日志包含 request ID、状态码、路径、耗时和上游状态
- 静态文件、图片和 HTML 的缓存策略区分清楚
- CSP、X-Content-Type-Options、Referrer-Policy、Frame 限制等安全头正确
- 404/500 页面不暴露 Nginx、Python 或内部路径信息
- Nginx 不公开 `.git`、`.env`、数据库、备份、脚本、docs、测试文件和私有原图

任何修改必须：

1. 写入候选配置文件。
2. 保存原配置可恢复副本。
3. 运行 `nginx -t`。
4. 展示 diff。
5. 获取用户批准。
6. 才允许 reload。

## 10. 数据库升级、备份与恢复

生产数据库操作是最高风险部分。

### 10.1 先确认环境

查明：

- 当前数据库是否 development、staging 或 production
- 已应用 migration 列表
- 是否包含 Phase 5 communications/audit migration
- Web 代码与数据库 schema 是否匹配
- 是否存在长事务、失败 migration、异常连接和容量压力

### 10.2 生产前备份

使用项目脚本创建数据库备份：

```bash
set -a
source /etc/mt-presence/database.env
set +a
MT_BACKUP_DIR=/var/backups/mt-presence bash scripts/backup_production_database.sh
bash scripts/verify_production_backup.sh /var/backups/mt-presence/<backup.dump>
```

不得输出数据库密码。

验证：

- 备份文件非空
- SHA-256 manifest 存在
- manifest 副本保存在与备份不同的位置
- 权限最小化
- 备份加密或位于加密存储
- 备份保留策略明确
- 磁盘剩余空间足够

### 10.3 恢复演练

把已验证备份恢复到隔离 staging/recovery clone。

必须证明：

- 数据库可以恢复
- schema 与关键行数合理
- Storage object 引用没有明显失配
- 恢复环境无法误发邮件或触发真实生产 webhook
- 恢复环境使用独立非生产凭据

仅“成功生成 dump”不等于备份有效。

### 10.4 Migration 验收

在隔离 clone 上运行：

```bash
MT_DEPLOY_ENVIRONMENT=staging \
MT_APPLY_PHASE1_BASELINE=no \
bash scripts/deploy_supabase_phase1.sh
```

然后只在 development 或 staging clone 运行：

```bash
MT_TEST_ENVIRONMENT=development bash scripts/database_acceptance_gate.sh
```

确认 fixture 完全清理。

绝对禁止把 `/etc/mt-presence/database.env` 用于上述 rollback-only acceptance。

### 10.5 生产 Migration

只有以下全部满足并取得明确批准后才可执行：

- 备份验证通过
- 恢复演练通过
- staging migration 通过
- database acceptance 通过
- 应用 release 已准备
- 回滚/恢复负责人明确
- 维护窗口明确

现有生产库不得重新应用非幂等 baseline：

```bash
MT_DEPLOY_ENVIRONMENT=production \
MT_ALLOW_PRODUCTION=yes \
MT_APPLY_PHASE1_BASELINE=no \
bash scripts/deploy_supabase_phase1.sh
```

生产迁移后只能执行只读 schema/catalog 和 HTTPS smoke verification，不运行 fixture 测试。

## 11. Supabase 与对象存储

核对：

- Auth redirect allowlist 只包含正式可信域名和必要回调
- 生产不允许 localhost 回调残留，除非有明确运维理由
- Web 只持有 publishable key
- Scanner secret 与数据库凭据分离
- RLS 在所有关键表启用
- anon/authenticated/service 权限与文档一致
- public Works 只返回已发布 DTO
- original 永远私有
- 只有 clean 的 display/thumbnail 可以公开交付
- signed URL 生命周期有界
- 公开 API 不暴露 owner UUID、原图、私有 EXIF/GPS、review evidence、bucket/key
- authoritative empty/error 不回退本地 sample 或 IndexedDB

对象存储不包含在 PostgreSQL dump 中，必须额外提供：

- 加密备份或 provider recovery policy
- original/display/thumbnail bucket 的保留策略
- 对象与数据库 metadata 一致性检查
- 删除、takedown、restore、retention 的操作流程
- 恢复单个测试对象和数据库引用的演练
- orphan object 检测与人工处置流程

对象存储恢复策略未验证前，正式上线仍有数据恢复 Blocker。

## 12. SSH 与主机安全

检查并提出建议，但危险变更必须单独批准。

- 日常部署使用 SSH Key
- root 密码不写入脚本或聊天
- 验证第二个 SSH 会话后才考虑禁用 password login
- 是否需要禁用直接 root SSH，必须结合现有运维方式判断
- SSH 端口变更不是安全目标本身，不要为了“看起来安全”盲目更改
- 主机防火墙只允许必要端口
- 系统服务使用最小权限用户
- systemd 使用 `NoNewPrivileges`、`ProtectSystem`、`PrivateTmp` 等现有模板防护
- 日志和备份目录权限合理
- 自动安全更新策略必须先评估重启影响
- 不安装不必要面板、数据库 Web 管理器或未知监控 Agent
- 不把开发工具、浏览器 profile、Git credentials 和个人 SSH key复制到服务器

## 13. 应用发布与回滚

禁止通过 SCP/rsync 直接覆盖 `/opt/mt-presence/current` 内的运行文件。

正确流程：

1. 本地工作树干净。
2. release gate 通过。
3. commit 有精确 tag。
4. 使用 `build_production_release.sh` 构建不可变发布包。
5. 校验 SHA-256。
6. 通过 SSH 传输发布包和校验和。
7. 安装到新的 `/opt/mt-presence/releases/<release-id>`。
8. 运行 production preflight。
9. 不激活地完成检查。
10. 获得明确批准。
11. 原子切换 `current` symlink。
12. 重启 Web/Scanner，reload Nginx。
13. 运行只读 smoke test。
14. 保留 `previous` 直至观察期结束。

发布管理器必须拒绝：

- checksum 不匹配
- 路径穿越
- symlink/device/FIFO
- 缺少必要文件
- 发布包中包含环境文件
- 重复 release ID
- dirty/untagged release

回滚要求：

- 应用回滚使用原子 symlink swap
- 数据库不能依赖自动 down migration
- 数据库失败时停止写入并恢复到新的 recovery database/project
- 不直接覆盖失败生产库
- 回滚后重新运行生产验证
- 记录操作时间、操作者、release ID 和结果

## 14. 可用性与健康检查

验证：

- `/healthz` 不依赖外部 provider，可以快速返回
- `/readyz` 能真实探测 Supabase/provider
- provider 故障时 `/readyz` 返回 503
- `/healthz` 和 `/readyz` 禁止缓存
- systemd 健康检查 timer 正常运行
- 外部 uptime monitor 检查 HTTPS `/healthz`
- 可信内部监控检查 loopback `/readyz`
- 监控不会携带或记录 secret
- 健康检查频率不会造成压力

告警至少覆盖：

- HTTPS 不可用
- 5xx 比例升高
- 延迟异常
- Web/Scanner 重启
- `/readyz` 连续失败
- Scanner queue age 超阈值
- failed/flagged 扫描异常增长
- 磁盘或 inode 不足
- 内存压力/OOM
- 数据库连接失败
- 备份任务失败
- TLS 证书即将过期
- Nginx 配置或服务失败

## 15. 日志、隐私与审计

确认日志包含足够诊断信息，但不泄露用户隐私。

应记录：

- timestamp
- request ID
- path，不含 query string
- method
- status
- duration
- upstream status
- 服务启动、停止和异常摘要

不得记录：

- Cookie
- Authorization header
- access/refresh token
- Supabase secret
- 数据库密码
- signed URL
- 完整 query string
- 询价正文和回复正文
- 用户密码
- MFA code
- 私有 Storage path
- 原始审核证据

检查：

- journald 或日志轮转策略
- 最大占用空间
- 保留期限
- 日志访问权限
- request ID 是否贯穿 Nginx 和应用
- 生产 traceback 是否隐藏
- Audit Ledger 是否只展示允许字段

## 16. 性能优化

先测量，再修改。不要通过主观判断添加缓存或压缩。

测试页面：

- Home
- Works
- Work Detail
- About
- Lightbox
- Contact
- Dashboard
- Upload Studio
- Review

视口：

- 1440×900
- 1024×768
- 390×844

网络条件：

- 正常宽带
- Fast 3G 或等价弱网模拟

测量：

- LCP
- CLS
- INP 或交互延迟
- TTFB
- HTML/JS/CSS 体积
- 首屏图片体积
- 请求数量
- 缓存命中
- 图片解码和布局跳动

优化原则：

- Hero 与首屏图片设置准确尺寸/aspect-ratio，避免 CLS
- 首屏关键图片可以高优先级，但不要预加载整页画廊
- Works 非首屏图片使用合理 lazy loading
- 使用 display/thumbnail 衍生图，不向公开页面发送 original
- 根据现有图片管线评估 WebP/AVIF，不要破坏浏览器兼容和取证边界
- HTML/身份相关响应不使用危险公共缓存
- 指纹化静态资源使用长期 immutable cache
- 未指纹化 HTML/CSS/JS 使用保守缓存和正确 revalidation
- Nginx gzip/Brotli 仅用于适合的文本资源，不重复压缩图片
- 不要通过删除可访问性、错误态或安全校验换取性能分数

## 17. 生产 Smoke Test

先运行只读验证：

```bash
python3 scripts/verify_production.py --base-url https://<domain>
```

脚本应从应用主机通过 HTTPS 验证公网边界，并通过 loopback 验证 `/readyz`。

激活后，使用专门的 disposable production-test identities 完成：

1. Register、Verify、Sign In、Sign Out、Forgot/Reset。
2. Admin MFA。
3. 上传一张不敏感测试图片。
4. 等待 Scanner clean。
5. Draft readiness。
6. Submit for Review。
7. Reviewer claim/start/decision。
8. Admin approve and publish。
9. 公开 Works 和 creator profile 可见。
10. Takedown 和 Restore。
11. Guest 与 authenticated inquiry。
12. Notifications unread/read。
13. Inbox 隔离、reply、Close/Reopen。
14. User suspend/reactivate。
15. Reviewer role grant/revoke。
16. Audit Ledger 记录正确且不泄露隐私。
17. Home、Works、Detail、About、Lightbox、Contact、Dashboard、Review 的桌面与移动视觉。
18. 浏览器 console/page errors 为空。

所有写入型 Smoke 使用可清理的专用测试身份和测试资源，不得使用客户账户。

## 18. 上线后一小时观察

激活后至少观察一小时：

- Nginx 4xx/5xx
- Web latency
- Web/Scanner restart
- `/healthz`
- `/readyz`
- Scanner queue depth 和 oldest age
- 上传失败
- inquiry 创建失败
- Inbox reply 失败
- audit failure event
- 数据库连接
- CPU、内存、Swap、磁盘、inode
- TLS 和 DNS

观察期结束前保留上一 release，不要删除。

出现以下任一情况应停止继续发布并评估回滚：

- 连续 readiness 失败
- 5xx 明显上升
- 登录/session 异常
- 上传或扫描长期卡住
- Review/Publish 失败
- 数据泄露迹象
- 数据库迁移不一致
- 日志出现 secret
- CPU/内存/磁盘失控

## 19. 文档与版本一致性

如果修改代码、脚本、部署配置或职责边界，必须同步更新：

- `docs/architecture/project-map.md`
- `README.md`
- `CHANGELOG.md`
- 相关 operations 文档
- `VERSION`

核对 Git tag、VERSION、README 当前版本、构建包 release ID 和服务器 current symlink 必须一致。

不要保留“代码 v1.2.3、README v1.0.0、服务器未知版本”这种漂移。

## 20. 输出格式

第一阶段只读审计后，必须使用以下结构报告，不能立即修改生产环境：

```text
服务器身份：
- Host / domain：仅显示非敏感标识
- 环境：production / staging / development / unknown
- 当前 release：...
- 当前 commit/tag：...

总体结论：
- 上线成熟度：...%
- 是否建议立即正式上线：是 / 否
- Blocker 数量：...

Blocker：
1. 问题：...
   证据：...
   影响：...
   建议：...
   需要的权限或确认：...
   回滚方式：...

High / Medium / Low：
- ...

建议执行顺序：
1. ...
2. ...

本轮只读检查：
- 已检查：...
- 未检查：...
- 未检查原因：...

下一步需要用户确认的变更：
- ...
```

生产变更完成后，必须报告：

```text
已完成：
- ...

未完成：
- ...

备份：
- 数据库备份验证：通过/失败
- 恢复演练：通过/失败
- 对象存储恢复：通过/失败

发布：
- Release ID：...
- Previous release：...
- Current symlink：...
- Migration：...

验证：
- release gate：...
- staging database gate：...
- production preflight：...
- read-only production verifier：...
- authenticated smoke：...
- browser desktop/mobile：...

监控：
- healthz：...
- readyz：...
- Scanner queue：...
- 5xx/latency：...

回滚状态：
- 上一版本是否仍保留：...
- 回滚命令是否已验证：...

风险：
- ...
```

## 21. 完成定义

只有以下全部满足才可以宣布“服务器生产化完成”：

- 本地 release gate 通过
- 工作树干净且 commit 有精确 tag
- 版本信息一致
- 数据库备份已验证
- 恢复演练已完成
- Phase 5 等候选 migration 在隔离环境通过
- rollback-only database gate 未在生产主库运行且在安全环境通过
- 对象存储恢复策略已配置并演练
- Web/Scanner/database secret 完全分离
- Web 与 Scanner 均以非 root 运行
- Scanner 常驻、ClamD 与签名健康
- Nginx 配置通过且只代理 loopback
- HTTPS 与证书续期有效
- `/healthz` 外部监控和 `/readyz` 内部监控已启用
- 日志无 secret 和私密正文
- 生产 preflight 通过
- 只读 production verifier 通过
- disposable identity 全链路 smoke 通过
- 1440、1024、390 视觉与无横向溢出验收通过
- 上线后一小时没有达到回滚阈值
- previous release 和回滚方案仍可用
- 文档与项目功能地图已同步

任何一项没有证据，都必须标注“未验证”，不能写成“已完成”。

请先从阶段 A 的本地和远程只读审计开始。不要在第一次连接服务器时直接安装、升级、迁移、重启或删除任何内容。
