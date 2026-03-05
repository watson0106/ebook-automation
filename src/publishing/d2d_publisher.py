"""Draft2Digital への自動投稿モジュール（Playwright使用）"""
import asyncio
from pathlib import Path
from dataclasses import dataclass
from typing import Optional

from playwright.async_api import async_playwright, Page, Browser, TimeoutError as PlaywrightTimeoutError
from rich.console import Console

from config.settings import settings

console = Console()

D2D_BASE_URL = "https://www.draft2digital.com"
D2D_LOGIN_URL = f"{D2D_BASE_URL}/login/"
D2D_DASHBOARD_URL = f"{D2D_BASE_URL}/dashboard/"
D2D_NEW_BOOK_URL = f"{D2D_BASE_URL}/book/new/"


@dataclass
class PublishResult:
    success: bool
    book_title: str
    d2d_book_url: str = ""
    error_message: str = ""


@dataclass
class BookMetadata:
    title: str
    subtitle: str
    description: str
    author_name: str
    keywords: list[str]
    language: str = "Japanese"
    category: str = "Nonfiction / Self-Help"
    price_usd: float = 4.99
    epub_path: Path = None
    cover_path: Path = None


class D2DPublisher:
    def __init__(self):
        self.email = settings.d2d_email
        self.password = settings.d2d_password
        self.headless = settings.headless_browser

    async def _login(self, page: Page) -> bool:
        """D2Dにログイン"""
        console.print("[cyan]🔐 D2Dにログイン中...[/cyan]")
        await page.goto(D2D_LOGIN_URL, wait_until="domcontentloaded")
        await page.wait_for_timeout(2000)

        # メールアドレス入力
        email_field = await page.wait_for_selector(
            "input[type='email'], input[name='email'], input[id='email']",
            timeout=10000,
        )
        await email_field.fill(self.email)

        # パスワード入力
        pw_field = await page.wait_for_selector(
            "input[type='password'], input[name='password']",
            timeout=10000,
        )
        await pw_field.fill(self.password)

        # ログインボタンクリック
        login_btn = await page.wait_for_selector(
            "button[type='submit'], input[type='submit'], .login-btn, button:has-text('Sign In'), button:has-text('ログイン')",
            timeout=10000,
        )
        await login_btn.click()

        # ダッシュボードへのリダイレクト待ち
        try:
            await page.wait_for_url("**/dashboard/**", timeout=20000)
            console.print("[green]✅ ログイン成功[/green]")
            return True
        except PlaywrightTimeoutError:
            # URLが変わらなくてもページが変わっている可能性がある
            current_url = page.url
            if "login" not in current_url:
                console.print("[green]✅ ログイン成功[/green]")
                return True
            console.print(f"[red]❌ ログイン失敗: {current_url}[/red]")
            return False

    async def _fill_book_metadata(self, page: Page, meta: BookMetadata) -> None:
        """本のメタデータフォームを入力"""
        console.print("[cyan]📝 メタデータを入力中...[/cyan]")

        # タイトル
        await self._fill_field(page, ["input[name='title']", "#title", "[placeholder*='title']"], meta.title)

        # サブタイトル
        try:
            await self._fill_field(
                page,
                ["input[name='subtitle']", "#subtitle", "[placeholder*='subtitle']"],
                meta.subtitle,
                required=False,
            )
        except Exception:
            pass

        # 著者名
        await self._fill_field(
            page,
            ["input[name='author']", "#author", "[placeholder*='author']", "[name*='Author']"],
            meta.author_name,
        )

        # 説明文
        try:
            desc_field = await page.wait_for_selector(
                "textarea[name='description'], #description, textarea[placeholder*='description']",
                timeout=5000,
            )
            await desc_field.fill(meta.description)
        except Exception:
            console.print("[yellow]  説明文フィールドが見つかりませんでした（後で設定してください）[/yellow]")

        # 言語選択
        try:
            lang_selector = await page.wait_for_selector(
                "select[name='language'], #language",
                timeout=5000,
            )
            await lang_selector.select_option(label=meta.language)
        except Exception:
            pass

    async def _fill_field(
        self,
        page: Page,
        selectors: list[str],
        value: str,
        required: bool = True,
    ) -> bool:
        """複数セレクタでフィールドを探して入力"""
        for selector in selectors:
            try:
                field = await page.wait_for_selector(selector, timeout=3000)
                if field:
                    await field.clear()
                    await field.fill(value)
                    return True
            except Exception:
                continue
        if required:
            raise RuntimeError(f"フィールドが見つかりません: {selectors}")
        return False

    async def _upload_epub(self, page: Page, epub_path: Path) -> bool:
        """EPUBファイルをアップロード"""
        console.print(f"[cyan]📤 EPUBアップロード中: {epub_path.name}[/cyan]")
        try:
            file_input = await page.wait_for_selector(
                "input[type='file'][accept*='epub'], input[type='file']",
                timeout=10000,
            )
            await file_input.set_input_files(str(epub_path))
            # アップロード完了を待つ
            await page.wait_for_timeout(5000)
            console.print("[green]  ✅ EPUBアップロード完了[/green]")
            return True
        except Exception as e:
            console.print(f"[red]  ❌ EPUBアップロード失敗: {e}[/red]")
            return False

    async def _upload_cover(self, page: Page, cover_path: Path) -> bool:
        """カバー画像をアップロード"""
        console.print(f"[cyan]🖼️  カバーアップロード中: {cover_path.name}[/cyan]")
        try:
            # カバー画像のファイル入力を探す
            cover_inputs = await page.query_selector_all("input[type='file']")
            for inp in cover_inputs:
                accept = await inp.get_attribute("accept")
                if accept and ("image" in accept or "jpg" in accept or "png" in accept):
                    await inp.set_input_files(str(cover_path))
                    await page.wait_for_timeout(3000)
                    console.print("[green]  ✅ カバーアップロード完了[/green]")
                    return True

            # フォールバック：2番目のファイル入力を使用
            if len(cover_inputs) >= 2:
                await cover_inputs[1].set_input_files(str(cover_path))
                await page.wait_for_timeout(3000)
                console.print("[green]  ✅ カバーアップロード完了（フォールバック）[/green]")
                return True

        except Exception as e:
            console.print(f"[yellow]  ⚠️ カバーアップロード失敗: {e}[/yellow]")
        return False

    async def _set_price(self, page: Page, price_usd: float) -> None:
        """価格を設定"""
        try:
            price_field = await page.wait_for_selector(
                "input[name='price'], #price, [placeholder*='price']",
                timeout=5000,
            )
            await price_field.fill(str(price_usd))
        except Exception:
            console.print("[yellow]  価格フィールドが見つかりませんでした[/yellow]")

    async def _navigate_new_book_form(self, page: Page) -> bool:
        """新規本の投稿フォームに移動"""
        # ダッシュボードから「新しい本を追加」ボタンを探す
        try:
            await page.goto(D2D_NEW_BOOK_URL, wait_until="domcontentloaded")
            await page.wait_for_timeout(2000)
            return True
        except Exception:
            pass

        # ボタンを探す
        try:
            add_btn = await page.wait_for_selector(
                "a:has-text('Add'), a:has-text('New Book'), button:has-text('Add Book'), "
                "a:has-text('新しい本'), .add-book-btn",
                timeout=10000,
            )
            await add_btn.click()
            await page.wait_for_timeout(2000)
            return True
        except Exception as e:
            console.print(f"[red]新規本フォームへの移動失敗: {e}[/red]")
            return False

    async def _submit_and_publish(self, page: Page) -> tuple[bool, str]:
        """フォームを送信して投稿"""
        console.print("[cyan]🚀 投稿中...[/cyan]")
        try:
            submit_btn = await page.wait_for_selector(
                "button[type='submit']:has-text('Save'), "
                "button:has-text('Publish'), "
                "button:has-text('Submit'), "
                "input[type='submit']",
                timeout=10000,
            )
            await submit_btn.click()
            await page.wait_for_timeout(5000)

            # 成功URLを確認
            current_url = page.url
            success = "error" not in current_url and "login" not in current_url
            return success, current_url
        except Exception as e:
            return False, str(e)

    async def publish_book(self, meta: BookMetadata) -> PublishResult:
        """
        D2Dに本を投稿する

        Args:
            meta: 本のメタデータ（タイトル、説明、ファイルパス等）

        Returns:
            PublishResult: 投稿結果
        """
        if not self.email or not self.password:
            return PublishResult(
                success=False,
                book_title=meta.title,
                error_message="D2D_EMAIL または D2D_PASSWORD が設定されていません",
            )

        async with async_playwright() as pw:
            browser = await pw.chromium.launch(
                headless=self.headless,
                args=["--no-sandbox", "--disable-dev-shm-usage"],
            )
            context = await browser.new_context(
                locale="ja-JP",
                timezone_id="Asia/Tokyo",
                viewport={"width": 1280, "height": 900},
            )
            page = await context.new_page()

            try:
                # ログイン
                if not await self._login(page):
                    return PublishResult(
                        success=False,
                        book_title=meta.title,
                        error_message="D2Dへのログインに失敗しました",
                    )

                # 新規本フォームへ移動
                if not await self._navigate_new_book_form(page):
                    return PublishResult(
                        success=False,
                        book_title=meta.title,
                        error_message="新規本フォームへの移動に失敗しました",
                    )

                # EPUBアップロード（先にファイルをアップロードしてからメタデータ入力）
                if meta.epub_path and meta.epub_path.exists():
                    await self._upload_epub(page, meta.epub_path)

                # カバーアップロード
                if meta.cover_path and meta.cover_path.exists():
                    await self._upload_cover(page, meta.cover_path)

                # メタデータ入力
                await self._fill_book_metadata(page, meta)

                # 価格設定
                await self._set_price(page, meta.price_usd)

                # スクリーンショットを保存（デバッグ用）
                screenshot_path = settings.output_reports_dir / f"d2d_before_submit_{meta.title[:20]}.png"
                screenshot_path.parent.mkdir(parents=True, exist_ok=True)
                await page.screenshot(path=str(screenshot_path))
                console.print(f"[dim]  スクリーンショット: {screenshot_path}[/dim]")

                # 投稿
                success, result_url = await self._submit_and_publish(page)

                if success:
                    console.print(f"[bold green]🎉 D2D投稿成功！[/bold green]")
                    console.print(f"   URL: {result_url}")
                    return PublishResult(
                        success=True,
                        book_title=meta.title,
                        d2d_book_url=result_url,
                    )
                else:
                    return PublishResult(
                        success=False,
                        book_title=meta.title,
                        error_message=f"投稿失敗: {result_url}",
                    )

            except Exception as e:
                console.print(f"[red]❌ D2D投稿中にエラー: {e}[/red]")
                # エラー時のスクリーンショット
                try:
                    error_screenshot = settings.output_reports_dir / f"d2d_error_{meta.title[:20]}.png"
                    await page.screenshot(path=str(error_screenshot))
                    console.print(f"[dim]  エラースクリーンショット: {error_screenshot}[/dim]")
                except Exception:
                    pass
                return PublishResult(
                    success=False,
                    book_title=meta.title,
                    error_message=str(e),
                )
            finally:
                await browser.close()
