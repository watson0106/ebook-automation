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

SYSTEM_PROMPT = """あなたは「賢者とユイの対話形式」で本の本質を伝える人気ライターです。

## キャラクター設定

**賢者（けんじゃ）**
- 50代の穏やかな老哲学者
- 難しい概念をシンプルなたとえ話で説明する
- 口癖：「そうじゃな」「面白い視点じゃ」「核心を突いておるな」

**ユイ（ゆい）**
- 20代の好奇心旺盛な読者の代弁者
- 読者が「自分も同じこと思ってた！」と共感できる存在
- 口癖：「なるほど！」「えっ、それってどういうことですか？」「つまり〜ってことですね！」

## 執筆ルール
1. 対話形式（賢者とユイの会話）で書く
2. 各章は2000〜3000文字を目安に
3. 具体的な例やたとえ話を豊富に使う
4. 著作権に配慮し、本の文章を直接引用せず、テーマや考え方を自分の言葉で解説する
"""

CALL_INTERVAL = 4
_last_call = 0.0
MODEL_NAME = None


# ── モデル選択 ────────────────────────────────────────────────────────────────
def select_model():
    global MODEL_NAME

    # まず利用可能なモデル一覧を取得して表示
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
        for attempt in range(3):  # 429時は最大3回リトライ
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
                if "429" in s and attempt < 2:
                    wait = 30 * (attempt + 1)
                    print(f"  ⏳ {name} レート制限 — {wait}秒待機してリトライ...")
                    time.sleep(wait)
                    continue
                code = "404" if "404" in s else "429" if "429" in s else "403" if "403" in s else type(e).__name__
                print(f"  ✗ {name} ({code})")
                break

    print(f"\n❌ どのモデルも使えませんでした。")
    print(f"   利用可能なモデル一覧: {available}")
    print(f"   最後のエラー: {last_error}")
    print()
    print("対処法:")
    print("  1. Google Cloud Console で 'Generative Language API' を有効化してください")
    print("     https://console.cloud.google.com/apis/library/generativelanguage.googleapis.com")
    print("  2. または Google AI Studio で新しいAPIキーを作成してください")
    print("     https://aistudio.google.com/apikey")
    sys.exit(1)


# ── API呼び出し ───────────────────────────────────────────────────────────────
def call_gemini(prompt: str, max_tokens: int = 4096, json_mode: bool = False) -> str:
    global _last_call
    wait = CALL_INTERVAL - (time.time() - _last_call)
    if wait > 0:
        time.sleep(wait)
    for attempt, backoff in enumerate([0, 30, 60, 120]):
        if backoff:
            print(f"  ⚠️ レート制限 — {backoff}秒待機中...")
            time.sleep(backoff)
        try:
            _last_call = time.time()
            if json_mode:
                cfg = types.GenerateContentConfig(
                    temperature=0.9,
                    max_output_tokens=max_tokens,
                    response_mime_type="application/json",
                )
            else:
                cfg = types.GenerateContentConfig(
                    system_instruction=SYSTEM_PROMPT,
                    temperature=0.9,
                    max_output_tokens=max_tokens,
                )
            r = client.models.generate_content(
                model=MODEL_NAME,
                contents=prompt,
                config=cfg,
            )
            return r.text or ""
        except Exception as e:
            if "429" in str(e) and attempt < 3:
                continue
            raise
    raise RuntimeError("Gemini API 呼び出しに失敗しました")


def extract_json(text: str) -> dict:
    if not text:
        raise ValueError("APIレスポンスが空です")
    # json_mode の場合はそのままパース試行
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass
    m = re.search(r"```(?:json)?\s*([\s\S]+?)\s*```", text)
    if m:
        return json.loads(m.group(1))
    m = re.search(r"\{[\s\S]+\}", text)
    if m:
        return json.loads(m.group(0))
    print(f"  ⚠️ JSONパース失敗。レスポンス先頭200文字: {text[:200]!r}")
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
CSS = b"body{font-family:serif;line-height:1.9;margin:2em;}h1,h2,h3{margin-top:1.5em;}p{margin:.5em 0;}strong{font-weight:bold;}"


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


# ── メイン ────────────────────────────────────────────────────────────────────
def main():
    select_model()
    out = Path("output")
    out.mkdir(exist_ok=True)

    print(f"\n📖 対象: {BOOK_TITLE}\n")

    # 書籍情報
    print("🔍 書籍情報を取得中...")
    book_info = extract_json(call_gemini(f"""以下の書籍タイトルの情報をJSON形式で回答してください。

タイトル: {BOOK_TITLE}

以下のキーを含むJSONオブジェクトを返してください：
- author: 著者名（不明なら"不明"）
- category: ジャンル（ビジネス/自己啓発/投資/心理学/小説/歴史/科学 など）
- description: 本の内容を3〜5文で説明

実在する書籍なら正確に、不明な場合は推測で構いません。""", max_tokens=512, json_mode=True))

    author = book_info.get("author", "不明")
    category = book_info.get("category", "ビジネス")
    description = book_info.get("description", "")
    print(f"   著者: {author}  カテゴリ: {category}")

    # 章構成
    print("📚 章構成を計画中...")
    plan = extract_json(call_gemini(f"""以下の本について賢者とユイの対話形式の解説本を作ります。

対象書籍:
タイトル: {BOOK_TITLE} / 著者: {author}
カテゴリ: {category}
説明: {description or '（なし）'}

以下のキーを含むJSONオブジェクトを返してください：
- book_title: 「【賢者とユイが語る】〇〇の本質」形式のタイトル
- subtitle: 「〇〇が教えてくれる人生の知恵」形式のサブタイトル
- description: 本の説明文（300文字程度）
- keywords: キーワードの配列（3つ）
- chapter_titles: 章タイトルの配列（5〜7章）""", max_tokens=2048, json_mode=True))

    print(f"   タイトル: {plan['book_title']}")
    toc_str = "\n".join(f"{i+1}. {t}" for i, t in enumerate(plan["chapter_titles"]))

    # まえがき
    print("✍️  まえがきを執筆中...")
    foreword = call_gemini(f"""『{BOOK_TITLE}』（著：{author}）の解説書のまえがきを書いてください。
- この本を手に取った読者へのメッセージ
- 賢者とユイというキャラクターの紹介
- この解説本で得られること
- 400〜600文字、マークダウン形式""")

    # 各章
    chapters = []
    for i, title in enumerate(plan["chapter_titles"], 1):
        print(f"✍️  第{i}章「{title}」を執筆中...")
        content = call_gemini(f"""『{BOOK_TITLE}』（著：{author}）の解説本の第{i}章を書いてください。

章タイトル: {title}
全章構成:
{toc_str}

注意：
- 本の文章を直接引用しない（著作権配慮）
- テーマ・考え方を自分の言葉で解説する
- 賢者とユイの自然な対話形式
- 2000〜3000文字
- マークダウン形式（**ユイ**：〜 / **賢者**：〜）""", max_tokens=4096)
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

    md_path = out / f"{safe}.md"
    md_path.write_text(full_text, encoding="utf-8")
    epub_path = build_epub(plan, foreword, chapters, afterword, out)
    docx_path = build_docx(plan, foreword, chapters, afterword, out)

    print()
    print("=" * 50)
    print("🎉 完成！")
    print("=" * 50)
    print(f"📖 タイトル : {plan['book_title']}")
    print(f"📝 総文字数 : {len(full_text):,} 文字")
    print(f"📚 章数     : {len(chapters)} 章")
    print(f"💾 Markdown : {md_path}  ({md_path.stat().st_size // 1024} KB)")
    print(f"💾 EPUB     : {epub_path}  ({epub_path.stat().st_size // 1024} KB)")
    print(f"💾 Word     : {docx_path}  ({docx_path.stat().st_size // 1024} KB)")
    print()
    print("GitHub Actions の Artifacts からダウンロードできます")


if __name__ == "__main__":
    main()
