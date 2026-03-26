"""Amazon Kindleベストセラーランキングのスクレイパー"""
import asyncio
from typing import Optional

import aiohttp
from bs4 import BeautifulSoup
from rich.console import Console

from ソース.リサーチ import BookInfo

console = Console()

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "ja-JP,ja;q=0.9",
}

KINDLE_CATEGORIES = {
    "Kindleビジネス": "https://www.amazon.co.jp/gp/bestsellers/digital-text/2886336051",
    "Kindle自己啓発": "https://www.amazon.co.jp/gp/bestsellers/digital-text/2886405051",
    "Kindle総合": "https://www.amazon.co.jp/gp/bestsellers/digital-text/",
}


async def fetch_page(session: aiohttp.ClientSession, url: str) -> Optional[str]:
    try:
        async with session.get(url, headers=HEADERS, timeout=aiohttp.ClientTimeout(total=30)) as resp:
            if resp.status == 200:
                return await resp.text(encoding="utf-8", errors="replace")
    except Exception as e:
        console.print(f"[red]Fetch error: {e}[/red]")
    return None


def parse_kindle_bestsellers(html: str, category: str) -> list[BookInfo]:
    soup = BeautifulSoup(html, "lxml")
    books = []
    items = soup.select("div.zg-grid-general-faceout, li.zg-item-immersion, [data-asin]")
    rank = 1

    for item in items[:20]:
        try:
            asin = item.get("data-asin", "")
            title_el = (
                item.select_one("div._cDEzb_p13n-sc-css-line-clamp-1_1Fn1y")
                or item.select_one(".p13n-sc-truncated")
                or item.select_one("span.zg-text-center-align a")
            )
            title = title_el.get_text(strip=True) if title_el else ""
            if not title:
                continue

            author_el = item.select_one("span.a-size-small.a-color-secondary, .a-row.a-size-small span")
            author = author_el.get_text(strip=True) if author_el else "不明"

            price_el = item.select_one("span._cDEzb_p13n-sc-price_3mJ9Z, span.p13n-sc-price")
            price = price_el.get_text(strip=True) if price_el else ""

            img_el = item.select_one("img")
            cover_url = img_el.get("src", "") if img_el else ""

            link_el = item.select_one("a.a-link-normal")
            book_url = ""
            if link_el and link_el.get("href"):
                href = link_el["href"]
                book_url = f"https://www.amazon.co.jp{href}" if href.startswith("/") else href

            books.append(BookInfo(
                title=title,
                author=author,
                source="kindle",
                rank=rank,
                category=category,
                isbn=asin,
                price=price,
                cover_url=cover_url,
                url=book_url,
                tags=["kindle", "ebook", "bestseller", category],
            ))
            rank += 1
        except Exception:
            continue

    return books


async def scrape_kindle_bestsellers(categories: Optional[list[str]] = None) -> list[BookInfo]:
    """Kindleベストセラーを取得"""
    target = {k: v for k, v in KINDLE_CATEGORIES.items() if not categories or k in categories}
    all_books: list[BookInfo] = []

    async with aiohttp.ClientSession() as session:
        for cat_name, url in target.items():
            console.print(f"[cyan]Kindle スクレイプ中: {cat_name}[/cyan]")
            html = await fetch_page(session, url)
            if html:
                books = parse_kindle_bestsellers(html, cat_name)
                all_books.extend(books)
                console.print(f"  -> {len(books)} 件取得")
            await asyncio.sleep(2)

    return all_books
