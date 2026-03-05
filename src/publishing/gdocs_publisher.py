"""Google Docs APIを使って GeneratedBook をGoogleドキュメントに書き出すモジュール"""
import json
import re
from pathlib import Path
from typing import Optional

from rich.console import Console

from config.settings import settings
from src.content import GeneratedBook

console = Console()

# Google Docs API スコープ
_SCOPES = ["https://www.googleapis.com/auth/documents"]


def _get_docs_service():
    """サービスアカウント認証で Google Docs サービスを取得"""
    try:
        from google.oauth2 import service_account
        from googleapiclient.discovery import build
    except ImportError as e:
        raise RuntimeError(
            "Google APIライブラリが見つかりません。"
            "'pip install google-api-python-client google-auth' を実行してください。"
        ) from e

    sa_path = settings.google_service_account_json
    if not sa_path:
        raise ValueError(
            "GOOGLE_SERVICE_ACCOUNT_JSON が未設定です。"
            ".env に サービスアカウントJSONファイルのパスを設定してください。"
        )

    creds = service_account.Credentials.from_service_account_file(
        sa_path, scopes=_SCOPES
    )
    return build("docs", "v1", credentials=creds)


def _markdown_to_requests(text: str, heading_level: Optional[int] = None) -> list[dict]:
    """
    マークダウン本文を Google Docs batchUpdate リクエスト用の
    insertText + updateParagraphStyle リクエストに変換する。

    戻り値: (テキスト, スタイル情報) のリスト
    各要素は {"text": str, "style": str} の辞書
    """
    paragraphs = []
    lines = text.split("\n")
    i = 0
    while i < len(lines):
        line = lines[i]
        # 見出し
        m = re.match(r"^(#{1,6})\s+(.*)", line)
        if m:
            level = len(m.group(1))
            para_style = f"HEADING_{level}"
            paragraphs.append({"text": m.group(2).strip(), "style": para_style})
            i += 1
            continue

        # 空行 → 段落区切り
        if line.strip() == "":
            i += 1
            continue

        # 通常テキスト（複数行を結合せず1行ずつ段落にする）
        paragraphs.append({"text": line.rstrip(), "style": "NORMAL_TEXT"})
        i += 1

    return paragraphs


def _build_requests(book: GeneratedBook, document_id: str, service) -> list[dict]:
    """
    ドキュメントに追記するための batchUpdate リクエストリストを構築する。
    既存コンテンツの末尾に追加する形式にする。
    """
    # 現在のドキュメント末尾インデックスを取得
    doc = service.documents().get(documentId=document_id).execute()
    body_content = doc.get("body", {}).get("content", [])
    end_index = 1
    for elem in body_content:
        ei = elem.get("endIndex", 1)
        if ei > end_index:
            end_index = ei
    # 最後の改行の前に挿入（末尾の \n を避ける）
    insert_index = max(end_index - 1, 1)

    requests = []
    current_index = insert_index

    def append_paragraph(text: str, named_style: str = "NORMAL_TEXT", bold: bool = False):
        nonlocal current_index
        full_text = text + "\n"
        requests.append({
            "insertText": {
                "location": {"index": current_index},
                "text": full_text,
            }
        })
        text_len = len(full_text)
        start = current_index
        end = current_index + text_len

        requests.append({
            "updateParagraphStyle": {
                "range": {"startIndex": start, "endIndex": end},
                "paragraphStyle": {"namedStyleType": named_style},
                "fields": "namedStyleType",
            }
        })
        if bold:
            requests.append({
                "updateTextStyle": {
                    "range": {"startIndex": start, "endIndex": end - 1},
                    "textStyle": {"bold": True},
                    "fields": "bold",
                }
            })
        current_index = end

    # ─── タイトル ───
    append_paragraph(book.book_title, "TITLE")
    if book.subtitle:
        append_paragraph(book.subtitle, "SUBTITLE")

    # ─── 書誌情報 ───
    append_paragraph(f"元書籍: 『{book.source_title}』 著: {book.source_author}", "NORMAL_TEXT")
    append_paragraph("", "NORMAL_TEXT")  # 空行

    # ─── まえがき ───
    append_paragraph("まえがき", "HEADING_1")
    for para in _markdown_to_requests(book.foreword):
        append_paragraph(para["text"], para["style"])
    append_paragraph("", "NORMAL_TEXT")

    # ─── 各章 ───
    for ch in book.chapters:
        append_paragraph(f"第{ch.number}章　{ch.title}", "HEADING_1")
        for para in _markdown_to_requests(ch.content):
            append_paragraph(para["text"], para["style"])
        append_paragraph("", "NORMAL_TEXT")

    # ─── あとがき ───
    append_paragraph("あとがき", "HEADING_1")
    for para in _markdown_to_requests(book.afterword):
        append_paragraph(para["text"], para["style"])

    # ─── 区切り線テキスト ───
    append_paragraph("", "NORMAL_TEXT")
    append_paragraph("─" * 40, "NORMAL_TEXT")
    append_paragraph("", "NORMAL_TEXT")

    return requests


class GDocsPublisher:
    """GeneratedBook を Google ドキュメントに追記するクラス"""

    def __init__(self, document_id: Optional[str] = None):
        self.document_id = document_id or settings.gdoc_document_id
        if not self.document_id:
            raise ValueError("document_id が未設定です。settings.gdoc_document_id または引数で指定してください。")

    def publish(self, book: GeneratedBook) -> str:
        """
        ドキュメントに本を追記する。
        戻り値: ドキュメントURL
        """
        console.print(f"[cyan]📄 Google ドキュメントに書き出し中...[/cyan]")
        console.print(f"   Document ID: {self.document_id}")

        service = _get_docs_service()
        requests = _build_requests(book, self.document_id, service)

        if not requests:
            console.print("[yellow]  書き出すコンテンツがありませんでした。[/yellow]")
            return self._doc_url()

        # batchUpdate は 1回のリクエストに上限があるので 500件ずつ分割
        batch_size = 500
        for i in range(0, len(requests), batch_size):
            chunk = requests[i: i + batch_size]
            service.documents().batchUpdate(
                documentId=self.document_id,
                body={"requests": chunk},
            ).execute()
            console.print(f"   [{i + len(chunk)}/{len(requests)}] リクエスト送信完了")

        url = self._doc_url()
        console.print(f"[bold green]  ✅ Googleドキュメントへの書き出し完了[/bold green]")
        console.print(f"   URL: {url}")
        return url

    def _doc_url(self) -> str:
        return f"https://docs.google.com/document/d/{self.document_id}/edit"
