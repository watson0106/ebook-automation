"""MarkdownコンテンツからEPUBファイルを生成するモジュール"""
import re
import uuid
from pathlib import Path

import ebooklib
from ebooklib import epub
from rich.console import Console

from config.settings import settings
from src.content import GeneratedBook

console = Console()

CSS_STYLES = """
@charset "UTF-8";

body {
    font-family: "Hiragino Kaku Gothic ProN", "Noto Sans CJK JP", sans-serif;
    font-size: 1em;
    line-height: 1.8;
    color: #333333;
    margin: 0;
    padding: 1em 1.5em;
}

h1 {
    font-size: 1.8em;
    font-weight: bold;
    color: #1a1a2e;
    border-bottom: 3px solid #e94560;
    padding-bottom: 0.3em;
    margin-top: 0;
    margin-bottom: 0.8em;
}

h2 {
    font-size: 1.4em;
    font-weight: bold;
    color: #16213e;
    border-left: 4px solid #e94560;
    padding-left: 0.5em;
    margin-top: 1.5em;
    margin-bottom: 0.8em;
}

h3 {
    font-size: 1.2em;
    color: #0f3460;
    margin-top: 1.2em;
}

p {
    margin: 0.7em 0;
    text-indent: 1em;
}

.dialog-sage {
    background-color: #f0f4ff;
    border-left: 4px solid #4a90d9;
    padding: 0.8em 1em;
    margin: 0.8em 0;
    border-radius: 0 8px 8px 0;
}

.dialog-yui {
    background-color: #fff0f5;
    border-left: 4px solid #e94560;
    padding: 0.8em 1em;
    margin: 0.8em 0;
    border-radius: 0 8px 8px 0;
}

.speaker-sage {
    font-weight: bold;
    color: #4a90d9;
    font-size: 0.9em;
}

.speaker-yui {
    font-weight: bold;
    color: #e94560;
    font-size: 0.9em;
}

blockquote {
    border-left: 3px solid #ccc;
    padding-left: 1em;
    color: #666;
    font-style: italic;
    margin: 1em 0;
}

.chapter-number {
    font-size: 0.85em;
    color: #999;
    text-transform: uppercase;
    letter-spacing: 0.1em;
}

.foreword, .afterword {
    background-color: #fafafa;
    border: 1px solid #eee;
    padding: 1.5em;
    border-radius: 8px;
    margin: 1em 0;
}

hr {
    border: none;
    border-top: 1px solid #ddd;
    margin: 2em 0;
}
"""


def markdown_to_html(md_text: str) -> str:
    """
    シンプルなMarkdown→HTML変換
    （賢者/ユイの対話パターンに対応）
    """
    lines = md_text.split("\n")
    html_parts = []
    in_paragraph = False

    for line in lines:
        stripped = line.strip()

        if not stripped:
            if in_paragraph:
                html_parts.append("</p>")
                in_paragraph = False
            continue

        # 見出し
        if stripped.startswith("### "):
            if in_paragraph:
                html_parts.append("</p>")
                in_paragraph = False
            html_parts.append(f"<h3>{_escape(stripped[4:])}</h3>")
        elif stripped.startswith("## "):
            if in_paragraph:
                html_parts.append("</p>")
                in_paragraph = False
            html_parts.append(f"<h2>{_escape(stripped[3:])}</h2>")
        elif stripped.startswith("# "):
            if in_paragraph:
                html_parts.append("</p>")
                in_paragraph = False
            html_parts.append(f"<h1>{_escape(stripped[2:])}</h1>")
        # 賢者/先生の発話パターン: **賢者**：... または **先生**：...
        elif re.match(r"\*\*(?:賢者|先生)\*\*[：:]", stripped):
            if in_paragraph:
                html_parts.append("</p>")
                in_paragraph = False
            speaker = re.match(r"^\*\*(.+?)\*\*[：:]", stripped).group(1)
            content = re.sub(r"^\*\*(?:賢者|先生)\*\*[：:]\s*", "", stripped)
            html_parts.append(
                f'<div class="dialog-sage">'
                f'<span class="speaker-sage">{speaker}</span><br/>{_inline_md(_escape(content))}'
                f"</div>"
            )
        # ユイの発話パターン: **ユイ**：...
        elif re.match(r"\*\*ユイ\*\*[：:]", stripped):
            if in_paragraph:
                html_parts.append("</p>")
                in_paragraph = False
            content = re.sub(r"^\*\*ユイ\*\*[：:]\s*", "", stripped)
            html_parts.append(
                f'<div class="dialog-yui">'
                f'<span class="speaker-yui">ユイ</span><br/>{_inline_md(_escape(content))}'
                f"</div>"
            )
        # 区切り線
        elif stripped in ("---", "***", "___"):
            if in_paragraph:
                html_parts.append("</p>")
                in_paragraph = False
            html_parts.append("<hr/>")
        # 引用
        elif stripped.startswith("> "):
            if in_paragraph:
                html_parts.append("</p>")
                in_paragraph = False
            html_parts.append(f"<blockquote><p>{_inline_md(_escape(stripped[2:]))}</p></blockquote>")
        # 通常のテキスト
        else:
            if not in_paragraph:
                html_parts.append("<p>")
                in_paragraph = True
            else:
                html_parts.append("　")  # 段落内の改行は全角スペースで
            html_parts.append(_inline_md(_escape(stripped)))

    if in_paragraph:
        html_parts.append("</p>")

    return "\n".join(html_parts)


def _escape(text: str) -> str:
    return text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def _inline_md(text: str) -> str:
    """インラインMarkdown（太字・斜体）をHTMLに変換"""
    text = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", text)
    text = re.sub(r"\*(.+?)\*", r"<em>\1</em>", text)
    text = re.sub(r"`(.+?)`", r"<code>\1</code>", text)
    return text


def build_epub(
    book: GeneratedBook,
    cover_image_path: Path | None = None,
    output_path: Path | None = None,
) -> Path:
    """
    GeneratedBookオブジェクトからEPUBファイルを生成

    Args:
        book: 生成された本データ
        cover_image_path: カバー画像パス（JPEG）
        output_path: 出力先EPUBパス

    Returns:
        生成されたEPUBファイルのパス
    """
    console.print(f"[cyan]📖 EPUB生成中: {book.book_title}[/cyan]")

    epub_book = epub.EpubBook()

    # メタデータ設定
    book_uid = str(uuid.uuid4())
    epub_book.set_identifier(book_uid)
    epub_book.set_title(book.book_title)
    epub_book.set_language("ja")
    epub_book.add_author(settings.author_name)
    epub_book.add_metadata("DC", "description", book.description)
    epub_book.add_metadata("DC", "subject", ", ".join(book.keywords))

    # CSSを追加
    css_item = epub.EpubItem(
        uid="style",
        file_name="style/style.css",
        media_type="text/css",
        content=CSS_STYLES.encode("utf-8"),
    )
    epub_book.add_item(css_item)

    # カバー画像を設定
    if cover_image_path and cover_image_path.exists():
        with open(cover_image_path, "rb") as f:
            cover_data = f.read()
        epub_book.set_cover("cover.jpg", cover_data)

    # 目次ページ
    toc_items = []

    # まえがき
    foreword_html = f"""<?xml version="1.0" encoding="utf-8"?>
<!DOCTYPE html>
<html xmlns="http://www.w3.org/1999/xhtml">
<head>
    <title>まえがき</title>
    <link rel="stylesheet" href="style/style.css" type="text/css"/>
</head>
<body>
<h1>まえがき</h1>
<div class="foreword">
{markdown_to_html(book.foreword)}
</div>
</body>
</html>"""
    foreword_chapter = epub.EpubHtml(
        title="まえがき",
        file_name="foreword.xhtml",
        lang="ja",
        content=foreword_html,
    )
    foreword_chapter.add_item(css_item)
    epub_book.add_item(foreword_chapter)
    toc_items.append(foreword_chapter)

    # 各章
    chapter_items = []
    for ch in book.chapters:
        chapter_html = f"""<?xml version="1.0" encoding="utf-8"?>
<!DOCTYPE html>
<html xmlns="http://www.w3.org/1999/xhtml">
<head>
    <title>第{ch.number}章 {ch.title}</title>
    <link rel="stylesheet" href="style/style.css" type="text/css"/>
</head>
<body>
<p class="chapter-number">第 {ch.number} 章</p>
<h1>{_escape(ch.title)}</h1>
{markdown_to_html(ch.content)}
</body>
</html>"""
        chapter_item = epub.EpubHtml(
            title=f"第{ch.number}章 {ch.title}",
            file_name=f"chapter_{ch.number:02d}.xhtml",
            lang="ja",
            content=chapter_html,
        )
        chapter_item.add_item(css_item)
        epub_book.add_item(chapter_item)
        chapter_items.append(chapter_item)
        toc_items.append(chapter_item)

    # あとがき
    afterword_html = f"""<?xml version="1.0" encoding="utf-8"?>
<!DOCTYPE html>
<html xmlns="http://www.w3.org/1999/xhtml">
<head>
    <title>あとがき</title>
    <link rel="stylesheet" href="style/style.css" type="text/css"/>
</head>
<body>
<h1>あとがき</h1>
<div class="afterword">
{markdown_to_html(book.afterword)}
</div>
</body>
</html>"""
    afterword_chapter = epub.EpubHtml(
        title="あとがき",
        file_name="afterword.xhtml",
        lang="ja",
        content=afterword_html,
    )
    afterword_chapter.add_item(css_item)
    epub_book.add_item(afterword_chapter)
    toc_items.append(afterword_chapter)

    # 目次設定
    epub_book.toc = tuple(toc_items)
    epub_book.add_item(epub.EpubNcx())
    epub_book.add_item(epub.EpubNav())

    # スパイン（読む順番）
    epub_book.spine = ["nav", foreword_chapter] + chapter_items + [afterword_chapter]

    # 出力パス決定
    if output_path is None:
        safe_title = re.sub(r'[\\/*?:"<>|【】]', "", book.book_title)[:50]
        settings.output_epubs_dir.mkdir(parents=True, exist_ok=True)
        output_path = settings.output_epubs_dir / f"{safe_title}.epub"

    epub.write_epub(str(output_path), epub_book)
    console.print(f"[bold green]✅ EPUB生成完了: {output_path}[/bold green]")
    console.print(f"   ファイルサイズ: {output_path.stat().st_size / 1024:.1f} KB")

    return output_path
