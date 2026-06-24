# 测试上传功能连接到数据库

## 功能说明

从 2026-06-17 开始，manage.html 的上传功能已完全连接到本地 SQLite 数据库。上传的图片会：

1. 在浏览器中生成 `original`、`display`、`thumbnail` 和 `square_slice` 资产
2. 调用 `POST /api/archive/images` 创建数据库记录
3. 同时保存到 IndexedDB 作为浏览器 fallback
4. 在 works.html 公开页面中可以查看到上传的作品

## 测试步骤

### 1. 启动服务器

```bash
cd /Users/starfeld/Web_MT
python3 server.py --port 8131
```

服务器会在 http://127.0.0.1:8131/ 启动。

### 2. 打开管理页面

在浏览器中访问：
```
http://127.0.0.1:8131/manage.html
```

### 3. 上传测试图片

1. 点击页面顶部的 "Import Images" 按钮
2. 选择一张或多张图片（支持多选）
3. 观察上传进度：
   - Reading：读取文件和元数据
   - Compressing：生成 display 版本
   - Slicing：生成方形切片（如果不是 1:1 比例）
   - Analyzing：分类分析
   - Saving：保存到数据库

### 4. 检查上传状态

成功的上传会显示以下之一：
- ✓ **"Saved to local archive database and IndexedDB."** - 成功写入数据库
- ⚠️ **"Saved locally. Local archive database sync unavailable."** - 只保存到 IndexedDB（数据库不可用）
- ⚠️ **"Saved to IndexedDB only: [错误信息]"** - 数据库写入失败，但已保存到浏览器

### 5. 验证数据库中的记录

在终端中运行：

```bash
# 查看所有上传的记录
sqlite3 data/archive.db "SELECT id, title, source_type, visibility FROM images WHERE source_type = 'upload';"

# 查看上传记录的详细信息
sqlite3 data/archive.db "SELECT * FROM archive_image_view WHERE source_type = 'upload' LIMIT 1;"

# 统计上传记录数量
sqlite3 data/archive.db "SELECT COUNT(*) FROM images WHERE source_type = 'upload';"
```

### 6. 在公开页面查看

1. 打开 works.html：
   ```
   http://127.0.0.1:8131/works.html
   ```

2. 上传的图片应该出现在作品列表中
3. 点击图片可以打开作品详情层查看完整信息

### 7. 编辑上传的作品

1. 在 manage.html 左侧列表中选择上传的作品
2. 编辑标题、描述、标签等字段
3. 点击 "Save Current" 保存
4. 系统会调用 `PATCH /api/archive/images/{id}` 更新数据库

## API 端点

### POST /api/archive/images

创建新的上传记录。

**请求体示例：**
```json
{
  "id": "upload-1718616000-0",
  "title": "My Uploaded Image",
  "description": "A beautiful landscape",
  "content_type": "concrete",
  "display_mode": "color",
  "visibility": "published",
  "sort_order": 0,
  "original_width": 1920,
  "original_height": 1080,
  "ratio_category_code": "sixteen_to_nine",
  "original_filename": "landscape.jpg",
  "exif": {},
  "tag_groups": [
    {"label": "Subject", "tags": ["Landscape"]},
    {"label": "Mood", "tags": ["Peaceful"]}
  ]
}
```

### PATCH /api/archive/images/{id}

更新现有记录（sample 或 upload 都支持）。

### GET /api/archive/images

读取所有 published 的作品（包括 sample 和 upload）。

## 故障排查

### 问题：上传显示 "Local archive database sync unavailable"

**原因：** 数据库文件不存在或服务器未运行

**解决：**
```bash
# 确保数据库已创建
python3 scripts/seed_local_archive_db.py

# 确保服务器正在运行
python3 server.py --port 8131
```

### 问题：上传后在 works.html 看不到

**原因：** 可能的原因：
1. visibility 设置为 draft 或 private
2. 浏览器缓存了旧数据
3. API 返回错误

**解决：**
1. 在 manage.html 中检查作品的 Visibility 设置，改为 Published
2. 刷新 works.html 页面（Ctrl+Shift+R 强制刷新）
3. 打开浏览器开发者工具查看 Network 面板的 API 请求

## 代码修改说明

### server.py 的修改

1. 新增 `handle_archive_image_create()` 方法处理 POST 请求
2. 在 `do_POST()` 中路由到新的创建方法
3. 验证上传数据的必填字段（id, original_width, original_height, ratio_category_code）

### manage.js 的修改

1. `shouldSyncRecordToArchiveApi()` 现在对 `upload` 类型也返回 true
2. 新增 `archiveApiCreatePayload()` 函数生成创建请求的完整数据
3. `syncArchiveApiRecord()` 支持 `isNewUpload` 参数，自动选择 POST 或 PATCH
4. `importUploadedFiles()` 在上传时调用 `syncArchiveApiRecord(record, true)`
5. 添加错误处理：数据库同步失败时仍然保存到 IndexedDB

## 数据流程

```
用户选择图片
    ↓
archive-upload.js 处理图片
    ↓
生成 original/display/thumbnail/square_slice 资产
    ↓
manage.js 调用 syncArchiveApiRecord(record, true)
    ↓
POST /api/archive/images → SQLite 插入 images 表
    ↓
同时保存到 IndexedDB
    ↓
works.html 从 SQLite 读取显示
```

## 注意事项

1. **图片文件本身仍然存储在 IndexedDB**：SQLite 只存储元数据，图片二进制数据在浏览器中以 Blob 形式存储
2. **首页设置仍在 IndexedDB**：`site_settings.homepage` 暂时不写入 SQLite
3. **assets 和 square_slices 表暂未使用**：当前只写入 `images`、`image_tags` 和 `image_taggings` 表
4. **visibility 默认为 published**：上传的图片默认可见，可以在管理页面修改
