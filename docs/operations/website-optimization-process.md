# MT Presence 网站优化流程

## 1. 目标与完成范围

本轮优化收敛当前网站的公开页面性能、数据来源、异常恢复、可访问性和验证流程。清单以现有模块为范围，每项包含实现、验收和文档；清单完成后结束本轮开发。

**环境事实（更新至 2026-10-08）**：

- 项目已有生产部署，主域名为 `https://mtdo.cn`。`domain-migration.md` 与 `offsite-recovery-rehearsal-2026-09-17.md` 记录域名切换、生产备份、165 个对象完整隔离恢复和定时器状态。
- 本轮 HTTPS 只读检查确认 `/`、`/healthz`、公开 Works API 可用，`/dashboard` 正确跳转登录，敏感 SQL 路径拒绝访问。
- release `v1.6.1` 已于 2026-10-07 激活到 `https://mtdo.cn`，运行时代码沿用已验收的 `v1.6.0`；本轮本地测试、服务器实际 release 和外部依赖状态分别记录在发布观察文档中。
- 此前未提交的部署、备份和文档改动已完成归属审查，形成干净提交和 `v1.6.1` 标签；生产激活与外部验收证据单独记录在发布观察文档中。
- 2026-10-08 认证修复 `v1.6.4` 已激活并通过生产 smoke/readiness；邮件两轮完整生产验收成功，Google 身份列表兼容问题已修复，用户确认登录、注册、修改密码人工测试全部通过。证据见 `auth-acceptance-2026-10-08.md`。

本轮完成代码发布、首轮生产观察和认证修复验收；持续监控/告警、受控容量压测和最终媒体授权仍是后续独立验收工作，异地备份按用户要求暂时搁置。TUS、云端收藏、支付、AI、配额扩展和新的审核状态必须另立需求。线上日志 request_time 观察不能替代受控容量压测。

## 2. 执行原则

1. 根据当前代码和功能地图定位问题，每次改动限定一个可验收边界。
2. 复用现有 HTML/CSS/JavaScript、BFF、Supabase、Scanner 和 release gate。
3. 公开内容来自 published 权威边界；preview 必须显式启用，provider 失败不能伪造空态或 sample 成功。
4. 同时处理 loading、empty、error、retry 和成功效果；失败不丢失可恢复输入，不伪报持久化成功。
5. 代码职责变更同步 `project-map.md` 和模块规格；测试证据写入本流程，避免创建冲突的完成报告。
6. 数据库造数据、rollback 和并发验收只连接 development/隔离 clone，禁止生产主库。

## 3. 阶段与验收清单

| 阶段 | 工作与验收标准 | 本轮状态 |
|---|---|---|
| 0 基线与范围 | 核对真实实现、生产历史、工作区改动；固定有限清单 | 已完成 |
| 1 图片与动效 | 首页/About 静态尺寸匹配 JPEG；滚动图片 lazy/async；首图保持即时加载；作品带可暂停 | 已完成 |
| 2 数据来源与异常 | 12 秒公开列表超时；严格 DTO；权威错误不 fallback；Works/Lightbox 可见错误和重试；隔离首页 preview；修复 About 响应读取 | 已完成 |
| 3 数据库与运维证据 | 五组数据库验收、Review/Scanner、并发、清理；核对既有完整恢复记录；生产只读 smoke | 已完成 |
| 4 浏览器体验 | 10 个公开路由 × 3 视口；错误/空态/慢请求/存储/preview；Workspace 与 Review 批量流程；截图检查与本地性能采样 | 已完成 |
| 5 文档与统一门禁 | 更新模块规格、功能地图和运维说明；完整 release gate、patch 检查通过 | 已完成 |

## 4. 已实施的优化

### 公开页面性能与可访问性

- 首页 16 张作品/Statement 图片和 About 首图补真实 `width`/`height`；校验直接读取 JPEG SOF，不新增图片依赖。
- 作品带图片使用 lazy loading/async decoding，About 首图保持 eager 并异步解码。
- 首页 Selected Works 提供 Pause motion/Resume motion，按钮状态通过 `aria-pressed` 同步；系统 reduced motion 自动关闭动效。
- 更新所有引用本轮共享 CSS/JS 的 HTML 缓存版本，降低发布后新旧文件错配风险。

### 数据来源与异常恢复

- 公开列表统一使用现有 `public-archive.js` 中的 `fetchArchivePayload()`；12 秒取消等待，始终清理计时器。
- 无效 JSON、缺失 items、缺 ID/展示 URL 的行都进入错误态；展示 URL 不回退 original。权威 API 的错误/空结果不能回退私有缓存或 sample。
- Works 显示 loading/error；失败隐藏无作品空态并提供 Retry，重试保留 URL 筛选且加载中禁用按钮。
- Lightbox 将服务错误与真实空收藏分开，提供 Retry，不因 API 失败删除原有收藏 ID。
- Storage getter/读取受限时页面继续工作；quota/写入失败显示局部错误，保留仍可读的旧数据。作品详情收藏失败不再次写入以避免异常恢复重复抛错。
- About 正确读取公开接口的 `payload.creator`，真实作者资料可以替换默认展示。
- 首页 IndexedDB 设置只在服务端确认 development + loopback + `MT_LOCAL_ARCHIVE_PREVIEW=1` 后读取；普通公开页面保持版本内图文。
- Legacy `manage.html` 保留 Admin+AAL2 direct-route 兼容；`collections.html` 保留历史链接兼容，均不扩展为新的公开主流程。

### 验收可靠性

- Scanner SQL 验收改用 data-free 隔离 clone，在事务内创建专用用户/Inbox/图片及 original/display/thumbnail 匹配 Storage 对象，由真实 trigger 入队，不再依赖已有用户的三个 queued jobs。
- Scanner claim 的 JSONB null 必须拒绝，避免没有任务仍误判通过；测试以 rollback 结束。
- Review 原图断言与当前治理政策对齐：Admin+AAL2 只读 derivative，原图权限要求 assigned Reviewer。
- 新增公开浏览器验收脚本；静态图片合同、首页 JS 语法与浏览器脚本语法进入 release gate。

## 5. 验收证据（2026-10-02）

### 隔离数据库

以已有恢复环境中的空 schema baseline 创建临时数据库 `mt_opt_acceptance_20261002`，通过以下测试后删除该数据库：

- `database_acceptance_gate.sh`：Dashboard/Public Delivery/Admin Works/Admin Users/Communications 五组通过；fixtures 回滚/缺失检查通过。
- `test_review_queue_database.sql`：角色/AAL/RLS、self-review、Storage、CAS/幂等、稳定 replay、通知/审计与 self-publish 通过。
- `test_workspace_asset_scanner_database.sql`：disjoint claim、重放/冲突、retry、lease reclaim、旧 token 拒绝、耗尽 fail closed 通过。
- `test_review_queue_concurrency.py`：两个不同 PostgreSQL backend 的 start claim race、decision CAS race、同 key replay 通过，固定 fixtures 清理通过。
- `isolated_database_removed=yes`；现有恢复环境保留，生产数据库未作为测试目标。

### 浏览器与交互

- `test_public_browser.py`：1440×900、1024×768、390×844；Home/About/Works/Lightbox/Contact/Work/Creator/Sign In/Privacy/Terms 共 30 个路由视口检查通过。
- 检查无页面横向溢出；手机比例筛选允许在有界横向容器内滚动，最后一项键盘可达。honeypot 隐藏字段不当作可见控件。
- provider error → Retry 保留筛选、Lightbox 恢复、权威空集合、真实 13 秒慢响应触发 12 秒超时、禁止 Storage getter、首页私有设置与显式 preview 隔离均通过。
- 正常页面无未捕获脚本错误；测试结束关闭 browser/server。
- `test_workspace_trash_browser.py`：桌面/手机 Trash 只读、Restore busy/success、Quick Upload、Ready Draft batch submit、无页面错误通过。
- `test_review_batch_browser.py`：批量选择、checklist、逐件独立审计、响应式和无页面错误通过。
- `test_public_interaction_state.js`：原交互、Storage getter/quota、malformed DTO、original-only 拒绝、provider error 不 fallback 与超时回归通过。
- 已人工检查公开页面截图，包含首页手机、Works 手机和 About 桌面；未见主要按钮遮挡、图片比例损坏或横向页面溢出。

### 本地性能采样

单次 loopback 合成数据、复用浏览器缓存；三种视口取样如下：

| 页面 | CLS 范围 | 观察到的 LCP（ms） | Resource transferSize（bytes） |
|---|---:|---:|---:|
| Home | 0 | 40–72 | 37,994–2,852,445 |
| About | 0.0036–0.0191 | 36–48 | 58,028–76,031 |
| Works | 0 | 16–40 | 47,890–152,441 |

这些数据仅证明本地采样时的布局/绘制状态；LCP 在页面快照时读取，未进行真实网络限速或足够多次重复，不是线上完整 Web Vitals、p95、容量或优化前后百分比证据。缓存使 transferSize 差异明显。原始 JSON/截图保存在 gitignored `tmp/optimization/`。

### 生产只读检查

- `https://mtdo.cn/`：200；HSTS/CSP/X-Frame-Options/nosniff/Referrer-Policy/request ID 存在。
- `/healthz`：200；公开列表 `?limit=1`：200、来源 `supabase-public`，无敏感字段。
- `/dashboard`：303 登录跳转；`/database/product_schema.sql`：404。
- 2026-09-17 完整恢复证据已核对；本轮不重复创建生产备份、不修改 DNS/服务/数据库，也不推断实时定时器或外部监控状态。

### 统一门禁

最终 `bash scripts/release_gate.sh` exit code 0，输出 `Release gate passed`；`git diff --check` 通过。门禁覆盖 Python/JavaScript/Shell 语法、全部静态合同、公开交互与图片合同、认证/上传/Scanner/Review/公开交付/Dashboard/治理/通信边界、生产工具模拟验收以及备份/告警/恢复边界。门禁中的生产工具验收使用受控测试服务，不等同于线上发布。

**本轮清单已全部完成。** 当前剩余事项是独立的新版本发布和持续运维，不是未完成的本地优化代码。

## 6. 可重复验证命令

```bash
node scripts/test_public_interaction_state.js
python3 scripts/test_public_image_contract.py
python3 scripts/test_public_browser.py
python3 scripts/test_workspace_trash_browser.py
python3 scripts/test_review_batch_browser.py
bash scripts/release_gate.sh
git diff --check
```

浏览器命令需要已安装 `agent-browser`，公开脚本只访问 loopback 合成数据，无真实凭据。数据库命令必须先明确设置指向隔离 clone 的 PGHOST/PGPORT/PGDATABASE/PGUSER/PGPASSWORD，并确认环境与 schema/migrations 一致：

```bash
MT_TEST_ENVIRONMENT=development bash scripts/database_acceptance_gate.sh
psql -X --set ON_ERROR_STOP=1 --file scripts/test_review_queue_database.sql
MT_TEST_ENVIRONMENT=development psql -X --set ON_ERROR_STOP=1 --file scripts/test_workspace_asset_scanner_database.sql
MT_TEST_ENVIRONMENT=development python3 scripts/test_review_queue_concurrency.py
```

Scanner 测试额外要求 data-free schema clone，不能连接已有用户/作品/任务的开发库。并发测试会提交临时 fixtures，必须确认目标隔离并检查 finally 清理结果。

## 7. 回滚与后续运营边界

- 本轮变更限定 HTML/CSS/JS、preview 渲染、测试和文档，没有业务 schema migration。发布时仍使用现有不可变 release/previous 回滚流程。
- 回滚本轮时仅反向应用本轮代码差异，保留此前未提交的备份/部署改动；不得 `git reset --hard` 或覆盖全部工作区。
- 未来新版本发布需审查当前全部改动归属、形成干净可审查 commit/tag、核对备份、预检、激活、smoke 和首小时观察；本轮验证不自动授权生产激活。
- 备份新鲜度、Scanner 队列、告警和监测是持续运维事项，需要持续执行；它们不作为本轮永远无法结束的开发清单。
