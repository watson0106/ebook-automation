"""Google Drive へ .docx をアップロードして Google ドキュメントに変換するモジュール"""
from pathlib import Path

import requests as req_lib
from rich.console import Console

from config.settings import settings

console = Console()


def _get_access_token() -> str:
    """リフレッシュトークンからアクセストークンを取得"""
    resp = req_lib.post(
        "https://oauth2.googleapis.com/token",
        data={
            "client_id": settings.google_oauth_client_id,
            "client_secret": settings.google_oauth_client_secret,
            "refresh_token": settings.google_oauth_refresh_token,
            "grant_type": "refresh_token",
        },
    )
    resp.raise_for_status()
    return resp.json()["access_token"]


def upload_docx_as_gdoc(docx_path: Path, folder_id: str | None = None) -> str:
    """
    .docx を Google Drive にアップロードし、Google ドキュメントに変換する。

    Args:
        docx_path: アップロードする .docx ファイルのパス
        folder_id: アップロード先フォルダの ID（省略時はマイドライブ直下）

    Returns:
        作成された Google ドキュメントの URL
    """
    access_token = _get_access_token()
    headers = {"Authorization": f"Bearer {access_token}"}

    metadata: dict = {
        "name": docx_path.stem,
        "mimeType": "application/vnd.google-apps.document",
    }
    if folder_id:
        metadata["parents"] = [folder_id]

    console.print("[cyan]  Google Drive へアップロード中...[/cyan]")

    import json
    resp = req_lib.post(
        "https://www.googleapis.com/upload/drive/v3/files",
        headers=headers,
        params={"uploadType": "multipart", "fields": "id,webViewLink"},
        files={
            "metadata": (None, json.dumps(metadata), "application/json; charset=UTF-8"),
            "file": (
                docx_path.name,
                docx_path.read_bytes(),
                "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            ),
        },
    )
    resp.raise_for_status()
    file = resp.json()

    url = file.get("webViewLink", f"https://docs.google.com/document/d/{file['id']}/edit")
    console.print(f"[bold green]  ✅ Google ドキュメント作成完了[/bold green]")
    console.print(f"     [link={url}]{url}[/link]")
    return url
