"""The prepared document snapshot and its measured audio boundaries."""

import json
import wave
from bisect import bisect_right
from collections import defaultdict
from dataclasses import dataclass
from html import escape
from itertools import groupby
from pathlib import Path

from markdown_it import MarkdownIt

from .markdown import inline_speech_parts, normalize_speech_parts, split_frontmatter


@dataclass(frozen=True)
class AudioCue:
    text: str
    kind: str
    line_start: int
    line_end: int
    start_frame: int
    end_frame: int
    sample_rate: int

    @property
    def start_ms(self) -> int:
        return (self.start_frame * 1000 + self.sample_rate - 1) // self.sample_rate


@dataclass(frozen=True)
class AudioDocument:
    source_text: str
    sample_rate: int
    cues: tuple[AudioCue, ...]

    def cue_at(self, milliseconds: int) -> int | None:
        if not self.cues:
            return None
        frame = max(0, milliseconds) * self.sample_rate // 1000
        return max(0, bisect_right(self.cues, frame, key=lambda cue: cue.start_frame) - 1)


def load_audio_document(audio_path: Path) -> AudioDocument | None:
    sidecar = audio_path.with_suffix(".cues.json")
    if not sidecar.exists():
        return None
    payload = json.loads(sidecar.read_text(encoding="utf-8"))
    if payload.get("schema_version") != 1 or not isinstance(payload.get("source_text"), str):
        raise ValueError("Belgenin ses bölüm bilgileri geçersiz.")
    with wave.open(str(audio_path)) as audio:
        rate, frames = audio.getframerate(), audio.getnframes()
    if payload.get("sample_rate") != rate:
        raise ValueError("Ses ve bölüm bilgileri aynı örnekleme hızını kullanmıyor.")
    lines = len(payload["source_text"].splitlines())
    cues = []
    end = 0
    for item in payload["cues"]:
        bounds = [item[key] for key in ("line_start", "line_end", "start_frame", "end_frame")]
        if any(type(value) is not int for value in bounds):
            raise ValueError("Bölüm sınırları tam sayı olmalı.")
        line_start, line_end, start_frame, end_frame = bounds
        if (
            not 0 <= line_start < line_end <= lines
            or start_frame != end
            or not start_frame <= end_frame <= frames
            or not isinstance(item["text"], str)
            or not isinstance(item["kind"], str)
        ):
            raise ValueError("Belgenin ses bölüm sınırları geçersiz.")
        cues.append(
            AudioCue(item["text"], item["kind"], line_start, line_end, start_frame, end_frame, rate)
        )
        end = end_frame
    if not cues or end != frames:
        raise ValueError("Bölüm bilgileri hazırlanan sesin tamamını kapsamıyor.")
    return AudioDocument(payload["source_text"], rate, tuple(cues))


def _linked_text(text, labels, job_id):
    parts = []
    for cue_index, characters in groupby(enumerate(text), key=lambda item: labels.get(item[0])):
        visible = escape("".join(character for _, character in characters))
        if cue_index is None:
            parts.append(visible)
        else:
            parts.append(
                f'<a href="segment:{job_id}:{cue_index}" name="cue-{cue_index}">{visible}</a>'
            )
    return "".join(parts)


def _cue_labels(parts, candidates, used):
    speech, positions = normalize_speech_parts(parts)
    labels = defaultdict(dict)
    cursor = 0
    for index, cue in candidates:
        if index in used:
            continue
        start = speech.find(cue.text, cursor)
        if start < 0:
            continue
        end = start + len(cue.text)
        leaf_ranges = {}
        for leaf, offset in positions[start:end]:
            if leaf in leaf_ranges:
                first, last = leaf_ranges[leaf]
                leaf_ranges[leaf] = min(first, offset), max(last, offset)
            else:
                leaf_ranges[leaf] = offset, offset
        for leaf, (first, last) in leaf_ranges.items():
            for offset in range(first, last + 1):
                labels[leaf][offset] = index
        used.add(index)
        cursor = end
    return labels


def render_document_html(document: AudioDocument, job_id: int) -> str:
    """Overlay WAV cue links on original Markdown leaves without replacing blocks."""
    markdown = MarkdownIt("commonmark", {"html": True}).enable("table")
    source_body, line_offset = split_frontmatter(document.source_text)
    tokens = markdown.parse(source_body)
    by_range = defaultdict(list)
    for index, cue in enumerate(document.cues):
        by_range[(cue.line_start, cue.line_end, cue.kind == "code")].append((index, cue))
    used = set()
    for token in tokens:
        if token.map is None:
            continue
        code = token.type in {"fence", "code_block"}
        candidates = by_range[(token.map[0] + line_offset, token.map[1] + line_offset, code)]
        if token.type == "inline":
            children = token.children or []
            labels = _cue_labels(inline_speech_parts(children), candidates, used)
            for index, child in enumerate(children):
                if child.type in {"text", "code_inline"}:
                    child.meta["cue_html"] = _linked_text(child.content, labels[index], job_id)
        elif code:
            labels = _cue_labels([(0, token.content)], candidates, used)
            token.meta["cue_html"] = _linked_text(token.content, labels[0], job_id)

    def text_leaf(tokens, index, options, environment):
        token = tokens[index]
        return token.meta.get("cue_html", escape(token.content))

    def inline_code(tokens, index, options, environment):
        return "<code>" + text_leaf(tokens, index, options, environment) + "</code>"

    def code_block(tokens, index, options, environment):
        token = tokens[index]
        language = token.info.strip().split(maxsplit=1)[0] if token.info.strip() else ""
        attributes = f' class="language-{escape(language, quote=True)}"' if language else ""
        content = token.meta.get("cue_html", escape(token.content))
        return f"<pre><code{attributes}>{content}</code></pre>\n"

    def image_alt(tokens, index, options, environment):
        def visible(children):
            return "".join(
                child.content
                if child.type in {"text", "code_inline"}
                else " "
                if child.type in {"softbreak", "hardbreak"}
                else visible(child.children or [])
                if child.type == "image"
                else ""
                for child in children
            )

        return (
            '<span class="image-alt">' + escape(visible(tokens[index].children or [])) + "</span>"
        )

    markdown.renderer.rules.update(
        {
            "text": text_leaf,
            "code_inline": inline_code,
            "fence": code_block,
            "code_block": code_block,
            "image": image_alt,
            "link_open": lambda *arguments: "<span>",
            "link_close": lambda *arguments: "</span>",
            "html_inline": lambda tokens, index, *arguments: escape(tokens[index].content),
            "html_block": lambda tokens, index, *arguments: (
                "<pre>" + escape(tokens[index].content) + "</pre>\n"
            ),
        }
    )
    body = markdown.renderer.render(tokens, markdown.options, {})
    if line_offset:
        metadata = "".join(document.source_text.splitlines(keepends=True)[:line_offset])
        body = '<pre class="frontmatter">' + escape(metadata) + "</pre>\n" + body
    return (
        "<html><head><style>"
        + """
        body { color: #e9e2d6; font-family: 'Segoe UI'; font-size: 13px; }
        a { color: #e9e2d6; text-decoration: none; }
        h1 { font-size: 22px; } h2 { font-size: 19px; } h3 { font-size: 16px; }
        p { margin-top: 8px; margin-bottom: 12px; }
        pre, code { font-family: 'Cascadia Mono', Consolas; color: #c4bcae; }
        blockquote { color: #d2c3a8; margin-left: 12px; }
        table { border-collapse: collapse; margin-bottom: 8px; }
        td, th { border: 1px solid #494137; padding: 5px; }
    """
        + "</style></head><body>"
        + body
        + "</body></html>"
    )
