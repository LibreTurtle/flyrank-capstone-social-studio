import re
from html.parser import HTMLParser


class ArticleTextParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.title_parts: list[str] = []
        self.text_parts: list[str] = []
        self._in_title = False
        self._ignored_depth = 0

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag in {"script", "style", "noscript"}:
            self._ignored_depth += 1
        elif tag == "title":
            self._in_title = True
        elif tag in {"p", "h1", "h2", "h3", "br", "div", "li"}:
            self.text_parts.append("\n")

    def handle_endtag(self, tag: str) -> None:
        if tag in {"script", "style", "noscript"} and self._ignored_depth:
            self._ignored_depth -= 1
        elif tag == "title":
            self._in_title = False

    def handle_data(self, data: str) -> None:
        if self._ignored_depth:
            return
        cleaned = data.strip()
        if cleaned:
            (self.title_parts if self._in_title else self.text_parts).append(cleaned)


def extract_article(html: str) -> tuple[str, str]:
    parser = ArticleTextParser()
    parser.feed(html)
    title = " ".join(parser.title_parts).strip()
    body = re.sub(r"\n\s*\n+", "\n", "\n".join(parser.text_parts)).strip()
    if not body:
        raise ValueError("The URL did not contain readable article text")
    return title or "Untitled article", body


def title_from_markdown(markdown: str) -> str:
    for line in markdown.splitlines():
        heading = re.match(r"^#{1,6}\s+(.+?)\s*#*\s*$", line.strip())
        if heading:
            return heading.group(1)
    return "Untitled article"
