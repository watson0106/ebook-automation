#!/usr/bin/env python3
"""
Google OAuth 2.0 再認証スクリプト
実行後にブラウザが開くのでログインし、リフレッシュトークンを自動保存します。
"""
import http.server
import os
import threading
import urllib.parse
import webbrowser
from pathlib import Path

import requests

ENV_FILE = Path(__file__).parent.parent / ".env"
REDIRECT_URI = "http://localhost:8765/callback"
SCOPES = "https://www.googleapis.com/auth/drive"


def load_env():
    env = {}
    if ENV_FILE.exists():
        for line in ENV_FILE.read_text().splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1)
                env[k.strip()] = v.strip()
    return env


def save_refresh_token(token: str):
    text = ENV_FILE.read_text()
    if "GOOGLE_OAUTH_REFRESH_TOKEN=" in text:
        lines = []
        for line in text.splitlines():
            if line.startswith("GOOGLE_OAUTH_REFRESH_TOKEN="):
                lines.append(f"GOOGLE_OAUTH_REFRESH_TOKEN={token}")
            else:
                lines.append(line)
        ENV_FILE.write_text("\n".join(lines) + "\n")
    else:
        with ENV_FILE.open("a") as f:
            f.write(f"\nGOOGLE_OAUTH_REFRESH_TOKEN={token}\n")
    print(f"✅ .env を更新しました: GOOGLE_OAUTH_REFRESH_TOKEN={token[:20]}...")


def main():
    env = load_env()
    client_id = env.get("GOOGLE_OAUTH_CLIENT_ID", "")
    client_secret = env.get("GOOGLE_OAUTH_CLIENT_SECRET", "")

    if not client_id or not client_secret:
        print("❌ .env に GOOGLE_OAUTH_CLIENT_ID / GOOGLE_OAUTH_CLIENT_SECRET が設定されていません")
        return

    auth_url = (
        "https://accounts.google.com/o/oauth2/v2/auth"
        f"?client_id={urllib.parse.quote(client_id)}"
        f"&redirect_uri={urllib.parse.quote(REDIRECT_URI)}"
        f"&response_type=code"
        f"&scope={urllib.parse.quote(SCOPES)}"
        f"&access_type=offline"
        f"&prompt=consent"
    )

    received_code = threading.Event()
    auth_code = [None]

    class Handler(http.server.BaseHTTPRequestHandler):
        def log_message(self, *a):
            pass

        def do_GET(self):
            parsed = urllib.parse.urlparse(self.path)
            params = urllib.parse.parse_qs(parsed.query)
            code = params.get("code", [None])[0]
            self.send_response(200)
            self.send_header("Content-type", "text/html; charset=utf-8")
            self.end_headers()
            if code:
                auth_code[0] = code
                self.wfile.write(
                    "<h1>認証完了！このタブを閉じてターミナルに戻ってください。</h1>".encode()
                )
            else:
                self.wfile.write("<h1>エラー: コードが取得できませんでした</h1>".encode())
            received_code.set()

    server = http.server.HTTPServer(("localhost", 8765), Handler)
    t = threading.Thread(target=server.serve_forever)
    t.daemon = True
    t.start()

    print("🌐 ブラウザを開きます... (自動で開かない場合は以下のURLをコピーしてください)")
    print(f"\n{auth_url}\n")
    webbrowser.open(auth_url)

    print("⏳ Googleログイン待機中...")
    received_code.wait(timeout=300)
    server.shutdown()

    if not auth_code[0]:
        print("❌ タイムアウト: 認証コードを受け取れませんでした")
        return

    # コードをトークンに交換
    resp = requests.post(
        "https://oauth2.googleapis.com/token",
        data={
            "code": auth_code[0],
            "client_id": client_id,
            "client_secret": client_secret,
            "redirect_uri": REDIRECT_URI,
            "grant_type": "authorization_code",
        },
    )
    tokens = resp.json()

    if "refresh_token" not in tokens:
        print(f"❌ トークン取得失敗: {tokens}")
        return

    save_refresh_token(tokens["refresh_token"])
    print("\n✅ 認証完了！これで Google Drive へのアップロードが使えます。")


if __name__ == "__main__":
    main()
