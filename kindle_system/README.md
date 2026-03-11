# Kindle自動取得システム

MacOS上でKindleアプリの全ページを自動スクリーンショットし、OCRでテキスト化するシステムです。

## セットアップ

```bash
# 仮想環境を作成してライブラリをインストール
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

### 事前に必要なもの（Homebrewで導入）

```bash
brew install tesseract
brew install tesseract-lang
```

### アクセシビリティ権限の設定

- システム設定 → プライバシーとセキュリティ → アクセシビリティ
- 「ターミナル」と「Visual Studio Code」をリストに追加してオンにする

## 使い方

```bash
source venv/bin/activate

python src/main.py                  # 全自動実行
python src/main.py --capture-only   # キャプチャだけ
python src/main.py --ocr-only       # OCRだけ
```

## フォルダ構成

```
kindle_system/
├── src/              ソースコード
│   ├── main.py
│   ├── kindle_capture.py
│   └── ocr_processor.py
├── output/           生成ファイル
│   ├── screenshots/  スクショ保存先（実行日時フォルダごと）
│   └── texts/        OCRテキスト保存先
├── .vscode/          VS Code設定
├── requirements.txt
└── README.md
```

## 処理の流れ

1. Kindleアプリを自動起動
2. 「本を開いてからEnterを押してください」と表示して待機
3. Enterが押されたらページを順番にスクリーンショット
4. 同じページが2回連続したら最終ページと判定して終了
5. OCRで日本語テキストに変換（横書き・縦書き自動判定）
6. `output/texts/` にテキストファイルとして保存
