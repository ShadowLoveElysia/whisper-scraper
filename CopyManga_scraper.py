# /// script
# requires-python = ">=3.10"
# dependencies = [
#     "playwright",
#     "requests",
#     "rich",
#     "pyperclip",
# ]
# ///

import os
import sys
import re
import json
import locale
import random
import asyncio
import hashlib
import shutil
import signal
import requests
import argparse
import math
import subprocess
import pyperclip
import time
import base64
from rich.console import Console
from rich.progress import Progress, SpinnerColumn, BarColumn, TextColumn, TimeRemainingColumn
from rich.panel import Panel
from rich.prompt import Prompt, Confirm
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from urllib.parse import urljoin, urlparse
from playwright.async_api import async_playwright

console = Console()

def signalHandler(sig, frame):
    console.print("\n[bold red]System: Signal Interrupt Detected. Initiating Emergency Shutdown...[/bold red]")
    raise KeyboardInterrupt

signal.signal(signal.SIGINT, signalHandler)

STEALTH_JS = "" # Generated dynamically in Elysia class

STANDARD_JS = """
Object.defineProperty(navigator, 'webdriver', { get: () => undefined });
Object.defineProperty(navigator, 'languages', { get: () => ['zh-CN', 'zh'] });
"""

class Phantom:
    def __init__(self, page):
        self.page = page

    def _bezierPoint(self, t, p0, p1, p2, p3):
        u = 1 - t
        tt = t * t
        uu = u * u
        uuu = uu * u
        ttt = tt * t
        
        x = uuu * p0['x'] + 3 * uu * t * p1['x'] + 3 * u * tt * p2['x'] + ttt * p3['x']
        y = uuu * p0['y'] + 3 * uu * t * p1['y'] + 3 * u * tt * p2['y'] + ttt * p3['y']
        return {'x': x, 'y': y}

    async def humanMove(self, targetElement=None, x=0, y=0):
        start = {'x': 0, 'y': 0}
        
        if targetElement:
            box = await targetElement.bounding_box()
            if not box:
                return
            end = {
                'x': box['x'] + box['width'] * random.uniform(0.2, 0.8),
                'y': box['y'] + box['height'] * random.uniform(0.2, 0.8)
            }
        else:
            end = {'x': x, 'y': y}

        start = {
            'x': end['x'] + random.uniform(-200, 200),
            'y': end['y'] + random.uniform(-200, 200)
        }
        
        start['x'] = max(0, min(start['x'], 1920))
        start['y'] = max(0, min(start['y'], 1080))

        c1 = {
            'x': start['x'] + (end['x'] - start['x']) * random.uniform(0.3, 0.7),
            'y': start['y'] + (end['y'] - start['y']) * random.uniform(0.1, 0.5)
        }
        c2 = {
            'x': start['x'] + (end['x'] - start['x']) * random.uniform(0.3, 0.7),
            'y': end['y'] + (end['y'] - start['y']) * random.uniform(0.1, 0.5)
        }

        steps = random.randint(15, 30)
        for i in range(steps):
            t = i / steps
            if t < 0.5:
                tweaked_t = 2 * t * t
            else:
                tweaked_t = -1 + (4 - 2 * t) * t
            
            p = self._bezierPoint(tweaked_t, start, c1, c2, end)
            await self.page.mouse.move(p['x'], p['y'])
            await asyncio.sleep(random.uniform(0.005, 0.015))
        
        await self.page.mouse.move(end['x'], end['y'])

        if random.random() < 0.8:
            for _ in range(random.randint(2, 4)):
                jx = end['x'] + random.uniform(-3, 3)
                jy = end['y'] + random.uniform(-3, 3)
                await self.page.mouse.move(jx, jy)
                await asyncio.sleep(random.uniform(0.05, 0.1))

    async def humanClick(self, element):
        await self.humanMove(targetElement=element)
        await asyncio.sleep(random.uniform(0.05, 0.2))
        await self.page.mouse.down()
        await asyncio.sleep(random.uniform(0.05, 0.15))
        await self.page.mouse.up()

    async def randomScrollBack(self):
        dist = -1 * random.randint(300, 800)
        await self.page.evaluate(f"window.scrollBy({{top: {dist}, behavior: 'smooth'}})")
        await asyncio.sleep(random.uniform(1.0, 2.0))
        await self.page.evaluate(f"window.scrollBy({{top: {-dist}, behavior: 'smooth'}})")

    async def randomUselessClick(self):
        w = 1920
        x = random.choice([random.uniform(10, 100), random.uniform(w-100, w-10)])
        y = random.uniform(100, 800)
        await self.humanMove(x=x, y=y)
        await self.page.mouse.click(x, y)

class Eden:
    def __init__(self, lang=None):
        try:
            sys_lang = locale.getlocale()[0]
            sys_lang = sys_lang[:2] if sys_lang else 'en'
        except:
            sys_lang = 'en'
            
        self.lang = lang or sys_lang
        if self.lang not in ['zh', 'en', 'ja']:
            self.lang = 'en'
        
        self.separator = "=" * 60
        self.subSeparator = "-" * 60
        
        self.scripts = {
            "start": {
                "zh": "\nSystem: 初始化核心组件...",
                "en": "\nSystem: Initializing core components...",
                "ja": "\nSystem: コアコンポーネントを初期化中..."
            },
            "welcome": {
                "zh": "System: 欢迎使用漫画采集终端 [Elysia Ver.]",
                "en": "System: Welcome to Comic Scraper Terminal [Elysia Ver.]",
                "ja": "System: マンガ収集ターミナルへようこそ [Elysia Ver.]"
            },
            "config_loaded": {
                "zh": "Config: 检测到历史配置，已自动加载记忆。",
                "en": "Config: History detected. Memory loaded.",
                "ja": "Config: 履歴を検出しました。メモリをロードしました。"
            },
            "clipboard_found": {
                "zh": "Input: 检测到剪贴板中存在链接: [cyan]{}[/cyan]\n       是否直接使用此目标? (y/N): ",
                "en": "Input: Link detected in clipboard: [cyan]{}[/cyan]\n       Use this target? (y/N): ",
                "ja": "Input: クリップボードにリンクを検出: [cyan]{}[/cyan]\n       このターゲットを使用しますか? (y/N): "
            },
            "switch_lang": {
                "zh": "System: 语言已切换为: 简体中文",
                "en": "System: Language switched to: English",
                "ja": "System: 言語が切り替わりました: 日本語"
            },
            "toggle_sniff": {
                "zh": "Config: 剪贴板自动嗅探已 {}",
                "en": "Config: Clipboard auto-sniff is now {}",
                "ja": "Config: クリップボード自動検出は现在 {} です"
            },
            "sniff_on": {
                "zh": "开启",
                "en": "ON",
                "ja": "ON"
            },
            "sniff_off": {
                "zh": "关闭",
                "en": "OFF",
                "ja": "OFF"
            },
            "input_url": {
                "zh": "Input: 请输入漫画目录页网址 (或直接在浏览器复制): ",
                "en": "Input: Please enter the comic catalog URL (or just Copy from browser): ",
                "ja": "Input: マンガの目次URLを入力してください (またはブラウザからコピー): "
            },
            "ask_name": {
                "zh": "Input: 请输入漫画名称 (将创建同名专属文件夹): ",
                "en": "Input: Enter Comic Name (Creates a dedicated subfolder): ",
                "ja": "Input: マンガ名を入力してください (専用サブフォルダを作成します): "
            },
            "default_mode_info": {
                "zh": "Config: 当前配置概览\n      [输出目录='{}' | 线程数={} | 并发数={} | 后台模式={} | 滑动间隔={}s | 冷却时间={}s]",
                "en": "Config: Current Settings\n      [Output='{}' | Threads={} | Concurrent={} | Headless={} | ScrollWait={}s | Pause={}s]",
                "ja": "Config: 現在の設定\n      [出力='{}' | スレッド={} | 同時={} | 画面なし={} | 待機={}s | 冷却={}s]"
            },
            "ask_use_default": {
                "zh": "Input: 是否应用上述配置? [Y/n]: ",
                "en": "Input: Apply these settings? [Y/n]: ",
                "ja": "Input: 上記の設定を適用しますか? [Y/n]: "
            },
            "ask_mode": {
                "zh": "Input: 请选择采集模式:\n      1: 狂暴模式 (多章节并发 | 随机滚动 | 速度快)\n      2: 拟人模式 (单章节处理 | 随机滚动+时间抖动 | 更安全/反爬强)\n      选择 [1/2] (默认: 1): ",
                "en": "Input: Select Mode:\n      1: Turbo (Concurrent Chapters | Random Scroll | Fast)\n      2: Human (Single Chapter | Random Scroll + Timing Jitter | Safer/Stealth)\n      Select [1/2] (Default: 1): ",
                "ja": "Input: モード選択:\n      1: ターボ (複数章同時 | ランダムスクロール | 高速)\n      2: 擬人化 (単一章処理 | ランダム + 時間のゆらぎ | より安全/回避力强)\n      选择 [1/2] (默认: 1): "
            },
            "mode_human_activated": {
                "zh": "Config: 已激活拟人模式。强制并发=1，启用随机平滑滚动算法。",
                "en": "Config: Human Mode activated. Forced Concurrent=1, Random Smooth Scroll enabled.",
                "ja": "Config: 擬人化モード有効。同時実行=1、ランダムスムーズスクロール有効。"
            },
            "ask_merge_pdf": {
                "zh": "Input: 下载任务结束。是否自动将所有章节合并为 PDF? [Y/n]: ",
                "en": "Input: Tasks finished. Batch merge chapters into PDF? [Y/n]: ",
                "ja": "Input: タスク完了。すべての章をPDFに結合しますか？ [Y/n]: "
            },
            "ask_ebook_convert": {
                "zh": "Input: 是否启用全自动电子书转换 (安全模式)? [Y/n]: ",
                "en": "Input: Enable full-auto E-book conversion (Safe Mode)? [Y/n]: ",
                "ja": "Input: 全自動電子書籍转换 (セーフモード) を有効にしますか？ [Y/n]: "
            },
            "downloading_tool": {
                "zh": "System: 未检测到 PDF 合并工具，正在自动下载 (Image2PDF.py)...",
                "en": "System: PDF tool not found. Downloading automatically (Image2PDF.py)...",
                "ja": "System: PDFツールが見つかりません。自動ダウンロード中 (Image2PDF.py)..."
            },
            "starting_merge": {
                "zh": "System: 启动 PDF 合并进程...",
                "en": "System: Starting PDF merge process...",
                "ja": "System: PDF結合プロセスを開始します..."
            },
            "chapter_analysis": {
                "zh": "Data: 发现 {} 个章节 | 常规: {} (范围: {}) | 带小数的章节: {} (可能是番外或特殊章节)",
                "en": "Data: Found {} chapters | Regular: {} (Range: {}) | Special Chapters: {} (Likely omake/specials)",
                "ja": "Data: {} 章を発見 | 通常: {} (範囲: {}) | 小数点のある章: {} (番外編や特別編の可能性があります)"
            },
            "ask_vol_filter": {
                "zh": "Input: 同时检测到“卷”与“话”。请选择采集目标:\n      a: 仅下载“话” (忽略卷)\n      b: 仅下载“卷” (忽略话)\n      直接回车保留全部: ",
                "en": "Input: Both Volumes and Chapters detected. Select target:\n      a: Chapters Only (Ignore Volumes)\n      b: Volumes Only (Ignore Chapters)\n      Press Enter to keep both: ",
                "ja": "Input: 「卷」と「话」の両方が検出されました。ターゲットを選択:\n      a: 「话」のみ (卷を無視)\n      b: 「卷」のみ (話を無視)\n      Enterキーで両方を保持: "
            },
            "ask_download_all": {
                "zh": "Input: 是否下载全部章节? [Y/n]: ",
                "en": "Input: Download all chapters? [Y/n]: ",
                "ja": "Input: すべての章を下载しますか? [Y/n]: "
            },
            "ask_select_mode": {
                "zh": "Input: 选择模式:\n      a: 最新 N 话 (倒序)\n      b: 指定范围 (如 1-20)\n      c: 多段范围 (如 1-5 10-12)\n      d: 仅下载整数章节 (剔除小数)\n      选择 [a/b/c/d]: ",
                "en": "Input: Select Mode:\n      a: Latest N\n      b: Range (e.g., 1-20)\n      c: Multi-Range (e.g., 1-5 10-12)\n      d: Integers Only (No decimals)\n      Select [a/b/c/d]: ",
                "ja": "Input: モード選択:\n      a: 最新 N 話\n      b: 範囲指定 (例 1-20)\n      c: 複数範囲 (例 1-5 10-12)\n      d: 整数章のみ (小数除外)\n      選択 [a/b/c/d]: "
            },
            "ask_latest_count": {
                "zh": "Input: 下载最新的多少话? (默认: 10): ",
                "en": "Input: How many latest chapters? (Default: 10): ",
                "ja": "Input: 最新の何話をダウンロードしますか? (デフォルト: 10): "
            },
            "ask_range": {
                "zh": "Input: 请输入范围 (例如 1-20): ",
                "en": "Input: Enter range (e.g. 1-20): ",
                "ja": "Input: 範囲を入力してください (例 1-20): "
            },
            "ask_multi_range": {
                "zh": "Input: 请输入多段范围 (空格分隔, 如 1-5 8-10): ",
                "en": "Input: Enter multi-ranges (space separated, e.g. 1-5 8-10): ",
                "ja": "Input: 複数範囲を入力してください (スペース区切り, 例 1-5 8-10): "
            },
            "selection_result": {
                "zh": "Config: 已选中 {} 个章节进行下载。",
                "en": "Config: Selected {} chapters for download.",
                "ja": "Config: ダウンロード用に {} 章が選択されました。"
            },
            "ask_auto_merge_trigger": {
                "zh": "Input: 是否在采集任务结束后自动触发合并/转换逻辑? (y/N): ",
                "en": "Input: Auto trigger merge/convert after scraping? (y/N): ",
                "ja": "Input: 収集完了後に自動で結合/変換を実行しますか？ (y/N): "
            },
            "ask_merge_format_menu": {
                "zh": "\n--- 常用格式 ---\n  1) EPUB (通用)  2) PDF (文档)  3) CBZ (漫画)\n--- Kindle 专用 ---\n  4) MOBI (旧)    5) AZW3 (新)\n--- 其他格式 (需Calibre) ---\n  6) DOCX  7) TXT  8) KEPUB  9) FB2  10) LIT\n  11) LRF  12) PDB  13) PMLZ 14) RB  15) RTF\n  16) TCR  17) TXTZ 18) HTMLZ\n--- 特殊选项 ---\n  19) 全部原生格式 (EPUB+PDF+CBZ)\nInput: 请选择目标格式 (序号, 默认: 1): ",
                "en": "\n--- Common ---\n  1) EPUB  2) PDF  3) CBZ\n--- Kindle ---\n  4) MOBI  5) AZW3\n--- Others (Calibre required) ---\n  6) DOCX  7) TXT  8) KEPUB  9) FB2  10) LIT ...\n--- Special ---\n  19) All Native (EPUB+PDF+CBZ)\nInput: Select target format (ID, Default: 1): ",
                "ja": "\n--- 一般 ---\n  1) EPUB  2) PDF  3) CBZ\n--- Kindle ---\n  4) MOBI  5) AZW3\n--- その他 ---\n  19) 全ネイティブ (EPUB+PDF+CBZ)\nInput: ターゲット形式を選択 (番号, デフォルト: 1): "
            },
            "ask_output": {
                "zh": "Input: 请指定输出目录 (默认: {}): ",
                "en": "Input: Output Directory (Default: {}): ",
                "ja": "Input: 出力ディレクトリ (デフォルト: {}): "
            },
            "ask_threads": {
                "zh": "Input: 设置下载线程数 (默认: {}): ",
                "en": "Input: Download Threads (Default: {}): ",
                "ja": "Input: ダウンロードスレッド数 (デフォルト: {}): "
            },
            "ask_concurrent": {
                "zh": "Input: 设置并发章节数 (默认: {}): ",
                "en": "Input: Concurrent Chapters (Default: {}): ",
                "ja": "Input: 同時実行チャプター数 (デフォルト: {}): "
            },
            "ask_scroll_wait": {
                "zh": "Input: 页面滑动基础等待时间(秒) (默认: {}): ",
                "en": "Input: Base Scroll Wait Time (sec) (Default: {}): ",
                "ja": "Input: 基本スクロール待機時間 (秒) (デフォルト: {}): "
            },
            "ask_pause_duration": {
                "zh": "Input: 遇到反爬虫或降级模式时的冷却时间(秒) (默认: {}): ",
                "en": "Input: Pause duration on anti-bot or downgrade (sec) (Default: {}): ",
                "ja": "Input: 回避またはダウングレード時の待機時間 (秒) (デフォルト: {}): "
            },
            "ask_block_ads": {
                "zh": "Input: [yellow]是否启用战术资源拦截? (加快速度但可能导致加载失败) [y/N] (默认: {}): [/yellow]",
                "en": "Input: [yellow]Enable Tactical Resource Blocking? (Faster but risky) [y/N] (Default: {}): [/yellow]",
                "ja": "Input: [yellow]戦術的リソースブロックを有効にしますか？ (高速ですがリスクあり) [y/N] (デフォルト: {}): [/yellow]"
            },
            "ask_cookie_enable": {
                "zh": "Input: 是否启用 Cookie 注入 (用于会员/登录内容)? [y/N] (默认: N): ",
                "en": "Input: Enable Cookie Injection (For Member/Login content)? [y/N] (Default: N): ",
                "ja": "Input: Cookie インジェクションを有効にしますか？ [y/N] (デフォルト: N): "
            },
            "ask_cookie_wizard": {
                "zh": "System: 未检测到 Cookies 或需要更新。\nInput: 是否启动 [登录向导] 以捕获 Cookie? (将打开浏览器供您登录) [Y/n]: ",
                "en": "System: Cookies missing or update needed.\nInput: Launch [Login Wizard] to capture cookies? (Opens browser) [Y/n]: ",
                "ja": "System: Cookieが見つからないか更新が必要です。\nInput: [ログインウィザード] を起動してCookieを取得しますか？ [Y/n]: "
            },
            "cookie_success": {
                "zh": "Config: Cookie 已捕获并保存至 cookies.json",
                "en": "Config: Cookies captured and saved to cookies.json",
                "ja": "Config: Cookie が取得され cookies.json に保存されました"
            },
            "ask_headless": {
                "zh": "Input: 是否启用后台静默模式? [Y/n] (默认: {}): ",
                "en": "Input: Enable Headless (Background) Mode? [Y/n] (Default: {}): ",
                "ja": "Input: バックグラウンドモードを有効にしますか? [Y/n] (デフォルト: {}): "
            },
            "ask_browser": {
                "zh": "Input: 选择浏览器引擎 [1: Edge (默认) | 2: Chrome]: ",
                "en": "Input: Select Browser Engine [1: Edge (Default) | 2: Chrome]: ",
                "ja": "Input: ブラウザエンジンの選択 [1: Edge (デフォルト) | 2: Chrome]: "
            },
            "ask_repair": {
                "zh": "\nInput: 是否运行完整性检查与修复工具? (补全丢失 + 查重) [y/N]: ",
                "en": "\nInput: Run Integrity Check & Repair Tool? (Recover missing + Dedup) [y/N]: ",
                "ja": "\nInput: 整合性チェックと修復ツールを実行しますか? (欠落复元 + 重複確認) [y/N]: "
            },
            "launch_browser": {
                "zh": "Browser: 正在启动浏览器引擎 ({}) ...",
                "en": "Browser: Launching browser engine ({})...",
                "ja": "Browser: ブラウザエンジンを起動中 ({}) ..."
            },
            "nav_catalog": {
                "zh": "Nav: 正在访问目标目录: {}",
                "en": "Nav: Navigating to catalog: {}",
                "ja": "Nav: 目次に移動中: {}"
            },
            "scavenging": {
                "zh": "Search: 正在分析页面资源 (模式: {}) ...",
                "en": "Search: Analyzing page resources (Mode: {})...",
                "ja": "Search: ページリソースを分析中 (モード: {}) ..."
            },
            "chapter_analysis": {
                "zh": "Data: 发现 {} 个项目 | 常规: {} | 卷数: {} | 小数: {} (可能是番外或特殊章节)",
                "en": "Data: Found {} items | Regular: {} | Volumes: {} | Decimals: {} (Likely specials/omake)",
                "ja": "Data: {} 個の項目を発見 | 通常: {} | 巻数: {} | 小数点: {} (番外編の可能性があります)"
            },
            "next_page": {
                "zh": "Nav: 检测到翻页单元，正在前往第 {}/{} 页...",
                "en": "Nav: Paging detected, moving to page {}/{}...",
                "ja": "Nav: ページングを検出、{}/{} ページに移動中..."
            },
            "done": {
                "zh": "System: 所有任务执行完毕。",
                "en": "System: All tasks completed.",
                "ja": "System: 全てのタスクが完了しました。"
            },
            "shutdown": {
                "zh": "System: 正在进行优雅退出，清理残留资源...",
                "en": "System: Shutting down gracefully. Cleaning resources...",
                "ja": "System: 正常にシャットダウンしています。リソースをクリーニング中..."
            },
            "ask_retry": {"zh": "Warning: 监测到 {} 个下载失败样本。是否尝试重构 (Retry)? [Y/n]: ", "en": "Warning: {} failed downloads detected. Attempt reconstruction? [Y/n]: ", "ja": "Warning: {} 個の下载失败を検出。再構築 (リトライ) しますか？ [Y/n]: "},
            "ip_limit_auto": {"zh": "Warning: 检测到 IP 限制 (超时)。已自动切换为拟人模式 (单线程)，这将增加耗时。", "en": "Warning: IP limit detected. Auto-switched to Human Mode (Single Thread). Slower but safer.", "ja": "Warning: IP制限を検出。擬人化モード（シングルスレッド）に切り替えました。"},
            "ip_limit_ask": {"zh": "Warning: 检测到 IP 限制 (超时)。是否切换为拟人模式? [Y/n]: ", "en": "Warning: IP limit detected. Switch to Human Mode? [Y/n]: ", "ja": "Warning: IP制限を検出。擬人化モードに切り替えますか？ [Y/n]: "},
                        "dashboard_menu": {"zh": "\nSystem: 任务队列空闲。请选择下一步指令:\n      [green]a[/green]: 完整性检查 (Repair)\n      [green]b[/green]: PDF 合并 (Merge)\n      [green]c[/green]: 采集新目标 (New Task)\n      [green]e[/green]: 切换语言 (Switch Lang)\n      [green]f[/green]: 自动嗅探开关 (Toggle Sniff)\n      [green]g[/green]: 自动降级开关 (Auto-Downgrade)\n      [green]d[/green]: 退出终端 (Exit)\n      选择 [a/b/c/d/e/f/g] (默认: d): ", "en": "\nSystem: Task queue idle. Await instructions:\n      [green]a[/green]: Integrity Check\n      [green]b[/green]: PDF Merge\n      [green]c[/green]: Scrape New Target\n      [green]e[/green]: Switch Language\n      [green]f[/green]: Toggle Auto-Sniff\n      [green]g[/green]: Toggle Auto-Downgrade\n      [green]d[/green]: Exit Terminal\n      Select [a/b/c/d/e/f/g] (Default: d): ", "ja": "\nSystem: 待機中。指示を選択してください:\n      [green]a[/green]: 整合性チェック\n      [green]b[/green]: PDF 結合\n      [green]c[/green]: 新しいターゲット\n      [green]e[/green]: 言語切り替え\n      [green]f[/green]: 自動検出切り替え\n      [green]g[/green]: 自動ダウングレード\n      [green]d[/green]: 終了\n      選択 [a/b/c/d/e/f/g] (デフォルト: d): "},
            "ask_new_url": {
                "zh": "Input: 请输入新的漫画目录页网址: ",
                "en": "Input: Enter new comic catalog URL: ",
                "ja": "Input: 新しいマンガの目次URLを入力してください: "
            },
            "error": {
                "zh": "Error: {}",
                "en": "Error: {}",
                "ja": "Error: {}"
            }
        }

    def say(self, key, *args):
        msg = self.scripts.get(key, {}).get(self.lang, "")
        if args:
            msg = msg.format(*args)
        console.print(msg)
    
    def ask(self, key, *args):
        msg = self.scripts.get(key, {}).get(self.lang, "")
        if args:
            msg = msg.format(*args)
        return console.input(msg)
    
    def openGateway(self, path):
        try:
            os.startfile(os.path.abspath(path))
        except:
            pass

    def notify(self, title, message):
        """Send a Windows System Notification (Toast)"""
        if sys.platform == "win32":
            try:
                ps_script = f"""
                [Windows.UI.Notifications.ToastNotificationManager, Windows.UI.Notifications, ContentType=WindowsRuntime] > $null;
                $template = [Windows.UI.Notifications.ToastNotificationManager]::GetTemplateContent([Windows.UI.Notifications.ToastTemplateType]::ToastText02);
                $xml = $template.GetXml();
                $template.GetElementsByTagName("text")[0].AppendChild($template.CreateTextNode("{title}")) > $null;
                $template.GetElementsByTagName("text")[1].AppendChild($template.CreateTextNode("{message}")) > $null;
                $toast = [Windows.UI.Notifications.ToastNotification]::new($template);
                $notifier = [Windows.UI.Notifications.ToastNotificationManager]::CreateToastNotifier("Comic Scraper");
                $notifier.Show($toast);
                """
                subprocess.run(["powershell", "-Command", ps_script], capture_output=True, creationflags=subprocess.CREATE_NO_WINDOW)
            except: pass

    def singFinale(self):
        try:
            if sys.platform == "win32":
                import winsound
                winsound.MessageBeep(winsound.MB_ICONASTERISK)
            else:
                print('\a')
        except:
            pass
    
    def printSeparator(self):
        console.print(self.separator, style="dim")
    
    def printSubSeparator(self):
        console.print(self.subSeparator, style="dim")
    
    def sanitize(self, name):
        return re.sub(r'[\\/*?:"<>|]', "", name).strip()

class Elysia:
    def __init__(self):
        self.parser = argparse.ArgumentParser()
        self.parser.add_argument("url", type=str, nargs="?")
        self.parser.add_argument("-o", "--output", type=str, default="manga_downloads")
        self.parser.add_argument("-n", "--name", type=str, default=None)
        self.parser.add_argument("-t", "--threads", type=int, default=10)
        self.parser.add_argument("-c", "--concurrent", type=int, default=5)
        self.parser.add_argument("-w", "--scroll-wait", type=float, default=2.0)
        self.parser.add_argument("-p", "--pause-duration", type=float, default=3.0)
        self.parser.add_argument("-l", "--lang", type=str, choices=['zh', 'en', 'ja'], default=None)
        self.parser.add_argument("--headless", action="store_true", default=True)
        self.parser.add_argument("--no-headless", action="store_false", dest="headless")
        self.parser.add_argument("--browser", type=str, default="edge", choices=['edge', 'chrome'])
        self.parser.add_argument("--simulation", action="store_true", default=False)
        self.args = self.parser.parse_args()
        
        self.eden = Eden(self.args.lang)
        self.blacklistFile = "blacklist.yaml"
        self.configFile = "config.json"
        self.blackList = self.loadBlacklist()
        self.memory = self.loadConfig()
        
        self.batch_mode = False
        self.batch_tasks = []
        
        self.generate_stealth_js() # Initialize dynamic stealth script
        self.detectBatchMode()

        if len(sys.argv) == 1 or self.batch_mode:
            self.interactiveWizard()
        else:
            if not self.args.url:
                self.args.url = asyncio.run(self.sniffLoop())
                if not self.args.url:
                    sys.exit(0)

    def generate_stealth_js(self):
        gpus = [
            # NVIDIA 10 Series
            ("NVIDIA Corporation", "NVIDIA GeForce GTX 1050"), ("NVIDIA Corporation", "NVIDIA GeForce GTX 1050 Ti"),
            ("NVIDIA Corporation", "NVIDIA GeForce GTX 1060 3GB"), ("NVIDIA Corporation", "NVIDIA GeForce GTX 1060 6GB"),
            ("NVIDIA Corporation", "NVIDIA GeForce GTX 1070"), ("NVIDIA Corporation", "NVIDIA GeForce GTX 1070 Ti"),
            ("NVIDIA Corporation", "NVIDIA GeForce GTX 1080"), ("NVIDIA Corporation", "NVIDIA GeForce GTX 1080 Ti"),
            # NVIDIA 20 Series
            ("NVIDIA Corporation", "NVIDIA GeForce RTX 2060"), ("NVIDIA Corporation", "NVIDIA GeForce RTX 2060 SUPER"),
            ("NVIDIA Corporation", "NVIDIA GeForce RTX 2070"), ("NVIDIA Corporation", "NVIDIA GeForce RTX 2070 SUPER"),
            ("NVIDIA Corporation", "NVIDIA GeForce RTX 2080"), ("NVIDIA Corporation", "NVIDIA GeForce RTX 2080 Ti"),
            # NVIDIA 30 Series
            ("NVIDIA Corporation", "NVIDIA GeForce RTX 3050"), ("NVIDIA Corporation", "NVIDIA GeForce RTX 3060"),
            ("NVIDIA Corporation", "NVIDIA GeForce RTX 3060 Ti"), ("NVIDIA Corporation", "NVIDIA GeForce RTX 3070"),
            ("NVIDIA Corporation", "NVIDIA GeForce RTX 3070 Ti"), ("NVIDIA Corporation", "NVIDIA GeForce RTX 3080"),
            ("NVIDIA Corporation", "NVIDIA GeForce RTX 3080 Ti"), ("NVIDIA Corporation", "NVIDIA GeForce RTX 3090"),
            # NVIDIA 40 Series
            ("NVIDIA Corporation", "NVIDIA GeForce RTX 4060"), ("NVIDIA Corporation", "NVIDIA GeForce RTX 4060 Ti"),
            ("NVIDIA Corporation", "NVIDIA GeForce RTX 4070"), ("NVIDIA Corporation", "NVIDIA GeForce RTX 4070 Ti"),
            ("NVIDIA Corporation", "NVIDIA GeForce RTX 4080"), ("NVIDIA Corporation", "NVIDIA GeForce RTX 4090"),
            # NVIDIA Future/High-End
            ("NVIDIA Corporation", "NVIDIA GeForce RTX 5070"), ("NVIDIA Corporation", "NVIDIA GeForce RTX 5080"),
            ("NVIDIA Corporation", "NVIDIA GeForce RTX 5090"), ("NVIDIA Corporation", "NVIDIA TITAN RTX"),
            # AMD
            ("ATI Technologies Inc.", "AMD Radeon RX 580"), ("ATI Technologies Inc.", "AMD Radeon RX 590"),
            ("ATI Technologies Inc.", "AMD Radeon RX 5700 XT"), ("ATI Technologies Inc.", "AMD Radeon RX 6600 XT"),
            ("ATI Technologies Inc.", "AMD Radeon RX 6700 XT"), ("ATI Technologies Inc.", "AMD Radeon RX 6800 XT"),
            ("ATI Technologies Inc.", "AMD Radeon RX 6900 XT"), ("ATI Technologies Inc.", "AMD Radeon RX 7900 XTX"),
            # Intel
            ("Intel Inc.", "Intel(R) Iris(TM) Xe Graphics"), ("Intel Inc.", "Intel(R) UHD Graphics 630"),
            ("Intel Inc.", "Intel(R) Arc(TM) A750 Graphics"), ("Intel Inc.", "Intel(R) Arc(TM) A770 Graphics")
        ]
        
        vendor, renderer = random.choice(gpus)
        console.print(f"[dim]System: Spoofing GPU -> {renderer} ({vendor})[/dim]")
        
        self.stealth_js = f"""
            // 1. Webdriver override
            Object.defineProperty(navigator, 'webdriver', {{ get: () => undefined }});

            // 2. Realistic window.chrome
            window.chrome = {{
                runtime: {{}},
                app: {{ isInstalled: false, InstallState: {{ DISABLED: 'disabled', INSTALLED: 'installed', NOT_INSTALLED: 'not_installed' }}, RunningState: {{ CANNOT_RUN: 'cannot_run', RUNNING: 'running', READY_TO_RUN: 'ready_to_run' }} }},
                csi: () => {{}},
                loadTimes: () => {{}}
            }};

            // 3. Plugins mimic
            Object.defineProperty(navigator, 'plugins', {{ get: () => [1, 2, 3, 4, 5] }});

            // 4. Languages and platform
            Object.defineProperty(navigator, 'languages', {{ get: () => ['zh-CN', 'zh', 'en-US', 'en'] }});
            Object.defineProperty(navigator, 'platform', {{ get: () => 'Win32' }});

            // 5. WebGL Vendor/Renderer mask ({renderer})
            const getParameter = WebGLRenderingContext.prototype.getParameter;
            WebGLRenderingContext.prototype.getParameter = function(parameter) {{
                if (parameter === 37445) return '{vendor}';
                if (parameter === 37446) return '{renderer}';
                return getParameter.apply(this, arguments);
            }};

            // 6. Permissions API
            const originalQuery = window.navigator.permissions.query;
            window.navigator.permissions.query = (parameters) => (
                parameters.name === 'notifications' ?
                Promise.resolve({{ state: Notification.permission }}) :
                originalQuery(parameters)
            );

            // 7. Anti-Anti-Debugging (Bilibili/Official Site Fix)
            try {{
                const _constructor = Function.prototype.constructor;
                Function.prototype.constructor = function(s) {{
                    if (s && typeof s === 'string' && s.includes('debugger')) return function(){{}};
                    return _constructor.apply(this, arguments);
                }};
                
                const _setInterval = window.setInterval;
                window.setInterval = function(func, delay) {{
                    if (func && func.toString().includes('debugger')) return -1;
                    return _setInterval.apply(this, arguments);
                }};
            }} catch (e) {{}}

            // 8. Native Code Masquerade (Bypass "toString" detection)
            const nativeToString = Function.prototype.toString;
            const hookedFunctions = new WeakSet();
            
            // Helper to mark function as "native"
            const makeNative = (func, original) => {{
                hookedFunctions.add(func);
                try {{
                    Object.defineProperty(func, 'name', {{ value: original.name }});
                    Object.defineProperty(func, 'length', {{ value: original.length }});
                }} catch(e) {{}}
                return func;
            }};

            Function.prototype.toString = function() {{
                if (hookedFunctions.has(this)) {{
                    return "function " + this.name + "() {{ [native code] }}";
                }}
                return nativeToString.apply(this, arguments);
            }};
            
            // Apply to overrides
            window.navigator.permissions.query = makeNative(window.navigator.permissions.query, originalQuery);
            WebGLRenderingContext.prototype.getParameter = makeNative(WebGLRenderingContext.prototype.getParameter, getParameter);
        """

    def detectBatchMode(self):
        if self.args.url and os.path.isfile(self.args.url) and self.args.url.endswith('.txt'):
            self.batch_mode = True
            try:
                valid_tasks = []
                with open(self.args.url, 'r', encoding='utf-8') as f:
                    lines = f.readlines()
                
                auto_pick_all = False

                for idx, line in enumerate(lines):
                    line = line.strip()
                    if not line: continue
                    
                    # Split into URL and the Rest (maxsplit=1 handles variable spacing)
                    parts = line.split(maxsplit=1)
                    
                    u = parts[0]
                    if not u.startswith('http'): continue
                    
                    n = None
                    if len(parts) == 2:
                        raw_name = parts[1].strip()
                        
                        # Support both standard (") and smart/Chinese (“, ”) quotes
                        has_standard_quotes = raw_name.startswith('"') and raw_name.endswith('"')
                        has_smart_quotes = raw_name.startswith('“') and raw_name.endswith('”')
                        
                        # Case 1: Quoted Name (Explicitly Supported)
                        if (has_standard_quotes or has_smart_quotes) and len(raw_name) > 1:
                            n = raw_name[1:-1]
                        
                        # Case 2: Ambiguous Name (Contains spaces, no quotes)
                        elif ' ' in raw_name:
                            if auto_pick_all:
                                n = raw_name
                            else:
                                console.print(f"\n[yellow]Warning:[/yellow] 结构歧义检测 (第 {idx+1} 行)")
                                console.print(f"原始内容: [cyan]{line}[/cyan]")
                                console.print(f"检测到名称包含空格。请选择处理方式:")
                                
                                sub_parts = raw_name.split()
                                opt_a = raw_name
                                opt_b = sub_parts[0]
                                opt_c = sub_parts[1] if len(sub_parts) > 1 else "N/A"
                                
                                console.print(f"  a: 全部使用 -> [green]{opt_a}[/green]")
                                console.print(f"  b: 仅使用第一段 -> [green]{opt_b}[/green]")
                                console.print(f"  c: 仅使用第二段 -> [green]{opt_c}[/green]")
                                console.print(f"  d: 手动输入名称")
                                console.print(f"  e: [bold]以后全部默认选 a[/bold] (不再询问)")
                                
                                choice = console.input("请选择 [a/b/c/d/e] (默认 a): ").strip().lower()
                                
                                if choice == 'b':
                                    n = opt_b
                                elif choice == 'c':
                                    n = opt_c if opt_c != "N/A" else opt_b
                                elif choice == 'd':
                                    n = console.input("请输入正确名称: ").strip()
                                elif choice == 'e':
                                    n = raw_name
                                    auto_pick_all = True
                                    console.print("[green]已启用自动批处理: 后续将默认使用完整名称。[/green]")
                                else:
                                    n = raw_name
                                
                                console.print("[dim i]Tip: 建议将包含空格的名称添加双引号 (如: http://... \"Name A\") 以自动识别，并忽略中间空格。[/dim i]")
                        
                        # Case 3: Simple Name (No spaces)
                        else:
                            n = raw_name
                    
                    valid_tasks.append({'url': u, 'name': n})
                
                self.batch_tasks = valid_tasks
                console.print(f"[green]Config: Batch Mode Detected. Loaded {len(self.batch_tasks)} tasks.[/green]")
            except Exception as e:
                console.print(f"[red]Batch Load Error: {e}[/red]")
                sys.exit(1)

    def loadConfig(self):
        if os.path.exists(self.configFile):
            try:
                with open(self.configFile, 'r', encoding='utf-8') as f:
                    return json.load(f)
            except:
                pass
        return {}

    def saveConfig(self, settings):
        try:
            with open(self.configFile, 'w', encoding='utf-8') as f:
                json.dump(settings, f, indent=4, ensure_ascii=False)
        except:
            pass

    def loadBlacklist(self):
        s = set()
        s.add("cff929163059bb9289870e308156c81a")
        if os.path.exists(self.blacklistFile):
            try:
                with open(self.blacklistFile, 'r', encoding='utf-8') as f:
                    for line in f:
                        line = line.strip()
                        if line.startswith("-"):
                            val = line.lstrip("-").strip().strip('"').strip("'")
                            if val: s.add(val)
            except:
                pass
        return s

    def addToBlacklist(self, hashVal):
        if hashVal in self.blackList: return
        try:
            file_exists = os.path.exists(self.blacklistFile)
            has_content = file_exists and os.path.getsize(self.blacklistFile) > 0
            with open(self.blacklistFile, 'a', encoding='utf-8') as f:
                if not has_content: f.write("blacklist:\n")
                f.write(f'  - "{hashVal}"\n')
            self.blackList.add(hashVal)
            self.eden.say("hash_added", hashVal)
        except:
            pass

    async def sniffLoop(self):
        if not self.memory.get("auto_sniff", True):
            return self.eden.ask("input_url").strip()

        console.print(self.eden.scripts["input_url"][self.eden.lang], end="")
        last_clip = pyperclip.paste().strip()
        import msvcrt
        typed = ""
        while True:
            if msvcrt.kbhit():
                char = msvcrt.getwche()
                if char in ['\r', '\n']:
                    res = typed.strip()
                    if res:
                        print("") # Force newline after manual entry
                        return res
                    print("\n" + self.eden.scripts["input_url"][self.eden.lang], end="", flush=True)
                    typed = ""
                    continue
                elif char == '\b':
                    if typed:
                        typed = typed[:-1]
                        print("\b \b", end="")
                    continue
                typed += char
            try:
                curr = pyperclip.paste().strip()
                if curr.startswith("http") and curr != last_clip:
                    print("\n")
                    display = curr[:30] + "..." if len(curr) > 30 else curr
                    q = self.eden.ask("clipboard_found", display).strip().lower()
                    if q == 'y':
                        return curr
                    last_clip = curr
                    print(self.eden.scripts["input_url"][self.eden.lang] + typed, end="")
            except:
                pass
            await asyncio.sleep(0.1)

    async def cookieWizard(self, url):
        console.print("[yellow]System: Launching Cookie Login Wizard...[/yellow]")
        console.print("[yellow]Action: Please login in the opened browser window. Ensure you can read the comic.[/yellow]")
        
        async with async_playwright() as p:
            # Enhanced Stealth for Login Wizard
            try:
                ch = "msedge" if (self.args.browser == "edge" or not self.args.browser) else "chrome"
                browser = await p.chromium.launch(
                    headless=False, 
                    channel=ch,
                    args=["--disable-blink-features=AutomationControlled", "--no-sandbox", "--disable-infobars"],
                    ignore_default_args=["--enable-automation"]
                )
            except Exception as e:
                console.print(f"[yellow]Warning: Failed to launch {ch} ({e}). Falling back to bundled Chromium...[/yellow]")
                browser = await p.chromium.launch(
                    headless=False,
                    args=["--disable-blink-features=AutomationControlled", "--no-sandbox", "--disable-infobars"],
                    ignore_default_args=["--enable-automation"]
                )
            
            context = await browser.new_context()
            page = await context.new_page()
            
            try:
                await page.goto(url, timeout=60000)
            except:
                console.print("[red]Warning: Initial navigation failed. Please navigate manually.[/red]")
            
            # Loop for verification
            while True:
                console.input("\n[bold green]Input: 登录并确认能正常阅读后，请在此按回车键 (Press Enter to capture cookies)...[/bold green]")
                
                # Optional: Check simple connectivity or content?
                # For now, trust the user.
                
                cookies = await context.cookies()
                if cookies:
                    with open("cookies.json", "w") as f:
                        json.dump(cookies, f, indent=2)
                    self.eden.say("cookie_success")
                    break
                else:
                    retry = console.input("[red]Error: No cookies found. Retry? [Y/n]: [/red]").strip().lower()
                    if retry == 'n': break
            
            await browser.close()

    def interactiveWizard(self):
        defaults = {"output": "manga_downloads", "threads": 10, "concurrent": 5, "headless": True, "scroll_wait": 2.0, "pause_duration": 3.0, "browser": "edge", "auto_sniff": True, "lang": None, "auto_downgrade": True, "block_ads": False}
        if self.memory:
            defaults.update(self.memory)

        if defaults["lang"]:
            self.eden.lang = defaults["lang"]
        else:
            try:
                sys_lang = locale.getlocale()[0]
                sys_lang = sys_lang[:2] if sys_lang else 'en'
            except:
                sys_lang = 'en'
            if sys_lang not in ['zh', 'en', 'ja']:
                sys_lang = 'en'
            print(f"Select Language / 选择语言 [zh/en/ja] (Default: {sys_lang}): ", end="")
            lang_choice = input().strip().lower()
            self.eden.lang = lang_choice if lang_choice in ['zh', 'en', 'ja'] else sys_lang
            
        self.eden.printSeparator()
        self.eden.say("welcome")
        print("")
        self.eden.printSeparator()
        
        if self.memory:
            self.eden.say("config_loaded")
        
        if not self.batch_mode:
            if not self.args.url:
                self.args.url = asyncio.run(self.sniffLoop())

            while not self.args.url:
                self.args.url = self.eden.ask("input_url").strip()
            
            name_input = self.eden.ask("ask_name").strip()
            if name_input:
                self.args.name = self.eden.sanitize(name_input)
        else:
             # In batch mode, we skip URL/Name input but ensure args.url is valid for subsequent checks (though Griseo uses batch_tasks)
             pass

        self.eden.printSubSeparator()
        mode_choice = self.eden.ask("ask_mode").strip()
        if mode_choice == '2':
            self.args.simulation = True
            defaults["concurrent"] = 1
            self.eden.say("mode_human_activated")
        
        
        # --- OFFICIAL SITE CHECK (Early Detection) ---
        target_urls = [self.args.url]
        if self.batch_mode and self.batch_tasks:
            target_urls = [t['url'] for t in self.batch_tasks]
        
        official_kws = [
            'bilibili', 'qq.com', 'kuaikan', '163.com', 'ac.qq', 'banga', # CN
            'bookwalker', 'cmoa', 'ebj', 'ganma', 'piccoma', 'comico',    # JP
            'ridibooks', 'naver', 'kakao', 'webtoons', 'lezhin', 'tappy'  # KR/Global
        ]
        is_official = any(any(k in u for k in official_kws) for u in target_urls)

        if is_official:
            console.print("\n[bold yellow]System: 检测到正版/会员制漫画站点 (如 Bilibili/BookWalker)。[/bold yellow]")
            console.print("[dim]Tip: 必须配置 Cookie 以获取完整内容，且强烈建议关闭后台模式。[/dim]")
            
            # Enforce defaults for official sites
            defaults["cookie_enable"] = True
            defaults["headless"] = False
            defaults["concurrent"] = 1
            defaults["threads"] = 4
            
            # Skip "Use Default" prompt to force configuration review
            use_default = 'n'
        else:
            self.eden.printSubSeparator()
            self.eden.say("default_mode_info", defaults["output"], defaults["threads"], defaults["concurrent"], "Yes" if defaults["headless"] else "No", defaults["scroll_wait"], defaults["pause_duration"])
            use_default = self.eden.ask("ask_use_default").strip().lower()

        if use_default in ['', 'y']:
            self.args.output = defaults["output"]
            self.args.threads = defaults["threads"]
            self.args.concurrent = defaults["concurrent"]
            self.args.headless = defaults["headless"]
            self.args.scroll_wait = defaults["scroll_wait"]
            self.args.pause_duration = defaults["pause_duration"]
            self.args.browser = defaults["browser"]
            self.args.block_ads = defaults.get("block_ads", False)
            self.args.cookie_enable = defaults.get("cookie_enable", False)
        else:
            out = self.eden.ask("ask_output", defaults["output"]).strip()
            if out: self.args.output = out
            t = self.eden.ask("ask_threads", defaults["threads"]).strip()
            if t.isdigit(): self.args.threads = int(t)
            
            # Concurrent Logic
            if is_official:
                console.print(f"Input: 设置并发章节数 (正版限制: 默认 1): ", end="")
                c = input().strip()
                self.args.concurrent = int(c) if c.isdigit() else 1
            elif not getattr(self.args, 'simulation', False):
                c = self.eden.ask("ask_concurrent", defaults["concurrent"]).strip()
                if c.isdigit(): self.args.concurrent = int(c)
            else:
                self.args.concurrent = 1
            
            w = self.eden.ask("ask_scroll_wait", defaults["scroll_wait"]).strip()
            try: self.args.scroll_wait = float(w)
            except: pass
            p_input = self.eden.ask("ask_pause_duration", defaults["pause_duration"]).strip()
            self.args.pause_duration = float(p_input) if p_input else defaults["pause_duration"]
            
            # Block Ads
            ba = self.eden.ask("ask_block_ads", "Y" if defaults.get("block_ads") else "n").strip().lower()
            self.args.block_ads = ba == 'y'
            
            # Headless Logic
            h_def = "n" if is_official else ("Y" if defaults["headless"] else "n")
            h = self.eden.ask("ask_headless", h_def).strip().lower()
            if h:
                self.args.headless = h == 'y'
            else:
                self.args.headless = h_def.lower() == 'y'
            
            b = self.eden.ask("ask_browser").strip()
            if b == '2': self.args.browser = "chrome"
            else: self.args.browser = "edge"
            
            # Cookie Injection (Manual Setup)
            if is_official:
                ce = console.input("Input: 是否启用 Cookie 注入? [Y/n] (默认: Y): ").strip().lower()
                self.args.cookie_enable = ce != 'n'
            else:
                ce = self.eden.ask("ask_cookie_enable").strip().lower()
                self.args.cookie_enable = ce == 'y'
        
        # --- COOKIE WIZARD TRIGGER ---
        if self.args.cookie_enable:
            has_cookie = os.path.exists("cookies.json")
            need_update = False
            
            if not has_cookie:
                if is_official:
                    console.print("[red]Error: 未检测到 cookies.json。正版站点无法在无凭证情况下爬取。[/red]")
                    cw = console.input("Input: 是否立即启动 [登录向导] 以捕获 Cookie? [Y/n] (默认: Y): ").strip().lower()
                    if cw != 'n': need_update = True
                else:
                    cw = self.eden.ask("ask_cookie_wizard").strip().lower()
                    if cw in ['', 'y']: need_update = True
            elif not use_default: # Only ask to update if not using default config
                if console.input(f"Input: 检测到现有 Cookies。是否更新? [y/N]: ").strip().lower() == 'y':
                    need_update = True

            if need_update:
                target = self.args.url
                if self.batch_mode and self.batch_tasks:
                    target = self.batch_tasks[0]['url']
                elif self.batch_mode:
                    target = "https://www.bilibili.com"
                
                asyncio.run(self.cookieWizard(target))

        self.args.auto_merge = False
        self.args.merge_format = "epub"
        self.eden.printSubSeparator()
        q_auto = self.eden.ask("ask_auto_merge_trigger").strip().lower()
        if q_auto == 'y':
            self.args.auto_merge = True
            format_map = {
                "1": "epub", "2": "pdf", "3": "cbz", "4": "mobi", "5": "azw3",
                "6": "docx", "7": "txt", "8": "kepub", "9": "fb2", "10": "lit",
                "11": "lrf", "12": "pdb", "13": "pmlz", "14": "rb", "15": "rtf",
                "16": "tcr", "17": "txtz", "18": "htmlz", "19": "all"
            }
            f_choice = self.eden.ask("ask_merge_format_menu").strip()
            self.args.merge_format = format_map.get(f_choice, "epub")
        else:
            self.args.auto_merge = False
            
        new_config = {"output": self.args.output, "threads": self.args.threads, "concurrent": self.args.concurrent, "headless": self.args.headless, "scroll_wait": self.args.scroll_wait, "pause_duration": self.args.pause_duration, "browser": self.args.browser, "auto_sniff": defaults.get("auto_sniff", True), "lang": self.eden.lang, "auto_merge": self.args.auto_merge, "merge_format": self.args.merge_format, "auto_downgrade": defaults.get("auto_downgrade", True), "block_ads": getattr(self.args, 'block_ads', False)}
        self.saveConfig(new_config); self.eden.printSeparator()

elysia = Elysia()

class Mobius:
    def __init__(self):
        self.session = requests.Session()
        self.session.headers.update({"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36 Edg/120.0.0.0", "Accept": "image/avif,image/webp,image/apng,image/svg+xml,image/*,*/*;q=0.8"})
        self.anomalies = []

    def checkInfinity(self, p):
        k = hashlib.md5()
        with open(p, "rb") as f:
            for c in iter(lambda: f.read(4096), b""): k.update(c)
        return k.hexdigest()

    def experiment(self, u, p, r):
        if os.path.exists(p): return
        self.session.headers.update({"Referer": r})
        t_p = p + ".tmp"
        success = False
        max_retries = 10
        for attempt in range(max_retries):
            try:
                res = self.session.get(u, timeout=20)
                if res.status_code == 200:
                    with open(t_p, 'wb') as f: f.write(res.content)
                    if os.path.exists(p): os.remove(p)
                    os.rename(t_p, p)
                    success = True
                    return
                elif res.status_code == 404:
                    break
            except:
                pass
            time.sleep(min(math.pow(2, attempt), 30))
        if not success:
            if os.path.exists(t_p): os.remove(t_p)
            self.anomalies.append({'url': u, 'path': p, 'referer': r})

    def execute(self, targets, folder, referer, chapterTitle="Unknown", progress_callback=None):
        if not targets: return
        with ThreadPoolExecutor(max_workers=elysia.args.threads) as lab:
            futures = []
            for idx, src in enumerate(targets):
                if isinstance(src, dict):
                    ext = src.get('ext', '.jpg')
                    dest = os.path.join(folder, f"raw_{str(idx).zfill(5)}{ext}")
                    with open(dest, 'wb') as f: f.write(src['data'])
                else:
                    ext = os.path.splitext(urlparse(src).path)[1] or ".jpg"
                    futures.append(lab.submit(self.experiment, src, os.path.join(folder, f"raw_{str(idx).zfill(5)}{ext}"), referer))
            for f in futures:
                f.result()
            if progress_callback: progress_callback()

    def reconstruct(self):
        if not self.anomalies: return 0
        targets = self.anomalies [:]
        self.anomalies.clear()
        with Progress(SpinnerColumn(), TextColumn("[progress.description]{task.description}"), BarColumn(), TextColumn("[progress.percentage]{task.percentage:>3.0f}%"), TimeRemainingColumn(), console=console) as progress:
            tid = progress.add_task("[red]Reconstructing...", total=len(targets))
            with ThreadPoolExecutor(max_workers=elysia.args.threads) as lab:
                for f in [lab.submit(self.experiment, i['url'], i['path'], i['referer']) for i in targets]:
                    f.result()
                    progress.advance(tid)
        recovered = len(targets) - len(self.anomalies)
        return recovered

    def purify(self, folder):
        raws = sorted([os.path.join(folder, f) for f in os.listdir(folder) if f.startswith("raw_")])
        valids = []
        igns = set()
        ip = os.path.join(folder, "ignore.json")
        if os.path.exists(ip):
            try:
                with open(ip, 'r', encoding='utf-8') as f:
                    igns.update(json.load(f).get("ignored", []))
            except:
                pass
        for f in raws:
            try:
                if self.checkInfinity(f) in elysia.blackList:
                    try:
                        igns.add(int(os.path.basename(f).split('_')[1].split('.')[0]))
                    except:
                        pass
                    os.remove(f)
                    console.print(f"[yellow]Block:[/yellow] Removed blacklisted file: {os.path.basename(f)}")
                else:
                    valids.append(f)
            except:
                pass
        if igns:
            try:
                with open(ip, 'w', encoding='utf-8') as f:
                    json.dump({"ignored": list(igns)}, f)
            except:
                pass
        for idx, f in enumerate(valids):
            np = os.path.join(folder, f"{str(idx+1).zfill(3)}{os.path.splitext(f)[1]}")
            if os.path.exists(np): os.remove(np)
            os.rename(f, np)

    def repairRealm(self):
        root = os.path.join(elysia.args.output, elysia.args.name) if elysia.args.name else elysia.args.output
        if not os.path.exists(root): return
        for r, _, fs in os.walk(root):
            if "urls.json" in fs:
                try:
                    with open(os.path.join(r, "urls.json"), "r", encoding="utf-8") as f:
                        urls = json.load(f)
                    igns = set()
                    ip = os.path.join(r, "ignore.json")
                    if os.path.exists(ip):
                        with open(ip, 'r', encoding='utf-8') as f:
                            igns.update(json.load(f).get("ignored", []))
                    miss = []
                    exp = 1
                    for idx, u in enumerate(urls):
                        if idx in igns: continue
                        if not any(os.path.exists(os.path.join(r, f"{str(exp).zfill(3)}{ex}")) for ex in ['.jpg', '.jpeg', '.png', '.webp']):
                            miss.append(u)
                        exp += 1
                    if miss: self.execute(miss, r, elysia.args.url, "Repair")
                except:
                    pass
        hashes = {}
        counts = Counter()
        files = [os.path.join(r, f) for r, _, fs in os.walk(root) for f in fs if f.lower().endswith(('.jpg', '.jpeg', '.png', '.webp'))]
        with ThreadPoolExecutor(max_workers=elysia.args.threads * 2) as lab:
            res = list(lab.map(lambda p: (self.checkInfinity(p), p) if os.path.exists(p) else None, files))
        for r in filter(None, res):
            h, p = r
            counts[h] += 1
            if h not in hashes: hashes[h] = p
        dups = {h: c for h, c in counts.items() if c > 1}
        if dups:
            for h in dups:
                if h not in elysia.blackList:
                    if elysia.eden.ask("ask_add_blacklist", h).strip().lower() == 'y':
                        uh = elysia.eden.ask("ask_hash_input").strip()
                        elysia.addToBlacklist(uh if uh else h)
        blist = [p for p in files if os.path.exists(p) and self.checkInfinity(p) in elysia.blackList]
        if blist and elysia.eden.ask("ask_cleanup_blacklist", len(blist)).strip().lower() == 'y':
            for f in blist:
                try: os.remove(f)
                except: pass

mobius = Mobius()

class Pardofelis:
    def __init__(self):
        self.nextSign = ["text=下一页", "text=Next", "text=次へ", "a[rel='next']", ".next", ".next-page", "text=下一章", "button.next", "text=下一頁"]

    async def sniff(self, page, url, seen):
        treasures = await page.evaluate("""() => {
            let winW = window.innerWidth;
            return Array.from(document.querySelectorAll('img'))
                .filter(i => {
                    let rect = i.getBoundingClientRect();
                    let centerX = rect.left + rect.width / 2;
                    let ratio = i.naturalHeight / i.naturalWidth;
                    // Relaxed constraints for Webtoons (Long Strip) support
                    // Removed ratio upper limit to allow very tall images
                    return i.naturalWidth > 150 && (ratio > 0.2) && Math.abs(centerX - winW / 2) < winW * 0.45;
                })
                .map(i => i.src);
        }""")
        res = []
        for src in treasures:
            if src and not src.startswith("data:"):
                full = urljoin(url, src); l = full.lower()
                if not any(x in l for x in ['avatar', 'ad', 'logo', 'icon', 'comment', 'recommend', 'user']):
                    if full not in seen: seen.add(full); res.append(full)
        return res

    async def scavenge(self, ctx, url, scramble_protection=False):
        can = await ctx.new_page()
        await can.add_init_script(elysia.stealth_js)
        
        # Optional: Load external Inspector.js
        if os.path.exists("inspector.js"):
            try:
                with open("inspector.js", "r", encoding="utf-8") as f:
                    await can.add_init_script(f.read())
            except: pass
            
        ph = Phantom(can)
        all_res = []
        seen_urls = set()
        blobs = {}
        
        if scramble_protection:
            console.print("[yellow]System: Scramble Protection Active. Ignoring raw network resources.[/yellow]")

        async def handle(res):
            try:
                ct = res.headers.get("content-type", "").lower()
                # Relaxed filters: Allow png, gif, octet-stream
                if res.status == 200 and any(t in ct for t in ["image/", "application/octet-stream"]):
                    try:
                        cl = int(res.headers.get("content-length", 0))
                    except:
                        cl = 20000 # Assume valid if no length
                    
                    # Lower threshold to 10KB to catch optimized/small images
                    if cl > 10240:
                        u = res.url; ul = u.lower()
                        if not any(x in ul for x in ['avatar', 'ad', 'logo', 'icon', 'loading', 'user', 'comment', 'recommend', 'banner', 'sidebar', 'head', 'favicon']):
                            blobs[u] = await res.body()
            except: pass
        can.on("response", handle)
        try:
            await can.goto(url, timeout=120000, wait_until='domcontentloaded')
            await asyncio.sleep(3)
            
            # --- CAPTCHA / SECURITY CHECK SUSPENSION ---
            try:
                page_title = await can.title()
                page_text = await can.evaluate("document.body.innerText.substring(0, 1000)")
                
                chk_kws = ["Just a moment", "Verify you are human", "Cloudflare", "Attention Required", "Security Check", "人机验证", "安全检测", "请完成验证", "验证码", "CAPTCHA", "Access denied", "403 Forbidden"]
                
                hit = any(k.lower() in page_title.lower() for k in chk_kws) or \
                      any(k.lower() in page_text.lower() for k in chk_kws)
                
                if hit:
                    elysia.eden.notify("⚠️ CAPTCHA Detected", "Script paused. Please solve verification.")
                    elysia.eden.singFinale()
                    
                    console.print(f"\n[bold red]System: CAPTCHA/Security Check detected![/bold red]")
                    console.print(f"[dim]URL: {url}[/dim]")
                    
                    if elysia.args.headless:
                        console.print("[red bold]CRITICAL: Running in Headless Mode![/red bold]")
                        console.print("[red]You cannot see the browser to solve this. Please restart with Headless=No.[/red]")
                        console.print("[dim](Pressing Enter will try to continue anyway...)[/dim]")
                    else:
                        console.print("[yellow]Action: Script PAUSED. Please solve the verification in the opened browser window.[/yellow]")
                    
                    # Non-blocking input wait
                    await asyncio.to_thread(console.input, "\n[bold green]Input: 完成验证后，请在此按回车键继续 (Press Enter after solving)...[/bold green]")
                    
                    console.print("[green]System: Resuming operations...[/green]")
                    await asyncio.sleep(3)
            except: pass

            # --- ERROR BUTTON INTERVENTION ---
            # 探测是否存在“重新加载”之类的按钮，若存在则尝试修复
            retry_kws = ["重新加载", "重试", "刷新", "Reload", "Retry", "Refresh", "点我"]
            for _ in range(2): # 尝试修复两次
                clicked_retry = await can.evaluate(f"""(kws) => {{
                    const el = Array.from(document.querySelectorAll('button, a, div, span')).find(e => {{
                        const t = e.innerText || "";
                        return kws.some(kw => t.includes(kw)) && e.offsetParent !== null;
                    }});
                    if (el) {{ el.click(); return true; }}
                    return false;
                }}""", retry_kws)
                if clicked_retry: await asyncio.sleep(5)
                else: break

            # --- PRE-SCROLL TO TRIGGER LAZY LOAD ---
            await can.evaluate("window.scrollBy(0, 800)")
            await asyncio.sleep(1.0)

            tp = 1; cp = 1; pm = False
            
            env = await can.evaluate("""() => {
                let large_imgs = Array.from(document.querySelectorAll('img')).filter(i => i.naturalWidth > 400);
                return {
                    sh: document.body.scrollHeight,
                    lic: large_imgs.length,
                    tc: document.body.innerText
                };
            }""")
            
            # Smart Mode Detection: DISABLED (Always Scroll)
            # We still parse cp/tp for logging/future use, but force pm=False
            m = re.search(r'(\d+)\s*/\s*(\d+)', env['tc'])
            if m:
                cp = int(m.group(1)); tp = int(m.group(2))
            
            probe_js = """() => {
                let winW = window.innerWidth;
                let imgs = Array.from(document.querySelectorAll('img')).filter(i => {
                    let rect = i.getBoundingClientRect();
                    let centerX = rect.left + rect.width / 2;
                    let isCentered = Math.abs(centerX - winW / 2) < winW * 0.45;
                    let ratio = i.naturalHeight / i.naturalWidth;
                    return i.naturalWidth > 150 && 
                           (ratio > 0.2) && 
                           isCentered &&
                           i.complete &&
                           rect.width > 0 && rect.height > 0;
                });
                imgs.sort((a, b) => (b.naturalWidth * b.naturalHeight) - (a.naturalWidth * a.naturalHeight));
                if (imgs.length === 0) return null;
                let mi = imgs[0]; let rect = mi.getBoundingClientRect();
                return { y: rect.bottom, src: mi.src };
            }"""
            
            main_info = await can.evaluate(probe_js)
            if not pm and main_info:
                for s in self.nextSign:
                    btn = await can.query_selector(s)
                    if btn:
                        b_rect = await btn.bounding_box()
                        if b_rect and b_rect['y'] > main_info['y'] - 300 and b_rect['y'] < main_info['y'] + 1000:
                            if env['lic'] <= 2: pm = True; break
            
            bottom_hit_count = 0

            while True:
                if pm:
                    current_main = None
                    for _ in range(40):
                        current_main = await can.evaluate(probe_js)
                        if current_main and current_main['src'] not in seen_urls:
                            src = current_main['src']
                            if src in blobs:
                                all_res.append({'data': blobs[src], 'ext': '.jpg'})
                                seen_urls.add(src); break
                        await asyncio.sleep(0.5)
                    
                    if cp >= tp: break
                    found_btn = False
                    for s in self.nextSign:
                        btn = await can.query_selector(s)
                        if btn and await btn.is_visible():
                            elysia.eden.say("next_page", cp + 1, tp)
                            await ph.humanClick(btn)
                            await asyncio.sleep(elysia.args.scroll_wait + 1)
                            cp += 1; found_btn = True; break
                    if not found_btn: break
                else:
                    # Slower, more reliable scrolling
                    await can.evaluate(f"window.scrollBy({{top: window.innerHeight * {random.uniform(0.4, 0.7)}, behavior: 'smooth'}})")
                    await asyncio.sleep(elysia.args.scroll_wait)
                    batch = await self.sniff(can, url, seen_urls)
                    all_res.extend(batch)
                    
                    ch = await can.evaluate("window.pageYOffset + window.innerHeight")
                    th = await can.evaluate("document.body.scrollHeight")
                    
                    if ch >= th - 50:
                        # Reached bottom? Try to "Shake" to trigger lazy load
                        await asyncio.sleep(2.0)
                        
                        # Scroll UP to trigger intersection observers from bottom-up
                        await can.evaluate("window.scrollBy(0, -600)")
                        await asyncio.sleep(1.0)
                        
                        # Scroll DOWN in steps to re-trigger
                        await can.evaluate("window.scrollBy(0, 300)")
                        await asyncio.sleep(0.5)
                        await can.evaluate("window.scrollTo(0, document.body.scrollHeight)")
                        await asyncio.sleep(2.0)
                        
                        final_th = await can.evaluate("document.body.scrollHeight")
                        if final_th <= th:
                            bottom_hit_count += 1
                            
                            # Adaptive Retry: Increase wait time if we keep hitting bottom (helps with network congestion)
                            wait_times = {1: 2.0, 2: 5.0, 3: 8.0}
                            wait_t = wait_times.get(bottom_hit_count, 3.0)

                            if bottom_hit_count < 3:
                                await asyncio.sleep(wait_t) # Adaptive wait
                                continue
                            
                            # Reached absolute bottom 3 times. Check for "Next Page" button
                            found_next = False
                            for s in self.nextSign:
                                # Skip "Next Chapter" buttons
                                if "下一章" in s or "Next Chapter" in s: continue
                                
                                try:
                                    btn = await can.query_selector(s)
                                    if btn and await btn.is_visible():
                                        txt = await btn.inner_text()
                                        if "章" in txt or "Chapter" in txt: continue

                                        await ph.humanClick(btn)
                                        await asyncio.sleep(elysia.args.scroll_wait + 2)
                                        found_next = True
                                        bottom_hit_count = 0 # Reset on success
                                        break
                                except: pass
                            
                            if found_next:
                                continue

                            break
                        else:
                            bottom_hit_count = 0 # Content expanded, reset
            
            # --- DESPERATE FALLBACK & PROTECTION ---
            
            # If Scramble Protection is ON, discard raw network images (they are likely shredded/encrypted)
            if scramble_protection and all_res:
                console.print(f"[yellow]System: Discarded {len(all_res)} raw images (Scramble Protection). forcing memory extraction...[/yellow]")
                all_res.clear()

            if not all_res:
                if not scramble_protection:
                    # 1. DOM Fallback (Only if not protected, as DOM likely has shredded img tags too)
                    console.print("[yellow]System: Main scan failed. Attempting desperate fallback...[/yellow]")
                    fallback = await can.evaluate("""() => {
                        return Array.from(document.querySelectorAll('img'))
                            .filter(i => i.naturalWidth > 150)
                            .map(i => i.src);
                    }""")
                    for src in fallback:
                        if src and not src.startswith("data:"):
                            full = urljoin(url, src)
                            if full not in seen_urls:
                                seen_urls.add(full)
                                all_res.append(full)
                    
                    # 2. Blob Rescue (Only if not protected)
                    if not all_res and blobs:
                        console.print(f"[yellow]Blob Rescue: Checking {len(blobs)} captured resources...[/yellow]")
                        sorted_blobs = sorted(blobs.items(), key=lambda x: len(x[1]), reverse=True)
                        for u, data in sorted_blobs:
                            if len(data) > 20000:
                                ext = os.path.splitext(urlparse(u).path)[1] or ".jpg"
                                all_res.append({'data': data, 'ext': ext})
                        if all_res:
                            console.print(f"[green]Blob Rescue: Recovered {len(all_res)} images from network traffic.[/green]")

            # 3. Canvas Rescue (Memory Extraction) - Runs if empty OR Protected
            if not all_res:
                console.print("[yellow]System: Engaging Memory Extraction (Canvas)...[/yellow]")
                canvas_data = await can.evaluate("""() => {
                    return Array.from(document.querySelectorAll('canvas'))
                        .filter(c => c.width > 200 && c.height > 200)
                        .map(c => {
                            try { return c.toDataURL('image/png'); }
                            catch(e) { return null; }
                        })
                        .filter(d => d !== null);
                }""")
                
                canvas_count = 0
                for data_url in canvas_data:
                    try:
                        header, encoded = data_url.split(",", 1)
                        data = base64.b64decode(encoded)
                        all_res.append({'data': data, 'ext': '.png'})
                        canvas_count += 1
                    except: pass
                
                if canvas_count > 0:
                    console.print(f"[green]Memory Extraction: Recovered {canvas_count} images from Rendered Canvas.[/green]")

            # 4. Visual Protocol (Screenshots) - Final Resort
            if not all_res:
                console.print("[red]All methods failed. Engaging Visual Protocol (Screenshots)...[/red]")
                try:
                    await can.evaluate("window.scrollTo(0, 0)")
                    await asyncio.sleep(2.0)
                    
                    total_height = await can.evaluate("document.body.scrollHeight")
                    viewport_height = await can.evaluate("window.innerHeight")
                    current_y = 0
                    shot_count = 0
                    
                    while current_y < total_height:
                        # Take screenshot of viewport
                        shot = await can.screenshot(type='jpeg', quality=80)
                        all_res.append({'data': shot, 'ext': '.jpg'})
                        shot_count += 1
                        
                        current_y += viewport_height
                        if current_y < total_height:
                            await can.evaluate(f"window.scrollTo(0, {{current_y}})")
                            await asyncio.sleep(1.5) # Wait for render
                    
                    console.print(f"[green]Visual Protocol: Captured {shot_count} viewport snapshots.[/green]")
                except Exception as e:
                    console.print(f"[red]Visual Protocol Failed: {{e}}[/red]")

            if all_res:
                console.print(f"[yellow]Fallback: Found {{len(all_res)}} images via relaxed criteria.[/yellow]")

            return all_res
        except Exception:
            return all_res
        finally:
            try: await can.close()
            except: pass

pardofelis = Pardofelis()

class Griseo:
    def __init__(self):
        self.bronya = None
        self.use_stealth = True
        self.ip_limit_hit = False
        self.downgraded = False
        self.history = []
        self.lock = asyncio.Lock()

    def parseRangeStr(self, rs, ts):
        inds = set()
        for p in rs.strip().split():
            try:
                if '-' in p:
                    s, e = map(int, p.split('-'))
                    for i in range(s - 1, e):
                        if 0 <= i < len(ts): inds.add(i)
                else:
                    i = int(p) - 1
                    if 0 <= i < len(ts): inds.add(i)
            except: pass
        return inds

    async def paint(self, sem, b, ch, total, idx, progress=None, tid=None):
        if not hasattr(self, 'serial_lock'): self.serial_lock = asyncio.Semaphore(1)
        
        if self.downgraded:
            await self.serial_lock.acquire()
            try:
                await asyncio.sleep(random.uniform(elysia.args.pause_duration, elysia.args.pause_duration + 2))
                return await self._paintCore(sem, b, ch, total, idx, progress, tid)
            finally:
                self.serial_lock.release()
        
        return await self._paintCore(sem, b, ch, total, idx, progress, tid)

    async def _paintCore(self, sem, b, ch, total, idx, progress, tid):
        async with sem:
            if self.downgraded and self.serial_lock.locked() == False:
                return await self.paint(sem, b, ch, total, idx, progress, tid)

            # Realistic User Agent to avoid "HeadlessChrome" detection
            ua = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36 Edg/120.0.0.0"
            vp = {'width': 1920 + random.randint(-50, 50), 'height': 1080 + random.randint(-50, 50)}
            
            ctx = await b.new_context(user_agent=ua, viewport=vp)
            if self.use_stealth: await ctx.add_init_script(elysia.stealth_js)
            else: await ctx.add_init_script(STANDARD_JS)
            
            # Optional: Load external Inspector.js
            if os.path.exists("inspector.js"):
                try:
                    with open("inspector.js", "r", encoding="utf-8") as f:
                        await ctx.add_init_script(f.read())
                except: pass
            
            # --- COOKIE INJECTION ---
            if getattr(elysia.args, 'cookie_enable', False):
                if os.path.exists("cookies.json"):
                    try:
                        with open("cookies.json", 'r') as f:
                            cookies = json.load(f)
                        await ctx.add_cookies(cookies)
                        # console.print("[dim]Cookies Loaded.[/dim]")
                    except: pass

            # --- TACTICAL RESOURCE BLOCKING (Speed Boost) ---
            if getattr(elysia.args, 'block_ads', False):
                # Block useless resources to save bandwidth and CPU
                await ctx.route("**/*", lambda route: route.abort() 
                    if route.request.resource_type in ['font', 'media', 'texttrack', 'object', 'beacon', 'csp_report', 'imageset'] 
                    or any(x in route.request.url for x in ['google-analytics', 'doubleclick', 'facebook', 'adsystem', 'moatads'])
                    else route.continue_()
                )
            
            title = elysia.eden.sanitize(ch['name']) or f"Chapter_{idx+1}"
            try:
                root = os.path.join(elysia.args.output, elysia.args.name) if elysia.args.name else elysia.args.output
                canvas = os.path.join(root, title); os.makedirs(canvas, exist_ok=True)
                if progress and tid: progress.update(tid, description=f"[cyan]Working: {title}")
                
                # Check for sites known to use Image Scrambling/Shredding
                scrambled_kws = ['bookwalker', 'ridibooks', 'kakao', 'pixiv']
                is_scrambled = any(k in ch['url'] for k in scrambled_kws)
                
                # Removed hard timeout (was 40s) which caused partial downloads on slow connections/high concurrency
                cols = await pardofelis.scavenge(ctx, ch['url'], scramble_protection=is_scrambled)
                
                async with self.lock:
                    self.history.append(1 if cols else 0)
                    if len(self.history) > elysia.args.concurrent * 2: self.history.pop(0)
                    
                    # 只有当样本量足够且 Empty 占比 >= 50% 时才触发降级
                    if len(self.history) >= min(4, elysia.args.concurrent):
                        fail_rate = self.history.count(0) / len(self.history)
                        if fail_rate >= 0.5 and not self.downgraded:
                            self.ip_limit_hit = True
                            if elysia.memory.get("auto_downgrade", True):
                                elysia.eden.say("ip_limit_auto")
                                self.downgraded = True
                            else:
                                # 这里不再强制中断，而是标记状态
                                self.ip_limit_hit = True

                if cols:
                    try:
                        with open(os.path.join(canvas, "urls.json"), "w", encoding="utf-8") as f:
                            json.dump([u if isinstance(u, str) else 'blob' for u in cols], f, indent=2)
                    except: pass
                    await asyncio.to_thread(mobius.execute, cols, canvas, ch['url'], title, None)
                    await asyncio.to_thread(mobius.purify, canvas)
                    progress.console.log(f"[green]✓ Done:[/green] {title} ({len(cols)} pages)")
                    return canvas
                else:
                    progress.console.log(f"[yellow]! Empty:[/yellow] {title} (Pending Retry)")
                    return None # 返回 None 触发 executeMission 的末尾重试

            except Exception as e:
                progress.console.log(f"[red]✗ Error:[/red] {ch['name']} - {e}")
                return None
            finally:
                try: await ctx.close()
                except: pass

    def clean_tmp(self):
        root = os.path.join(elysia.args.output, elysia.args.name) if elysia.args.name else elysia.args.output
        if os.path.exists(root):
            for r, _, fs in os.walk(root):
                for f in fs:
                    if f.endswith(".tmp"):
                        try: os.remove(os.path.join(r, f))
                        except: pass

    async def validate_browser(self):
        async with async_playwright() as p:
            ch = "msedge" if elysia.args.browser == "edge" else "chrome"
            try:
                # Stealth Args: Hide automation flags to prevent "DevTools Detected" blocks
                b = await p.chromium.launch(
                    channel=ch, 
                    headless=True,
                    args=["--disable-blink-features=AutomationControlled", "--no-sandbox", "--disable-infobars"],
                    ignore_default_args=["--enable-automation"]
                )
                await b.close()
                return True
            except:
                alt = "chrome" if ch == "msedge" else "edge"
                if console.input(f"[yellow]Launch failed. Switch to {alt}? [Y/n]: [/yellow]").strip().lower() in ['', 'y']:
                    elysia.args.browser = alt
                    if elysia.memory:
                        elysia.memory['browser'] = alt
                        elysia.saveConfig(elysia.memory)
                    return True
                return False

    async def executeMission(self):
        self.clean_tmp()
        if not await self.validate_browser(): return

        elysia.eden.say("start")
        
        async with async_playwright() as p:
            ch = "msedge" if elysia.args.browser == "edge" else "chrome"
            # Stealth Args applied here as well
            self.bronya = await p.chromium.launch(
                channel=ch, 
                headless=elysia.args.headless,
                args=["--disable-blink-features=AutomationControlled", "--no-sandbox", "--disable-infobars"],
                ignore_default_args=["--enable-automation"]
            )
            
            stars = []
            max_catalog_retries = 2
            for attempt in range(max_catalog_retries + 1):
                try:
                    ua = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36 Edg/120.0.0.0" if not self.use_stealth else None
                    ctx = await self.bronya.new_context(user_agent=ua)
                    
                    # Stealth Args applied here as well
                    if self.use_stealth: await ctx.add_init_script(elysia.stealth_js)
                    else: await ctx.add_init_script(STANDARD_JS)
                    
                    # --- COOKIE INJECTION (Crucial for Catalog Load) ---
                    if getattr(elysia.args, 'cookie_enable', False):
                        if os.path.exists("cookies.json"):
                            try:
                                with open("cookies.json", 'r') as f:
                                    cookies = json.load(f)
                                await ctx.add_cookies(cookies)
                                # console.print("[dim]Catalog: Cookies Injected.[/dim]")
                            except: pass

                    page = await ctx.new_page()
                    elysia.eden.say("nav_catalog", elysia.args.url)
                    
                    # Visual Countdown for Loading
                    try:
                        with console.status(f"[bold cyan]Loading Catalog...[/bold cyan]") as status:
                            try:
                                # Standard navigation with reasonable timeout (60s)
                                await page.goto(elysia.args.url, timeout=60000, wait_until='domcontentloaded')
                                await asyncio.sleep(2) # Stabilization wait
                            except Exception as e:
                                console.print(f"[yellow]Warning: Navigation timeout or error ({e}). Attempting to proceed...[/yellow]")
                        
                        # Support for SPA/Modern sites: Query A tags AND Buttons/Divs that look like chapters
                        els = await page.query_selector_all("a, button, div[class*='item'], li")
                        if not els: raise Exception("No links/elements found (White Screen?)")
                        
                        # --- INITIALIZE CATALOG STATE ---
                        raw_stars = []
                        seen = set()
                        kws = ["话", "話", "回", "卷", "册", "冊", "chapter", "ch", "vol", "volume", "episode", "ep"]
                        is_bilibili = 'bilibili' in elysia.args.url
                        is_loose_mode = any(s in elysia.args.url for s in ['qq', 'kuaikan', '163', 'bookwalker', 'ridibooks'])
                        
                        cat_path = urlparse(elysia.args.url).path.strip('/')
                        path_segments = [s for s in cat_path.split('/') if s]
                        manga_slug = path_segments[-1] if path_segments else ""

                        # --- BILIBILI PARTITION AGGREGATOR ---
                        if is_bilibili:
                            try:
                                # Find partition buttons (e.g., 1-50, 51-100, 101-150)
                                partitions = await page.query_selector_all("div[class*='section'], div[class*='tabs'] div, div[class*='ep-list'] div")
                                valid_tabs = []
                                seen_tab_texts = set()
                                
                                for p in partitions:
                                    txt = (await p.inner_text()).strip()
                                    if re.search(r'\d+\s*-\s*\d+', txt) and txt not in seen_tab_texts:
                                        valid_tabs.append(p); seen_tab_texts.add(txt)
                                
                                if len(valid_tabs) > 1:
                                    console.print(f"[cyan]Nav: Bilibili partitions detected ({len(valid_tabs)} sections). Aggregating catalog...[/cyan]")
                                    for tab in valid_tabs:
                                        try:
                                            await tab.click()
                                            await asyncio.sleep(1.5)
                                            current_els = await page.query_selector_all("a")
                                            for el in current_els:
                                                h = await el.get_attribute("href")
                                                t = (await el.inner_text()).strip()
                                                if h and t:
                                                    full = urljoin(elysia.args.url, h)
                                                    if full != elysia.args.url and full not in seen:
                                                        # Reuse the lock detection logic here
                                                        is_l = await el.evaluate("""e => {
                                                            const b = e.closest('.m-chapter-item, .tag.container, div, li');
                                                            if (!b) return false;
                                                            return !!b.querySelector('.lock-icon.locked, .tag.lock-icon.locked, .locked, [class*="locked"], [class*="pay"]');
                                                        }""")
                                                        if is_l: continue
                                                        if any(c.isdigit() for c in t):
                                                            raw_stars.append({
                                                                "name": t, "url": full, 
                                                                "sort_key": float(re.findall(r"\d+\.?\d*", t)[0]) if re.findall(r"\d+\.?\d*", t) else 0.0,
                                                                "is_special": ('.' in str(float(re.findall(r"\d+\.?\d*", t)[0])) and not str(float(re.findall(r"\d+\.?\d*", t)[0])).endswith('.0')) if re.findall(r"\d+\.?\d*", t) else False,
                                                                "is_vol": any(kw in t.lower() for kw in ["卷", "vol", "volume"]),
                                                                "parent": "bilibili_aggregated"
                                                            })
                                                            seen.add(full)
                                        except: continue
                                    
                                    if raw_stars:
                                        stars = sorted(raw_stars, key=lambda x: (x['is_vol'], x['sort_key']))
                                        final_unique = []
                                        seen_names = set()
                                        for s in stars:
                                            if s['name'] not in seen_names:
                                                final_unique.append(s); seen_names.add(s['name'])
                                        stars = final_unique
                                        break # Success, exit retry loop
                            except Exception as e:
                                console.print(f"[dim]Note: Bilibili aggregator issue ({e}).[/dim]")

                        # --- AUTO-EXPANDER PROBE (Smooth Scroll Detection) ---
                        if not is_bilibili:
                            try:
                                expand_kws = ["查看", "全部", "展开", "展開", "更多", "章节", "章節", "点击", "點擊", "显示", "顯示", "完整", "Show", "All", "Load", "More", "Expand", "Chapters"]
                                for _ in range(8):
                                    clicked_any = await page.evaluate(f"""(kws) => {{
                                        const targets = Array.from(document.querySelectorAll('button, a, div, span, p, li, section, i'));
                                        let found = false;
                                        targets.forEach(e => {{
                                            const text = (e.innerText || "").toLowerCase();
                                            let matched = new Set();
                                            kws.forEach(kw => {{ if(text.includes(kw.toLowerCase())) matched.add(kw.toLowerCase()); }});
                                            if (matched.size >= 2) {{
                                                const s = window.getComputedStyle(e);
                                                if (s.display !== 'none' && s.visibility !== 'hidden' && s.opacity !== '0' && e.offsetHeight > 0) {{
                                                    e.scrollIntoView({{behavior: 'instant', block: 'center'}});
                                                    ['mousedown', 'mouseup', 'click'].forEach(n => e.dispatchEvent(new MouseEvent(n, {{bubbles:true, cancelable:true, view:window, buttons:1}})));
                                                    if (typeof e.click === 'function') e.click();
                                                    found = true;
                                                }}
                                            }}
                                        }});
                                        return found;
                                    }}""", expand_kws)
                                    if clicked_any:
                                        await asyncio.sleep(3); continue 
                                    await page.evaluate("window.scrollBy(0, 800)")
                                    await asyncio.sleep(elysia.args.scroll_wait)
                                    if await page.evaluate("window.innerHeight + window.pageYOffset >= document.body.scrollHeight - 50"): break
                            except: pass
                        
                        # --- GENERAL LINK COLLECTION ---
                        await asyncio.sleep(2)
                        els = await page.query_selector_all("a")
                        
                        if not elysia.args.name and manga_slug:
                             elysia.args.name = manga_slug
                             console.print(f"[yellow]Auto-assigned Name: {manga_slug}[/yellow]")

                        for el in els:
                            try:
                                href = await el.get_attribute("href")
                                text = (await el.inner_text()).strip()
                                if not href or not text: continue
                                
                                full = urljoin(elysia.args.url, href)
                                if full != elysia.args.url and full not in seen:
                                    tl = text.lower()
                                    has_digit = any(c.isdigit() for c in text)
                                    has_kw = any(kw in tl for kw in kws)
                                    
                                    if has_digit and (has_kw or is_bilibili or (is_loose_mode and len(text) < 30) or len(text) < 10):
                                        if manga_slug and manga_slug not in full: 
                                            if not (is_bilibili or is_loose_mode): continue
                                        
                                        p_info = await el.evaluate("""e => {
                                            let p1 = e.parentElement;
                                            let p2 = p1 ? p1.parentElement : null;
                                            return (p2 ? (p2.className + p2.id) : "") + "_" + (p1 ? (p1.className + p1.id) : "");
                                        }""")
                                        
                                        # --- LOCK DETECTION ---
                                        is_locked = await el.evaluate("""e => {
                                            const b_container = e.closest('.m-chapter-item, .tag.container, div, li, section, a');
                                            if (b_container) {
                                                const lock = b_container.querySelector('.lock-icon.locked, .tag.lock-icon.locked, .locked, [class*="locked"], [class*="pay"], [class*="vip"], .m-lock-icon, [class*="limit"]');
                                                if (lock) return true;
                                                const badges = b_container.querySelectorAll('i, span, div');
                                                for (let b of badges) {
                                                    const style = window.getComputedStyle(b);
                                                    if (style.backgroundImage.includes('lock') || style.backgroundImage.includes('pay')) return true;
                                                }
                                            }
                                            const text = (e.innerText || "").toLowerCase();
                                            if (text.includes("付费") || text.includes("解锁") || text.includes("券") || text.includes("限免结束")) return true;
                                            if (text.includes("等") && text.includes("天")) return true; 
                                            return false;
                                        }""")
                                        if is_locked: continue

                                        raw_stars.append({
                                            "name": text, "url": full, "sort_key": float(re.findall(r"\d+\.?\d*", text)[0]) if re.findall(r"\d+\.?\d*", text) else 0.0,
                                            "is_special": ('.' in str(float(re.findall(r"\d+\.?\d*", text)[0])) and not str(float(re.findall(r"\d+\.?\d*", text)[0])).endswith('.0')) if re.findall(r"\d+\.?\d*", text) else False,
                                            "is_vol": any(kw in tl for kw in ["卷", "vol", "volume", "册", "冊"]),
                                            "parent": p_info
                                        })
                                        seen.add(full)
                            except: continue
                        
                        if raw_stars:
                            stars = sorted(raw_stars, key=lambda x: (x['is_vol'], x['sort_key']))
                            final_unique = []
                            seen_names = set()
                            for s in stars:
                                if s['name'] not in seen_names:
                                    final_unique.append(s); seen_names.add(s['name'])
                            stars = final_unique
                            break # Success
                        
                        if not stars: raise Exception("No chapters found")
                    except (TimeoutError, Exception) as e:
                        console.print(f"[red]Error during catalog load: {e}[/red]")
                        if self.use_stealth and attempt < max_catalog_retries:
                            self.use_stealth = False
                            console.print("[yellow]System: Switching to Standard Identity and retrying...[/yellow]")
                            continue
                        else:
                            return

                except Exception as e:
                    if attempt < max_catalog_retries:
                        continue
                    else:
                        return

            if not stars:
                return

            total = len(stars)
            vol_c = sum(1 for s in stars if s['is_vol'])
            decimal_c = sum(1 for s in stars if s['is_special'] and not s['is_vol'])
            reg_c = total - vol_c - decimal_c
            
            elysia.eden.printSeparator()
            elysia.eden.say("chapter_analysis", total, reg_c, vol_c, decimal_c)
            elysia.eden.printSubSeparator()
        
            if vol_c > 0 and reg_c > 0:
                if elysia.batch_mode:
                    console.print("[yellow]Batch Mode: Keeping both Volumes and Chapters.[/yellow]")
                    v_filter = ''
                else:
                    v_filter = elysia.eden.ask("ask_vol_filter").strip().lower()

                if v_filter == 'a':
                    stars = [s for s in stars if not s['is_vol']]
                    console.print("[yellow]System: Filtered to Chapters only.[/yellow]")
                elif v_filter == 'b':
                    stars = [s for s in stars if s['is_vol']]
                    console.print("[yellow]System: Filtered to Volumes only.[/yellow]")
                
                total = len(stars)
            
            if elysia.batch_mode:
                dl_all = 'y'
            else:
                dl_all = elysia.eden.ask("ask_download_all").strip().lower()
            
            final_stars = stars
            if dl_all not in ['', 'y']:
                mode = elysia.eden.ask("ask_select_mode").strip().lower()
                if mode == 'a':
                    try:
                        count = int(elysia.eden.ask("ask_latest_count").strip())
                        final_stars = stars[-count:]
                    except: pass
                elif mode == 'b':
                    final_stars = [stars[i] for i in sorted(self.parseRangeStr(elysia.eden.ask("ask_range").strip(), stars))]
                elif mode == 'c':
                    final_stars = [stars[i] for i in sorted(self.parseRangeStr(elysia.eden.ask("ask_multi_range").strip(), stars))]
                elif mode == 'd':
                    final_stars = [s for s in stars if not s['is_special']]
            
            elysia.eden.say("selection_result", len(final_stars))
            elysia.eden.printSeparator()
            
            if elysia.args.concurrent > len(final_stars): elysia.args.concurrent = len(final_stars)
            semaphore = asyncio.Semaphore(elysia.args.concurrent)
            
            with Progress(SpinnerColumn(), TextColumn("[progress.description]{task.description}"), BarColumn(), TextColumn("[progress.percentage]{task.percentage:>3.0f}%"), TimeRemainingColumn(), console=console, refresh_per_second=10) as progress:
                main_task = progress.add_task("[bold cyan]Total Progress", total=len(final_stars))
                
                # 建立重试队列系统
                queue = list(enumerate(final_stars))
                retry_counts = {i: 0 for i in range(len(final_stars))}
                finished_count = 0
                
                while queue:
                    tasks = [self.paint(semaphore, self.bronya, s, len(final_stars), i, progress, main_task) for i, s in queue]
                    results = await asyncio.gather(*tasks)
                    
                    # 筛选出本轮成功的索引
                    success_indices = [idx for idx, res in enumerate(results) if res is not None]
                    finished_count += len(success_indices)
                    progress.update(main_task, completed=finished_count)

                    # 处理失败项
                    next_queue = []
                    for idx, res in enumerate(results):
                        if res is None:
                            q_idx, q_item = queue[idx]
                            retry_counts[q_idx] += 1
                            
                            if retry_counts[q_idx] <= 3:
                                next_queue.append((q_idx, q_item))
                            else:
                                progress.console.log(f"[red]✗ Give Up:[/red] {q_item['name']} (Max Retries Reached)")
                    
                    queue = next_queue
                    
                    if queue:
                        # 降级模式下的额外冷却
                        if self.downgraded:
                            progress.console.log(f"[yellow]System: {len(queue)} items pending. Cooling down ({elysia.args.pause_duration}s)...[/yellow]")
                            await asyncio.sleep(elysia.args.pause_duration + 2)
                        else:
                            progress.console.log(f"[dim]System: {len(queue)} items need attention, re-queueing...[/dim]")

            await self.bronya.close()
            
            elysia.eden.printSeparator()
            elysia.eden.say("done")
            
            if mobius.anomalies:
                elysia.eden.printSeparator()
                if elysia.batch_mode:
                    console.print("[yellow]Batch Mode: Auto-retrying anomalies...[/yellow]")
                    await asyncio.to_thread(mobius.reconstruct)
                else:
                    retry_q = elysia.eden.ask("ask_retry", len(mobius.anomalies))
                    if retry_q.strip().lower() == 'y':
                        await asyncio.to_thread(mobius.reconstruct)

    async def dashboard(self):
        while True:
            elysia.eden.printSeparator()
            choice = elysia.eden.ask("dashboard_menu").strip().lower()
            if choice == 'a': await asyncio.to_thread(mobius.repairRealm)
            elif choice == 'b':
                sn = "Image2PDF.py"
                if not os.path.exists(sn):
                    elysia.eden.say("downloading_tool")
                    s = False
                    for _ in range(10):
                        try:
                            r = requests.get("https://raw.githubusercontent.com/ShadowLoveElysia/Bulk-Ebook-Merger-Converter/main/Image2PDF.py", timeout=10)
                            if r.status_code == 200:
                                with open(sn, 'wb') as f: f.write(r.content)
                                s = True; break
                        except: time.sleep(1)
                    if not s: continue
                q_e = elysia.eden.ask("ask_ebook_convert").strip().lower()
                elysia.eden.say("starting_merge")
                td = os.path.abspath(os.path.join(elysia.args.output, elysia.args.name) if elysia.args.name else elysia.args.output)
                try: subprocess.run(["uv", "run", sn, td] + (["--auto-merge"] if q_e in ['', 'y'] else []), check=True)
                except Exception as e: elysia.eden.say("error", e)
            elif choice == 'c':
                nu = await elysia.sniffLoop()
                if not nu: continue
                ni = elysia.eden.ask("ask_name").strip()
                elysia.args.name = elysia.eden.sanitize(ni) if ni else None
                elysia.args.url = nu
                return "RESTART"
            elif choice == 'e':
                ls = ['zh', 'en', 'ja']
                elysia.eden.lang = ls[(ls.index(elysia.eden.lang) + 1) % len(ls)]
                elysia.eden.say("switch_lang")
                if elysia.memory:
                    elysia.memory['lang'] = elysia.eden.lang
                    elysia.saveConfig(elysia.memory)
            elif choice == 'f':
                nv = not elysia.memory.get("auto_sniff", True); elysia.memory['auto_sniff'] = nv; elysia.saveConfig(elysia.memory); elysia.eden.say("toggle_sniff", elysia.eden.scripts["sniff_on" if nv else "sniff_off"][elysia.eden.lang])
            elif choice == 'g':
                nv = not elysia.memory.get("auto_downgrade", True); elysia.memory['auto_downgrade'] = nv; elysia.saveConfig(elysia.memory)
                status = elysia.eden.scripts["sniff_on" if nv else "sniff_off"][elysia.eden.lang]
                console.print(f"Config: Auto-Downgrade is now {status}")
            elif choice in ['d', '']: return "EXIT"

    async def auto_trigger_merge(self):
        if not getattr(elysia.args, 'auto_merge', False): return
        sn = "Image2PDF.py"
        if not os.path.exists(sn):
            elysia.eden.say("downloading_tool")
            s = False
            for _ in range(10):
                try:
                    r = requests.get("https://raw.githubusercontent.com/ShadowLoveElysia/Bulk-Ebook-Merger-Converter/main/Image2PDF.py", timeout=10)
                    if r.status_code == 200:
                        with open(sn, 'wb') as f: f.write(r.content)
                        s = True; break
                except: time.sleep(1)
            if not s: return
        elysia.eden.say("starting_merge")
        td = os.path.abspath(os.path.join(elysia.args.output, elysia.args.name) if elysia.args.name else elysia.args.output)
        try:
            fmt = getattr(elysia.args, 'merge_format', 'epub')
            subprocess.run(["uv", "run", sn, td, "--auto-merge", "--merge-format", fmt], check=True)
        except Exception as e: elysia.eden.say("error", e)

    async def batch_trigger_merge(self, dirs):
        if not getattr(elysia.args, 'auto_merge', False): return
        sn = "Image2PDF.py"
        if not os.path.exists(sn):
            elysia.eden.say("downloading_tool")
            s = False
            for _ in range(10):
                try:
                    r = requests.get("https://raw.githubusercontent.com/ShadowLoveElysia/Bulk-Ebook-Merger-Converter/main/Image2PDF.py", timeout=10)
                    if r.status_code == 200:
                        with open(sn, 'wb') as f: f.write(r.content)
                        s = True; break
                except: time.sleep(1)
            if not s: return
        elysia.eden.say("starting_merge")
        
        fmt = getattr(elysia.args, 'merge_format', 'epub')
        for td in dirs:
            if not os.path.exists(td): continue
            console.print(f"[bold cyan]Merging: {os.path.basename(td)}[/bold cyan]")
            try:
                subprocess.run(["uv", "run", sn, td, "--auto-merge", "--merge-format", fmt], check=True)
            except Exception as e: elysia.eden.say("error", e)

    async def start(self):
        if elysia.batch_mode:
            processed_dirs = []
            console.print(f"[bold cyan]Starting Batch Processing ({len(elysia.batch_tasks)} tasks)...[/bold cyan]")
            
            for i, task in enumerate(elysia.batch_tasks):
                elysia.args.url = task['url']
                elysia.args.name = elysia.eden.sanitize(task['name']) if task['name'] else None
                console.rule(f"[bold yellow]Batch Task {i+1}/{len(elysia.batch_tasks)}: {elysia.args.name or elysia.args.url}[/bold yellow]")
                
                await self.executeMission()
                
                if elysia.args.name:
                    pd = os.path.join(elysia.args.output, elysia.args.name)
                else:
                    pd = elysia.args.output 
                
                if pd not in processed_dirs: processed_dirs.append(pd)

            if elysia.args.auto_merge:
                await self.batch_trigger_merge(processed_dirs)
            
            elysia.eden.singFinale()
            elysia.eden.notify("任务完成 / Mission Complete", f"Batch processing of {len(elysia.batch_tasks)} tasks finished.")
            console.print("[bold green]Batch Job Completed.[/bold green]")
        else:
            while True:
                await self.executeMission()
                await self.auto_trigger_merge()
                final_target = os.path.join(elysia.args.output, elysia.args.name) if elysia.args.name else elysia.args.output
                elysia.eden.openGateway(final_target)
                elysia.eden.singFinale()
                elysia.eden.notify("任务完成 / Mission Complete", f"Download finished: {elysia.args.name or 'Comic'}")
                if (await self.dashboard()) == "EXIT": break
                console.clear()

if __name__ == "__main__":
    if not os.path.exists(elysia.args.output): os.makedirs(elysia.args.output)
    try: asyncio.run(Griseo().start())
    except KeyboardInterrupt: elysia.eden.say("shutdown")
    except Exception as e: elysia.eden.say("error", e)