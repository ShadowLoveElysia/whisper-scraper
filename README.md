# 拟人化爬虫工具集

一个专注于反人机检测的个人内容采集工具集，通过模拟真实用户行为来绕过网站的反爬虫机制。

## 重要声明

本项目不是高并发暴力爬虫，而是：
- 拟人化行为：模拟真实用户的鼠标移动、滚动、点击
- 温和速度：低并发、随机延迟，避免触发反爬虫
- 个人使用：为个人备份和离线阅读设计
- 反检测：对抗 Cloudflare、reCAPTCHA 等人机验证

**本项目不包含任何破解网站鉴权的功能。**

如果目标内容为权限内容（会员专享/付费内容），你需要：
- 使用已购买该资源的账号登录
- 使用已开通会员的账号登录
- 本工具仅帮助你下载你有权访问的内容

请遵守网站服务条款，仅用于个人学习和研究。

---

## 当前可用脚本

### 1. Kakuyomu_scraper.py - Kakuyomu小说采集器
**目标网站：** [Kakuyomu](https://kakuyomu.jp/)

**功能：**
- 自动展开折叠目录
- 手动模式备用方案
- Cookie 登录支持
- Sakura LLM 翻译（日→中）
- 三语界面（中/英/日）

**使用：**
```bash
python novel_scraper.py
```

### 2. CopyManga_scraper.py - CopyManga漫画采集器
**目标网站：** [CopyManga](https://copymanga.com/)

**功能：**
- 拟人化鼠标移动
- 图片防盗链破解
- 断点续传
- 自动重试机制
- 三语界面（中/英/日）

**使用：**
```bash
python comic_scraper.py
```

---

## 快速开始

### 安装依赖
```bash
# 使用 uv（推荐）
uv run novel_scraper.py

# 或手动安装
pip install playwright rich pyperclip aiohttp natsort
playwright install chromium
```

### 基本流程
1. 运行脚本
2. 复制目标网址（自动检测）或手动输入
3. 配置下载参数
4. 首次使用会启动登录向导（如需要）
5. 等待下载完成

---

## 模板脚本

提供两个通用模板方便开发新爬虫：

- `base_scraper_template.py` - 文本内容爬虫模板
- `base_image_scraper_template.py` - 图片内容爬虫模板

---

## 支持的网站

| 网站 | 类型 | 状态 | 脚本文件 |
|------|------|------|----------|
| [Kakuyomu](https://kakuyomu.jp/) | 小说 | ✅ | `novel_scraper.py` |
| [CopyManga](https://copymanga.com/) | 漫画 | ✅ | `comic_scraper.py` |
| 哔哩哔哩漫画 | 漫画 | ❌ | 计划中 |
| 腾讯动漫 | 漫画 | ❌ | 计划中 |
| 快看漫画 | 漫画 | ❌ | 计划中 |
| 起点中文网 | 小说 | ❌ | 计划中 |
| 晋江文学城 | 小说 | ❌ | 计划中 |

---

## 核心技术

- **Playwright** - 无头浏览器自动化
- **Rich** - 终端界面
- **反检测策略** - 隐藏 WebDriver、贝塞尔曲线鼠标、随机延迟

---

本项目仅供学习交流使用，请尊重内容创作者的版权，支持正版。

---

## 相关工具

下载完成后，你可能需要：

**📚 合并和转换电子书**
[Bulk-Ebook-Merger-Converter](https://github.com/ShadowLoveElysia/Bulk-Ebook-Merger-Converter)
将下载的章节合并为完整电子书，支持多种格式转换（EPUB、MOBI、PDF 等）

**🌐 翻译外文小说**
[AiNiee-Next](https://github.com/ShadowLoveElysia/AiNiee-Next)
使用 AI 翻译下载的外文小说，支持多种翻译引擎

---

## 需要支持新网站？

如果你需要爬取特定网站，欢迎提交 Issue：

1. 提供目标网站 URL
2. 提供测试账号（如需登录）
3. 发送邮件至：**ShadowVap@outlook.com**
4. 邮件标题：`[爬虫] Issue #编号 - 网站名称`
5. 邮件内容：复述需求和提供测试信息

**注意：** 仅支持个人学习研究用途的网站。
