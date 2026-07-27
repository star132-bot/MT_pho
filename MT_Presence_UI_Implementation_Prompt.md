# MT Presence 最终 UI 实现任务

你现在需要完成 MT Presence 高级摄影作品网站的最终 UI 实现。

这不是设计讨论任务，也不是只修改顶部导航。请直接检查现有项目、完成代码修改、运行项目、逐页截图对比并修正，直到以下五个页面都达到参考图效果。

## 项目与视觉参考

项目目录：

`/Users/starfeld/Web_MT`

最终视觉参考：

1. About 页面：
   `/Users/starfeld/Web_MT/output/imagegen2/mt-presence-about.png`
2. Lightbox 页面：
   `/Users/starfeld/Web_MT/output/imagegen2/mt-presence-lightbox.png`
3. Home 页面和账户菜单：
   `/Users/starfeld/Web_MT/output/imagegen2/mt-presence-quiet-editorial-header-v1.png`
4. 作品详情页面：
   `/Users/starfeld/Web_MT/output/imagegen2/mt-presence-work_detail.png`
5. Works 页面：
   `/Users/starfeld/Web_MT/output/imagegen2/mt-presence-works-v2.png`

请先实际读取并查看以上五张图片，然后再修改代码。不要依靠文字猜测页面样式。参考图片是最终的视觉目标。

## 一、总体目标

网站风格定义：`Quiet Editorial Photography Archive`。

关键词：

- 高级国际摄影网站
- 当代艺术画廊
- 摄影出版物
- 克制、安静
- 编辑排版
- 大面积留白
- 高对比度衬线字体
- 细分隔线
- 深森林绿色强调
- 图片是视觉主体

网站不能做成：

- SaaS 后台
- Behance 或 Adobe 仿站
- 电商网站
- 营销落地页
- 彩色卡片网站
- 玻璃拟态网站

## 二、执行边界

开始修改前：

1. 检查项目使用的框架、路由、状态管理和样式体系。
2. 检查当前 Git 状态和用户已有修改。
3. 不覆盖用户未提交的修改。
4. 复用现有组件、数据、接口、图片和功能。
5. 不重新创建另一个项目。
6. 不使用静态截图代替网页实现。
7. 不将参考图直接作为页面背景。
8. 页面必须是真实 HTML、CSS 和组件实现。
9. 所有按钮、搜索、筛选、收藏和选择功能必须能够交互。
10. 不要只完成首页或顶部导航后就停止。

## 三、统一设计系统

推荐颜色：

- 页面背景：`#F7F7F4`、`#FAFAF8` 或项目现有近白色
- 主文字：`#171817`
- 次级文字：`#666A66`
- 细分隔线：`rgba(23, 24, 23, 0.14)`
- 深森林绿色：`#244F45`
- 深色首页顶栏：`#101210` 或接近黑色
- 错误与退出：克制暗红色

字体：

- 品牌、大标题、作品名称：高对比度 Editorial Serif
- 导航、搜索、表单、按钮、元数据：中性 Sans-serif

优先复用项目已有字体。如果需要替换，必须保证中英文兼容、加载稳定，不允许字体闪烁导致布局跳动。

圆角规则：

- 普通按钮和面板：4–8px
- 搜索框：左右完整半圆，`border-radius: 999px`
- 头像：圆形
- 禁止到处使用 20–30px 大圆角

阴影规则：

- 大部分页面不使用明显阴影
- 只有账户菜单和轻提示可以使用克制的短阴影
- 禁止彩色阴影和发光效果

## 四、GlobalHeader 全局顶栏

创建一个真正复用的 `GlobalHeader` 组件，并在以下页面使用：

- Home
- Works
- About
- Lightbox
- Contact
- Review
- 作品详情
- 其他主要公开页面

不能在每个页面复制一套不同的顶栏代码。

桌面端布局：

- 高度约 64px
- 宽度 100%
- 左侧：MT Presence
- 中间：全局搜索框
- 右侧：Home / Works / About / Lightbox / Contact / Review
- 导航后面增加细竖线
- 然后显示用户头像
- 最右侧为三点菜单按钮
- 当前页面使用深森林绿色细下划线
- 所有内容垂直居中
- 顶栏底部使用 1px 细分隔线

搜索框：

- 宽度约 500px
- 高度约 40px
- 左右完整半圆
- `border-radius: 999px`
- 细灰色边框
- 不要厚重阴影
- 占位文字：`Search works, artists, tags`
- 保留搜索图标
- 不要做成占满屏幕的巨大搜索框

亮色页面使用近白色顶栏。

Home 页面使用深色顶栏：

- 深色背景
- 白色文字
- 深色半圆搜索框
- 搜索框边框清晰但克制
- 结构和尺寸与亮色版本完全一致

## 五、Home 页面

参考图：

`/Users/starfeld/Web_MT/output/imagegen2/mt-presence-quiet-editorial-header-v1.png`

目标：

- 顶部为深色 GlobalHeader
- 下方为宽幅摄影 Hero
- 使用项目现有高质量摄影作品
- 图片占据绝大部分首屏
- 不要左右分屏成两块独立面板
- 不要用彩色渐变遮罩
- 允许在照片较暗区域放置标题

Hero 文案结构：

- 小型大写分类文字
- 大型衬线标题
- 一句简洁介绍
- Enter Works 主按钮
- About the Practice 文字链接

标题不需要机械复制参考图中的英文内容，可以使用项目已有内容，但必须保持大衬线标题、左侧对齐、强对比和充足留白，且不遮挡照片主体。

首屏底部需要露出 Selected Works 下一部分，让用户知道页面可以继续滚动。

账户菜单在 Home 页面使用深色版本，参考图中右上角展开状态。

## 六、Works 页面

参考图：

`/Users/starfeld/Web_MT/output/imagegen2/mt-presence-works-v2.png`

这是必须严格遵守的页面。

页面结构：

`GlobalHeader → 约 28–32px 间距 → 分类筛选栏 → 图片瀑布流 → 简洁页脚`

禁止增加：

- PHOTOGRAPHIC ARCHIVE
- 巨大的 Works 标题
- Works 页面介绍文案
- 28 WORKS 大型统计区
- 大面积空白 Hero
- 左侧导航栏

筛选栏：

- All
- Abstract
- Concrete
- Square
- Portrait
- Landscape
- Panorama
- 当前筛选使用细绿色或深色下划线
- 类型和比例之间使用细竖线分隔
- 不要把所有筛选做成胶囊按钮
- 筛选栏可以 sticky，但不能遮挡顶栏

作品区域：

- 使用 Masonry 瀑布流
- 保留原始图片比例
- 约 4–5 列，按照现有屏幕宽度自适应
- 图片之间保持均匀白色间距
- 不使用厚重卡片背景
- 不使用统一强制裁切
- 图片是页面绝对主体

Hover 状态：

- 只在当前图片上显示作品标题
- 显示收藏图标
- 显示下载图标
- 使用克制的底部暗色渐变保证可读性
- 不覆盖整张图片

收藏交互：

- 点击收藏后页面不能刷新
- 不能重新请求整个页面
- 不能回到页面顶部
- 不能导致瀑布流重新排列
- 收藏图标原地变成深森林绿色填充
- 显示轻量 Toast：`Saved to Lightbox`
- Toast 约两秒后消失
- 不使用 alert
- API 失败时回滚收藏状态
- 收藏状态必须同步到 Lightbox

## 七、作品详情页面

参考图：

`/Users/starfeld/Web_MT/output/imagegen2/mt-presence-work_detail.png`

页面不是弹窗，也不是带模糊背景的 Lightbox。

布局：

- 顶部使用亮色 GlobalHeader
- 主体为左右两栏
- 左侧约 55–60%：大幅作品图片
- 右侧约 40–45%：作品信息
- 图片应完整、清晰，不出现顶部虚化
- 左右区域使用宽松留白
- 页面背景为近白色

右侧内容顺序：

1. 作品序号，例如 07 / 28
2. 上一张、下一张按钮
3. 大型衬线作品标题
4. 作品简短描述
5. 操作按钮
6. 元数据
7. 标签
8. Related Works

操作按钮：

- Saved 或 Add to Lightbox
- Inquire
- Download

Saved 状态使用深森林绿色。

元数据使用简洁 definition list，不要做成彩色卡片：

- TYPE
- RATIO
- SIZE
- CAPTURED

标签可以使用小型细边框标签，但圆角要克制。Related Works 使用小型横向缩略图。

## 八、About 页面

参考图：

`/Users/starfeld/Web_MT/output/imagegen2/mt-presence-about.png`

桌面端主体：

- 顶部亮色 GlobalHeader
- 主体使用左右两栏编辑网格
- 左侧约 44–48%：大型竖向摄影图片
- 右侧约 52–56%：介绍文字
- 图片和文字之间使用充足留白
- 可以增加一条短的深森林绿色水平线连接视觉关系

右侧文字结构：

1. 小型大写：ABOUT THE PRACTICE
2. 大型衬线标题：MT Presence 或动态用户/品牌名称
3. 一段大型衬线主张
4. 两到三段正文介绍

页面下方信息区域：

- Based in USA
- Available for commissions
- Working internationally
- 艺术家头像
- Read the artist statement

不要使用彩色信息卡片。信息区通过细竖线或留白分组。

内容必须从真实用户资料或项目数据读取。不要把参考图中的人物、地区和文字永久写死；没有数据时才使用合理默认值。

## 九、Lightbox 页面

参考图：

`/Users/starfeld/Web_MT/output/imagegen2/mt-presence-lightbox.png`

Lightbox 是“已收藏作品的选择与询价页面”，不是简单收藏列表。

页面结构：

- 顶部亮色 GlobalHeader
- 页面标题和说明区域
- Clear all
- Inquire about selected (N)
- 选择工具栏
- 左侧作品列表
- 右侧选择摘要

标题区域保持参考图中的比例，不要做成巨大 Hero。

顶部内容：

- YOUR SELECTION
- Lightbox
- Choose the works you would like to discuss.
- N SAVED WORKS

选择工具栏：

- Select all
- Selected X of Y
- Sort by Date saved

作品网格：

- 三列为主
- 每张作品左上角有选择圆圈
- 已选择：绿色圆形和白色勾
- 未选择：透明或白色圆圈
- 选中作品可以增加非常轻的绿色边框
- 图片下方显示作品名、类型和 Remove
- Remove 只删除对应作品

右侧摘要：

- 显示：`X works will be attached`
- 显示选中作品的小缩略图和名称
- 提供 Review selection
- 明确显示：`Only the works you select will be attached to your inquiry.`

关键逻辑：

- 收藏作品不等于选择作品
- 用户可以只选择一部分收藏作品
- 未选中的作品不能发送到 Contact
- `Inquire about selected (N)` 中的数量实时更新
- N 为 0 时按钮禁用
- 选择状态返回页面后应该保留
- 删除收藏时同步删除其选择状态
- Clear all 必须有防误操作确认
- Contact 页面只接收已选择作品的 ID

## 十、用户头像和账户菜单

用户登录后：

- 显示头像
- 不显示 Sign in
- Review 位于顶部主导航
- Review 不允许出现在账户菜单中

头像问题必须修复：

- 页面首次渲染就预留头像容器
- 不允许头像延迟出现导致导航跳动
- 不允许头像随机消失
- 加载期间显示稳定 initials fallback
- 加载失败显示姓名缩写
- 多个页面共享同一份用户状态
- 不要每个页面重复请求用户资料
- 上传新头像后所有页面立即同步更新

头像支持上传：

- JPG、PNG、WebP
- 文件大小验证
- 图片预览
- 中心裁切
- `object-fit: cover`
- 上传失败保留旧头像
- 刷新后仍显示最新头像

账户菜单内容：

- 用户头像
- 用户名称
- 邮箱
- Active account
- Dashboard
- Workspace
- Account Settings
- 分隔线
- Sign out

禁止出现：

- Review
- Sign in
- 重复公共导航

亮色页面使用亮色账户菜单，Home 深色页面使用深色菜单。

交互要求：

- 点击头像或三点按钮打开
- 点击页面外关闭
- Escape 关闭
- 支持键盘操作
- 正确设置 aria 属性
- 菜单不能超出视口

## 十一、Review

Review 必须出现在主导航：

`Home / Works / About / Lightbox / Contact / Review`

要求：

- 登录后显示
- 作为独立页面
- 当前页面显示绿色下划线
- 不放进头像菜单
- 不要同时显示用户头像和 Sign in
- 保留现有 Review 功能，不要因为视觉改造破坏审核流程

## 十二、搜索功能

GlobalHeader 中的搜索框必须在所有主要页面出现。

功能：

- 搜索作品标题
- 搜索标签
- 搜索作品类型
- 根据项目现有能力搜索艺术家
- 使用 debounce
- Enter 提交
- Escape 关闭搜索建议
- 搜索不能造成不必要的页面刷新
- 搜索词可以同步到 URL
- 返回页面时恢复搜索词
- 无结果时显示克制的空状态
- 加载时不能让顶栏尺寸变化

## 十三、响应式要求

桌面端必须优先匹配五张参考图。

平板端：

- 缩小搜索框和导航间距
- 保持头像可见
- 不允许元素重叠
- About 可以保持两栏或变为比例更合理的两栏
- Detail 页面可以缩小左右比例

移动端：

- Logo 保留
- 搜索框折叠为搜索图标或独立展开层
- 主导航收进移动菜单
- 头像入口保留
- Works 变为 1–2 列
- Lightbox 右侧摘要移动到作品列表上方或底部 sticky 区
- About 改为单列
- Detail 改为图片在上、信息在下
- 不允许横向溢出
- 交互目标至少 44px

## 十四、工程实现要求

- 复用项目现有框架
- 创建可复用 GlobalHeader
- 创建统一设计 token
- 复用现有数据和 API
- 不硬编码作品列表
- 不用截图作为背景
- 不重复编写用户状态逻辑
- 不引入不必要的大型 UI 库
- 不删除现有功能
- 不修改无关页面
- 不覆盖用户未提交改动
- 不留下 console error
- 不留下 TypeScript、lint 或构建错误

如果项目已有组件库，优先基于现有组件扩展。

## 十五、实施顺序

必须按照以下顺序完成：

1. 检查项目结构和现有功能
2. 建立全局设计 token
3. 完成 GlobalHeader
4. 完成头像稳定加载和账户菜单
5. 完成 Works
6. 修复无刷新收藏
7. 完成作品详情
8. 完成 Lightbox 选择逻辑
9. 完成 About
10. 对齐 Home
11. 检查 Review 顶级导航
12. 完成响应式
13. 运行测试和构建
14. 启动项目逐页截图对比
15. 根据截图继续修正，不能第一次能运行就停止

## 十六、验收标准

以下项目全部满足才能结束：

- Home 与参考图整体风格一致
- Works 与 `mt-presence-works-v2.png` 一致
- Works 没有多余标题 Hero
- Works 筛选栏直接接在顶栏下方
- Detail 与参考图保持左右编辑布局
- Detail 顶部没有虚化区域
- About 与参考图保持大图加文字布局
- Lightbox 与参考图保持作品选择加右侧摘要
- Lightbox 可以只选择部分作品
- Contact 只接收选中的作品
- 所有页面使用同一个 GlobalHeader
- 搜索框左右完整半圆
- 搜索框在所有主要页面可见
- 登录后不出现 Sign in
- Review 位于主导航
- Review 不在账户菜单
- 头像首次渲染不闪烁、不消失
- 用户能够上传头像
- 收藏 Works 时页面不刷新
- 收藏图标原地变色
- 显示 Saved to Lightbox 轻提示
- 页面没有左侧边栏
- 没有 Behance 或 Adobe 品牌
- 没有新增 console error
- 测试、lint、构建通过
- 桌面、平板、移动端没有明显布局错误

## 十七、完成后的交付内容

完成后必须提供：

1. 修改文件清单
2. 每个文件的职责
3. 关键状态和交互实现说明
4. 测试、lint、构建结果
5. 以下页面的实际浏览器截图：
   - Home
   - Works
   - Work Detail
   - About
   - Lightbox
   - 账户菜单展开状态
6. 实际截图与参考图的差异说明
7. 尚未完成的问题

不要只提供方案或 CSS 示例。

请完成实际代码修改、启动项目、打开浏览器验收并反复修正。五个参考页面没有全部完成之前，不要宣称任务完成。
