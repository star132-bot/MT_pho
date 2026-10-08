# 网站与 Supabase 持续监控

## 范围与前置条件

- 应用服务器每分钟检查回环 `/readyz`，验证 Supabase provider 可用性。
- 独立于应用服务器的观察节点检查 `https://mtdo.cn/healthz`，覆盖域名、TLS、Nginx 和应用主机不可达。
- 使用运维已授权的邮件或 HTTPS webhook；配置复用 `/etc/mt-presence/offsite-alert.env`，权限0600。Python只用标准库。外部节点不需要应用、数据库、Supabase或生产SSH凭据。

## 使用流程与效果

1. 8秒超时，禁止重定向，必须精确 HTTP 200和JSON合同：公开health为 `{"status":"ok"}`；回环readiness为 `{"status":"ready","dependencies":{"supabase":"available"}}`。
2. 首次正常静默。连续两次失败生成incident与故障通知，持续失败不重复。连续两次正常生成恢复通知。反向样本重置连续计数。
3. 状态先落盘再投递。发送失败保留FIFO待发事件，每轮重试、最多处理8条；恢复不会抹掉未送达的故障，先故障后恢复。
4. 至少一次投递：远端接受与本地确认之间进程退出可能导致重复，同一事件保留相同event ID供接收端去重。
5. TLS SMTP、拒绝跳转的HTTPS webhook复用既有通知传输。任一配置渠道成功即视为远端接受，其余失败写入脱敏审计；实际收件另行验证。

## 需求、状态与异常反馈

- `state.json`保存check、连续计数、incident、待发队列，events保留投递审计。目录0700、文件0600，文件锁与原子替换/fsync，重启不会丢掉故障状态。
- HTTP/JSON/DNS/TLS/网络超时返回稳定分类，通知包含check、incident、时间和原因，不含响应正文、probe URL、应用日志或秘密。
- journal输出check/result/probe_ms/pending。退出1表示探测失败或通知待发，退出2表示配置/状态错误。修复通知配置或网络后下一轮自动重试；网站正常服务独立于监控结果。
- 状态损坏必须保留原文件及events，停止监控timer，由运维按审计恢复后重启；禁止静默清空，避免漏报或虚假恢复。
- 队列4096条、状态16MiB上限；达到上限保留现状报错，运维优先修复发送渠道并审查历史事件。事件审计归档由运维处理。
- `/healthz` p95目标300ms；8秒是故障探测超时，不是性能验收。监控节点或所有通知渠道故障时无法保证送达，需外部独立观察和任务状态检查。
- 不自动重启网站、切换数据库或回滚release；运维收到通知后依部署runbook决定恢复措施。异地备份保持用户指定的搁置状态。

## 配置与运维

- 应用节点安装 `deploy/mt-presence-healthcheck.service`/`.timer`，代码通过 `/opt/mt-presence/current/scripts/monitor_health.py` 跟随release。
- 外部Linux节点将 `monitor_health.py`/`notify_offsite_failure.py` 安装到 `/opt/mt-presence-monitor/scripts/`，安装 `deploy/mt-presence-uptime.service`/`.timer`；节点必须与应用服务器独立。
- 共享告警环境文件只提供运维邮件/webhook配置，不包含应用数据库权限。`systemctl list-timers`和对应unit的`journalctl`用于检查下一次调度、最近探测及发送失败。

## 安全验收

### GitHub外部观察方案

`.github/workflows/uptime.yml`已提供独立于应用主机的GitHub-hosted探测，默认关闭。启用前需确认收件渠道，初始化 `codex/monitor-state` 分支（只包含空version 1的state.json），将授权通知配置放入 `MT_MONITOR_*` Actions Secrets，再设置repository variable `MT_UPTIME_ENABLED=true`。不向GitHub提供生产SSH或Supabase权限。

外部探测每5分钟计划执行，连续两次失败/恢复才通知，正常静默。先用 `--record-only` 记录incident/待发事件并push到独立状态分支，保存成功才用 `--deliver-only` 发送，随后再次push投递确认与脱敏审计。前置push失败不会发送；后置push失败时下轮仍用已保存的同一event ID重试。该仓库公开，分支仅包含check、时间、原因、event ID等监控元数据，不包含凭据、地址、URL或响应正文。

手工dispatch的 `rehearse_notifications=true` 使用独立回环fixture和独立rehearsal目录，按同样的先保存后发送步骤演练TEST故障/恢复，不修改生产探针或其状态。同一run重试复用已有演练，后续schedule/dispatch用 `--resume` 继续投递所有未完成演练事件，默认不创建新演练。

GitHub schedule可能延迟或丢弃，公开仓库60天无活动会自动禁用，因此不能承诺精确5分钟SLA；运维须检查workflow状态及最近schedule执行。需要严格分钟级可用性时使用独立Linux节点timer。平台限制依据 [GitHub schedule文档](https://docs.github.com/en/actions/reference/workflows-and-actions/events-that-trigger-workflows#schedule)。

- 隔离fixture覆盖连续故障/恢复、不重复、重启、未送达队列、坏JSON/跳转/超时、SMTP异常脱敏与webhook fallback。
- 生产保持正常；独立回环测试服务先返回503、再返回正确JSON，以独立check/state目录运行 `--test`，发送标记TEST的故障和恢复通知。
- 两封通知必须实际到达授权邮箱（或接收端持久记录），记录时间、check与event ID，不记录收件地址或凭据。
- 外部任务必须实际启用并留下独立节点运行证据，一次本机smoke不满足。部署及送达情况写入当日验收记录。

```sh
python3 scripts/test_health_monitor.py
python3 scripts/test_offsite_alert.py
python3 scripts/validate_production_deployment.py
bash scripts/release_gate.sh
```
