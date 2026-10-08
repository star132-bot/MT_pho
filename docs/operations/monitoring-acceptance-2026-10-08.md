# 2026-10-08 网站与 Supabase 监控验收

## 当前范围与状态

按既有release-readiness第4项实施网站/Supabase持续监控、故障和恢复通知。用户已确认现有告警邮箱由本人接收。认证沿用已验收版本，异地备份继续搁置。

**生产监控已启用，故障与恢复通知的真实收件验收通过。** GitHub外部探测的手工演练和独立runner状态恢复均单独记录；截至验收截止时间仍没有原生自动schedule成功证据，因此自动调度验收未完成。

## 发布与应用主机

- 代码提交 `5fb5ff4b1a35a22c4256165ee7634c42af500e82`，release tag `v1.6.5` 已推送main及GitHub。干净工作区exact-tag构建通过。
- 包名 `mt-presence-v1.6.5.tar.gz`，SHA-256 `7936f08f256bcdafd426f9449ad19ebf770e089af6439ef4dd6196ebaed7db34`；安装器验证并安装到 `/opt/mt-presence/releases/v1.6.5`。
- 2026-10-08约09:39 UTC原子activate完成，current=`v1.6.5`、previous=`v1.6.4`。Web/Scanner重启时各自production preflight执行；随后二者active/running且NRestarts=0。
- 新 `mt-presence-healthcheck.service` 已安装，timer enabled/active，每分钟检查回环 `/readyz`。安装后多个实际timer周期healthy，incident=null、failures=0、pending=0。目录0700、state文件0600。
- 激活后完整公开HTTPS/受信Supabase readiness只读smoke通过：liveness、provider、公开壳/security headers、权威Works、私有路径拒绝、匿名保护及CSRF边界。
- 回滚时可原子activate `v1.6.4`，恢复该版本的healthcheck service并daemon-reload，重启Web/Scanner与timer；旧unit已保留在root-only发布工具目录。生产主库未写测试fixture。

## 外部观察节点

- GitHub-hosted Ubuntu runner从独立于应用主机的位置检查 `https://mtdo.cn/healthz`。
- `.github/workflows/uptime.yml`已active，repository variable `MT_UPTIME_ENABLED=true`；每5分钟计划执行。平台可能延迟/丢弃schedule、公开仓库长期无活动可能禁用，限制和处置见 `health-monitoring.md`，不承诺精确5分钟SLA。
- 初始化 `codex/monitor-state` 独立分支，先保存queued transitions并push成功才发送，再push投递确认；远端确认前失败时按同一event ID重试。生产健康state与演练state分离。
- 运维通知配置经加密SSH传递到GitHub Actions Secrets。没有写入仓库或发布包；未向GitHub提供生产SSH、Supabase或数据库权限。只复用用户授权的SMTP邮箱渠道。
- [独立外部故障/恢复演练 #37758161818](https://github.com/star132-bot/MT_pho/actions/runs/37758161818) success；真实公开probe healthy，演练两条事件均smtp delivered/errors=[]，state分支pending=0。
- [独立第二轮dispatch #37758803142](https://github.com/star132-bot/MT_pho/actions/runs/37758803142) success：另一runner恢复既有state，production-https.successes=2、pending=0，无新故障或恢复通知。手工dispatch记录与自动schedule分别核验。
- 截至2026-10-08 11:03 UTC，workflow状态为active、默认分支为`main`、变量`MT_UPTIME_ENABLED=true`，但限定`event=schedule`查询仍无运行记录；不能把两次`workflow_dispatch`写成自动调度验收完成。已核对远端workflow定义仍包含`2-59/5 * * * *`，未发现配置缺失。由于GitHub schedule可能延迟或丢弃，当前结论为自动调度尚未验收；后续应在仓库有新的schedule记录后，用run链接、生产probe和`codex/monitor-state`状态完成一次只读复核。截止跟进已删除，网站自身GitHub定时任务和本机timer持续保留。

## 真实通知与收件证据

两条路径均以独立回环fixture模拟503→200、连续两次故障/恢复，邮件主题带 `TEST Health failure`/`TEST Health recovered`。真实网站及Supabase没有被人为停用。

| 来源 | 类型 | 事件发生时间 UTC | event ID | SMTP审计 | 收件证据 |
|---|---|---|---|---|---|
| 应用服务器 | failure | 2026-10-08T09:37:26.115936Z | `44609ad12309df55957abc4e6b2b257f12220433f694e115261566474043a477` | delivered，errors=[] | 授权邮箱INBOX匹配此事件header |
| 应用服务器 | recovery | 2026-10-08T09:37:28.824495Z | `0666569180b3664c07dad873022dfa01edf4e77031f265b8d34e82b797ede52f` | delivered，errors=[] | 授权邮箱INBOX匹配此事件header |
| GitHub外部节点 | failure | 2026-10-08T09:39:34.337977Z | `f721e0b17aa2884e693e814a8d335411dcb35db828b6f830339783cb5d4ed60b` | delivered，errors=[] | 授权邮箱INBOX匹配此事件header |
| GitHub外部节点 | recovery | 2026-10-08T09:39:34.362173Z | `a98afef823bb3a75194cc0b11bb143608c2f05352e3799f18d283989aad09b1a` | delivered，errors=[] | 授权邮箱INBOX匹配此事件header |

收件核验使用同一授权发送/接收账号的TLS IMAP，仅readonly打开INBOX并按 `X-MT-Presence-Event-ID` 搜索四条测试事件，四项均找到。未读取无关邮件正文、标记已读、修改或删除邮件；未记录邮箱地址、密码、IMAP UID或无关内容。证明实际进入收件箱，不仅是SMTP服务器接受。

应用主机演练状态保存在 `/var/lib/mt-presence-health-rehearsal-20261008`；外部演练状态保存在独立分支 `rehearsals/37758161818`。两处incident闭合，pending=0；生产健康checks无incident。

## 实现与验证

- 严格HTTP 200/JSON、8秒超时、公开HTTPS与回环readiness边界；连续两次故障/恢复，持久incident去重，通知失败FIFO重试，状态损坏保留并明确反馈。
- 复用TLS SMTP、拒绝跳转的HTTPS webhook、0600 spool/原子替换与fsync，SMTP异常脱敏并保留webhook fallback。
- 16项隔离监控测试通过，包含远端checkpoint恢复后的同ID/FIFO、record-only无发送、drain失败重试及演练resume；原offsite alert测试隔离真实环境并通过。
- 本地完整release gate、workflow YAML/嵌入shell语法、systemd unit解析、patch integrity通过。GitHub [代码发布门禁 #37756683775](https://github.com/star132-bot/MT_pho/actions/runs/37756683775)及[准备记录门禁 #37757018945](https://github.com/star132-bot/MT_pho/actions/runs/37757018945)均success。
- 功能地图、运维模块规格和 `health-monitoring.md`同步维护；p95/容量测试及素材授权仍为独立任务，监控不自动重启网站/切换数据库/回滚release。
