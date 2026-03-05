from dataclasses import dataclass, field


@dataclass
class Chapter:
    number: int
    title: str
    content: str  # マークダウン形式


@dataclass
class GeneratedBook:
    source_title: str       # 元の本のタイトル
    source_author: str      # 元の本の著者
    book_title: str         # 生成された要約本のタイトル
    subtitle: str
    description: str        # D2D用の本の説明
    keywords: list[str]
    chapters: list[Chapter]
    foreword: str           # まえがき
    afterword: str          # あとがき
    total_chars: int = 0

    def full_text(self) -> str:
        parts = [f"# {self.book_title}\n\n## {self.subtitle}\n\n"]
        parts.append(f"## まえがき\n\n{self.foreword}\n\n")
        for ch in self.chapters:
            parts.append(f"## 第{ch.number}章 {ch.title}\n\n{ch.content}\n\n")
        parts.append(f"## あとがき\n\n{self.afterword}\n\n")
        return "".join(parts)
