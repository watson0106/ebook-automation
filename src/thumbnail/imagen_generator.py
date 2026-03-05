"""Google Imagen 3 APIを使ったサムネイル（カバー画像）生成モジュール"""
import re
from pathlib import Path

from google import genai
from google.genai import types
from PIL import Image, ImageDraw, ImageFont
from rich.console import Console

from config.settings import settings

console = Console()

# eBook カバーの標準サイズ（D2D推奨: 縦長 1:1.5）
COVER_WIDTH = 1600
COVER_HEIGHT = 2400


class ThumbnailGenerator:
    def __init__(self):
        self.client = genai.Client(api_key=settings.google_api_key)
        self.model = settings.imagen_model

    def generate_cover_image(
        self,
        imagen_prompt: str,
        negative_prompt: str = "",
        output_path: Path | None = None,
    ) -> Path:
        """
        Imagen 3でカバー画像を生成する

        Args:
            imagen_prompt: 画像生成プロンプト（英語）
            negative_prompt: ネガティブプロンプト
            output_path: 保存先パス
        """
        console.print("[cyan]🎨 Imagen 3でカバー画像を生成中...[/cyan]")

        # eBook カバー向けにプロンプトを強化
        enhanced_prompt = (
            f"{imagen_prompt}, "
            "professional ebook cover design, portrait orientation 2:3 ratio, "
            "high quality, 1600x2400 pixels, book cover layout"
        )

        response = self.client.models.generate_images(
            model=self.model,
            prompt=enhanced_prompt,
            config=types.GenerateImagesConfig(
                number_of_images=1,
                aspect_ratio="2:3",       # 縦長（eBook標準）
                safety_filter_level="block_only_high",
                person_generation="allow_adult",
            ),
        )

        if not response.generated_images:
            raise RuntimeError("Imagen 3から画像が生成されませんでした")

        image_data = response.generated_images[0].image.image_bytes
        img = Image.frombytes("RGB", (COVER_WIDTH, COVER_HEIGHT), image_data)

        # 出力パスを決定
        if output_path is None:
            settings.output_thumbnails_dir.mkdir(parents=True, exist_ok=True)
            output_path = settings.output_thumbnails_dir / "cover.jpg"

        img.save(output_path, "JPEG", quality=95)
        console.print(f"[green]✅ カバー画像保存: {output_path}[/green]")
        return output_path

    def add_title_overlay(
        self,
        image_path: Path,
        book_title: str,
        subtitle: str,
        author_name: str,
    ) -> Path:
        """
        生成済み画像にタイトルテキストをオーバーレイ

        Args:
            image_path: 元のカバー画像パス
            book_title: 本のタイトル
            subtitle: サブタイトル
            author_name: 著者名
        """
        console.print("[cyan]📝 タイトルをオーバーレイ中...[/cyan]")

        img = Image.open(image_path).convert("RGBA")
        overlay = Image.new("RGBA", img.size, (0, 0, 0, 0))
        draw = ImageDraw.Draw(overlay)

        w, h = img.size

        # 上部・下部に半透明バーを追加
        draw.rectangle([0, 0, w, int(h * 0.25)], fill=(0, 0, 0, 160))
        draw.rectangle([0, int(h * 0.78), w, h], fill=(0, 0, 0, 140))

        # フォントをシステムから探す
        font_title = self._get_font(72)
        font_subtitle = self._get_font(40)
        font_author = self._get_font(36)

        # タイトル（上部）
        title_lines = self._wrap_text(book_title, font_title, int(w * 0.85), draw)
        y = 40
        for line in title_lines:
            bbox = draw.textbbox((0, 0), line, font=font_title)
            x = (w - (bbox[2] - bbox[0])) // 2
            draw.text((x, y), line, font=font_title, fill=(255, 255, 255, 255))
            y += bbox[3] - bbox[1] + 10

        # サブタイトル（下部）
        sub_y = int(h * 0.80)
        sub_lines = self._wrap_text(subtitle, font_subtitle, int(w * 0.80), draw)
        for line in sub_lines:
            bbox = draw.textbbox((0, 0), line, font=font_subtitle)
            x = (w - (bbox[2] - bbox[0])) // 2
            draw.text((x, sub_y), line, font=font_subtitle, fill=(220, 220, 220, 255))
            sub_y += bbox[3] - bbox[1] + 8

        # 著者名（最下部）
        author_y = int(h * 0.93)
        bbox = draw.textbbox((0, 0), author_name, font=font_author)
        x = (w - (bbox[2] - bbox[0])) // 2
        draw.text((x, author_y), author_name, font=font_author, fill=(200, 200, 200, 255))

        # 合成
        composed = Image.alpha_composite(img, overlay).convert("RGB")

        # 上書き保存
        composed.save(image_path, "JPEG", quality=95)
        console.print(f"[green]✅ テキストオーバーレイ完了: {image_path}[/green]")
        return image_path

    def _get_font(self, size: int):
        """日本語フォントを取得（フォールバック付き）"""
        font_candidates = [
            "/usr/share/fonts/truetype/noto/NotoSansCJK-Regular.ttc",
            "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
            "/usr/share/fonts/truetype/fonts-japanese-gothic.ttf",
            "/System/Library/Fonts/ヒラギノ角ゴシック W3.ttc",
            "/System/Library/Fonts/Hiragino Sans GB.ttc",
        ]
        for path in font_candidates:
            try:
                return ImageFont.truetype(path, size)
            except Exception:
                continue
        return ImageFont.load_default()

    def _wrap_text(self, text: str, font, max_width: int, draw: ImageDraw.Draw) -> list[str]:
        """テキストを最大幅でラップ"""
        lines = []
        current = ""
        for char in text:
            test = current + char
            bbox = draw.textbbox((0, 0), test, font=font)
            if bbox[2] - bbox[0] > max_width and current:
                lines.append(current)
                current = char
            else:
                current = test
        if current:
            lines.append(current)
        return lines

    def generate_for_book(
        self,
        book_title: str,
        subtitle: str,
        imagen_prompt: str,
        negative_prompt: str = "",
        filename: str | None = None,
    ) -> Path:
        """
        本全体のカバーを生成（Imagen生成 → テキストオーバーレイ）

        Returns:
            カバー画像のパス
        """
        safe_name = re.sub(r'[\\/*?:"<>|【】]', "", book_title)[:40]
        output_filename = filename or f"{safe_name}_cover.jpg"
        output_path = settings.output_thumbnails_dir / output_filename
        settings.output_thumbnails_dir.mkdir(parents=True, exist_ok=True)

        # 画像生成
        self.generate_cover_image(imagen_prompt, negative_prompt, output_path)

        # テキストオーバーレイ
        self.add_title_overlay(
            output_path,
            book_title,
            subtitle,
            settings.author_name,
        )

        return output_path
