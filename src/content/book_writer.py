"""Gemini APIを使って賢者とユイの対話形式で本を執筆するモジュール"""
import json
import re
import time
import requests
from pathlib import Path

from rich.console import Console

from config.settings import settings
from src.research import BookInfo
from src.content import Chapter, GeneratedBook
from src.content.prompts import (
    SYSTEM_PROMPT,
    BOOK_PLAN_PROMPT,
    CHAPTER_PROMPT,
    FOREWORD_PROMPT,
    AFTERWORD_PROMPT,
    THUMBNAIL_PROMPT,
)

console = Console()

GEMINI_API_URL = "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"

# 無料枠レート制限: gemini-2.0-flash = 15回/分 → 4秒間隔
CALL_INTERVAL_SEC = 5
# 429エラー時の待機秒数（指数バックオフ）
RETRY_WAIT_SECS = [30, 60, 120]


class BookWriter:
    def __init__(self):
        self.api_key = settings.google_api_key
        self.model = settings.gemini_model
        self._last_call_time: float = 0.0

    def _call_gemini(self, prompt: str, system: str = SYSTEM_PROMPT, max_tokens: int = 4096) -> str:
        """Gemini REST APIを呼び出してテキストを生成（レート制限対応）"""
        # 前回呼び出しからの最小間隔を確保
        elapsed = time.time() - self._last_call_time
        if elapsed < CALL_INTERVAL_SEC:
            wait = CALL_INTERVAL_SEC - elapsed
            console.print(f"  [dim]⏳ レート制限対策: {wait:.1f}秒待機...[/dim]")
            time.sleep(wait)

        url = GEMINI_API_URL.format(model=self.model)
        payload = {
            "system_instruction": {
                "parts": [{"text": system}]
            },
            "contents": [
                {"role": "user", "parts": [{"text": prompt}]}
            ],
            "generationConfig": {
                "maxOutputTokens": max_tokens,
                "temperature": 0.9,
            },
        }

        for attempt, retry_wait in enumerate([0] + RETRY_WAIT_SECS):
            if retry_wait > 0:
                console.print(f"  [yellow]⏳ 429エラー: {retry_wait}秒後にリトライ ({attempt}/{len(RETRY_WAIT_SECS)})...[/yellow]")
                time.sleep(retry_wait)

            self._last_call_time = time.time()
            response = requests.post(
                url,
                params={"key": self.api_key},
                json=payload,
                timeout=120,
            )

            if response.status_code == 429:
                if attempt < len(RETRY_WAIT_SECS):
                    continue
                response.raise_for_status()

            response.raise_for_status()
            data = response.json()
            return data["candidates"][0]["content"]["parts"][0]["text"]

    def _extract_json(self, text: str) -> dict:
        """テキストからJSONを抽出"""
        match = re.search(r"```(?:json)?\s*([\s\S]+?)\s*```", text)
        if match:
            return json.loads(match.group(1))
        match = re.search(r"\{[\s\S]+\}", text)
        if match:
            return json.loads(match.group(0))
        raise ValueError(f"JSON not found in response: {text[:200]}")

    def lookup_book_info(self, title: str) -> dict:
        """タイトルだけから著者・カテゴリ・説明をGeminiで調べる"""
        console.print(f"[cyan]🔍 書籍情報を検索中: {title}[/cyan]")
        prompt = f"""以下の書籍タイトルについて、実際の書籍情報を調べてJSON形式で回答してください。

タイトル: {title}

```json
{{
  "author": "著者名（不明な場合は「不明」）",
  "category": "カテゴリ（ビジネス/自己啓発/投資/心理学/小説/歴史/科学 など）",
  "description": "この本の内容を3〜5文で説明"
}}
```

実在する書籍であれば正確な情報を、不明な場合は推測で構いません。"""
        response = self._call_gemini(prompt, max_tokens=512)
        try:
            info = self._extract_json(response)
            console.print(f"  著者: [bold]{info.get('author', '不明')}[/bold]  カテゴリ: {info.get('category', 'ビジネス')}")
            return info
        except Exception:
            return {"author": "不明", "category": "ビジネス", "description": ""}

    def plan_book(self, book_info: BookInfo) -> dict:
        """本の構成を計画する"""
        console.print(f"[cyan]📚 本の構成を計画中: {book_info.title}[/cyan]")
        prompt = BOOK_PLAN_PROMPT.format(
            title=book_info.title,
            author=book_info.author,
            category=book_info.category,
            description=book_info.description or "（説明なし）",
        )
        response = self._call_gemini(prompt, max_tokens=2048)
        plan = self._extract_json(response)
        console.print(f"  タイトル: [bold]{plan['book_title']}[/bold]")
        console.print(f"  章数: {len(plan['chapter_titles'])} 章")
        return plan

    def write_foreword(self, book_info: BookInfo) -> str:
        """まえがきを執筆"""
        console.print("[cyan]  まえがきを執筆中...[/cyan]")
        prompt = FOREWORD_PROMPT.format(
            title=book_info.title,
            author=book_info.author,
        )
        return self._call_gemini(prompt)

    def write_chapter(
        self,
        book_info: BookInfo,
        chapter_number: int,
        chapter_title: str,
        all_chapters: list[str],
    ) -> str:
        """1章分を執筆"""
        console.print(f"[cyan]  第{chapter_number}章「{chapter_title}」を執筆中...[/cyan]")
        prompt = CHAPTER_PROMPT.format(
            chapter_number=chapter_number,
            title=book_info.title,
            author=book_info.author,
            chapter_title=chapter_title,
            all_chapters="\n".join(f"{i+1}. {t}" for i, t in enumerate(all_chapters)),
        )
        return self._call_gemini(prompt, max_tokens=4096)

    def write_afterword(self, book_info: BookInfo, chapter_titles: list[str]) -> str:
        """あとがきを執筆"""
        console.print("[cyan]  あとがきを執筆中...[/cyan]")
        prompt = AFTERWORD_PROMPT.format(
            title=book_info.title,
            author=book_info.author,
            chapters="\n".join(f"{i+1}. {t}" for i, t in enumerate(chapter_titles)),
        )
        return self._call_gemini(prompt)

    def generate_thumbnail_prompt(self, plan: dict, book_info: BookInfo) -> dict:
        """サムネイル用のImagen 3プロンプトを生成"""
        prompt = THUMBNAIL_PROMPT.format(
            book_title=plan["book_title"],
            subtitle=plan["subtitle"],
            keywords=", ".join(plan.get("keywords", [])),
            category=book_info.category,
        )
        response = self._call_gemini(prompt, max_tokens=1024)
        try:
            return self._extract_json(response)
        except Exception:
            return {"prompt": response, "negative_prompt": "blurry, low quality, text errors"}

    def write_book(self, book_info: BookInfo) -> GeneratedBook:
        """本全体を執筆して GeneratedBook オブジェクトを返す"""
        console.print(f"\n[bold green]✍️  執筆開始: {book_info.title}[/bold green]")

        # 1. 構成計画
        plan = self.plan_book(book_info)
        chapter_titles = plan["chapter_titles"]

        # 2. まえがき
        foreword = self.write_foreword(book_info)

        # 3. 各章を執筆
        chapters = []
        for i, title in enumerate(chapter_titles, 1):
            content = self.write_chapter(book_info, i, title, chapter_titles)
            chapters.append(Chapter(number=i, title=title, content=content))

        # 4. あとがき
        afterword = self.write_afterword(book_info, chapter_titles)

        book = GeneratedBook(
            source_title=book_info.title,
            source_author=book_info.author,
            book_title=plan["book_title"],
            subtitle=plan["subtitle"],
            description=plan["description"],
            keywords=plan.get("keywords", []),
            chapters=chapters,
            foreword=foreword,
            afterword=afterword,
        )
        book.total_chars = len(book.full_text())

        console.print(f"[bold green]✅ 執筆完了！ 総文字数: {book.total_chars:,} 文字[/bold green]")
        return book

    def save_book(self, book: GeneratedBook, output_dir: Path | None = None) -> Path:
        """生成した本をMarkdownファイルとして保存"""
        save_dir = output_dir or settings.data_dir
        save_dir.mkdir(parents=True, exist_ok=True)

        safe_title = re.sub(r'[\\/*?:"<>|【】]', "", book.book_title)[:50]
        filepath = save_dir / f"{safe_title}.md"

        with open(filepath, "w", encoding="utf-8") as f:
            f.write(book.full_text())

        console.print(f"[green]📝 保存: {filepath}[/green]")
        return filepath
