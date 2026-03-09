"""Google Drive へ .docx をアップロードして Google ドキュメントに変換するモジュール"""
from pathlib import Path

from rich.console import Console

from config.settings import settings

console = Console()


def _build_service():
    from google.oauth2.credentials import Credentials
    from googleapiclient.discovery import build

    creds = Credentials(
        token=None,
        refresh_token=settings.google_oauth_refresh_token,
        token_uri="https://oauth2.googleapis.com/token",
        client_id=settings.google_oauth_client_id,
        client_secret=settings.google_oauth_client_secret,
        scopes=["https://www.googleapis.com/auth/drive"],
    )
    return build("drive", "v3", credentials=creds, cache_discovery=False)


def upload_docx_as_gdoc(docx_path: Path, folder_id: str | None = None) -> str:
    """
    .docx を Google Drive にアップロードし、Google ドキュメントに変換する。

    Args:
        docx_path: アップロードする .docx ファイルのパス
        folder_id: アップロード先フォルダの ID（省略時はマイドライブ直下）

    Returns:
        作成された Google ドキュメントの URL
    """
    from googleapiclient.http import MediaFileUpload

    service = _build_service()

    metadata: dict = {
        "name": docx_path.stem,
        "mimeType": "application/vnd.google-apps.document",
    }
    if folder_id:
        metadata["parents"] = [folder_id]

    media = MediaFileUpload(
        str(docx_path),
        mimetype="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        resumable=True,
    )

    console.print("[cyan]  Google Drive へアップロード中...[/cyan]")
    file = (
        service.files()
        .create(body=metadata, media_body=media, fields="id,webViewLink")
        .execute()
    )

    url = file.get("webViewLink", f"https://docs.google.com/document/d/{file['id']}/edit")
    console.print(f"[bold green]  ✅ Google ドキュメント作成完了[/bold green]")
    console.print(f"     [link={url}]{url}[/link]")
    return url
