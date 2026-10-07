"""Convert Markdown into immutable source snapshots with bounded speech segments."""

import re
from dataclasses import dataclass
from pathlib import Path

from markdown_it import MarkdownIt
from markdown_it.token import Token

_HIDDEN_INLINE_TAG = re.compile(r"<\s*(/?)\s*(script|style)\b", re.IGNORECASE)
_CONTROL_CHARACTERS = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")


@dataclass(frozen=True)
class MarkdownSegment:
    """A speech segment and its zero-based, end-exclusive source line range."""

    text: str
    kind: str
    line_start: int
    line_end: int


@dataclass(frozen=True)
class MarkdownSnapshot:
    source_text: str
    segments: tuple[MarkdownSegment, ...]


def split_frontmatter(text: str) -> tuple[str, int]:
    """Return the Markdown body and its original source line offset."""
    lines = text.lstrip("\ufeff").splitlines(keepends=True)
    if lines and lines[0].strip() == "---":
        for index, line in enumerate(lines[1:], 1):
            if line.strip() in {"---", "..."}:
                return "".join(lines[index + 1 :]), index + 1
    return "".join(lines), 0


def inline_speech_parts(children: list[Token]) -> list[tuple[int, str]]:
    """Extract spoken leaves without images, markup, or hidden HTML contents."""
    parts = []
    hidden_tags = []
    for index, child in enumerate(children):
        if child.type == "html_inline":
            tag = _HIDDEN_INLINE_TAG.match(child.content)
            if tag:
                name = tag.group(2).lower()
                if tag.group(1):
                    if hidden_tags and hidden_tags[-1] == name:
                        hidden_tags.pop()
                else:
                    hidden_tags.append(name)
            continue
        if hidden_tags:
            continue
        if child.type in {"text", "code_inline"}:
            parts.append((index, child.content))
        elif child.type in {"softbreak", "hardbreak"}:
            parts.append((index, " "))
    return parts


def normalize_speech_parts(
    parts: list[tuple[int, str]],
) -> tuple[str, list[tuple[int, int]]]:
    """Normalize speech while retaining a leaf/character position for each character."""
    characters = []
    positions = []
    whitespace = None
    for leaf, text in parts:
        for offset, character in enumerate(text):
            if _CONTROL_CHARACTERS.fullmatch(character):
                continue
            if character.isspace():
                if characters and whitespace is None:
                    whitespace = (leaf, offset)
                continue
            if whitespace is not None:
                characters.append(" ")
                positions.append(whitespace)
                whitespace = None
            characters.append(character)
            positions.append((leaf, offset))
    return "".join(characters), positions


def _inline_text(children: list[Token]) -> str:
    return "".join(text for _, text in inline_speech_parts(children))


def _split_text(text: str, max_chars: int) -> list[str]:
    segments = []
    while len(text) > max_chars:
        boundary = text.rfind(" ", 0, max_chars + 1)
        if boundary <= 0:
            boundary = max_chars
        segments.append(text[:boundary])
        text = text[boundary:].lstrip()
    if text:
        segments.append(text)
    return segments


def _inline_kind(parents: list[Token]) -> str:
    types = {parent.type for parent in parents}
    if "heading_open" in types:
        return "heading"
    if "th_open" in types or "td_open" in types:
        return "table_cell"
    if "list_item_open" in types:
        return "list_item"
    if "blockquote_open" in types:
        return "blockquote"
    return "paragraph"


def parse_markdown(text: str, include_code: bool = False, max_chars: int = 600) -> MarkdownSnapshot:
    """Keep the full source and map visible speech to original source lines."""
    if not isinstance(max_chars, int) or max_chars < 1:
        raise ValueError("Metin parçası uzunluğu pozitif bir tam sayı olmalı.")
    body, line_offset = split_frontmatter(text)
    tokens = MarkdownIt("commonmark").enable("table").parse(body)
    segments = []
    parents = []
    for token in tokens:
        if token.nesting == 1:
            parents.append(token)
            continue
        if token.nesting == -1:
            parents.pop()
            continue
        if token.type == "inline":
            content = _inline_text(token.children or [])
            kind = _inline_kind(parents)
        elif include_code and token.type in {"fence", "code_block"}:
            content = token.content
            kind = "code"
        else:
            continue
        content, _ = normalize_speech_parts([(0, content)])
        if any(character.isalnum() for character in content):
            line_start, line_end = token.map
            segments.extend(
                MarkdownSegment(part, kind, line_start + line_offset, line_end + line_offset)
                for part in _split_text(content, max_chars)
            )
    if not segments:
        raise ValueError("Bu Markdown dosyasında okunabilecek metin bulunamadı.")
    return MarkdownSnapshot(text, tuple(segments))


def read_markdown_snapshot(path: Path, include_code: bool = False) -> MarkdownSnapshot:
    """Read UTF-8 once, preserving line endings and whitespace in the snapshot."""
    path = Path(path)
    if path.suffix.lower() not in {".md", ".markdown"}:
        raise ValueError("Yalnız .md veya .markdown dosyaları açılabilir.")
    try:
        text = path.read_bytes().decode("utf-8-sig")
    except UnicodeDecodeError as error:
        raise ValueError("Dosya UTF-8 olarak kaydedilmiş olmalı.") from error
    return parse_markdown(text, include_code=include_code)


def markdown_to_segments(text: str, include_code: bool = False, max_chars: int = 600) -> list[str]:
    """Read visible Markdown text in order, excluding code unless requested."""
    return [
        segment.text
        for segment in parse_markdown(text, include_code=include_code, max_chars=max_chars).segments
    ]


def read_markdown(path: Path, include_code: bool = False) -> list[str]:
    """Read a UTF-8 Markdown file; UTF-8 BOM and uppercase suffixes are accepted."""
    return [segment.text for segment in read_markdown_snapshot(path, include_code).segments]
