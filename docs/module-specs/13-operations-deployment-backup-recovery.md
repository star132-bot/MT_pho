# 13 发布、健康检查、备份与恢复运维系统

## 1. 功能范围与当前能力

运维系统负责 development 和生产的预检、不可变发布、原子激活、回滚、Web/Scanner 健康、PostgreSQL 备份、Storage 异地加密备份、告警和隔离恢复演练。

主要目录：`deploy/`、`scripts/production_preflight.py`、`scripts/verify_production.py`、`scripts/build_production_release.sh`、`scripts/manage_production_release.py`、`scripts/release_gate.sh`、备份/恢复脚本和 `docs/operations/`。

生产域名和部署已存在：`domain-migration.md` 与 `offsite-recovery-rehearsal-2026-09-17.md` 记录 `mtdo.cn`、生产备份定时器和完整隔离恢复；2026-10-02 HTTPS 只读检查也确认公开服务可用。本地当前变更是否已部署，必须核对具体 release；历史演练不代替每次发布的门禁，本轮优化代码未发布。

## 2. 发布前置条件

- 精确 release tag、clean worktree、release gate 通过、构建包 checksum 可验证。
- Web/scanner/database secrets 分离且权限正确；不把 `.env`、`.env.worker`、私钥和生产数据库凭据放入包。
- 目标服务器 SSH、磁盘、Nginx、systemd、Python、PostgreSQL client、ClamAV 和对象存储状态已只读核验。
- 数据库迁移前有验证过的 dump；迁移和 rollback-only acceptance 只能在 development 或隔离恢复克隆运行。
- `/healthz`、受保护 `/readyz`、公开 HTTPS、Supabase callback、邮件、Storage 和 scanner smoke 条件明确。
- 激活前存在上一版本和可执行回滚命令；禁止直接覆盖 active release。

## 3. 发布流程

1. `release_gate.sh` 执行静态 contract、语法、secret-free boundary、artifact、database gate 编排检查。
2. `build_production_release.sh` 从精确 tag 构建不可变 archive，并生成 checksum。
3. 服务器 installer 检查路径穿越、链接、设备、禁止文件、必需文件和 checksum，先安装不激活。
4. 对候选 release 执行 Web/Scanner preflight；通过后原子切换 `current`/`previous`。
5. `systemctl` 重启受控服务、`nginx -t` 后 reload，运行公开 HTTPS 与回环 readiness 验证。
6. 观察首小时日志、重启计数、健康、错误率和登录/上传/扫描/Review smoke；异常时切回 previous。

## 4. 备份与恢复流程

### 4.1 数据库 + Storage 异地批次

1. 源端生成保留 ownership/privileges 的 PostgreSQL custom dump 和独立 SHA-256 manifest。
2. 按数据库权威清单导出四个 allowlisted private buckets：`image-originals`、`image-display`、`image-thumbnails`、`profile-avatars`。
3. 导出前后比对 bucket、path、size、updated_at；变化时丢弃整批。
4. 完整批次用 GPG 公钥加密，通过来源 IP 受限、只写 `rrsync` 账号传输；目标端原子移入 root-only vault。
5. 目标端定时复核 checksum、新鲜度和磁盘余量；失败由 OnFailure 告警。

### 4.2 恢复演练

1. 只选择 vault 中完整批次，验证密文 checksum。
2. 从离线/macOS Keychain 恢复私钥到临时 root-only keyring；不把私钥落入仓库、日志或普通文件。
3. 解密到一次性 loopback-only Supabase 兼容环境，拒绝路径穿越/链接，校验所有文件 hash。
4. 使用与源等价的角色和 ACL 恢复数据库；重启 Auth/Storage/REST/Realtime 并做 readiness。
5. 把对象恢复到非生产 bucket，按 manifest 和数据库 metadata 验证至少一项 API 回读，再完成全对象校验。
6. 运行 rollback-only acceptance，确认所有 fixture 清理；删除临时环境和 plaintext，生产从不作为恢复目标。

## 5. 运行状态与反馈

- `Preflight failed`：阻止安装/激活，输出不含 secret 的原因和修复建议。
- `Health failed`：服务状态、Nginx、`/healthz` 或 protected readiness 失败，触发告警和回滚决策。
- `Backup running`：锁避免并发，源端和目标端都保留可审计状态；不覆盖已有 recovery point。
- `Backup stale/low disk`：定时器失败并告警；不能继续宣称具备恢复能力。
- `Restore failed`：隔离环境整体失败或清理，不触碰生产；报告具体阶段但不泄露凭据。
- `Rollback`：`current` 原子切回 `previous`，重启/验证后保留失败 release 供取证。

## 6. 需求规格

### 安全与可回滚

- 生产默认只读审计；重启 Web、Scanner、Nginx、PostgreSQL、主机、改 DNS/防火墙/证书或运行 migration 都必须有明确批准和回滚方案。
- systemd 服务使用最小权限、`ProtectSystem`、`PrivateTmp`、`PrivateDevices`、无不必要 capability；scanner secret 与 Web secret 分离。
- 发布包不可变、可校验、禁止 `.env`/私钥/数据库文件；激活必须原子化。
- 备份目标不能读取、删除或覆盖已提升的历史 recovery point；源端密文和离线恢复密钥分离保管。
- 所有演练必须明确 `MT_TEST_ENVIRONMENT=development` 或隔离恢复 guard，拒绝 production primary。

### 性能、容量与新鲜度目标

- `/healthz` 响应目标 p95 ≤ 300ms；`/readyz` 只从受信回环/运维位置访问。
- 发布安装和 checksum 校验不得修改 current；激活后服务在定义窗口内恢复 healthy。
- 备份每天至少一个成功点；目标端最新批次不能超过约 36 小时，低于磁盘余量阈值必须失败。
- 备份批次包含数据库、所有 allowlisted Storage objects、manifest 和 checksum；目标保留策略至少覆盖经批准的日常恢复点数量。
- 恢复演练必须能证明数据库 schema/ACL/RLS、Auth/Storage 服务、对象字节和业务 API 关系都可用。

## 7. 异常处理与回滚

| 异常 | 处理 |
|---|---|
| 构建/contract 失败 | 停在本地，不上传、不激活 |
| 安装校验失败 | 删除未激活临时目录或保留取证，current 不变 |
| preflight 失败 | 不重启服务；修复配置或换 release |
| 激活后健康失败 | 立即按 runbook 原子回滚 previous，验证 Nginx/Web/Scanner |
| 备份导出清单变化 | 丢弃整批，不传不完整密文 |
| 目标 checksum/新鲜度失败 | 告警，停止依赖该恢复点，不删除旧点 |
| 恢复角色/ACL 不兼容 | 隔离恢复失败并修正工具；不把“文件能解密”报告成完整恢复 |
| 告警发送失败 | 追加 root-only 审计 spool，并让服务任务保持失败；不能用去重掩盖发送失败 |

## 8. 边界与非目标

- 该系统不是实时复制、自动故障转移、云成本优化或无限扩展架构；这些属于独立架构项目。
- 不在没有域名/TLS、外部邮箱、对象恢复和真实 smoke 的情况下宣布生产上线。
- 不在生产主库运行 fixture-writing、rollback-only、并发竞争或破坏性测试。
- 不把一份成功 dump、一次文件 hash 或一次公开 `/healthz` 当成完整灾备证明。

## 9. 相关实现与验收

- 部署模板：`deploy/mt-presence*.service`、`deploy/nginx-*.conf`、`deploy/*environment.example`。
- 工具：`scripts/release_gate.sh`、`scripts/production_preflight.py`、`scripts/verify_production.py`、备份/恢复/告警脚本。
- 证据：`docs/operations/production-deployment.md`、`docs/operations/offsite-recovery-rehearsal-2026-09-17.md`。
- 验收：`scripts/validate_production_deployment.py`、`scripts/test_production_preflight.py`、`scripts/test_offsite_backup.py`、`scripts/test_offsite_alert.py`、`scripts/test_offsite_recovery_boundary.py`、`scripts/verify_production_backup.sh`。
