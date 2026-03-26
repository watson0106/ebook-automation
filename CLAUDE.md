# CLAUDE.md — eBook Automation System

## プロジェクト概要

「賢者とユイの読書倶楽部」ブランドの電子書籍を自動生成・出版するパイプライン。
人気本のリサーチ → 対話形式の要約本執筆 → カバー生成 → EPUB/DOCX作成 → Google Drive/D2D出版。

## 技術スタック

- **言語**: Python 3.11+
- **CLI**: Click + Rich
- **AI**: Gemini API (メイン) → Claude API (フォールバック) → Vertex AI (最終フォールバック)
- **画像生成**: Google Imagen 3 (Vertex AI経由)
- **スクレイピング**: Playwright, BeautifulSoup, aiohttp
- **出力形式**: EPUB (ebooklib), DOCX (python-docx)
- **クラウド**: Google Drive API (OAuth 2.0)
- **出版**: Draft2Digital (Playwright自動操作)
- **設定**: Pydantic Settings (.env)

## プロジェクト構造

```
メイン.py                          # CLIエントリポイント (Click)
依存パッケージ.txt                  # pip依存パッケージ一覧
設定/
  設定値.py                         # Pydantic設定 (.env読み込み)
ソース/
  リサーチ/                         # Amazon/Kindle/楽天スクレイピング
    管理.py                         # リサーチオーケストレーション
    Amazonスクレイパー.py
    Kindleスクレイパー.py
    楽天スクレイパー.py
  コンテンツ/                       # AI書籍生成
    執筆エンジン.py                 # Gemini/Claude/Vertex AI統合
    プロンプト.py                   # LLMプロンプトテンプレート
  電子書籍/
    EPUB生成.py                     # EPUB生成 (CSS付きHTML)
  出版/
    D2D投稿.py                      # Draft2Digital自動投稿 (Playwright)
    DOCX生成.py                     # Word文書生成
    Driveアップロード.py            # Google Drive アップロード
  サムネイル/
    画像生成.py                     # Imagen 3 カバー画像生成
スクリプト/
  電子書籍生成.py                   # GitHub Actions用ランナー
  Google認証.py                     # Google OAuth認証
.github/workflows/
  generate_ebook.yml                # 手動トリガーワークフロー
```

## CLIコマンド

```bash
python メイン.py setup                            # 初期セットアップ
python メイン.py research -s amazon kindle        # ベストセラーリサーチ
python メイン.py write -t "書籍タイトル"           # 要約本を執筆
python メイン.py thumbnail -t "タイトル"           # カバー画像生成
python メイン.py run -t "タイトル"                 # 全工程一括実行
python メイン.py publish --epub file.epub         # D2D投稿
python メイン.py docx -t "タイトル"               # DOCX生成 + Drive
```

## 開発ルール

### コミットメッセージ
- `fix:` バグ修正
- `Add` 新機能追加
- 日本語で簡潔に内容を記述する

### APIフォールバックチェーン
1. Gemini API (無料枠 / google-genai)
2. Claude API (Anthropic)
3. Vertex AI (Google Cloud サービスアカウント)

レート制限: 5秒間隔、リトライ待機 [30, 60, 120] 秒

### セキュリティ
- `.env`, `credentials.json`, `設定/service-account.json` は絶対にコミットしない
- APIキーはすべて環境変数経由で読み込む
- GitHub Secretsで管理 (GEMINI_API_KEY, GOOGLE_CLIENT_ID 等)

### コード規約
- 非同期処理は `asyncio` を使用（スクレイピング系）
- CLI出力は `rich.console.Console` を使用
- 設定は `設定.設定値.settings` シングルトン経由
- エラー時は try/except でフォールバック、exit code 1 を防ぐ

## 作業ルーティン

### セッション開始時（自動）
- 必ず `git pull` で最新状態を反映してから作業を開始する

### セッション終了時（自動）
- 作業で生まれた重要なルールを CLAUDE.md に追記する
- `git add . && git commit -m "update CLAUDE.md [日付]" && git push` を実行する

### 新規プロジェクト開始時（自動）
- CLAUDE.md を作成する
- GitHub リポジトリに接続されているか確認する
- 接続されていない場合は GitHub への接続を行う

## 既知の課題
- テストスイートが未整備（pytest/unittest なし）
- Kindle自動スクリーンショットシステムが未完成
