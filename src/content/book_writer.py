"""Gemini / Vertex AI / Claude APIを使って賢者とユイの対話形式で本を執筆するモジュール"""
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
VERTEX_REGION = "us-central1"
VERTEX_MODEL = "gemini-2.0-flash-001"

# 無料枠レート制限: 4秒間隔
CALL_INTERVAL_SEC = 5
RETRY_WAIT_SECS = [30, 60, 120]


class BookWriter:
    def __init__(self):
        self.api_key = settings.google_api_key
        self.model = settings.gemini_model
        self._last_call_time: float = 0.0
        self._vertex_token: str = ""
        self._vertex_token_expiry: float = 0.0

    def _get_vertex_token(self) -> str:
        """Vertex AI 用のアクセストークンをサービスアカウントから取得"""
        if self._vertex_token and time.time() < self._vertex_token_expiry - 60:
            return self._vertex_token
        from google.oauth2 import service_account
        from google.auth.transport.requests import Request
        creds = service_account.Credentials.from_service_account_file(
            "config/service-account.json",
            scopes=["https://www.googleapis.com/auth/cloud-platform"],
        )
        creds.refresh(Request())
        self._vertex_token = creds.token
        self._vertex_token_expiry = time.time() + 3600
        return self._vertex_token

    def _call_vertex(self, prompt: str, system: str = SYSTEM_PROMPT, max_tokens: int = 4096) -> str:
        """Vertex AI 経由で Gemini を呼び出す"""
        import json as _json
        token = self._get_vertex_token()
        sa = _json.load(open("config/service-account.json"))
        project_id = sa["project_id"]
        url = (
            f"https://{VERTEX_REGION}-aiplatform.googleapis.com/v1/projects/{project_id}"
            f"/locations/{VERTEX_REGION}/publishers/google/models/{VERTEX_MODEL}:generateContent"
        )
        payload = {
            "system_instruction": {"parts": [{"text": system}]},
            "contents": [{"role": "user", "parts": [{"text": prompt}]}],
            "generationConfig": {"maxOutputTokens": max_tokens, "temperature": 0.9},
        }
        response = requests.post(
            url,
            headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
            json=payload,
            timeout=120,
        )
        response.raise_for_status()
        return response.json()["candidates"][0]["content"]["parts"][0]["text"]

    def _call_claude(self, prompt: str, system: str = SYSTEM_PROMPT, max_tokens: int = 4096) -> str:
        """Claude APIを呼び出してテキストを生成"""
        response = requests.post(
            "https://api.anthropic.com/v1/messages",
            headers={
                "x-api-key": settings.anthropic_api_key,
                "anthropic-version": "2023-06-01",
                "content-type": "application/json",
            },
            json={
                "model": settings.claude_model,
                "max_tokens": max_tokens,
                "system": system,
                "messages": [{"role": "user", "content": prompt}],
            },
            timeout=120,
        )
        response.raise_for_status()
        return response.json()["content"][0]["text"]

    def _call_gemini(self, prompt: str, system: str = SYSTEM_PROMPT, max_tokens: int = 4096) -> str:
        """Gemini REST API → Vertex AI → Claude の順でフォールバック"""
        elapsed = time.time() - self._last_call_time
        if elapsed < CALL_INTERVAL_SEC:
            wait = CALL_INTERVAL_SEC - elapsed
            console.print(f"  [dim]⏳ レート制限対策: {wait:.1f}秒待機...[/dim]")
            time.sleep(wait)

        url = GEMINI_API_URL.format(model=self.model)
        payload = {
            "system_instruction": {"parts": [{"text": system}]},
            "contents": [{"role": "user", "parts": [{"text": prompt}]}],
            "generationConfig": {"maxOutputTokens": max_tokens, "temperature": 0.9},
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
                break

            if response.status_code == 403:
                break

            response.raise_for_status()
            return response.json()["candidates"][0]["content"]["parts"][0]["text"]

        # Vertex AI にフォールバック（タイムアウト時は最大3回リトライ）
        console.print("  [yellow]⚠️ Gemini direct API 失敗 → Vertex AI にフォールバック[/yellow]")
        last_err = None
        for attempt in range(3):
            try:
                return self._call_vertex(prompt, system, max_tokens)
            except Exception as e:
                last_err = e
                wait = (attempt + 1) * 15
                console.print(f"  [yellow]⚠️ Vertex AI 失敗 (attempt {attempt+1}/3): {type(e).__name__} → {wait}秒待機してリトライ[/yellow]")
                time.sleep(wait)
        raise RuntimeError(f"Vertex AI 3回リトライ全失敗: {last_err}")

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
