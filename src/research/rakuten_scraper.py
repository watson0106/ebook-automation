"""楽天ブックス ランキングのスクレイパー"""
import asyncio
import os
from typing import Optional

import aiohttp
from rich.console import Console

from src.research import BookInfo

console = Console()

# 楽天ブックスAPI（無料）
RAKUTEN_API_BASE = "https://app.rakuten.co.jp/services/api/BooksBook/Search/20170404"
GENRE_IDS = {
    "ビジネス": "001004008",
    "自己啓発": "001017",
    "投資": "001004013",
    "総合": "001",
}


async def fetch_rakuten_ranking(
    session: aiohttp.ClientSession,
    app_id: str,
    genre_id: str,
    genre_name: str,
) -> list[BookInfo]:
    """楽天ブックスAPIでランキングを取得"""
    params = {
        "applicationId": app_id,
        "booksGenreId": genre_id,
        "sort": "sales",
        "hits": 20,
        "outOfStockFlag": 0,
        "format": "json",
    }
    books = []
    try:
        async with session.get(RAKUTEN_API_BASE, params=params, timeout=aiohttp.ClientTimeout(total=30)) as resp:
            if resp.status != 200:
                console.print(f"[yellow]楽天API: HTTP {resp.status}[/yellow]")
                return books
            data = await resp.json()

        for rank, item in enumerate(data.get("Items", []), 1):
            book = item.get("Item", item)
            books.append(BookInfo(
                title=book.get("title", ""),
                author=book.get("author", "不明"),
                source="rakuten",
                rank=rank,
                category=genre_name,
                isbn=book.get("isbn", ""),
                description=book.get("itemCaption", ""),
                cover_url=book.get("largeImageUrl", book.get("mediumImageUrl", "")),
                price=str(book.get("itemPrice", "")),
                publisher=book.get("publisherName", ""),
                published_date=book.get("salesDate", ""),
                url=book.get("itemUrl", ""),
                tags=["rakuten", "bestseller", genre_name],
            ))
    except Exception as e:
        console.print(f"[red]楽天API エラー ({genre_name}): {e}[/red]")

    return books


async def scrape_rakuten_bestsellers(genres: Optional[list[str]] = None) -> list[BookInfo]:
    """楽天ブックスベストセラーを取得"""
    app_id = os.getenv("RAKUTEN_APP_ID", "")
    if not app_id:
        console.print("[yellow]RAKUTEN_APP_ID が未設定のため楽天スクレイプをスキップ[/yellow]")
        return []

    target_genres = {k: v for k, v in GENRE_IDS.items() if not genres or k in genres}
    all_books: list[BookInfo] = []

    async with aiohttp.ClientSession() as session:
        for genre_name, genre_id in target_genres.items():
            console.print(f"[cyan]楽天 スクレイプ中: {genre_name}[/cyan]")
            books = await fetch_rakuten_ranking(session, app_id, genre_id, genre_name)
            all_books.extend(books)
            console.print(f"  -> {len(books)} 件取得")
            await asyncio.sleep(1)

    return all_books


if __name__ == "__main__":
    books = asyncio.run(scrape_rakuten_bestsellers())
    for b in books[:5]:
        print(b)
