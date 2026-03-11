"""
kindle_capture.py
Kindleアプリの全ページを自動スクリーンショットするモジュール
"""

import os
import sys
import time
import hashlib
import subprocess
from datetime import datetime
from pathlib import Path

try:
    import pyautogui
    from PIL import Image, ImageGrab
except ImportError:
    print("必要なライブラリが不足しています。pip install -r requirements.txt を実行してください。")
    sys.exit(1)


OUTPUT_DIR = Path(__file__).parent / "output" / "screenshots"
PAGE_TURN_WAIT = 2.0
MAX_RETRIES = 3


def check_accessibility_permission() -> bool:
    """アクセシビリティ権限の確認（macOS）"""
    result = subprocess.run(
        ["osascript", "-e", 'tell application "System Events" to get name of first process whose frontmost is true'],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        print("\n[警告] アクセシビリティ権限が必要です。")
        print("以下の手順で設定してください：")
        print("  1. Apple メニュー → システム設定 を開く")
        print("  2. プライバシーとセキュリティ → アクセシビリティ を選択")
        print("  3. 「ターミナル」または「iTerm」をリストに追加してオンにする")
        print("  4. このスクリプトを再実行する\n")
        return False
    return True


def launch_kindle() -> bool:
    """Kindleアプリを起動する"""
    kindle_path = "/Applications/Kindle.app"
    if not os.path.exists(kindle_path):
        print("[エラー] Kindleアプリが見つかりません。")
        print("以下のURLからKindleをインストールしてください：")
        print("  https://www.amazon.co.jp/kindle-dbs/fd/kcp")
        return False

    print("Kindleアプリを起動中...")
    subprocess.Popen(["open", kindle_path])
    time.sleep(5)
    print("Kindleアプリを起動しました。")
    return True


def get_kindle_window() -> tuple[int, int, int, int] | None:
    """KindleウィンドウのBounding Boxを取得する（left, top, width, height）"""
    script = """
    tell application "System Events"
        tell process "Kindle"
            set w to front window
            set pos to position of w
            set sz to size of w
            return (item 1 of pos as string) & "," & (item 2 of pos as string) & "," & (item 1 of sz as string) & "," & (item 2 of sz as string)
        end tell
    end tell
    """
    result = subprocess.run(["osascript", "-e", script], capture_output=True, text=True)
    if result.returncode != 0 or not result.stdout.strip():
        return None
    try:
        parts = result.stdout.strip().split(",")
        left, top, width, height = int(parts[0]), int(parts[1]), int(parts[2]), int(parts[3])
        return (left, top, width, height)
    except (ValueError, IndexError):
        return None


def focus_kindle():
    """Kindleウィンドウをフォーカスする"""
    script = 'tell application "Kindle" to activate'
    subprocess.run(["osascript", "-e", script], capture_output=True)
    time.sleep(0.5)


def capture_kindle_window(bbox: tuple[int, int, int, int]) -> Image.Image:
    """Kindleウィンドウのスクリーンショットを撮る"""
    left, top, width, height = bbox
    region = (left, top, left + width, top + height)
    return ImageGrab.grab(bbox=region)


def image_hash(img: Image.Image) -> str:
    """画像のハッシュ値を計算する（同じページ判定用）"""
    img_small = img.resize((100, 100)).convert("L")
    return hashlib.md5(img_small.tobytes()).hexdigest()


def turn_page() -> bool:
    """右矢印キーでページをめくる"""
    try:
        pyautogui.press("right")
        return True
    except Exception:
        return False


def capture_all_pages(session_dir: Path | None = None) -> Path:
    """
    全ページをスクリーンショットする。
    戻り値：保存先ディレクトリ
    """
    if not check_accessibility_permission():
        sys.exit(1)

    if session_dir is None:
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        session_dir = OUTPUT_DIR / timestamp
    session_dir.mkdir(parents=True, exist_ok=True)

    focus_kindle()
    bbox = get_kindle_window()
    if bbox is None:
        print("[エラー] Kindleウィンドウが見つかりません。Kindleが起動しているか確認してください。")
        sys.exit(1)

    print(f"Kindleウィンドウ検出: left={bbox[0]}, top={bbox[1]}, width={bbox[2]}, height={bbox[3]}")
    print(f"保存先: {session_dir}")
    print("キャプチャを開始します。Ctrl+C で中断できます（保存済みファイルは残ります）。\n")

    page_num = 1
    prev_hash = None
    consecutive_same = 0

    try:
        while True:
            # ページキャプチャ（リトライあり）
            img = None
            for attempt in range(MAX_RETRIES):
                try:
                    img = capture_kindle_window(bbox)
                    break
                except Exception as e:
                    if attempt < MAX_RETRIES - 1:
                        print(f"  [リトライ {attempt + 1}/{MAX_RETRIES}] キャプチャ失敗: {e}")
                        time.sleep(1)
                    else:
                        print(f"  [スキップ] page_{page_num:04d}: キャプチャ失敗のためスキップします")
                        img = None

            if img is None:
                # スキップして次のページへ
                _turn_with_retry()
                page_num += 1
                continue

            current_hash = image_hash(img)

            # 同じページが2回連続したら終了
            if current_hash == prev_hash:
                consecutive_same += 1
                if consecutive_same >= 2:
                    print(f"\n同じページが2回連続して検出されました。最終ページと判断して終了します。")
                    break
            else:
                consecutive_same = 0

            # 保存
            filename = f"page_{page_num:04d}.png"
            filepath = session_dir / filename
            img.save(filepath, "PNG")
            print(f"[{page_num}] {filename} を保存しました")

            prev_hash = current_hash
            page_num += 1

            # ページめくり
            _turn_with_retry()
            time.sleep(PAGE_TURN_WAIT)

    except KeyboardInterrupt:
        print(f"\n[中断] Ctrl+C を受け取りました。{page_num - 1} ページ保存済みです。")

    total = len(list(session_dir.glob("*.png")))
    print(f"\nキャプチャ完了: {total} ページを {session_dir} に保存しました。")
    return session_dir


def _turn_with_retry():
    """リトライ付きページめくり"""
    for attempt in range(MAX_RETRIES):
        if turn_page():
            return
        time.sleep(1)
    print("[警告] ページめくりに失敗しましたが続行します。")


if __name__ == "__main__":
    if not launch_kindle():
        sys.exit(1)
    capture_all_pages()
