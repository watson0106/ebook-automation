"""
ocr_processor.py
スクリーンショット画像をOCRでテキスト化するモジュール
"""

import re
import sys
from pathlib import Path

try:
    import cv2
    import numpy as np
    import pytesseract
    from PIL import Image
    from tqdm import tqdm
except ImportError:
    print("必要なライブラリが不足しています。pip install -r requirements.txt を実行してください。")
    sys.exit(1)


SCREENSHOTS_DIR = Path(__file__).parent.parent / "output" / "screenshots"
TEXTS_DIR = Path(__file__).parent.parent / "output" / "texts"

# Tesseractの日本語設定
TESSERACT_LANG = "jpn"
PSM_HORIZONTAL = "--psm 6"   # 横書き
PSM_VERTICAL = "--psm 5"     # 縦書き


def preprocess_image(img_path: Path) -> np.ndarray:
    """画像の前処理：グレースケール・コントラスト強調・ノイズ除去"""
    img = cv2.imread(str(img_path))
    # グレースケール
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    # コントラスト強調（CLAHE）
    clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8))
    enhanced = clahe.apply(gray)
    # ガウシアンブラーでノイズ除去
    denoised = cv2.GaussianBlur(enhanced, (3, 3), 0)
    # 二値化（Otsu法）
    _, binary = cv2.threshold(denoised, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
    return binary


def ocr_image(processed: np.ndarray) -> str:
    """
    横書きと縦書きの両方でOCRを実行し、
    文字数が多い方の結果を返す。
    """
    pil_img = Image.fromarray(processed)

    config_h = f"-l {TESSERACT_LANG} {PSM_HORIZONTAL}"
    config_v = f"-l {TESSERACT_LANG} {PSM_VERTICAL}"

    text_h = pytesseract.image_to_string(pil_img, config=config_h)
    text_v = pytesseract.image_to_string(pil_img, config=config_v)

    # 有効文字数（空白・改行を除く）で比較
    count_h = len(re.sub(r"\s", "", text_h))
    count_v = len(re.sub(r"\s", "", text_v))

    return text_h if count_h >= count_v else text_v


def clean_text(text: str) -> str:
    """テキスト整形：不要な改行・ページ番号を除去"""
    # ページ番号パターンを除去（行頭・行末の数字のみの行）
    text = re.sub(r"^\s*\d{1,4}\s*$", "", text, flags=re.MULTILINE)
    # 3つ以上連続する改行を2つに統一
    text = re.sub(r"\n{3,}", "\n\n", text)
    # 行頭・行末の空白を除去
    lines = [line.strip() for line in text.splitlines()]
    text = "\n".join(lines)
    return text.strip()


def process_session(session_dir: Path) -> Path:
    """
    指定セッションディレクトリのスクリーンショットをOCR処理する。
    戻り値：テキスト保存先ディレクトリ
    """
    images = sorted(session_dir.glob("*.png"))
    if not images:
        print(f"[警告] {session_dir} に画像が見つかりません。")
        return TEXTS_DIR / session_dir.name

    output_dir = TEXTS_DIR / session_dir.name
    output_dir.mkdir(parents=True, exist_ok=True)

    print(f"\nOCR処理開始: {len(images)} ファイル → {output_dir}")

    for img_path in tqdm(images, desc="OCR処理中", unit="page"):
        try:
            processed = preprocess_image(img_path)
            raw_text = ocr_image(processed)
            cleaned = clean_text(raw_text)

            out_path = output_dir / (img_path.stem + ".txt")
            out_path.write_text(cleaned, encoding="utf-8")
        except Exception as e:
            tqdm.write(f"[エラー] {img_path.name}: {e}")

    return output_dir


def process_all_sessions() -> list[Path]:
    """screenshots/ 以下の全セッションを処理する"""
    if not SCREENSHOTS_DIR.exists():
        print(f"[エラー] {SCREENSHOTS_DIR} が存在しません。先にキャプチャを実行してください。")
        sys.exit(1)

    sessions = sorted([d for d in SCREENSHOTS_DIR.iterdir() if d.is_dir()])
    if not sessions:
        print("[エラー] 処理対象のセッションが見つかりません。")
        sys.exit(1)

    results = []
    for session in sessions:
        out = process_session(session)
        results.append(out)

    return results


if __name__ == "__main__":
    process_all_sessions()
