from dataclasses import dataclass, field
from typing import Optional


@dataclass
class BookInfo:
    """リサーチで見つかった本の情報"""
    title: str
    author: str
    source: str          # "amazon" | "rakuten" | "kindle"
    rank: int
    category: str = ""
    isbn: str = ""
    description: str = ""
    cover_url: str = ""
    price: str = ""
    publisher: str = ""
    published_date: str = ""
    url: str = ""
    tags: list[str] = field(default_factory=list)

    def __str__(self) -> str:
        return f"[{self.source}#{self.rank}] {self.title} / {self.author}"
