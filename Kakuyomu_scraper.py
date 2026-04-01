# /// script
# requires-python = ">=3.10"
# dependencies = [
#     "playwright",
#     "rich",
#     "pyperclip",
#     "aiohttp",
#     "natsort",
# ]
# ///

import os
import sys
import re
import json
import asyncio
import argparse
import signal
import random
import time
import pyperclip
import warnings
import natsort
from datetime import datetime
from rich.console import Console
from rich.progress import Progress, SpinnerColumn, BarColumn, TextColumn, TimeRemainingColumn
from rich.panel import Panel
from rich.prompt import Prompt, Confirm, IntPrompt
from playwright.async_api import async_playwright

# Suppress noisy asyncio resource warnings on Windows
warnings.filterwarnings("ignore", category=ResourceWarning)

console = Console()

# --- Global Signal Handler ---
def signal_handler(sig, frame):
    console.print("\n[bold red]System: Interrupt signal received. Shutting down...[/bold red]")
    # We rely on asyncio loop to catch this or system to exit, 
    # but strictly raising KeyboardInterrupt works for most loops.
    raise KeyboardInterrupt

signal.signal(signal.SIGINT, signal_handler)

# --- Configuration & State ---
CONFIG_FILE = "novel_config.json"
COOKIES_FILE = "cookies_novel.json"

DEFAULT_CONFIG = {
    "output_dir": "novel_downloads",
    "threads": 3,
    "headless": True,
    "user_agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "auto_merge": False,
    "translation": {
        "enabled": False,
        "api_base": "http://127.0.0.1:8080/v1",
        "api_key": "sk-no-key-required",
        "model": "",
        "prompt": "将下面的日文文本翻译成中文："
    }
}

# --- Stealth Scripts (Simplified) ---
STEALTH_JS = """
Object.defineProperty(navigator, 'webdriver', { get: () => undefined });
window.chrome = { runtime: {} };
Object.defineProperty(navigator, 'plugins', { get: () => [1, 2, 3, 4, 5] });
Object.defineProperty(navigator, 'languages', { get: () => ['ja', 'en-US', 'en'] });
"""

class ConfigManager:
    def __init__(self):
        self.config = DEFAULT_CONFIG.copy()
        self.load()

    def load(self):
        if os.path.exists(CONFIG_FILE):
            try:
                with open(CONFIG_FILE, 'r', encoding='utf-8') as f:
                    saved = json.load(f)
                    self.config.update(saved)
            except:
                pass

    def save(self):
        try:
            with open(CONFIG_FILE, 'w', encoding='utf-8') as f:
                json.dump(self.config, f, indent=4, ensure_ascii=False)
        except:
            pass
    
    def get(self, key):
        return self.config.get(key)

    def set(self, key, value):
        self.config[key] = value

config_manager = ConfigManager()

# --- Utilities ---
def sanitize_filename(name):
    # Remove illegal characters for Windows
    name = re.sub(r'[\\/*?:"<>|]', "", name)
    # Replace all types of whitespace (newlines, tabs) with a single space
    name = re.sub(r'\s+', " ", name)
    return name.strip()

def clean_chapter_title(raw_title):
    """Kakuyomu titles often include dates or sub-spans. Extract only the first line."""
    if not raw_title: return "Untitled"
    # Split by newline and take the first non-empty line
    lines = [l.strip() for l in raw_title.split('\n') if l.strip()]
    return lines[0] if lines else "Untitled"

# --- Core Scraper Classes ---

class SakuraTranslator:
    def __init__(self):
        self.config = config_manager.get("translation")
        self.api_url = f"{self.config['api_base'].rstrip('/')}/chat/completions"
        self.headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self.config['api_key']}"
        }

    async def check_connection(self):
        """Verify if the local LLM is reachable."""
        try:
            payload = {
                "model": self.config.get('model') or "sakura",
                "messages": [{"role": "user", "content": "Ping"}],
                "max_tokens": 1
            }
            async with aiohttp.ClientSession() as session:
                async with session.post(self.api_url, json=payload, headers=self.headers, timeout=5) as resp:
                    if resp.status == 200:
                        return True
                    else:
                        console.print(f"[red]LLM Connect Error: {resp.status}[/red]")
                        return False
        except Exception as e:
            console.print(f"[red]LLM Connect Failed: {e}[/red]")
            return False

    async def translate(self, text):
        """Translate a block of text."""
        if not text.strip():
            return ""

        # Official System Prompt for Sakura
        system_prompt = "你是一个轻小说翻译模型，可以流畅通顺地以日本轻小说的风格将日文翻译成简体中文，并联系上下文正确使用人称代词，不擅自添加原文中没有的代词。"
        
        # Official User Prompt (Default / No Glossary)
        # Note: If we implement glossary later, we'd use the other template.
        user_content = f"将下面的日文文本翻译成中文：\n{text}"

        payload = {
            "model": self.config.get('model') or "sakura",
            "messages": [
                {
                    "role": "system", 
                    "content": system_prompt
                },
                {
                    "role": "user", 
                    "content": user_content
                }
            ],
            "temperature": 0.1,
            "top_p": 0.3,
            "frequency_penalty": 0.0,
            "max_tokens": 4096 
        }

        retries = 3
        for attempt in range(retries):
            try:
                async with aiohttp.ClientSession() as session:
                    # High timeout for translation generation
                    async with session.post(self.api_url, json=payload, headers=self.headers, timeout=120) as resp:
                        if resp.status == 200:
                            data = await resp.json()
                            content = data['choices'][0]['message']['content']
                            return content
                        elif resp.status == 500: # Common for OOM or internal error
                            await asyncio.sleep(2)
                            continue
                        else:
                            console.print(f"[red]Translation API Error {resp.status}: {await resp.text()}[/red]")
                            return None
            except Exception as e:
                console.print(f"[yellow]Translation Timeout/Error (Attempt {attempt+1}): {e}[/yellow]")
                await asyncio.sleep(2)
        
        return None

class Localization:
    def __init__(self, lang=None):
        try:
            import locale
            # Robust detection for Windows
            sys_lang = locale.getdefaultlocale()[0]
            if not sys_lang:
                sys_lang = locale.getlocale()[0]
            
            sys_lang = str(sys_lang).lower()
            if 'chinese' in sys_lang or 'zh' in sys_lang:
                sys_lang = 'zh'
            elif 'ja' in sys_lang or 'jp' in sys_lang:
                sys_lang = 'ja'
            else:
                sys_lang = 'en'
        except:
            sys_lang = 'en'
            
        self.lang = lang or sys_lang
        if self.lang not in ['zh', 'en', 'ja']:
            self.lang = 'en'
        
        self.scripts = {
            "welcome": {
                "zh": "欢迎使用小说采集终端 [Sakura Ver.]",
                "en": "Welcome to Novel Scraper Terminal [Sakura Ver.]",
                "ja": "小说収集ターミナルへようこそ [Sakura Ver.]"
            },
            "input_url": {
                "zh": "请输入小说目录页网址 (例如 Kakuyomu)",
                "en": "Please enter the novel TOC URL (e.g. Kakuyomu)",
                "ja": "小説の目次URLを入力してください (例 Kakuyomu)"
            },
            "ask_output": {
                "zh": "请指定输出目录",
                "en": "Output Directory",
                "ja": "出力ディレクトリ"
            },
            "ask_threads": {
                "zh": "设置并发下载数",
                "en": "Concurrent Downloads",
                "ja": "同時ダウンロード数"
            },
            "ask_headless": {
                "zh": "是否启用后台静默模式?",
                "en": "Enable Headless (Background) Mode?",
                "ja": "バックグラウンドモードを有効にしますか?"
            },
            "ask_cookie_wizard": {
                "zh": "未检测到 Cookies。是否启动 [登录向导] 以捕获 Cookie?",
                "en": "Cookies missing. Launch [Login Wizard] to capture cookies?",
                "ja": "Cookieが見つかりません。[ログインウィザード] を起動してCookieを取得しますか？"
            },
            "login_intro": {
                "zh": "System: 正在启动登录向导...\nAction: 请在弹出的浏览器窗口中登录，确认能阅读后在此按回车。",
                "en": "System: Launching Login Wizard...\nAction: Please login in the browser window, then press Enter here.",
                "ja": "System: ログインウィザードを起動中...\nAction: ブラウザでログインし、完了したらここでEnterを押してください。"
            },
            "ask_translate": {
                "zh": "[bold magenta]是否启用 Sakura LLM 翻译功能? (将日文自动转为中文)[/bold magenta]",
                "en": "[bold magenta]Enable Sakura LLM Translation? (Auto-translate Japanese to Chinese)[/bold magenta]",
                "ja": "[bold magenta]Sakura LLM 翻訳を有効にしますか？ (日本語を中国語に自動翻訳)[/bold magenta]"
            },
            "nav_catalog": {
                "zh": "Nav: 正在访问目录: {}",
                "en": "Nav: Navigating to catalog: {}",
                "ja": "Nav: 目次に移動中: {}"
            },
            "found_chapters": {
                "zh": "Data: 发现 {} 个章节。",
                "en": "Data: Found {} chapters.",
                "ja": "Data: {} 章を発见。"
            }
        }

    def say(self, key, *args):
        msg = self.scripts.get(key, {}).get(self.lang, "")
        if args: msg = msg.format(*args)
        console.print(msg)
    
    def ask(self, key, default=None, *args):
        msg = self.scripts.get(key, {}).get(self.lang, "")
        if args: msg = msg.format(*args)
        return Prompt.ask(f"[cyan]{msg}[/cyan]", default=default)

    def ask_confirm(self, key, default=True, *args):
        msg = self.scripts.get(key, {}).get(self.lang, "")
        if args: msg = msg.format(*args)
        return Confirm.ask(f"[cyan]{msg}[/cyan]", default=default)

    def ask_int(self, key, default=3, *args):
        msg = self.scripts.get(key, {}).get(self.lang, "")
        if args: msg = msg.format(*args)
        return IntPrompt.ask(f"[cyan]{msg}[/cyan]", default=default)

eden = Localization()

# --- Core Scraper Classes ---

class BrowserEngine:
    def __init__(self, headless=True):
        self.headless = headless
        self.playwright = None
        self.browser = None

    async def start(self):
        self.playwright = await async_playwright().start()
        
        # Robust Browser Selection
        channels = ["chrome", "msedge", None] # Try Chrome, then Edge, then Bundled
        for channel in channels:
            try:
                self.browser = await self.playwright.chromium.launch(
                    headless=self.headless,
                    channel=channel,
                    args=["--disable-blink-features=AutomationControlled", "--no-sandbox"]
                )
                if channel: console.print(f"[dim]Browser: Launched with channel '{channel}'[/dim]")
                else: console.print(f"[dim]Browser: Launched with bundled Chromium[/dim]")
                return
            except Exception as e:
                if channel == None: # Final fallback failed
                    raise e
                continue
    
    async def new_context(self):
        ctx = await self.browser.new_context(
            user_agent=config_manager.get("user_agent"),
            viewport={'width': 1280, 'height': 800},
            locale='ja-JP'
        )
        await ctx.add_init_script(STEALTH_JS)
        
        # Load Cookies
        if os.path.exists(COOKIES_FILE):
            try:
                with open(COOKIES_FILE, 'r') as f:
                    cookies = json.load(f)
                await ctx.add_cookies(cookies)
            except:
                console.print("[yellow]Warning: Failed to load cookies.[/yellow]")
        
        return ctx

    async def stop(self):
        if self.browser:
            await self.browser.close()
        if self.playwright:
            await self.playwright.stop()

class KakuyomuScraper:
    def __init__(self, url, output_dir, threads):
        self.url = url
        self.output_dir = output_dir
        self.threads = threads
        self.engine = BrowserEngine(headless=config_manager.get("headless"))
        self.meta = {"title": "Unknown", "author": "Unknown", "chapters": []}
        self.base_dir = ""
        self.translator = SakuraTranslator() if config_manager.get("translation") and config_manager.get("translation").get("enabled") else None

    async def run_login_wizard(self):
        """
        Ultimate Login Method: Launch specific Chrome process via subprocess and attach.
        This bypasses Playwright's launch triggers which Google detects.
        """
        import subprocess
        import shutil

        eden.say("login_intro")
        
        # 1. Find Chrome Executable
        chrome_path = None
        candidates = [
            r"C:\Program Files\Google\Chrome\Application\chrome.exe",
            r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
            os.path.expandvars(r"%LOCALAPPDATA%\Google\Chrome\Application\chrome.exe"),
            r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe", # Fallback to Edge
            r"C:\Program Files\Microsoft\Edge\Application\msedge.exe"
        ]
        
        for p in candidates:
            if os.path.exists(p):
                chrome_path = p
                break
        
        if not chrome_path:
            console.print("[red]Error: Could not find Chrome.exe or msedge.exe installed in standard paths.[/red]")
            return

        # 2. Prepare Data Dir
        user_data_dir = os.path.abspath("browser_data_login")
        os.makedirs(user_data_dir, exist_ok=True)
        
        # 3. Launch Chrome Manually (Subprocess)
        # We use 0 as port to let Chrome pick a free one, but 9222 is standard. 
        # Using specific port makes connecting easier.
        debug_port = 9222
        
        cmd = [
            chrome_path,
            f"--remote-debugging-port={debug_port}",
            f"--user-data-dir={user_data_dir}",
            "--no-first-run",
            "https://kakuyomu.jp/login"
        ]
        
        console.print(f"[dim]Launching browser directly: {chrome_path}[/dim]")
        
        try:
            # Start the process independent of python script
            proc = subprocess.Popen(cmd)
        except Exception as e:
            console.print(f"[red]Failed to launch browser: {e}[/red]")
            return

        console.print(f"[yellow]Waiting for browser to initialize...[/yellow]")
        await asyncio.sleep(3)

        # 4. Connect Playwright to the running instance
        async with async_playwright() as p:
            try:
                browser = await p.chromium.connect_over_cdp(f"http://localhost:{debug_port}")
                context = browser.contexts[0]
                
                # Check if we have pages, or create new one (though Chrome should have opened one)
                if not context.pages:
                    page = await context.new_page()
                else:
                    page = context.pages[0]

                console.input("\n[bold green]Input: Press Enter after you have successfully logged in...[/bold green]")
                
                cookies = await context.cookies()
                with open(COOKIES_FILE, "w") as f:
                    json.dump(cookies, f, indent=2)
                console.print("[green]Success: Cookies saved.[/green]")
                
                # We do NOT close the browser here via playwright, as it might kill the subprocess awkwardly.
                # But we can try to close the context.
                await browser.close()
                
            except Exception as e:
                console.print(f"[red]Connection failed: {e}[/red]")
                console.print("[dim]Please ensure you closed all other Chrome instances using port 9222 if any.[/dim]")
            finally:
                # Cleanup subprocess if it's still running? 
                # Usually user might close it, or we leave it. 
                # Let's try to terminate it to be clean.
                if proc.poll() is None:
                    proc.terminate()

    async def fetch_catalog(self):
        manual_mode = False
        
        while True:
            # If switching to manual mode, we need to ensure the browser is visible
            if manual_mode:
                if self.engine:
                    # Close existing engine to restart with new headless setting
                    await self.engine.stop()
                self.engine = BrowserEngine(headless=False)

            eden.say("nav_catalog", self.url)
            await self.engine.start()
            ctx = await self.engine.new_context()
            page = await ctx.new_page()

            try:
                await page.goto(self.url, timeout=60000, wait_until="domcontentloaded")
                
                # Extract Meta
                self.meta['title'] = await page.title()
                try:
                    # Kakuyomu structure usually: #workTitle, #workAuthor-activityName
                    title_el = await page.query_selector("#workTitle")
                    if title_el:
                        self.meta['title'] = await title_el.inner_text()
                    
                    author_el = await page.query_selector("#workAuthor-activityName")
                    if author_el:
                        self.meta['author'] = await author_el.inner_text()
                except:
                    pass
                
                self.meta['title'] = sanitize_filename(self.meta['title'])
                console.print(f"Book: [bold]{self.meta['title']}[/bold] by [bold]{self.meta['author']}[/bold]")

                # Helper to find TOC scope
                async def find_toc_scope():
                    # Added specific class requested by user '._workId__workToc__P6xQs'
                    candidates = [
                        "._workId__workToc__P6xQs",
                        "aside", 
                        "[class*='workToc']", 
                        ".widget-toc-main", 
                        "#workEpisodes", 
                        ".widget-workEpisodes"
                    ]
                    
                    for sel in candidates:
                        try:
                            el = await page.query_selector(sel)
                            if el and await el.is_visible():
                                console.print(f"[dim]  Debug: Found TOC scope via selector: {sel}[/dim]")
                                return el
                        except: pass
                    
                    # Try finding by text "目次"
                    try:
                        toc_header = await page.query_selector("xpath=//*[text()='目次']/ancestor::aside | //*[text()='目次']/ancestor::div[contains(@class, 'Toc')]")
                        if toc_header and await toc_header.is_visible():
                             console.print(f"[dim]  Debug: Found TOC scope via text '目次'[/dim]")
                             return toc_header
                    except: pass
                    return None

                if manual_mode:
                    console.print("[yellow]Manual Mode: Please manually expand the Table of Contents in the browser window.[/yellow]")
                    console.input("[bold green]Action: Press Enter here after you have expanded all chapters...[/bold green]")
                else:
                    # --- Ultimate Visual Strategy: Click-Click-Click ---
                    console.print("[dim]Visual Scan: Expanding TOC elements...[/dim]")
                    
                    # 1. Scroll to trigger lazy loading
                    await page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
                    await asyncio.sleep(1.5)
                    await page.evaluate("window.scrollTo(0, 0)")

                    try:
                        # 2. Aggressive Accordion & Button Loop
                        for attempt in range(20):
                            clicked_any = False
                            scope = await find_toc_scope()
                            if not scope: 
                                scope = await page.query_selector("main") or page

                            # Log all buttons for debug (only first attempt)
                            if attempt == 0:
                                btns = await scope.query_selector_all("button, a, [role='button']")
                                btn_texts = []
                                for b in btns:
                                    try:
                                        t = await b.inner_text()
                                        if t.strip(): btn_texts.append(t.strip())
                                    except: pass
                                console.print(f"[dim]  Debug: Buttons found: {', '.join(btn_texts[:10])}...[/dim]")

                            # A. Expand Accordions
                            triggers = await scope.query_selector_all("[class*='Accordion'], [class*='trigger'], button:has-text('第'), button:has-text('章')")
                            for i, trigger in enumerate(triggers):
                                try:
                                    expanded = await trigger.get_attribute("aria-expanded")
                                    if expanded != "true" and await trigger.is_visible():
                                        await trigger.scroll_into_view_if_needed()
                                        await trigger.click()
                                        await asyncio.sleep(1.5)
                                        clicked_any = True
                                        console.print(f"[dim]  Expanded trigger: {i+1}[/dim]")
                                except: pass

                            # B. Click "Show All" / "More"
                            selectors = [
                                "button:has-text('もっと見る')",
                                "a:has-text('もっと見る')",
                                "button:has-text('すべて表示')",
                                "a:has-text('すべて表示')",
                                "button:has-text('エピソードをもっと見る')",
                                "[class*='loadMore']",
                                "[class*='readMore']"
                            ]
                            
                            for sel in selectors:
                                try:
                                    els = await scope.query_selector_all(sel)
                                    for el in els:
                                        if await el.is_visible():
                                            await el.scroll_into_view_if_needed()
                                            await el.click()
                                            await asyncio.sleep(2.0)
                                            clicked_any = True
                                            console.print(f"[dim]  Clicked expansion: {sel}[/dim]")
                                except: continue
                            
                            if not clicked_any: break
                                
                    except Exception as e:
                        console.print(f"[yellow]Visual expansion finished: {e}[/yellow]")

                # Extract Chapters
                import natsort
                raw_chapters = []
                seen_urls = set()
                
                target_scope = await find_toc_scope()
                if not target_scope: target_scope = page

                chapter_links = await target_scope.query_selector_all("a[href*='/episodes/']")
                # Fallback to page global if scope yielded nothing
                if not chapter_links:
                    chapter_links = await page.query_selector_all("a[href*='/episodes/']")
                
                console.print(f"[dim]  Debug: Found {len(chapter_links)} potential episode links.[/dim]")

                for el in chapter_links:
                    try:
                        link = await el.get_attribute("href")
                        if not link or "/episodes/" not in link: continue
                        url = "https://kakuyomu.jp" + link if link.startswith("/") else link
                        if url not in seen_urls:
                            title = await el.inner_text()
                            if title.strip():
                                raw_chapters.append({"title": title.strip(), "url": url})
                                seen_urls.add(url)
                    except: continue

                if not raw_chapters:
                    console.print("[red]Error: No chapters found.[/red]")
                    if not manual_mode:
                        console.print("[yellow]Switching to manual mode for retry...[/yellow]")
                        manual_mode = True
                        await ctx.close()
                        continue
                    else:
                        # If failed even in manual mode, maybe ask to try again or abort
                        if Confirm.ask("[red]No chapters found in manual mode. Try again?[/red]", default=True):
                            await ctx.close()
                            continue
                        return False

                # Natural Sort
                raw_chapters = natsort.natsorted(raw_chapters, key=lambda x: x['url'])
                
                self.meta['chapters'] = []
                for i, ch in enumerate(raw_chapters):
                    self.meta['chapters'].append({
                        "id": i + 1,
                        "title": sanitize_filename(clean_chapter_title(ch['title'])),
                        "url": ch['url']
                    })

                console.print(f"[green]Data: Found {len(self.meta['chapters'])} chapters.[/green]")
                
                # User Confirmation
                msg = f"Found {len(self.meta['chapters'])} chapters. Is this correct?"
                if Confirm.ask(f"[cyan]{msg}[/cyan]", default=True):
                    return True
                else:
                    console.print("[yellow]Switching to manual mode. Please help identify the chapters.[/yellow]")
                    manual_mode = True
                    await ctx.close()
                    # Loop will restart, re-init engine with headless=False
                    continue

            except Exception as e:
                console.print(f"[red]Catalog Error: {e}[/red]")
                return False
            finally:
                try:
                    await ctx.close()
                except: pass

    async def download_chapter(self, ctx, chapter, semaphore, progress, task_id):
        async with semaphore:
            page = await ctx.new_page()
            try:
                await page.goto(chapter['url'], timeout=45000, wait_until="domcontentloaded")
                
                # Check for "Follower only" or "Login required"
                # TODO: Add detection

                # Process Ruby (Furigana)
                # Convert <ruby>Kanji<rt>kana</rt></ruby> to Kanji(kana)
                await page.evaluate("""() => {
                    document.querySelectorAll('ruby').forEach(ruby => {
                        let rt = ruby.querySelector('rt');
                        if (rt) {
                            let kana = rt.innerText;
                            // Remove rt from ruby to get base text cleanly
                            rt.remove(); 
                            let base = ruby.innerText;
                            // Create text node replacement
                            let replacement = document.createTextNode(`${base}(${kana})`);
                            ruby.replaceWith(replacement);
                        }
                    });
                }""",)
                
                # Extract Text
                # Main content is usually in .widget-episodeBody
                content_el = await page.query_selector(".widget-episodeBody")
                if not content_el:
                    raise Exception("Content element not found")
                
                text = await content_el.inner_text()
                
                # Formatting
                header = f"{chapter['title']}\n{'='*len(chapter['title'])}\n\n"
                
                # Save Original
                filename = f"{str(chapter['id']).zfill(4)}_{chapter['title']}.txt"
                filepath = os.path.join(self.base_dir, filename)
                
                with open(filepath, "w", encoding="utf-8") as f:
                    f.write(header + text)
                
                # Translation Step
                if self.translator:
                    progress.update(task_id, description=f"[magenta]Translating: {chapter['title']}")
                    # Simple batch translation. 
                    # If text is very long (>2000 chars), we might want to split, but Sakura often handles ~4k tokens contexts.
                    # We'll trust the user has a decent context size or the chapter isn't huge.
                    translated_text = await self.translator.translate(text)
                    
                    if translated_text:
                        cn_filename = f"{str(chapter['id']).zfill(4)}_{chapter['title']}_CN.txt"
                        cn_filepath = os.path.join(self.base_dir, cn_filename)
                        header_cn = f"{chapter['title']} (CN)\n{'='*len(chapter['title'])}\n\n"
                        with open(cn_filepath, "w", encoding="utf-8") as f:
                            f.write(header_cn + translated_text)
                    else:
                        console.print(f"[red]Translation failed for: {chapter['title']}[/red]")
                    
                    progress.update(task_id, description=f"[cyan]Downloading...")

                progress.advance(task_id)
                # console.log(f"[dim]Saved: {chapter['title']}[/dim]")

            except Exception as e:
                console.print(f"[red]Failed: {chapter['title']} - {e}[/red]")
            finally:
                await page.close()
                # Random Jitter
                await asyncio.sleep(random.uniform(0.5, 1.5))

    async def start_download(self):
        if not self.meta['chapters']:
            return

        # Prepare Directory
        folder_name = f"{self.meta['title']} - {self.meta['author']}"
        folder_name = sanitize_filename(folder_name)
        self.base_dir = os.path.join(self.output_dir, folder_name)
        os.makedirs(self.base_dir, exist_ok=True)

        console.print(f"[green]Saving to: {self.base_dir}[/green]")

        # --- Fresh Start: Clean Directory ---
        # User requested "disable resume". We wipe existing txt files to prevent ID collisions.
        try:
            existing_files = [f for f in os.listdir(self.base_dir) if f.endswith(".txt")]
            if existing_files:
                console.print(f"[yellow]Fresh Start: Removing {len(existing_files)} existing files to ensure complete download...[/yellow]")
                for f in existing_files:
                    try:
                        os.remove(os.path.join(self.base_dir, f))
                    except: pass
        except Exception as e:
            console.print(f"[dim]Warning during cleanup: {e}[/dim]")

        # Prepare Concurrency
        sem = asyncio.Semaphore(self.threads)
        
        # We assume 1 context is enough, or maybe 1 per thread? 
        # 1 context is usually fine and more memory efficient, but separate pages.
        ctx = await self.engine.new_context()

        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            BarColumn(),
            TextColumn("[progress.percentage]{task.percentage:>3.0f}%"),
            TimeRemainingColumn(),
            console=console
        ) as progress:
            task = progress.add_task(f"[cyan]Downloading...[/cyan]", total=len(self.meta['chapters']))
            
            tasks = []
            for ch in self.meta['chapters']:
                tasks.append(self.download_chapter(ctx, ch, sem, progress, task))
            
            await asyncio.gather(*tasks)

        await ctx.close()
        await self.engine.stop()
        console.print("\n[bold green]All Done![/bold green]")
        
        # Optional: Ask to merge
        # But per instructions, primary output is individual files. 
        # I'll just leave a hint or auto-merge if configured (but default off).

# --- Interactive UI ---

class Interface:
    def __init__(self):
        pass

    def header(self):
        console.print(Panel.fit(
            "[bold magenta]Novel Scraper (Kakuyomu Ver.)[/bold magenta]\n"
            "[dim]Advanced text extraction with Playwright[/dim]",
            border_style="magenta"
        ))

    async def sniff_clipboard(self):
        """Sniff clipboard for Kakuyomu URLs"""
        console.print("[yellow]Hint: Copy a Kakuyomu URL to auto-detect...[/yellow]")
        last_clip = ""
        for _ in range(20): # Try for 2 seconds roughly
            try:
                curr = pyperclip.paste().strip()
                if "kakuyomu.jp/works/" in curr and curr != last_clip:
                    console.print(f"\n[bold green]Detected URL:[/bold green] {curr}")
                    if Confirm.ask("Use this URL?", default=True):
                        return curr
                    last_clip = curr
            except:
                pass
            await asyncio.sleep(0.1)
        return None

    def wizard(self):
        self.header()
        
        # 1. URL
        url = asyncio.run(self.sniff_clipboard())
        if not url:
            url = eden.ask("input_url")
        
        # 2. Output Dir
        default_out = config_manager.get("output_dir")
        output_dir = eden.ask("ask_output", default=default_out)
        config_manager.set("output_dir", output_dir)

        # 3. Threads
        console.print("[dim]Note: High concurrency may trigger anti-bot protections.[/dim]")
        threads = eden.ask_int("ask_threads", default=config_manager.get("threads"))
        config_manager.set("threads", threads)

        # 4. Headless
        headless = eden.ask_confirm("ask_headless", default=config_manager.get("headless"))
        config_manager.set("headless", headless)

        # 5. Cookie Check
        if not os.path.exists(COOKIES_FILE):
             if eden.ask_confirm("ask_cookie_wizard", default=False):
                 temp_scraper = KakuyomuScraper(url, output_dir, threads)
                 asyncio.run(temp_scraper.run_login_wizard())
        
        config_manager.save()
        return url, output_dir, threads

# --- Main Entry Point ---

def main():
    parser = argparse.ArgumentParser(description="Novel Scraper for Kakuyomu")
    parser.add_argument("url", nargs="?", help="The URL of the novel TOC")
    parser.add_argument("-o", "--output", help="Output directory")
    parser.add_argument("-t", "--threads", type=int, help="Number of download threads")
    parser.add_argument("--headless", action="store_true", help="Run browser in headless mode")
    parser.add_argument("--no-headless", action="store_false", dest="headless", help="Show browser window")
    
    args = parser.parse_args()

    # Determine mode
    if args.url:
        # CLI Mode
        url = args.url
        output = args.output or config_manager.get("output_dir")
        threads = args.threads or config_manager.get("threads")
        headless = args.headless if args.headless is not None else config_manager.get("headless")
    else:
        # Wizard Mode
        ui = Interface()
        url, output, threads = ui.wizard()
        # Wizard already saves config, reload headless pref from config just in case
        headless = config_manager.get("headless")

    # Run Scraper
    scraper = KakuyomuScraper(url, output, threads)
    # Override headless config in engine if needed, but we init engine inside scraper.
    # We need to update config manager or pass it. 
    # Current implementation reads config_manager inside BrowserEngine.
    config_manager.set("headless", headless) 
    
    async def run_session():
        if await scraper.fetch_catalog():
            await scraper.start_download()

    try:
        asyncio.run(run_session())
    except KeyboardInterrupt:
        pass
    except Exception as e:
        console.print(f"[red]Fatal Error: {e}[/red]")

if __name__ == "__main__":
    main()
