# 2026-10-08 网站与 Supabase 监控验收

## 范围与状态

按既有release-readiness第4项完成持续监控代码、通知与部署准备。认证不重复开发，异地备份继续搁置。

**当前为实现和发布准备通过，实际启用及真实收件待确认。** 不把一次smoke、fixture或SMTP接受等同于持续外部观察及用户收件。

## 已核实的生产基线

- 2026-10-08检查：current为 `v1.6.4`，Web/Scanner active，原readiness timer enabled/active，每分钟检查正常。
- 原healthcheck仅执行本机curl，没有故障/恢复incident状态；外部health持续观察尚无运行证据。
- 现有运维告警环境文件存在、0600，SMTP配置键有值。只核验有无配置，不记录凭据或收件地址。
- 2026-10-08T09:17Z前后，生产完整HTTPS只读smoke及回环Supabase readiness通过，生产数据库未写测试fixture。

## 实现与本地验收

- `monitor_health.py`：严格200/JSON、8秒超时、公开HTTPS/回环readiness边界、连续两次故障和恢复、incident去重、持久FIFO、原子状态与脱敏通知。
- `notify_offsite_failure.py`：复用SMTP/webhook，健康故障和恢复独立主题；SMTP异常归一化，保留webhook后续投递。原备份通知合同不变。
- `rehearse_health_notifications.py`：独立回环503→200探针，以TEST通知安全演练，不改变生产健康状态。
- systemd应用readiness与独立Linux外部观察模板；GitHub外部观察workflow默认关闭，独立状态分支与Actions Secrets启用后运行。
- 16项隔离监控验收全部通过，包含远端checkpoint恢复后保持同一event ID/FIFO、先记录后发送及演练resume；原offsite alert测试通过且不继承真实告警环境；完整 `bash scripts/release_gate.sh`通过；workflow YAML与嵌入shell语法及patch integrity通过。
- 功能地图、模块规格和运维runbook同步更新，见 `health-monitoring.md`。

## 完成最终验收还需要的信息与操作

1. 确认现有告警收件邮箱是授权运维渠道，或提供替代渠道。
2. 确认外部长期观察位置：独立Linux服务器/已有平台，或现有GitHub仓库的定时workflow。
3. 安装启用应用readiness新unit；外部方案配置持久状态与通知权限后实际启动，记录schedule运行证据。
4. 使用独立fixture发送真实TEST故障与恢复两条通知，核实授权邮箱/接收端实际收到并记录event ID和时间。

在前两项尚无答案时，不发送真实通知，不复制邮件凭据到外部平台，不替换正在运行的healthcheck unit；生产现有readiness检查继续工作。用户补充信息后接着完成3、4项，才能将这项任务标为完成。
