# Image Sources

当前图片是网站设计阶段的 AI 生成临时视觉样张，用于验证 MT Presence 的首页氛围、Infinite Marquee Gallery 和滚动过渡节奏。它们不是 MT 的最终正式作品，不应在正式上线时被表述为作者原作。

## 使用规则

- 正式发布前，优先替换为 MT 的真实摄影作品。
- 如果继续使用第三方素材，必须按对应平台许可、署名和使用限制处理。
- 如果使用模型生成图片，保存生成提示词、生成日期、模型、授权和筛选记录。
- 替换图片后同步更新 `docs/architecture/project-map.md` 和本文档。

## 摄影可信度规则

- 图片必须像摄影机能拍到的真实场景、真实空间、真实物体或真实光线。
- 抽象作品可以来自建筑光影、水面、雾、岩石、玻璃、空间局部等真实对象，但不能像纯纹理素材、AI 质感图或随机构成图。
- 不使用无法解释拍摄对象的图像作为摄影师作品展示。
- 不使用过度生成感、过度滤镜感、图库旅游照感太强的图片作为正式作品。
- 临时素材只用于验证排版和交互，不可在正式文案中表述为 MT 原作。

## 当前临时素材

以下图片都是 AI 生成的临时视觉样张，用于验证 2026-10-27 访客网站重设计（`design/site-mockups-v2`）的排版与氛围，不是 MT 的作品，正式上线前应替换为作者作品或作者授权的图片。

### 网站配图（2026-10-27）

生成模型：`gpt-image-2.5-sunburst`；生成脚本与全部提示词：仓库外的 `design/tools/generate_assets.py`。生成后按目标尺寸居中裁切、缩放并另存为 JPEG。

| 文件 | 尺寸 | 用途 | 画面 |
|---|---|---|---|
| `assets/art/home-hero.jpg` | 2400×1350 | 首页首屏 | 黑白云海与山脊，日出 |
| `assets/art/selected-01.jpg` | 1200×1600 | 首页精选作品 | 黑白雾中松树岩脊 |
| `assets/art/selected-02.jpg` | 1200×1500 | 首页精选作品 | 低饱和雨后高山湖泊 |
| `assets/art/selected-03.jpg` | 1100×1650 | 首页精选作品 | 黑白雾中松林 |
| `assets/art/selected-04.jpg` | 1200×1600 | 首页精选作品 | 黑白海崖 |
| `assets/art/selected-05.jpg` | 1400×1400 | 首页精选作品 | 黑白沙丘 |
| `assets/art/about.jpg` | 1200×1600 | 首页「关于创作」 | 黑白山脊上的摄影师背影（**占位，待换成老板本人照片**） |
| `assets/art/contact.jpg` | 2000×1333 | 联系页 | 黑白云中峭壁 |

### 仍在使用的早期素材（2026-06-06，`gpt-image-2-all`）

- `assets/art/hero-ci-jian.jpg`、`assets/art/hero-concrete.jpg`：后台登录页与找回密码页的配图。

`abstract-01`～`03`、`concrete-01`～`03` 已随旧首页删除。

## 本地样例作品

`assets/archive/` 下的 27 张样例作品在 2026-10-27 用 `gpt-image-2.5-sunburst` 重新生成（原为 `picsum.photos` 在线图库图片），按 `archive-data.js` 中原有的像素尺寸裁切，文件名不变。抽象（此间留灰）为黑白风景，具象（此间留彩）为低饱和彩色风景；每件样例同时配了中文标题和一句简介（`archive-data.js` 的 `title` / `description`），`scripts/seed_local_archive_db.py` 会把简介写入本地数据库。

这些样例只在本地开发预览中出现，不是 MT 的正式作品。正式作品由作者在后台上传，存放在数据库与对象存储中。

## 处理脚本

- `scripts/prepare_art_assets.py`：历史/备用处理脚本；读取 `tmp/art-source/` 下的源图，裁切、调色并输出到 `assets/art/`。
- `assets/art/metadata.json`：当前记录图片宽高、生成模型别名和生成日期；前端不再用它做比例筛选。
