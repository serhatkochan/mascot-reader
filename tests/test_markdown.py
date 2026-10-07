from pathlib import Path

import pytest

from mascot_reader.markdown import markdown_to_segments, read_markdown


def test_reads_markdown_blocks_and_visible_link_text_in_document_order():
    source = """# Başlık

Merhaba **dünya**. [Bağlantı](https://example.com) ve `kod`.

- Birinci
- İkinci

> Alıntı

| Ad | Yaş |
| --- | --- |
| Ece | 23 |
"""
    assert markdown_to_segments(source) == [
        "Başlık",
        "Merhaba dünya. Bağlantı ve kod.",
        "Birinci",
        "İkinci",
        "Alıntı",
        "Ad",
        "Yaş",
        "Ece",
        "23",
    ]


def test_skips_fenced_and_indented_code_by_default():
    source = "Önce.\n\n```python\nprint('gizli')\n```\n\n    gizli = 3\n\nSonra."
    assert markdown_to_segments(source) == ["Önce.", "Sonra."]


def test_can_include_code_blocks_as_text():
    source = "Önce.\n\n```python\nprint('a')\nprint('b')\n```\n\n    x = 3\n\nSonra."
    assert markdown_to_segments(source, include_code=True) == [
        "Önce.",
        "print('a') print('b')",
        "x = 3",
        "Sonra.",
    ]


def test_omits_images_frontmatter_and_executable_html():
    source = """---
title: Gizli başlık
secret: saklı
---
# Görünen

![Görsel açıklaması](image.png)

<script>alert('gizli')</script>

Önce <b>kalın</b> sonra.
"""
    assert markdown_to_segments(source) == ["Görünen", "Önce kalın sonra."]


def test_splits_long_paragraph_without_losing_order_or_words():
    source = "Birinci cümle burada. İkinci cümle daha uzun. Üçüncü cümle bitti."
    segments = markdown_to_segments(source, max_chars=30)
    assert len(segments) > 1
    assert all(len(segment) <= 30 for segment in segments)
    assert " ".join(segments) == source


def test_splits_single_long_word_to_keep_model_input_bounded():
    assert markdown_to_segments("a" * 75, max_chars=30) == ["a" * 30, "a" * 30, "a" * 15]


@pytest.mark.parametrize("source", ["", "  \n", "***\n---", "```\ncode only\n```"])
def test_rejects_documents_with_no_readable_text(source):
    with pytest.raises(ValueError):
        markdown_to_segments(source)


def test_rejects_invalid_chunk_limit():
    with pytest.raises(ValueError):
        markdown_to_segments("Merhaba", max_chars=0)


def test_reads_bom_prefixed_utf8_markdown(tmp_path: Path):
    source = tmp_path / "Türkçe.MD"
    source.write_bytes(b"\xef\xbb\xbf" + "# Şimdi\n\nışık".encode())
    assert read_markdown(source) == ["Şimdi", "ışık"]


def test_rejects_non_markdown_extension(tmp_path: Path):
    source = tmp_path / "notes.txt"
    source.write_text("Merhaba", encoding="utf-8")
    with pytest.raises(ValueError):
        read_markdown(source)


def test_reports_invalid_utf8(tmp_path: Path):
    source = tmp_path / "bad.markdown"
    source.write_bytes(b"\xff\xfe\x00")
    with pytest.raises(ValueError, match="UTF-8"):
        read_markdown(source)


def test_omits_inline_script_and_style_contents_but_keeps_surrounding_text():
    source = "Baş <script>alert('gizli')</script> orta <style>.gizli { color: red; }</style> son."
    assert markdown_to_segments(source) == ["Baş orta son."]
