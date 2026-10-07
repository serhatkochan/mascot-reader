from collections import Counter, defaultdict
from html.parser import HTMLParser

import pytest

from mascot_reader.markdown import parse_markdown
from mascot_reader.reading import AudioCue, AudioDocument, render_document_html


class RenderedDocument(HTMLParser):
    def __init__(self, html):
        super().__init__(convert_charrefs=True)
        self.tags = Counter()
        self.attributes = []
        self.body_text = ""
        self.code_blocks = []
        self.anchors = []
        self._body = False
        self._pre = None
        self._anchor = None
        self.feed(html)

    def handle_starttag(self, tag, attributes):
        self.tags[tag] += 1
        self.attributes.append((tag, dict(attributes)))
        if tag == "body":
            self._body = True
        elif tag == "pre":
            self._pre = len(self.code_blocks)
            self.code_blocks.append("")
        elif tag == "a":
            self._anchor = len(self.anchors)
            self.anchors.append([dict(attributes).get("href"), ""])

    def handle_endtag(self, tag):
        if tag == "body":
            self._body = False
        elif tag == "pre":
            self._pre = None
        elif tag == "a":
            self._anchor = None

    def handle_data(self, text):
        if self._body:
            self.body_text += text
        if self._pre is not None:
            self.code_blocks[self._pre] += text
        if self._anchor is not None:
            self.anchors[self._anchor][1] += text


def document(source, *, include_code=False, max_chars=600):
    snapshot = parse_markdown(source, include_code=include_code, max_chars=max_chars)
    return AudioDocument(
        source,
        48000,
        tuple(
            AudioCue(
                segment.text,
                segment.kind,
                segment.line_start,
                segment.line_end,
                index * 48000,
                (index + 1) * 48000,
                48000,
            )
            for index, segment in enumerate(snapshot.segments)
        ),
    )


def test_rendering_preserves_inline_formatting_and_heading_levels():
    source = "## **Başlık**\n\nBir *vurgulu* metin ve `satır içi kod`.\n"
    rendered = RenderedDocument(render_document_html(document(source), job_id=12))
    assert rendered.tags["h2"] == 1
    assert rendered.tags["strong"] == 1
    assert rendered.tags["em"] == 1
    assert rendered.tags["code"] == 1
    assert "Başlık" in rendered.body_text
    assert "Bir vurgulu metin ve satır içi kod." in rendered.body_text
    assert {href for href, _ in rendered.anchors} == {"segment:12:0", "segment:12:1"}


def test_rendering_preserves_nested_list_structure_and_start_number():
    source = "3. Birinci\n4. İkinci\n   - İç madde\n"
    rendered = RenderedDocument(render_document_html(document(source), job_id=2))
    assert rendered.tags["ol"] == 1
    assert rendered.tags["ul"] == 1
    assert rendered.tags["li"] == 3
    assert ("ol", {"start": "3"}) in rendered.attributes
    assert {href for href, _ in rendered.anchors} == {
        "segment:2:0",
        "segment:2:1",
        "segment:2:2",
    }


def test_rendering_preserves_table_headers_rows_alignment_and_duplicate_cell_cues():
    source = "| Ad | Not |\n| :--- | ---: |\n| Ece | Aynı |\n| Ece | Aynı |\n"
    rendered = RenderedDocument(render_document_html(document(source), job_id=3))
    assert rendered.tags["table"] == 1
    assert rendered.tags["thead"] == 1
    assert rendered.tags["tbody"] == 1
    assert rendered.tags["tr"] == 3
    assert rendered.tags["th"] == 2
    assert rendered.tags["td"] == 4
    assert ("th", {"style": "text-align:left"}) in rendered.attributes
    assert ("th", {"style": "text-align:right"}) in rendered.attributes
    assert rendered.anchors == [
        ["segment:3:0", "Ad"],
        ["segment:3:1", "Not"],
        ["segment:3:2", "Ece"],
        ["segment:3:3", "Aynı"],
        ["segment:3:4", "Ece"],
        ["segment:3:5", "Aynı"],
    ]


@pytest.mark.parametrize("include_code", [False, True])
def test_rendering_preserves_code_newlines_and_indentation_when_spoken_or_skipped(include_code):
    code = 'if ready:\n    print("merhaba")\n\n    return 3\n'
    source = "# Başlık\n\n```python\n" + code + "```\n"
    audio_document = document(source, include_code=include_code, max_chars=20)
    rendered = RenderedDocument(render_document_html(audio_document, job_id=4))
    assert rendered.code_blocks == [code]
    code_cue_links = {
        f"segment:4:{index}" for index, cue in enumerate(audio_document.cues) if cue.kind == "code"
    }
    assert code_cue_links.issubset({href for href, _ in rendered.anchors})
    assert bool(code_cue_links) == include_code


def test_rendering_keeps_image_alt_text_and_disables_remote_links_and_resources():
    source = "Önce ![Güneş **parlak**](https://example.com/image.png) sonra [burada](https://example.com).\n"
    rendered = RenderedDocument(render_document_html(document(source), job_id=5))
    assert "Önce Güneş parlak sonra burada." in rendered.body_text
    assert rendered.tags["img"] == 0
    assert all(href.startswith("segment:5:") for href, _ in rendered.anchors)
    assert all("src" not in attributes for _, attributes in rendered.attributes)
    assert "Güneş" not in "".join(text for _, text in rendered.anchors)


def test_rendering_does_not_insert_spaces_into_words_split_between_audio_chunks():
    source = "abc**def**ghi jklm\n"
    audio_document = document(source, max_chars=5)
    rendered = RenderedDocument(render_document_html(audio_document, job_id=6))
    assert rendered.body_text.strip() == "abcdefghi jklm"
    assert rendered.tags["strong"] == 1
    spoken = defaultdict(str)
    for href, text in rendered.anchors:
        spoken[href] += text
    assert {href: " ".join(text.split()) for href, text in spoken.items()} == {
        "segment:6:0": "abcde",
        "segment:6:1": "fghi",
        "segment:6:2": "jklm",
    }


def test_rendering_keeps_frontmatter_and_escapes_html_without_matching_it_to_speech():
    source = "---\ntitle: Bilgi\n---\n\n# Başlık\n\nÖnce <b>kalın</b> sonra.\n\n<script>gizli()</script>\n"
    rendered = RenderedDocument(render_document_html(document(source), job_id=7))
    assert "title: Bilgi" in rendered.body_text
    assert "Önce <b>kalın</b> sonra." in rendered.body_text
    assert "<script>gizli()</script>" in rendered.body_text
    assert rendered.tags["script"] == 0
    assert {href for href, _ in rendered.anchors} == {"segment:7:0", "segment:7:1"}


@pytest.mark.parametrize("start_frame,wanted_ms", [(0, 0), (1, 1), (48, 1), (49, 2), (96000, 2000)])
def test_cue_start_milliseconds_round_up_to_reach_the_actual_audio_frame(start_frame, wanted_ms):
    cue = AudioCue("Bölüm", "paragraph", 0, 1, start_frame, start_frame + 48000, 48000)
    assert cue.start_ms == wanted_ms


def test_clicking_fractional_millisecond_cue_selects_that_cue():
    audio_document = AudioDocument(
        "İlk\nİkinci\n",
        48000,
        (
            AudioCue("İlk", "paragraph", 0, 1, 0, 49, 48000),
            AudioCue("İkinci", "paragraph", 1, 2, 49, 96000, 48000),
        ),
    )
    assert audio_document.cue_at(1) == 0
    assert audio_document.cue_at(audio_document.cues[1].start_ms) == 1


def test_frontmatter_dot_closing_marker_keeps_body_cue_context_without_a_blank_line():
    source = "---\ntitle: Bilgi\n...\nBuradaki metin okunur.\n"
    rendered = RenderedDocument(render_document_html(document(source), job_id=8))
    assert rendered.anchors == [["segment:8:0", "Buradaki metin okunur."]]
    assert "---\ntitle: Bilgi\n...\n" in rendered.body_text


def test_frontmatter_link_definitions_do_not_change_the_body_speech_parse_context():
    source = "---\n[selam]: https://example.com\n---\n\n[selam] okunur.\n"
    rendered = RenderedDocument(render_document_html(document(source), job_id=9))
    assert rendered.anchors == [["segment:9:0", "[selam] okunur."]]
    assert "[selam]: https://example.com" in rendered.body_text
    assert all(href.startswith("segment:9:") for href, _ in rendered.anchors)
