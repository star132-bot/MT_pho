# 07 图片资产管线与可信扫描系统

## 1. 功能范围与当前能力

本系统把浏览器选中的图片变成可审核的多版本 private assets，并通过独立可信 Scanner 确认下载、文件类型、哈希、解码和恶意软件状态。它是 Upload readiness 和公开发布的安全前置条件。

主要代码：`archive-upload.js`、`workers/scan_adapters.py`、`workers/image_scanner.py`、`workers/image_probe.py`、`requirements-scanner.txt`、`.env.worker.example`、`scripts/configure_development_scanner.py`。Scanner 不得被 `server.py` 导入或共享 Web secret。

## 2. 前置条件与输入

- 上传已生成有效的 database asset/image 记录和 private Storage 对象。
- Scanner worker 有独立的 Supabase privileged credential、稳定 worker ID、ClamAV/clamdscan 和 hash-locked Pillow runtime。
- 任务具有有效 lease、attempt 次数和总预算；对象 URL 必须来自允许的 private bucket。
- 当前生产 systemd 隔离要求 `clamdscan --stream --no-summary`；开发环境可在无 mount namespace 时使用 `--fdpass`。

## 3. 处理流程

1. 浏览器读取原始图片，记录原始尺寸、MIME、checksum、基础 EXIF。
2. 浏览器生成 original（完整）、display（画廊）、thumbnail（列表）和非方图 square_slice；服务端保存资产关系。
3. Scanner 领取 leased job，校验 job token/attempt/lease，拒绝跨 owner 或跨 bucket 访问。
4. 通过受限 Storage 流读取对象，拒绝 redirect，限制字节数并计算 SHA-256；检查 magic/MIME 和 Pillow 完整 decode、EXIF orientation、多帧、decompression bomb。
5. 将内容流给 ClamAV；结果写入 append-only scan event 和当前政策 verdict：`clean`、`failed`、`flagged` 或 `retry`。
6. 只有所有必需当前版本 derivative 通过政策，Draft readiness 才能进入 Ready；发布系统再次验证当前版本和 clean 状态。

## 4. 状态、反馈与效果

- `Queued`：用户看到等待扫描；不可提交。
- `Processing`：显示处理中；lease 过期时由 worker reclaim，不让页面永久锁死。
- `Clean`：只由可信 worker 和当前 policy 产生；页面显示可继续 readiness。
- `Failed`：文件格式、哈希、解码、尺寸或系统性处理错误；用户能看到可行动的“重新上传/重试”。
- `Flagged`：恶意命中或安全拒绝；不可重试成 clean，进入受控失败流程并保留审计证据。
- `Retry`：网络、provider、ClamAV 依赖故障；有 bounded retry/backoff 和最终人工处理状态。
- `Unknown`：任何不确定都不能降级为 clean；显示“仍在检查/暂不可用”。

用户不直接操作 scanner verdict。上传完成的效果是资产可追踪；扫描成功的效果是 readiness 可能解锁；恶意或不确定结果只阻止后续发布，不破坏其他 Draft。

## 5. 需求规格

### 安全边界

- Scanner secret 与 Web secret 分离，`.env.worker` 权限 `0600`，不进入 Git、命令行、日志或浏览器。
- 只允许 allowlisted bucket/path；拒绝 redirect、路径穿越、符号链接、过大的对象和不匹配 checksum。
- 任务使用 lease token、attempt limit、过期拒绝和 append-only events，防止两个 worker 同时写最终 verdict。
- ClamAV 结果、Pillow 不确定、网络失败、下载截断和 policy drift 都 fail closed。
- 临时目录每个 worker `0700`，临时文件 `0600`，任务结束清理；结构化日志只能有非敏感字段。

### 性能与资源目标

- 下载、扫描、解码和总任务有独立 timeout；总预算不得超过 lease。
- 大文件采用流式读取，避免把完整原图放入 Web 进程内存。
- Pillow 子进程限制 CPU、NOFILE、进程数和可用内存（操作系统支持时）；拒绝 decompression bomb。
- Worker 具备 bounded concurrency，低内存主机不为每张图重复加载病毒库；生产默认使用 resident clamd。
- 扫描状态更新目标 p95 ≤ 2s（不含外部 ClamAV/Storage 延迟），超时进入 retry 而不是长时间占用 lease。

## 6. 异常处理

| 异常 | 用户反馈 | 系统恢复 |
|---|---|---|
| 非支持格式/损坏图片 | “文件无法读取” | 用户重新导出/上传，原失败记录保留 |
| 哈希或对象 metadata 不一致 | “上传内容已变化，请重新上传” | 取消该资产并阻止 clean |
| ClamAV 命中 | “文件未通过安全检查” | 标记 flagged；禁止自动重试成 clean |
| ClamAV/Storage 超时 | “安全检查暂时不可用” | lease reclaim + bounded retry |
| worker 崩溃 | 页面显示 processing/pending | 下一 worker 依据 lease reclaim；超过次数进入 failed |
| policy/version 变化 | Draft 回到 pending | 重新跑当前版本扫描，旧 clean 不直接继承 |

## 7. 边界与非目标

- 不把浏览器预览、文件扩展名或客户端 MIME 当作安全扫描结果。
- 不在 Web 请求线程里运行 ClamAV、Pillow 或读 scanner secret。
- 不实现通用杀毒平台、内容审核模型、OCR、反向图像搜索或自动编辑照片；这些需另立系统。
- 不允许管理员手工修改 verdict 绕过 scanner；如需人工处理，必须有单独审计和政策设计。

## 8. 相关实现与验收

- 代码：`archive-upload.js`、`workers/scan_adapters.py`、`workers/image_scanner.py`、`workers/image_probe.py`。
- 配置：`requirements-scanner.txt`、`.env.worker.example`、`deploy/mt-presence-scanner.service`。
- 验收：`scripts/validate_workspace_asset_scanner.py`、`scripts/test_workspace_asset_scanner.py`、`scripts/test_configure_development_scanner.py`、`scripts/production_preflight.py`。

## 9. 数据库状态机验收约束

`MT_TEST_ENVIRONMENT=development` + data-free 隔离 schema clone 才允许运行 `scripts/test_workspace_asset_scanner_database.sql`。脚本在事务中创建专用用户/Inbox/图片和三种匹配 Storage 的资产，使用真实 enqueue trigger；拒绝 JSONB null claim，验证 lease、重放、重试和耗尽，最后 rollback。不得用已有用户的队列任务做状态机验收。2026-10-02 隔离验收通过，临时数据库已删除。
