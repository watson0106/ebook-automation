"""Amazon Japan ベストセラーランキングのスクレイパー"""
import asyncio
import re
from typing import Optional

import aiohttp
from bs4 import BeautifulSoup
from rich.console import Console

from src.research import BookInfo

console = Console()

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "ja-JP,ja;q=0.9",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
}

# カテゴリURL（Amazon Japan ベストセラー）
CATEGORIES = {
    "ビジネス": "https://www.amazon.co.jp/gp/bestsellers/books/2275256051",
    "自己啓発": "https://www.amazon.co.jp/gp/bestsellers/books/2275257051",
    "投資・金融": "https://www.amazon.co.jp/gp/bestsellers/books/2275258051",
    "総合": "https://www.amazon.co.jp/gp/bestsellers/books/",
}


async def fetch_page(session: aiohttp.ClientSession, url: str) -> Optional[str]:
    """ページHTMLを取得"""
    try:
        async with session.get(url, headers=HEADERS, timeout=aiohttp.ClientTimeout(total=30)) as resp:
            if resp.status == 200:
                return await resp.text(encoding="utf-8", errors="replace")
            console.print(f"[yellow]Warning: {url} -> HTTP {resp.status}[/yellow]")
    except Exception as e:
        console.print(f"[red]Error fetching {url}: {e}[/red]")
    return None


def parse_bestsellers(html: str, category: str, source_url: str) -> list[BookInfo]:
    """ベストセラーHTMLを解析してBookInfoリストを返す"""
    soup = BeautifulSoup(html, "lxml")
    books = []

    # Amazon ベストセラーページのリスト項目
    items = soup.select("div.zg-grid-general-faceout, li.zg-item-immersion")
    if not items:
        items = soup.select("[data-asin]")

    rank = 1
    for item in items[:20]:
        try:
            asin = item.get("data-asin", "")

            # タイトル
            title_el = (
                item.select_one("div._cDEzb_p13n-sc-css-line-clamp-1_1Fn1y")
                or item.select_one(".p13n-sc-truncated")
                or item.select_one("span.zg-text-center-align a")
                or item.select_one("a.a-link-normal span")
            )
            title = title_el.get_text(strip=True) if title_el else ""
            if not title:
                continue

            # 著者
            author_el = (
                item.select_one("span.a-size-small.a-color-secondary")
                or item.select_one(".a-row.a-size-small span")
            )
            author = author_el.get_text(strip=True) if author_el else "不明"
            author = re.sub(r"^著者[:：]\s*", "", author)

            # 価格
            price_el = item.select_one("span._cDEzb_p13n-sc-price_3mJ9Z, span.p13n-sc-price")
            price = price_el.get_text(strip=True) if price_el else ""

            # カバー画像
            img_el = item.select_one("img")
            cover_url = img_el.get("src", "") if img_el else ""

            # URL
            link_el = item.select_one("a.a-link-normal")
            book_url = ""
            if link_el and link_el.get("href"):
                href = link_el["href"]
                if href.startswith("/"):
                    book_url = f"https://www.amazon.co.jp{href}"
                else:
                    book_url = href

            books.append(BookInfo(
                title=title,
                author=author,
                source="amazon",
                rank=rank,
                category=category,
                isbn=asin,
                price=price,
                cover_url=cover_url,
                url=book_url,
                tags=["amazon", "bestseller", category],
            ))
            rank += 1

        except Exception as e:
            console.print(f"[yellow]Parse error at rank {rank}: {e}[/yellow]")
            continue

    return books


async def scrape_amazon_bestsellers(categories: Optional[list[str]] = None) -> list[BookInfo]:
    """Amazon Japanのベストセラーを非同期スクレイプ"""
    target_cats = {k: v for k, v in CATEGORIES.items() if not categories or k in categories}
    all_books: list[BookInfo] = []

    async with aiohttp.ClientSession() as session:
        for cat_name, url in target_cats.items():
            console.print(f"[cyan]Amazon スクレイプ中: {cat_name}[/cyan]")
            html = await fetch_page(session, url)
            if html:
                books = parse_bestsellers(html, cat_name, url)
                all_books.extend(books)
                console.print(f"  -> {len(books)} 件取得")
            await asyncio.sleep(2)  # rate limiting

    return all_books


if __name__ == "__main__":
    books = asyncio.run(scrape_amazon_bestsellers())
    for b in books[:5]:
        print(b)
