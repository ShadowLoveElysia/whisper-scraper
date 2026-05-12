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
- 三语界面（中/英/日）

**使用：**
```bash
python novel_scraper.py
```

### 2. CopyManga_scraper.py - CopyManga漫画采集器
**目标网站：** [CopyManga](https://www.2026copy.com/)

**功能：**
- 拟人化鼠标移动
- 图片防盗链破解
- 自动展开折叠目录
- 手动模式备用方案
- Cookie 登录支持
- 断点续传
- 自动重试机制
- 三语界面（中/英/日）

**使用：**
```bash
python comic_scraper.py
```

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

## 支持的网站

| 网站 | 类型 | 状态 | 脚本文件 |
|------|------|------|----------|
| [Kakuyomu](https://kakuyomu.jp/) | 小说 | ✅ | `Kakuyomu_scraper.py` |
| [CopyManga](https://www.2026copy.com/) | 漫画 | ✅ | `CopyManga_scraper.py` |
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

---

## KFID_Scraper.py - 绯月论坛抽奖用户名采集器

`KFID_Scraper.py` 用于采集绯月 ScarletMoon/phpwind 风格帖子里的回复用户名，适合抽奖帖、奖励帖等需要统计参与用户的场景。

### 功能

- 使用 Playwright 打开浏览器手动登录，并保存登录态。
- 支持抓取单页帖子，也支持自动抓取全帖分页。
- 从楼层信息中提取论坛用户名。
- 按用户名去重，重复回复只保留首次出现。
- 默认不排除任何用户名。
- 可通过 `--exclude-name` 手动排除指定用户名。
- 导出 `txt`、`csv`、`json` 三种结果。
- `txt` 只输出用户名，方便直接用于论坛发币。
- `csv/json` 保留 UID、用户名、楼层、pid、发帖时间、页码，方便核对。
- 如果 URL 缺少 `sf` 参数，会尝试从当前目录保存过的离线 HTML 自动补全。

### 安装和运行

推荐使用 `uv`，脚本头部已经声明了 Playwright 依赖：

```bat
uv run KFID_Scraper.py -h
```

如果不用 `uv`，可以手动安装：

```bat
python -m pip install playwright
python -m playwright install chromium
```

### 登录论坛

第一次抓在线帖子前，先保存登录态：

```bat
uv run KFID_Scraper.py login
```

脚本会优先尝试 Edge，然后 Chrome，最后才尝试 Playwright 自带 Chromium。浏览器打开后，在浏览器里登录论坛；确认已经登录后，回到终端按 Enter。

成功后会生成：

```text
forum_auth_state.json
```

这个文件保存了登录态，不要提交到 GitHub，也不要发给别人。

如果想强制使用 Edge：

```bat
uv run KFID_Scraper.py login --channel msedge
```

### 抓取全帖用户名

CMD 里 `&` 会被当成命令分隔符，所以完整 URL 最稳妥的写法是加英文双引号：

```bat
uv run KFID_Scraper.py fetch-thread "https://bbs.kfpromax.com/read.php?tid=1079297&sf=742&fpage=0&toread=&page=6" -o forum_names_all
```

抓完后会生成：

```text
forum_names_all.txt
forum_names_all.csv
forum_names_all.json
```

其中 `forum_names_all.txt` 是最常用的结果文件，一行一个用户名。

### 只抓单页

```bat
uv run KFID_Scraper.py fetch-page "https://bbs.kfpromax.com/read.php?tid=1079297&sf=742&fpage=0&toread=&page=6" -o forum_names_page6
```

### 先测试一页

```bat
uv run KFID_Scraper.py fetch-thread "https://bbs.kfpromax.com/read.php?tid=1079297&sf=742&fpage=0&toread=&page=6" -o test_names --max-pages 1 --show
```

确认浏览器能打开页面、终端能抓到用户名后，再去掉 `--max-pages 1` 抓全帖。

### URL 自动补全

如果你只传了 `tid`：

```bat
uv run KFID_Scraper.py fetch-thread "https://bbs.kfpromax.com/read.php?tid=1079297"
```

脚本会尝试从当前目录的离线 HTML 里找同一个 `tid` 的 `sf` 参数，并自动补全 URL。

也可以手动指定 `sf`：

```bat
uv run KFID_Scraper.py fetch-thread "https://bbs.kfpromax.com/read.php?tid=1079297" --sf 742 -o forum_names_all
```

### 排除指定用户名

默认不排除任何用户名。需要排除时手动传：

```bat
uv run KFID_Scraper.py fetch-thread "https://bbs.kfpromax.com/read.php?tid=1079297&sf=742" --exclude-name zuimao6 -o forum_names_all
```

可以传多个：

```bat
uv run KFID_Scraper.py fetch-thread "https://bbs.kfpromax.com/read.php?tid=1079297&sf=742" --exclude-name user1 --exclude-name user2 -o forum_names_all
```

### 本地离线 HTML 解析

不需要登录，直接解析已经保存到本地的 HTML：

```bat
uv run KFID_Scraper.py parse-html "【HB】利用Ai来翻译Gal_小说_漫画的Ai翻译工具分享（帮项目作者代发）_个人日记 - 绯月ScarletMoon.html" -o forum_names_page6
```
