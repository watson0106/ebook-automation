#!/usr/bin/env python3
"""
eBook Automation System
人気本のリサーチ → 要約本執筆 → カバー生成 → D2D投稿 を自動化
"""
import asyncio
import json
import sys
from pathlib import Path

import click
from rich.console import Console
from rich.panel import Panel
from rich.text import Text

console = Console()


def print_banner():
    banner = Text()
    banner.append("📚 eBook Automation System\n", style="bold cyan")
    banner.append("賢者とユイの読書倶楽部 × D2D 自動投稿", style="dim")
    console.print(Panel(banner, border_style="cyan"))


@click.group()
def cli():
    """eBook自動化システム - 人気本リサーチからD2D投稿まで"""
    pass


@cli.command()
@click.option("--sources", "-s", multiple=True, default=["amazon", "kindle"],
              help="リサーチ対象 (amazon/rakuten/kindle)")
@click.option("--top", "-n", default=10, help="取得する本の件数")
@click.option("--output", "-o", type=click.Path(), default=None, help="結果JSONの保存先")
def research(sources, top, output):
    """① 人気本をリサーチする"""
    print_banner()
    console.print(f"\n[bold]リサーチ開始: {list(sources)}[/bold]\n")

    from src.research.manager import research_popular_books

    books = asyncio.run(research_popular_books(sources=list(sources), top_n=top))

    if output:
        from src.research.manager import save_report
        save_report(books, Path(output))

    console.print(f"\n[bold green]完了: {len(books)} 件の本を取得しました[/bold green]")


@cli.command()
@click.option("--title", "-t", required=True, help="対象書籍のタイトル")
@click.option("--author", "-a", default="不明", help="著者名")
@click.option("--category", "-c", default="ビジネス", help="カテゴリ")
@click.option("--description", "-d", default="", help="本の説明")
@click.option("--output-dir", type=click.Path(), default=None, help="出力ディレクトリ")
def write(title, author, category, description, output_dir):
    """② 賢者とユイの対話形式で要約本を執筆する"""
    print_banner()
    console.print(f"\n[bold]執筆開始: {title}[/bold]\n")

    from src.research import BookInfo
    from src.content.book_writer import BookWriter

    book_info = BookInfo(
        title=title,
        author=author,
        source="manual",
        rank=0,
        category=category,
        description=description,
    )

    writer = BookWriter()
    book = writer.write_book(book_info)
    out_dir = Path(output_dir) if output_dir else None
    filepath = writer.save_book(book, out_dir)

    console.print(f"\n[bold green]✅ 執筆完了！[/bold green]")
    console.print(f"   ファイル: {filepath}")
    console.print(f"   文字数: {book.total_chars:,}")


@cli.command()
@click.option("--title", "-t", required=True, help="本のタイトル")
@click.option("--subtitle", "-s", default="", help="サブタイトル")
@click.option("--prompt", "-p", default="", help="Imagen 3 プロンプト（省略時はClaudeが生成）")
@click.option("--output", "-o", type=click.Path(), default=None, help="出力画像パス")
def thumbnail(title, subtitle, prompt, output):
    """③ Imagen 3でカバー画像を生成する"""
    print_banner()
    console.print(f"\n[bold]サムネイル生成: {title}[/bold]\n")

    from src.thumbnail.imagen_generator import ThumbnailGenerator

    gen = ThumbnailGenerator()

    if not prompt:
        # Claudeにプロンプトを生成させる
        from src.research import BookInfo
        from src.content.book_writer import BookWriter
        book_info = BookInfo(title=title, author="", source="manual", rank=0)
        writer = BookWriter()
        plan = {"book_title": title, "subtitle": subtitle, "keywords": [], "description": ""}
        prompt_data = writer.generate_thumbnail_prompt(plan, book_info)
        prompt = prompt_data.get("prompt", f"Professional ebook cover for '{title}'")
        negative = prompt_data.get("negative_prompt", "")
        console.print(f"[dim]生成プロンプト: {prompt[:100]}...[/dim]")
    else:
        negative = ""

    out_path = Path(output) if output else None
    result_path = gen.generate_for_book(title, subtitle, prompt, negative, output_path=out_path)
    console.print(f"\n[bold green]✅ カバー画像生成完了: {result_path}[/bold green]")


@cli.command()
@click.option("--epub", "-e", required=True, type=click.Path(exists=True), help="EPUBファイルパス")
@click.option("--cover", "-c", type=click.Path(exists=True), default=None, help="カバー画像パス")
@click.option("--title", "-t", required=True, help="本のタイトル")
@click.option("--subtitle", "-s", default="", help="サブタイトル")
@click.option("--description", "-d", default="", help="本の説明")
@click.option("--price", "-p", default=4.99, type=float, help="価格（USD）")
def publish(epub, cover, title, subtitle, description, price):
    """④ D2Dアカウントに投稿する"""
    print_banner()
    console.print(f"\n[bold]D2D投稿: {title}[/bold]\n")

    from src.publishing.d2d_publisher import D2DPublisher, BookMetadata
    from config.settings import settings

    meta = BookMetadata(
        title=title,
        subtitle=subtitle,
        description=description,
        author_name=settings.author_name,
        keywords=[],
        epub_path=Path(epub),
        cover_path=Path(cover) if cover else None,
        price_usd=price,
    )

    publisher = D2DPublisher()
    result = asyncio.run(publisher.publish_book(meta))

    if result.success:
        console.print(f"\n[bold green]🎉 投稿成功！[/bold green]")
        console.print(f"   URL: {result.d2d_book_url}")
    else:
        console.print(f"\n[bold red]❌ 投稿失敗: {result.error_message}[/bold red]")
        sys.exit(1)


@cli.command()
@click.option("--title", "-t", required=True, help="対象書籍のタイトル")
@click.option("--author", "-a", default="不明", help="著者名")
@click.option("--category", "-c", default="ビジネス", help="カテゴリ")
@click.option("--description", "-d", default="", help="本の説明")
def run(title, author, category, description):
    """
    全工程を一括実行する
    執筆 → カバー生成 → EPUB作成 → 成果物レポート出力
    """
    print_banner()
    console.print(f"\n[bold cyan]🚀 全工程パイプライン開始[/bold cyan]")
    console.print(f"   対象: {title} / {author}\n")

    from src.research import BookInfo
    from src.content.book_writer import BookWriter
    from src.thumbnail.imagen_generator import ThumbnailGenerator
    from src.epub.epub_builder import build_epub

    book_info = BookInfo(
        title=title,
        author=author,
        source="manual",
        rank=0,
        category=category,
        description=description,
    )

    # ① 執筆
    console.print("[bold]--- STEP 1: 執筆 ---[/bold]")
    writer = BookWriter()
    book = writer.write_book(book_info)
    writer.save_book(book)

    # ② サムネイル生成
    console.print("\n[bold]--- STEP 2: カバー生成 ---[/bold]")
    thumbnail_prompt = writer.generate_thumbnail_prompt(
        {"book_title": book.book_title, "subtitle": book.subtitle,
         "keywords": book.keywords, "description": book.description},
        book_info,
    )
    gen = ThumbnailGenerator()
    cover_path = gen.generate_for_book(
        book.book_title,
        book.subtitle,
        thumbnail_prompt.get("prompt", f"Professional ebook cover for {title}"),
        thumbnail_prompt.get("negative_prompt", ""),
    )

    # ③ EPUB生成
    console.print("\n[bold]--- STEP 3: EPUB生成 ---[/bold]")
    epub_path = build_epub(book, cover_path)

    # 成果物レポート
    console.print("\n" + "=" * 50)
    console.print("[bold green]✅ 成果物が完成しました[/bold green]")
    console.print("=" * 50)
    console.print(f"\n[bold]📖 タイトル:[/bold] {book.book_title}")
    if book.subtitle:
        console.print(f"[bold]   サブタイトル:[/bold] {book.subtitle}")
    console.print(f"[bold]📝 文字数:[/bold] {book.total_chars:,} 文字")
    console.print(f"[bold]📚 章数:[/bold] {len(book.chapters)} 章")
    console.print(f"\n[bold]--- 成果物ファイル ---[/bold]")
    console.print(f"  EPUB  : [cyan]{epub_path.resolve()}[/cyan]  ({epub_path.stat().st_size / 1024:.1f} KB)")
    if cover_path and cover_path.exists():
        console.print(f"  カバー: [cyan]{cover_path.resolve()}[/cyan]  ({cover_path.stat().st_size / 1024:.1f} KB)")
    console.print(f"\n[dim]D2D投稿は 'python main.py publish' コマンドで別途実行できます。[/dim]")


@cli.command()
def setup():
    """初期セットアップ（.envファイルの確認・Playwrightのインストール）"""
    print_banner()
    import os, subprocess

    env_file = Path(".env")
    env_example = Path(".env.example")

    if not env_file.exists() and env_example.exists():
        import shutil
        shutil.copy(env_example, env_file)
        console.print("[yellow]⚠️  .env ファイルを作成しました。APIキーを設定してください。[/yellow]")
        console.print(f"   場所: {env_file.absolute()}")
    elif env_file.exists():
        console.print("[green]✅ .env ファイルが存在します[/green]")

    # Playwright ブラウザのインストール
    console.print("\n[cyan]Playwright ブラウザをインストール中...[/cyan]")
    result = subprocess.run(
        ["python", "-m", "playwright", "install", "chromium"],
        capture_output=True, text=True
    )
    if result.returncode == 0:
        console.print("[green]✅ Playwright セットアップ完了[/green]")
    else:
        console.print(f"[red]❌ Playwright インストール失敗: {result.stderr}[/red]")

    console.print("\n[bold]次のステップ:[/bold]")
    console.print("1. .env ファイルにAPIキーとD2D認証情報を設定")
    console.print("2. python main.py research  # 人気本をリサーチ")
    console.print("3. python main.py run --title '本のタイトル'  # 全工程実行")


if __name__ == "__main__":
    cli()
