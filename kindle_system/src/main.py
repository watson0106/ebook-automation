"""
main.py
Kindle自動取得システム エントリーポイント

使い方：
  python src/main.py                  # 全自動（キャプチャ → OCR）
  python src/main.py --capture-only   # キャプチャだけ
  python src/main.py --ocr-only       # OCRだけ
"""

import argparse
import sys
from pathlib import Path

# src/ 直下から実行されることを想定してパスを追加
sys.path.insert(0, str(Path(__file__).parent))

from kindle_capture import launch_kindle, capture_all_pages
from ocr_processor import process_all_sessions, process_session


def run_capture() -> Path:
    """キャプチャフェーズ"""
    if not launch_kindle():
        sys.exit(1)

    input("\nKindleで本を開いてから Enter を押してください... ")
    print()

    session_dir = capture_all_pages()
    return session_dir


def run_ocr(session_dir: Path | None = None):
    """OCRフェーズ"""
    if session_dir is not None:
        out_dirs = [process_session(session_dir)]
    else:
        out_dirs = process_all_sessions()

    print("\n========== OCR完了 ==========")
    for d in out_dirs:
        txt_files = list(d.glob("*.txt"))
        print(f"  保存先: {d}")
        print(f"  ファイル数: {len(txt_files)} ページ")
    print("==============================\n")


def main():
    parser = argparse.ArgumentParser(
        description="Kindle自動スクリーンショット＆OCRシステム",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "例:\n"
            "  python src/main.py                  全自動実行\n"
            "  python src/main.py --capture-only   キャプチャのみ\n"
            "  python src/main.py --ocr-only        OCRのみ（既存スクショを処理）"
        ),
    )
    parser.add_argument("--capture-only", action="store_true", help="キャプチャのみ実行")
    parser.add_argument("--ocr-only", action="store_true", help="OCRのみ実行（既存スクショを処理）")
    args = parser.parse_args()

    if args.capture_only and args.ocr_only:
        parser.error("--capture-only と --ocr-only は同時に指定できません。")

    print("============================")
    print("  Kindle自動取得システム")
    print("============================\n")

    if args.capture_only:
        session_dir = run_capture()
        total = len(list(session_dir.glob("*.png")))
        print(f"\n完了: {total} ページを {session_dir} に保存しました。")

    elif args.ocr_only:
        run_ocr()

    else:
        # 全自動
        session_dir = run_capture()
        print("\nキャプチャ完了。OCR処理を開始します...\n")
        run_ocr(session_dir)


if __name__ == "__main__":
    main()
