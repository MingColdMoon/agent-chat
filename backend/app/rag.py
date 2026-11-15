from __future__ import annotations

import math
import re
from collections import Counter
from html.parser import HTMLParser

from app.files import TEXT_EXTENSIONS


CHUNK_SIZE = 900
CHUNK_OVERLAP = 120
SUPPORTED_EXTENSIONS = TEXT_EXTENSIONS | {".pdf", ".docx", ".htm"}
TOKEN_PATTERN = re.compile(r"[A-Za-z0-9_]{2,}|[\u4e00-\u9fff]+")


class _HtmlTextParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.parts: list[str] = []
        self.skip_depth = 0

    def handle_starttag(
        self,
        tag: str,
        attrs: list[tuple[str, str | None]],
    ) -> None:
        if tag.lower() in {"script", "style", "noscript", "svg"}:
            self.skip_depth += 1
        elif tag.lower() in {"p", "br", "div", "li", "tr", "h1", "h2", "h3"}:
            self.parts.append("\n")

    def handle_endtag(self, tag: str) -> None:
        if tag.lower() in {"script", "style", "noscript", "svg"}:
            self.skip_depth = max(0, self.skip_depth - 1)
        elif tag.lower() in {"p", "div", "li", "tr", "h1", "h2", "h3"}:
            self.parts.append("\n")

    def handle_data(self, data: str) -> None:
        if self.skip_depth == 0:
            self.parts.append(data)


def _normalize_document_text(text: str) -> str:
    lines = []
    for line in text.replace("\r\n", "\n").replace("\r", "\n").split("\n"):
        compact = " ".join(line.split())
        if compact:
            lines.append(compact)
    return "\n".join(lines)


def _html_to_text(html: str) -> str:
    parser = _HtmlTextParser()
    parser.feed(html)
    return _normalize_document_text("".join(parser.parts))


def split_text_into_chunks(text: str) -> list[str]:
    normalized = text.replace("\r\n", "\n").strip()
    if not normalized:
        return []
    chunks: list[str] = []
    start = 0
    while start < len(normalized):
        end = min(len(normalized), start + CHUNK_SIZE)
        if end < len(normalized):
            boundary = max(
                normalized.rfind("\n\n", start, end),
                normalized.rfind("\n", start, end),
                normalized.rfind("。", start, end),
            )
            if boundary > start + CHUNK_SIZE // 2:
                end = boundary + 1
        chunk = normalized[start:end].strip()
        if chunk:
            chunks.append(chunk)
        if end >= len(normalized):
            break
        start = max(start + 1, end - CHUNK_OVERLAP)
    return chunks


def _tokens(text: str) -> list[str]:
    tokens: list[str] = []
    for match in TOKEN_PATTERN.findall(text.lower()):
        if re.fullmatch(r"[\u4e00-\u9fff]+", match):
            if len(match) <= 12:
                tokens.append(match)
            tokens.extend(
                match[index : index + 2]
                for index in range(max(0, len(match) - 1))
            )
        else:
            tokens.append(match)
    return tokens


def _bm25_scores(
    query_tokens: list[str],
    documents: list[list[str]],
) -> list[float]:
    if not documents:
        return []
    query_terms = list(dict.fromkeys(query_tokens))
    document_frequencies = Counter()
    for tokens in documents:
        token_set = set(tokens)
        for term in query_terms:
            if term in token_set:
                document_frequencies[term] += 1

    average_length = sum(len(tokens) for tokens in documents) / len(documents)
    average_length = max(1.0, average_length)
    document_count = len(documents)
    scores: list[float] = []
    for tokens in documents:
        frequencies = Counter(tokens)
        score = 0.0
        for term in query_terms:
            frequency = frequencies.get(term, 0)
            if frequency == 0:
                continue
            document_frequency = document_frequencies[term]
            inverse_frequency = math.log(
                1 + (document_count - document_frequency + 0.5)
                / (document_frequency + 0.5)
            )
            denominator = frequency + 1.5 * (
                1 - 0.75 + 0.75 * len(tokens) / average_length
            )
            score += inverse_frequency * (
                frequency * 2.5 / denominator
            )
        scores.append(score)
    return scores
