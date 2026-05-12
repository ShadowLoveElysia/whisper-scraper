# /// script
# requires-python = ">=3.10"
# dependencies = [
#     "playwright",
# ]
# ///

import argparse
import asyncio
import csv
import html
import json
import re
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from urllib.parse import parse_qsl, urlencode, urlparse, urlunparse


DEFAULT_EXCLUDED_NAMES: set[str] = set()
DEFAULT_STATE_FILE = "forum_auth_state.json"
DEFAULT_FORUM_HOME = "https://bbs.kfpromax.com/"
DEFAULT_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/120.0.0.0 Safari/537.36"
)


@dataclass
class ForumPost:
    uid: str
    username: str
    floor: int | None
    pid: str | None
    posted_at: str | None
    page: int | None


def read_html(path: Path) -> str:
    data = path.read_bytes()
    for encoding in ("utf-8", "gb18030", "gbk"):
        try:
            return data.decode(encoding)
        except UnicodeDecodeError:
            continue
    return data.decode("utf-8", errors="replace")


def clean_text(raw: str) -> str:
    raw = re.sub(r"<[^>]+>", "", raw)
    raw = html.unescape(raw)
    return re.sub(r"\s+", " ", raw).strip()


def extract_page_number(document: str) -> int | None:
    match = re.search(r"read\.php\?[^\"<>]*[?&]page=(\d+)", document)
    return int(match.group(1)) if match else None


def extract_max_page(document: str) -> int:
    pages = [int(value) for value in re.findall(r"(?:[?&]|&amp;)page=(\d+)", document)]
    return max(pages) if pages else 1


def set_url_page(url: str, page_number: int) -> str:
    parsed = urlparse(html.unescape(url))
    query = dict(parse_qsl(parsed.query, keep_blank_values=True))
    query["page"] = str(page_number)
    return urlunparse(parsed._replace(query=urlencode(query)))


def find_sf_in_document(document: str, tid: str) -> str | None:
    pattern = re.compile(
        rf"read\.php\?[^\"'<>]*\btid={re.escape(tid)}(?:&amp;|&|\b)[^\"'<>]*?(?:&amp;|&)sf=(\d+)",
        re.I,
    )
    match = pattern.search(document)
    if match:
        return match.group(1)

    pattern = re.compile(
        rf"\btid={re.escape(tid)}(?:&amp;|&|\b)[^\"'<>]*?(?:&amp;|&)sf=(\d+)",
        re.I,
    )
    match = pattern.search(document)
    return match.group(1) if match else None


def find_sf_from_saved_html(tid: str, search_dir: Path) -> str | None:
    for html_path in sorted(search_dir.glob("*.html")):
        try:
            sf = find_sf_in_document(read_html(html_path), tid)
        except OSError:
            continue
        if sf:
            print(f"自动识别 sf={sf}，来源: {html_path.name}")
            return sf
    return None


def normalize_thread_url(url: str, args: argparse.Namespace) -> str:
    parsed = urlparse(html.unescape(url))
    query = dict(parse_qsl(parsed.query, keep_blank_values=True))
    tid = query.get("tid")
    if not tid:
        return url

    if "sf" not in query:
        sf = getattr(args, "sf", None)
        if not sf:
            sf = find_sf_from_saved_html(tid, Path(getattr(args, "sf_source_dir", ".")))
        if sf:
            query["sf"] = sf
            query.setdefault("fpage", "0")
            query.setdefault("toread", "")
            query.setdefault("page", "1")
            completed = urlunparse(parsed._replace(query=urlencode(query)))
            print(f"已自动补全 URL: {completed}")
            return completed

    return url


def warn_if_url_lost_query_parts(url: str) -> None:
    parsed = urlparse(html.unescape(url))
    query = dict(parse_qsl(parsed.query, keep_blank_values=True))
    if parsed.path.endswith("/read.php") and "tid" in query and "sf" not in query:
        print()
        print("警告: URL 里没有 sf 参数。")
        print("没有从本地 HTML 或 --sf 参数里自动补全成功。")
        print("在 CMD 里 URL 必须加英文双引号，否则 &sf=... 会被当成另一条命令。")
        print('正确示例: fetch-thread "https://bbs.kfpromax.com/read.php?tid=1079297&sf=742&fpage=0&toread=&page=6"')
        print()


def iter_readtext_blocks(document: str):
    starts = list(re.finditer(r'<div\b[^>]*class="[^"]*\breadtext\b[^"]*"[^>]*>', document, re.I))
    for index, start in enumerate(starts):
        next_start = starts[index + 1].start() if index + 1 < len(starts) else len(document)
        close_marker = document.find('<div class="c"></div>', start.end(), next_start)
        end = close_marker if close_marker != -1 else next_start
        yield document[start.start():end]


def extract_post(block: str, page: int | None) -> ForumPost | None:
    profile_match = re.search(
        r'<a\b[^>]*href="[^"]*profile\.php\?action=show(?:&amp;|&)uid=(\d+)[^"]*"[^>]*>(.*?)</a>',
        block,
        re.I | re.S,
    )
    if not profile_match:
        return None

    pid_match = re.search(r'id="pid(\d+)"', block, re.I)
    floor_match = re.search(r">(\d+)\s*[楼¥]<", block)
    time_match = re.search(r"\b(20\d{2}-\d{2}-\d{2}\s+\d{2}:\d{2})\b", block)

    return ForumPost(
        uid=profile_match.group(1),
        username=clean_text(profile_match.group(2)),
        floor=int(floor_match.group(1)) if floor_match else None,
        pid=pid_match.group(1) if pid_match else None,
        posted_at=time_match.group(1) if time_match else None,
        page=page,
    )


def parse_posts(document: str, page: int | None = None) -> list[ForumPost]:
    page = page if page is not None else extract_page_number(document)
    posts = []
    for block in iter_readtext_blocks(document):
        post = extract_post(block, page)
        if post:
            posts.append(post)
    return posts


def unique_by_username(posts: list[ForumPost], excluded_names: set[str]) -> tuple[list[ForumPost], list[ForumPost], list[ForumPost]]:
    seen: set[str] = set()
    unique: list[ForumPost] = []
    duplicates: list[ForumPost] = []
    excluded: list[ForumPost] = []

    excluded_lower = {name.lower() for name in excluded_names}
    for post in posts:
        if post.username.lower() in excluded_lower:
            excluded.append(post)
            continue
        username_key = post.username.lower()
        if username_key in seen:
            duplicates.append(post)
            continue
        seen.add(username_key)
        unique.append(post)

    return unique, duplicates, excluded


def print_posts(posts: list[ForumPost]) -> None:
    for post in posts:
        floor = f"{post.floor}楼" if post.floor is not None else "-"
        page = f"p{post.page}" if post.page is not None else "p?"
        when = post.posted_at or "-"
        print(f"{post.username}\t{floor}\t{page}\t{when}\t{post.uid}")


def post_to_dict(post: ForumPost) -> dict[str, str | int | None]:
    return {
        "uid": post.uid,
        "username": post.username,
        "floor": post.floor,
        "pid": post.pid,
        "posted_at": post.posted_at,
        "page": post.page,
    }


def write_outputs(output_prefix: Path, unique: list[ForumPost], duplicates: list[ForumPost], excluded: list[ForumPost]) -> None:
    output_prefix.parent.mkdir(parents=True, exist_ok=True)

    csv_path = output_prefix.with_suffix(".csv")
    json_path = output_prefix.with_suffix(".json")
    txt_path = output_prefix.with_suffix(".txt")

    with csv_path.open("w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=["uid", "username", "floor", "pid", "posted_at", "page"])
        writer.writeheader()
        for post in unique:
            writer.writerow(post_to_dict(post))

    payload = {
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "unique_count": len(unique),
        "duplicate_count": len(duplicates),
        "excluded_count": len(excluded),
        "unique": [post_to_dict(post) for post in unique],
        "duplicates": [post_to_dict(post) for post in duplicates],
        "excluded": [post_to_dict(post) for post in excluded],
    }
    with json_path.open("w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)

    with txt_path.open("w", encoding="utf-8") as f:
        for post in unique:
            f.write(f"{post.username}\n")

    print()
    print(f"已导出 CSV: {csv_path}")
    print(f"已导出 JSON: {json_path}")
    print(f"已导出用户名: {txt_path}")


def require_playwright():
    try:
        from playwright.async_api import async_playwright
    except ModuleNotFoundError:
        print("缺少依赖: playwright")
        print("安装方式之一: python3 -m pip install playwright")
        print("首次安装后还需要: python3 -m playwright install chromium")
        raise SystemExit(2)
    return async_playwright


async def launch_browser(playwright, args: argparse.Namespace, headless: bool):
    channels = [args.channel] if args.channel else ["msedge", "chrome", None]
    last_error = None

    for channel in channels:
        try:
            browser = await playwright.chromium.launch(
                headless=headless,
                channel=channel,
                args=["--disable-blink-features=AutomationControlled"],
            )
            print(f"浏览器: {channel or 'playwright-chromium'}")
            return browser
        except Exception as exc:
            last_error = exc
            if args.channel:
                raise

    raise last_error


async def open_login_browser(args: argparse.Namespace) -> int:
    async_playwright = require_playwright()
    state_path = Path(args.state)

    async with async_playwright() as p:
        browser = await launch_browser(p, args, headless=False)
        context = await browser.new_context(
            user_agent=DEFAULT_USER_AGENT,
            viewport={"width": 1280, "height": 900},
            locale="zh-CN",
        )
        page = await context.new_page()
        await page.goto(args.url, wait_until="domcontentloaded", timeout=120_000)

        print()
        print("浏览器已打开。请在浏览器里登录论坛账号。")
        print("确认页面右上角已经是登录状态后，回到这里按 Enter 保存登录态。")
        input("登录完成后按 Enter...")

        state_path.parent.mkdir(parents=True, exist_ok=True)
        await context.storage_state(path=str(state_path))
        await browser.close()

    print(f"登录态已保存: {state_path}")
    return 0


def login_command(args: argparse.Namespace) -> int:
    return asyncio.run(open_login_browser(args))


async def fetch_one_page(args: argparse.Namespace) -> int:
    args.url = normalize_thread_url(args.url, args)
    state_path = Path(args.state)
    if not state_path.exists():
        print(f"登录态不存在: {state_path}")
        print("请先运行: python KFID_Scraper.py login")
        return 2
    warn_if_url_lost_query_parts(args.url)
    async_playwright = require_playwright()

    async with async_playwright() as p:
        browser = await launch_browser(p, args, headless=not args.show)
        context = await browser.new_context(
            storage_state=str(state_path),
            user_agent=DEFAULT_USER_AGENT,
            viewport={"width": 1280, "height": 900},
            locale="zh-CN",
        )
        page = await context.new_page()
        await page.goto(args.url, wait_until="domcontentloaded", timeout=120_000)
        await page.wait_for_timeout(800)
        document = await page.content()
        await browser.close()

    posts = parse_posts(document, page=extract_page_number(args.url) if isinstance(args.url, str) else None)
    unique, duplicates, excluded = unique_by_username(posts, set(args.exclude_name or DEFAULT_EXCLUDED_NAMES))

    print(f"来源: {args.url}")
    print(f"楼层回复数: {len(posts)}")
    print(f"唯一用户名数: {len(unique)}")
    print(f"重复回复数: {len(duplicates)}")
    print(f"已排除: {len(excluded)}")
    print()
    print("username\tfloor\tpage\tposted_at\tuid")
    print_posts(unique)

    if args.output:
        write_outputs(Path(args.output), unique, duplicates, excluded)
    return 0


def fetch_page_command(args: argparse.Namespace) -> int:
    return asyncio.run(fetch_one_page(args))


async def fetch_thread(args: argparse.Namespace) -> int:
    args.url = normalize_thread_url(args.url, args)
    state_path = Path(args.state)
    if not state_path.exists():
        print(f"登录态不存在: {state_path}")
        print("请先运行: python KFID_Scraper.py login")
        return 2
    warn_if_url_lost_query_parts(args.url)
    async_playwright = require_playwright()

    all_posts: list[ForumPost] = []
    async with async_playwright() as p:
        browser = await launch_browser(p, args, headless=not args.show)
        context = await browser.new_context(
            storage_state=str(state_path),
            user_agent=DEFAULT_USER_AGENT,
            viewport={"width": 1280, "height": 900},
            locale="zh-CN",
        )
        page = await context.new_page()

        print(f"打开首页: {args.url}")
        await page.goto(args.url, wait_until="domcontentloaded", timeout=120_000)
        await page.wait_for_timeout(800)
        first_document = await page.content()
        max_page = extract_max_page(first_document)
        if args.max_pages:
            max_page = min(max_page, args.max_pages)
        print(f"检测到页数: {max_page}")

        for page_number in range(1, max_page + 1):
            page_url = set_url_page(args.url, page_number)
            print(f"抓取第 {page_number}/{max_page} 页: {page_url}")
            if page_number == 1 and set_url_page(args.url, 1) == page.url:
                document = first_document
            else:
                await page.goto(page_url, wait_until="domcontentloaded", timeout=120_000)
                await page.wait_for_timeout(args.delay_ms)
                document = await page.content()
            page_posts = parse_posts(document, page=page_number)
            print(f"  本页楼层记录: {len(page_posts)}")
            all_posts.extend(page_posts)

        await browser.close()

    excluded_names = set(args.exclude_name or DEFAULT_EXCLUDED_NAMES)
    unique, duplicates, excluded = unique_by_username(all_posts, excluded_names)

    print()
    print(f"总楼层回复数: {len(all_posts)}")
    print(f"唯一用户名数: {len(unique)}")
    print(f"重复回复数: {len(duplicates)}")
    print(f"已排除: {len(excluded)} ({', '.join(sorted(excluded_names)) or '无'})")
    print()
    print("username\tfloor\tpage\tposted_at\tuid")
    print_posts(unique)

    if args.output:
        write_outputs(Path(args.output), unique, duplicates, excluded)
    return 0


def fetch_thread_command(args: argparse.Namespace) -> int:
    return asyncio.run(fetch_thread(args))


def parse_html_command(args: argparse.Namespace) -> int:
    html_path = Path(args.html)
    if not html_path.exists():
        print(f"文件不存在: {html_path}")
        return 2

    excluded_names = set(args.exclude_name or DEFAULT_EXCLUDED_NAMES)
    document = read_html(html_path)
    posts = parse_posts(document)
    unique, duplicates, excluded = unique_by_username(posts, excluded_names)

    print(f"来源: {html_path}")
    print(f"楼层回复数: {len(posts)}")
    print(f"唯一用户名数: {len(unique)}")
    print(f"重复回复数: {len(duplicates)}")
    print(f"已排除: {len(excluded)} ({', '.join(sorted(excluded_names)) or '无'})")
    print()
    print("username\tfloor\tpage\tposted_at\tuid")
    print_posts(unique)

    if args.output:
        write_outputs(Path(args.output), unique, duplicates, excluded)
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Collect forum usernames from ScarletMoon/phpwind thread pages.")
    subparsers = parser.add_subparsers(dest="command", required=True)

    parse_html = subparsers.add_parser("parse-html", help="Parse one saved/offline HTML page.")
    parse_html.add_argument("html", help="Path to the saved forum HTML page.")
    parse_html.add_argument(
        "--exclude-name",
        action="append",
        help="Username to exclude. Defaults to no exclusions.",
    )
    parse_html.add_argument(
        "-o",
        "--output",
        default="forum_names",
        help="Output prefix for .csv/.json/.txt files. Use empty string to skip writing files.",
    )
    parse_html.set_defaults(func=parse_html_command)

    login = subparsers.add_parser("login", help="Open a browser, let you log in, then save Playwright storage state.")
    login.add_argument(
        "--url",
        default=DEFAULT_FORUM_HOME,
        help="Forum page to open for manual login.",
    )
    login.add_argument(
        "--state",
        default=DEFAULT_STATE_FILE,
        help="Path to save Playwright storage state.",
    )
    login.add_argument(
        "--channel",
        default=None,
        choices=["chrome", "msedge"],
        help="Browser channel. Default tries Edge, Chrome, then Playwright Chromium.",
    )
    login.set_defaults(func=login_command)

    fetch_page = subparsers.add_parser("fetch-page", help="Fetch and parse one online thread page using saved login state.")
    fetch_page.add_argument("url", help="Thread page URL, for example read.php?...&page=1")
    fetch_page.add_argument(
        "--state",
        default=DEFAULT_STATE_FILE,
        help="Path to saved Playwright storage state.",
    )
    fetch_page.add_argument(
        "--exclude-name",
        action="append",
        help="Username to exclude. Defaults to no exclusions.",
    )
    fetch_page.add_argument("--sf", help="Manually provide the forum sf parameter when the URL omits it.")
    fetch_page.add_argument(
        "--sf-source-dir",
        default=".",
        help="Directory to scan for saved HTML when auto-filling sf.",
    )
    fetch_page.add_argument(
        "-o",
        "--output",
        default="forum_names_page",
        help="Output prefix for .csv/.json/.txt files. Use empty string to skip writing files.",
    )
    fetch_page.add_argument(
        "--show",
        action="store_true",
        help="Show the browser while fetching.",
    )
    fetch_page.add_argument(
        "--channel",
        default=None,
        choices=["chrome", "msedge"],
        help="Browser channel. Default tries Edge, Chrome, then Playwright Chromium.",
    )
    fetch_page.set_defaults(func=fetch_page_command)

    fetch_thread_parser = subparsers.add_parser("fetch-thread", help="Fetch all pages of one online thread using saved login state.")
    fetch_thread_parser.add_argument("url", help="Any page URL of the thread.")
    fetch_thread_parser.add_argument(
        "--state",
        default=DEFAULT_STATE_FILE,
        help="Path to saved Playwright storage state.",
    )
    fetch_thread_parser.add_argument(
        "--exclude-name",
        action="append",
        help="Username to exclude. Defaults to no exclusions.",
    )
    fetch_thread_parser.add_argument("--sf", help="Manually provide the forum sf parameter when the URL omits it.")
    fetch_thread_parser.add_argument(
        "--sf-source-dir",
        default=".",
        help="Directory to scan for saved HTML when auto-filling sf.",
    )
    fetch_thread_parser.add_argument(
        "-o",
        "--output",
        default="forum_names_all",
        help="Output prefix for .csv/.json/.txt files. Use empty string to skip writing files.",
    )
    fetch_thread_parser.add_argument(
        "--max-pages",
        type=int,
        default=None,
        help="Safety limit for testing, for example --max-pages 1.",
    )
    fetch_thread_parser.add_argument(
        "--delay-ms",
        type=int,
        default=1000,
        help="Delay after loading each page.",
    )
    fetch_thread_parser.add_argument(
        "--show",
        action="store_true",
        help="Show the browser while fetching.",
    )
    fetch_thread_parser.add_argument(
        "--channel",
        default=None,
        choices=["chrome", "msedge"],
        help="Browser channel. Default tries Edge, Chrome, then Playwright Chromium.",
    )
    fetch_thread_parser.set_defaults(func=fetch_thread_command)

    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
