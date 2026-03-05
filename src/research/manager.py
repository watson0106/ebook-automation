"""リサーチマネージャー：複数ソースからの人気本を統合・ランク付け"""
import asyncio
import json
from datetime import datetime
from pathlib import Path

from rich.console import Console
from rich.table import Table

from config.settings import settings
from src.research import BookInfo
from src.research.amazon_scraper import scrape_amazon_bestsellers
from src.research.rakuten_scraper import scrape_rakuten_bestsellers
from src.research.kindle_scraper import scrape_kindle_bestsellers

console = Console()


def deduplicate(books: list[BookInfo]) -> list[BookInfo]:
    """タイトル類似度でデュープを除去し、複数ソースにある本をスコアアップ"""
    seen: dict[str, BookInfo] = {}
    score: dict[str, int] = {}

    for book in books:
        # 正規化タイトルをキーに使用
        key = book.title.lower().replace("　", " ").replace("  ", " ").strip()
        # 短すぎるキーはスキップ
        if len(key) < 2:
            continue

        if key not in seen:
            seen[key] = book
            score[key] = 1
        else:
            score[key] += 1
            # 複数ソースに登場するなら説明を補完
            if not seen[key].description and book.description:
                seen[key].description = book.description

    # スコア順（複数ソース登場 > ランク順）でソート
    def sort_key(item: tuple) -> tuple:
        k, b = item
        return (-score[k], b.rank)

    sorted_books = [b for _, b in sorted(seen.items(), key=sort_key)]
    return sorted_books


def save_report(books: list[BookInfo], report_path: Path) -> None:
    """リサーチ結果をJSONで保存"""
    report_path.parent.mkdir(parents=True, exist_ok=True)
    data = {
        "generated_at": datetime.now().isoformat(),
        "total": len(books),
        "books": [
            {
                "title": b.title,
                "author": b.author,
                "source": b.source,
                "rank": b.rank,
                "category": b.category,
                "isbn": b.isbn,
                "description": b.description,
                "cover_url": b.cover_url,
                "price": b.price,
                "publisher": b.publisher,
                "url": b.url,
                "tags": b.tags,
            }
            for b in books
        ],
    }
    with open(report_path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    console.print(f"[green]レポート保存: {report_path}[/green]")


def load_report(report_path: Path) -> list[BookInfo]:
    """保存されたレポートを読み込む"""
    with open(report_path, "r", encoding="utf-8") as f:
        data = json.load(f)
    return [BookInfo(**item) for item in data["books"]]


async def research_popular_books(
    sources: list[str] | None = None,
    top_n: int = 10,
) -> list[BookInfo]:
    """
    複数ソースから人気本をリサーチして上位N件を返す

    Args:
        sources: ["amazon", "rakuten", "kindle"] のサブセット。Noneで全て
        top_n: 返す本の最大件数
    """
    all_books: list[BookInfo] = []
    use_sources = sources or ["amazon", "rakuten", "kindle"]

    tasks = []
    if "amazon" in use_sources:
        tasks.append(scrape_amazon_bestsellers())
    if "rakuten" in use_sources:
        tasks.append(scrape_rakuten_bestsellers())
    if "kindle" in use_sources:
        tasks.append(scrape_kindle_bestsellers())

    results = await asyncio.gather(*tasks, return_exceptions=True)
    for result in results:
        if isinstance(result, Exception):
            console.print(f"[red]スクレイプエラー: {result}[/red]")
        else:
            all_books.extend(result)

    console.print(f"\n総取得件数: {len(all_books)} 件")

    unique_books = deduplicate(all_books)
    console.print(f"重複除去後: {len(unique_books)} 件")

    top_books = unique_books[:top_n]

    # レポート保存
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    report_path = settings.output_reports_dir / f"research_{timestamp}.json"
    save_report(top_books, report_path)

    # テーブル表示
    table = Table(title=f"人気本トップ {len(top_books)}", show_lines=True)
    table.add_column("順位", style="bold yellow", width=4)
    table.add_column("タイトル", style="bold white", max_width=40)
    table.add_column("著者", style="cyan", max_width=20)
    table.add_column("ソース", style="magenta")
    table.add_column("カテゴリ", style="green")

    for i, book in enumerate(top_books, 1):
        table.add_row(str(i), book.title, book.author, book.source, book.category)

    console.print(table)
    return top_books
