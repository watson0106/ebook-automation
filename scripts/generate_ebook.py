"""
賢者とユイの読書倶楽部 — eBook自動生成スクリプト
GitHub Actions から実行される
"""
import os
import sys
import json
import re
import time
import html as html_module
from pathlib import Path

from google import genai
from google.genai import types
from ebooklib import epub
from docx import Document
from docx.enum.text import WD_ALIGN_PARAGRAPH

try:
    from google.oauth2 import service_account
    from googleapiclient.discovery import build
    from googleapiclient.http import MediaFileUpload
    _GDRIVE_AVAILABLE = True
except ImportError:
    _GDRIVE_AVAILABLE = False

# ── 設定 ──────────────────────────────────────────────────────────────────────
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY", "")
BOOK_TITLE = os.environ.get("BOOK_TITLE", "").strip()

if not GEMINI_API_KEY:
    print("❌ GEMINI_API_KEY が設定されていません")
    print("   GitHub リポジトリの Settings → Secrets and variables → Actions")
    print("   → New repository secret → Name: GEMINI_API_KEY を設定してください")
    sys.exit(1)

if not BOOK_TITLE:
    print("❌ BOOK_TITLE が設定されていません")
    sys.exit(1)

client = genai.Client(api_key=GEMINI_API_KEY)

CANDIDATES = [
    "gemini-2.5-flash",
    "gemini-2.5-pro",
    "gemini-2.0-flash",
    "gemini-2.0-flash-lite",
    "gemini-1.5-flash",
    "gemini-1.5-pro",
]

SYSTEM_PROMPT = """あなたは「先生とユイの対話形式」で本の本質を伝える人気ライターです。

## キャラクター設定

**賢者**
- 50代の穏やかな老哲学者
- 難しい概念をシンプルなたとえ話で説明する
- ユイからは必ず「先生」と呼ばれる
- 口癖：「そうじゃな」「面白い視点じゃ」「核心を突いておるな」

**ユイ（ゆい）**
- 20代の読者の代弁者
- 【重要】物語の冒頭ではアンチ・懐疑的な立場でスタートする
  - 自己啓発本や成功哲学に対して斜に構えた態度
  - 「そんなの当たり前じゃないですか」「本当にそれで変わるんですか？」「胡散臭い...」
- 賢者との対話を通じて、徐々に本の価値・深さに気づいていく
- 最終的には素直に学び、読者と一緒に成長する存在
- 賢者のことは必ず「先生」と呼ぶ
- 口癖（懐疑期）：「でも先生、それって...」「正直、怪しくないですか？」「本当にそんな単純な話なんですか？」
- 口癖（理解期）：「あ、なるほど！」「先生、それってつまり...」「わかってきた気がします！」

## 執筆ルール
1. 対話形式（賢者とユイの会話）で書く
2. 各章は2000〜3000文字を目安に
3. 具体的な例やたとえ話を豊富に使う
4. 著作権に配慮し、本の文章を直接引用せず、テーマや考え方を自分の言葉で解説する
5. ユイは賢者のことを必ず「先生」と呼ぶこと。対話の表記は「賢者」を使うこと。
"""

CALL_INTERVAL = 4
_last_call = 0.0
MODEL_NAME = None


# ── モデル選択 ────────────────────────────────────────────────────────────────
def _parse_retry_delay(error_str: str) -> int:
    """エラーメッセージからretryDelay秒数を取得（見つからなければ60秒）"""
    m = re.search(r"retryDelay['\"]?\s*[:=]\s*['\"]?(\d+)", error_str)
    if m:
        return int(m.group(1)) + 5  # バッファ5秒追加
    m = re.search(r"retry in (\d+)[\.\d]*\s*s", error_str)
    if m:
        return int(m.group(1)) + 5
    return 65  # デフォルト


def _is_quota_exhausted(error_str: str) -> bool:
    """日次クォータ超過かどうか（レート制限とは別）"""
    return "RESOURCE_EXHAUSTED" in error_str or "Quota exceeded" in error_str


def select_model():
    global MODEL_NAME

    print("📋 APIキーで利用可能なモデルを確認中...")
    try:
        available = [m.name for m in client.models.list()]
        print(f"   利用可能なモデル数: {len(available)}")
        gen_models = [m for m in available if "gemini" in m.lower()]
        print(f"   Geminiモデル: {gen_models[:10]}")
    except Exception as e:
        print(f"   モデル一覧取得失敗: {e}")
        available = []

    print("🔍 使えるモデルをテスト中...")
    last_error = None
    for name in CANDIDATES:
        for attempt in range(3):
            try:
                r = client.models.generate_content(
                    model=name,
                    contents="こんにちは",
                )
                _ = r.text
                MODEL_NAME = name
                print(f"✅ 使用モデル: {MODEL_NAME}")
                return
            except Exception as e:
                last_error = e
                s = str(e)
                if "429" in s or "RESOURCE_EXHAUSTED" in s:
                    if _is_quota_exhausted(s):
                        # 日次クォータ超過 → このモデルはスキップ
                        print(f"  ✗ {name} (日次クォータ超過 — 次のモデルへ)")
                        break
                    elif attempt < 2:
                        wait = _parse_retry_delay(s)
                        print(f"  ⏳ {name} レート制限 — {wait}秒待機してリトライ...")
                        time.sleep(wait)
                        continue
                code = "404" if "404" in s else "429" if "429" in s else "403" if "403" in s else type(e).__name__
                print(f"  ✗ {name} ({code})")
                break

    print(f"\n❌ どのモデルも使えませんでした。")
    print(f"   最後のエラー: {last_error}")
    print()
    print("対処法:")
    print("  1. Google AI Studio で新しいAPIキーを作成してください")
    print("     https://aistudio.google.com/apikey")
    print("  2. または有料プランへのアップグレードをご検討ください")
    sys.exit(1)


# ── API呼び出し ───────────────────────────────────────────────────────────────
def call_gemini(prompt: str, max_tokens: int = 4096, json_mode: bool = False) -> str:
    global _last_call
    wait = CALL_INTERVAL - (time.time() - _last_call)
    if wait > 0:
        time.sleep(wait)
    for attempt in range(4):
        try:
            _last_call = time.time()
            cfg = types.GenerateContentConfig(
                temperature=0.7 if json_mode else 0.9,
                max_output_tokens=max_tokens,
                **({"system_instruction": SYSTEM_PROMPT} if not json_mode else {}),
            )
            r = client.models.generate_content(
                model=MODEL_NAME,
                contents=prompt,
                config=cfg,
            )
            return r.text or ""
        except Exception as e:
            s = str(e)
            if ("429" in s or "RESOURCE_EXHAUSTED" in s) and attempt < 3:
                if _is_quota_exhausted(s):
                    # 日次クォータ超過は待っても解決しないので即失敗
                    raise
                wait_sec = _parse_retry_delay(s)
                print(f"  ⚠️ レート制限 — {wait_sec}秒待機中... (試行 {attempt+1}/4)")
                time.sleep(wait_sec)
                continue
            raise
    raise RuntimeError("Gemini API 呼び出しに失敗しました")


def extract_json(text: str) -> dict:
    if not text:
        raise ValueError("APIレスポンスが空です")
    # そのままパース
    try:
        return json.loads(text.strip())
    except json.JSONDecodeError:
        pass
    # コードブロック内
    m = re.search(r"```(?:json)?\s*([\s\S]+?)\s*```", text)
    if m:
        try:
            return json.loads(m.group(1))
        except json.JSONDecodeError:
            pass
    # 括弧の深さを数えて正確に抽出
    start = text.find('{')
    if start != -1:
        depth = 0
        for i, c in enumerate(text[start:], start):
            if c == '{':
                depth += 1
            elif c == '}':
                depth -= 1
                if depth == 0:
                    try:
                        return json.loads(text[start:i + 1])
                    except json.JSONDecodeError:
                        break
    print(f"  ⚠️ JSONパース失敗。レスポンス先頭300文字: {text[:300]!r}")
    raise ValueError("JSONが見つかりません")


# ── Markdown → HTML ───────────────────────────────────────────────────────────
def md_to_html(text: str) -> str:
    out = []
    for line in text.split("\n"):
        line = html_module.escape(line)
        if line.startswith("### "):
            line = f"<h3>{line[4:]}</h3>"
        elif line.startswith("## "):
            line = f"<h2>{line[3:]}</h2>"
        elif line.startswith("# "):
            line = f"<h1>{line[2:]}</h1>"
        elif line.strip() in ("", "---"):
            line = "<br/>"
        else:
            line = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", line)
            line = f"<p>{line}</p>"
        out.append(line)
    return "\n".join(out)


# ── EPUB生成 ──────────────────────────────────────────────────────────────────
CSS = b"body{font-family:serif;font-size:1.15em;line-height:2.0;margin:2em;}h1,h2,h3{margin-top:1.5em;}p{margin:.5em 0;}strong{font-weight:bold;}"


def build_epub(plan, foreword, chapters, afterword, out_dir: Path) -> Path:
    bk = epub.EpubBook()
    safe = re.sub(r'[\\/*?:"<>|【】\s]', "_", plan["book_title"])[:50]
    bk.set_identifier("id_" + safe)
    bk.set_title(plan["book_title"])
    bk.set_language("ja")
    bk.add_author("賢者とユイの読書倶楽部")

    css_item = epub.EpubItem(uid="style", file_name="style/main.css", media_type="text/css", content=CSS)
    bk.add_item(css_item)
    spine, toc = ["nav"], []

    def add_chapter(uid, fname, title, body_html):
        c = epub.EpubHtml(title=title, file_name=fname, lang="ja")
        c.content = f"<html><body><h2>{html_module.escape(title)}</h2>{body_html}</body></html>"
        c.add_item(css_item)
        bk.add_item(c)
        spine.append(c)
        toc.append(epub.Link(fname, title, uid))

    add_chapter("foreword", "foreword.xhtml", "まえがき", md_to_html(foreword))
    for ch in chapters:
        add_chapter(f"ch{ch['number']}", f"ch{ch['number']}.xhtml",
                    f"第{ch['number']}章　{ch['title']}", md_to_html(ch["content"]))
    add_chapter("afterword", "afterword.xhtml", "あとがき", md_to_html(afterword))

    bk.toc = toc
    bk.spine = spine
    bk.add_item(epub.EpubNcx())
    bk.add_item(epub.EpubNav())

    path = out_dir / f"{safe}.epub"
    epub.write_epub(str(path), bk)
    return path


# ── Word生成 ──────────────────────────────────────────────────────────────────
def add_md_to_doc(doc, text: str):
    for line in text.split("\n"):
        if line.startswith("## "):
            doc.add_heading(line[3:], level=2)
        elif line.startswith("# "):
            doc.add_heading(line[2:], level=1)
        elif line.strip() in ("", "---"):
            doc.add_paragraph("")
        else:
            para = doc.add_paragraph()
            for part in re.split(r"(\*\*.+?\*\*)", line):
                if part.startswith("**") and part.endswith("**"):
                    para.add_run(part[2:-2]).bold = True
                else:
                    para.add_run(part)


def build_docx(plan, foreword, chapters, afterword, out_dir: Path) -> Path:
    doc = Document()
    h = doc.add_heading(plan["book_title"], 0)
    h.alignment = WD_ALIGN_PARAGRAPH.CENTER
    p = doc.add_paragraph(plan["subtitle"])
    p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    doc.add_paragraph("著者：賢者とユイの読書倶楽部").alignment = WD_ALIGN_PARAGRAPH.CENTER
    doc.add_page_break()

    doc.add_heading("まえがき", level=1)
    add_md_to_doc(doc, foreword)
    doc.add_page_break()

    for ch in chapters:
        doc.add_heading(f"第{ch['number']}章　{ch['title']}", level=1)
        add_md_to_doc(doc, ch["content"])
        doc.add_page_break()

    doc.add_heading("あとがき", level=1)
    add_md_to_doc(doc, afterword)

    safe = re.sub(r'[\\/*?:"<>|【】\s]', "_", plan["book_title"])[:50]
    path = out_dir / f"{safe}.docx"
    doc.save(str(path))
    return path


# ── Google Docs アップロード ───────────────────────────────────────────────────
def cleanup_old_drive_files(service) -> None:
    """サービスアカウントのDriveにある古いファイルを削除してストレージを解放する"""
    try:
        results = service.files().list(
            pageSize=100,
            fields="files(id, name, mimeType)",
        ).execute()
        files = results.get("files", [])
        if files:
            print(f"  🗑️  古いファイルを {len(files)} 件削除中...")
            for f in files:
                try:
                    service.files().delete(fileId=f["id"]).execute()
                except Exception:
                    pass
    except Exception as e:
        print(f"  ⚠️  古いファイルの削除に失敗: {e}")


def upload_to_google_docs(docx_path: Path, title: str) -> str | None:
    """docxをGoogle Driveにアップロードし、Google Docsに変換して共有URLを返す"""
    credentials_json = os.environ.get("GOOGLE_CREDENTIALS_JSON", "")
    if not credentials_json:
        print("⚠️  GOOGLE_CREDENTIALS_JSON が未設定のためGoogle Docsアップロードをスキップ")
        return None
    if not _GDRIVE_AVAILABLE:
        print("⚠️  google-api-python-client が未インストールのためGoogle Docsアップロードをスキップ")
        return None
    try:
        credentials_info = json.loads(credentials_json)
        credentials = service_account.Credentials.from_service_account_info(
            credentials_info,
            scopes=["https://www.googleapis.com/auth/drive"],
        )
        service = build("drive", "v3", credentials=credentials, cache_discovery=False)

        # アップロード前に古いファイルを削除してストレージを確保
        cleanup_old_drive_files(service)

        file_metadata = {
            "name": title,
            "mimeType": "application/vnd.google-apps.document",
        }
        media = MediaFileUpload(
            str(docx_path),
            mimetype="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            resumable=True,
        )
        file = service.files().create(
            body=file_metadata, media_body=media, fields="id,webViewLink"
        ).execute()

        # 誰でも閲覧可能に設定
        service.permissions().create(
            fileId=file["id"],
            body={"type": "anyone", "role": "reader"},
        ).execute()

        return file.get("webViewLink", "")
    except Exception as e:
        print(f"⚠️  Google Docsアップロード失敗: {e}")
        return None


# ── メイン ────────────────────────────────────────────────────────────────────
def main():
    select_model()
    out = Path("output")
    out.mkdir(exist_ok=True)

    print(f"\n📖 対象: {BOOK_TITLE}\n")

    # 書籍情報
    print("🔍 書籍情報を取得中...")
    book_info = extract_json(call_gemini(f"""以下の書籍の情報をJSONのみで回答してください。前置きや説明は不要です。

タイトル: {BOOK_TITLE}

```json
{{
  "author": "著者名",
  "category": "自己啓発",
  "description": "2文以内の説明"
}}
```""", max_tokens=1024, json_mode=False))

    author = book_info.get("author", "不明")
    category = book_info.get("category", "ビジネス")
    description = book_info.get("description", "")
    print(f"   著者: {author}  カテゴリ: {category}")

    # 章構成
    print("📚 章構成を計画中...")
    plan = extract_json(call_gemini(f"""『{BOOK_TITLE}』の解説書の構成をJSONのみで返してください。前置きや説明は不要です。

```json
{{
  "book_title": "【賢者とユイが語る】嫌われる勇気の本質",
  "subtitle": "アドラー心理学が教えてくれる人生の知恵",
  "description": "100文字以内の説明",
  "keywords": ["キーワード1", "キーワード2", "キーワード3"],
  "chapter_titles": ["第1章タイトル", "第2章タイトル", "第3章タイトル", "第4章タイトル", "第5章タイトル", "第6章タイトル"]
}}
```""", max_tokens=2048, json_mode=False))

    print(f"   タイトル: {plan['book_title']}")
    toc_str = "\n".join(f"{i+1}. {t}" for i, t in enumerate(plan["chapter_titles"]))

    # まえがき
    print("✍️  まえがきを執筆中...")
    foreword = call_gemini(f"""『{BOOK_TITLE}』（著：{author}）の解説書のまえがきを書いてください。
- この本を手に取った読者へのメッセージ
- 先生とユイというキャラクターの紹介（ユイは最初は懐疑的・アンチだが先生との対話で学んでいく）
- この解説本で得られること
- 400〜600文字、マークダウン形式""")

    # 各章
    chapters = []
    total_chapters = len(plan["chapter_titles"])
    for i, title in enumerate(plan["chapter_titles"], 1):
        print(f"✍️  第{i}章「{title}」を執筆中...")
        # ユイの態度フェーズを章番号に応じて設定
        if i == 1:
            yui_phase = "【第1章：懐疑・アンチフェーズ】ユイは懐疑的・批判的。「本当にそんなことで変わるんですか？」「胡散臭い」「先生、それって怪しくないですか？」などの反応が多い。この本の価値にまだ全く懐疑的。"
        elif i <= total_chapters // 2:
            yui_phase = f"【第{i}章：変化フェーズ】ユイは少しずつ興味を持ち始めているが、まだ半信半疑。「先生...少しだけわかってきた気がします」「でも本当にそれだけで？」という反応が混在する。"
        else:
            yui_phase = f"【第{i}章：理解・成長フェーズ】ユイは本の価値を理解し始め、積極的に質問し学ぼうとしている。「先生、それってつまり...」「なるほど！そういうことだったんですね！」と素直に学ぶ姿勢になっている。"

        content = call_gemini(f"""『{BOOK_TITLE}』（著：{author}）の解説本の第{i}章を書いてください。

章タイトル: {title}
全章構成:
{toc_str}

ユイのキャラクター指示：
{yui_phase}

注意：
- 本の文章を直接引用しない（著作権配慮）
- テーマ・考え方を自分の言葉で解説する
- 賢者とユイの自然な対話形式
- ユイは賢者のことを必ず「先生」と呼ぶ（セリフ内では「先生」）
- 2000〜3000文字
- マークダウン形式で以下の見出し構造を使うこと：
  - 章タイトルは `# タイトル`（h1）
  - 章内の小タイトル・節は `## 小タイトル`（h2）
  - 対話は `**ユイ**：〜` / `**賢者**：〜`""", max_tokens=4096)
        chapters.append({"number": i, "title": title, "content": content})
        print(f"   ✅ 完了 ({len(content):,}文字)")

    # あとがき
    print("✍️  あとがきを執筆中...")
    afterword = call_gemini(f"""『{BOOK_TITLE}』解説本のあとがきを書いてください。
全章を通じたメッセージの総括と読者へのエール。400〜600文字、マークダウン形式。
全章タイトル:\n{toc_str}""")

    # ファイル保存
    safe = re.sub(r'[\\/*?:"<>|【】\s]', "_", plan["book_title"])[:50]

    parts = [
        f"# {plan['book_title']}\n",
        f"**{plan['subtitle']}**\n",
        "著者：賢者とユイの読書倶楽部\n",
        "---\n",
        "## まえがき\n", foreword, "\n---\n",
    ]
    for ch in chapters:
        parts += [f"## 第{ch['number']}章　{ch['title']}\n", ch["content"], "\n---\n"]
    parts += ["## あとがき\n", afterword]
    full_text = "\n".join(parts)

    # Google Docs にアップロード（一時的にdocxを作成してアップロード後に削除）
    docx_path = build_docx(plan, foreword, chapters, afterword, out)
    print("📤 Google Docs にアップロード中...")
    gdocs_url = upload_to_google_docs(docx_path, plan["book_title"])
    docx_path.unlink(missing_ok=True)

    print()
    print("=" * 50)
    print("🎉 完成！")
    print("=" * 50)
    print(f"📖 タイトル : {plan['book_title']}")
    print(f"📝 総文字数 : {len(full_text):,} 文字")
    print(f"📚 章数     : {len(chapters)} 章")
    if gdocs_url:
        print(f"🌐 Google Docs : {gdocs_url}")
    else:
        print("⚠️  Google Docs へのアップロードに失敗しました")


if __name__ == "__main__":
    main()
