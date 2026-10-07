import json
import threading
import wave
from dataclasses import FrozenInstanceError
from pathlib import Path

import numpy as np
import pytest

from mascot_reader.markdown import (
    MarkdownSegment,
    MarkdownSnapshot,
    parse_markdown,
    read_markdown_snapshot,
)
from mascot_reader.synthesis import AudioPreparer, PreparationCancelled

SOURCE = (
    "---\nname: meta\n---\n\n\n# Başlık\n\nSatır bir.\nSatır iki.\n\n"
    "- Liste\n\n> Alıntı\n\n| Ad | Yaş |\n| --- | --- |\n| Ece | 23 |\n\n"
    "```python\nx = 1\n```\n\n    y = 2\n\n"
)


def test_snapshot_keeps_full_source_and_maps_blocks_after_frontmatter():
    assert parse_markdown(SOURCE, include_code=True) == MarkdownSnapshot(
        SOURCE,
        (
            MarkdownSegment("Başlık", "heading", 5, 6),
            MarkdownSegment("Satır bir. Satır iki.", "paragraph", 7, 9),
            MarkdownSegment("Liste", "list_item", 10, 11),
            MarkdownSegment("Alıntı", "blockquote", 12, 13),
            MarkdownSegment("Ad", "table_cell", 14, 15),
            MarkdownSegment("Yaş", "table_cell", 14, 15),
            MarkdownSegment("Ece", "table_cell", 16, 17),
            MarkdownSegment("23", "table_cell", 16, 17),
            MarkdownSegment("x = 1", "code", 18, 21),
            MarkdownSegment("y = 2", "code", 22, 23),
        ),
    )


def test_snapshot_preserves_crlf_leading_spaces_and_trailing_blank_lines(tmp_path):
    source_text = "\r\n  # Başlık\r\n\r\nParagraf.  \r\n\r\n"
    path = tmp_path / "source.md"
    path.write_bytes(b"\xef\xbb\xbf" + source_text.encode())
    snapshot = read_markdown_snapshot(path)
    assert snapshot.source_text == source_text
    assert snapshot.segments == (
        MarkdownSegment("Başlık", "heading", 1, 2),
        MarkdownSegment("Paragraf.", "paragraph", 3, 4),
    )


def test_split_segments_and_table_cells_retain_their_source_block_ranges():
    source = "\nalpha beta gamma delta\n\n| Long |\n| --- |\n| alpha beta gamma delta |\n"
    assert parse_markdown(source, max_chars=10).segments == (
        MarkdownSegment("alpha beta", "paragraph", 1, 2),
        MarkdownSegment("gamma", "paragraph", 1, 2),
        MarkdownSegment("delta", "paragraph", 1, 2),
        MarkdownSegment("Long", "table_cell", 3, 4),
        MarkdownSegment("alpha beta", "table_cell", 5, 6),
        MarkdownSegment("gamma", "table_cell", 5, 6),
        MarkdownSegment("delta", "table_cell", 5, 6),
    )


def test_snapshot_is_immutable_and_excluded_code_remains_in_source():
    source = "# Başlık\n\n```py\nx = 1\n```\n"
    snapshot = parse_markdown(source)
    assert snapshot.source_text == source
    assert snapshot.segments == (MarkdownSegment("Başlık", "heading", 0, 1),)
    with pytest.raises(FrozenInstanceError):
        snapshot.source_text = "changed"
    with pytest.raises(FrozenInstanceError):
        snapshot.segments[0].text = "changed"


class TinyModel:
    def stream(self, text, *, speed, sample_rate):
        assert sample_rate == 48000
        yield np.zeros(2, dtype=np.float32)
        yield np.ones(3, dtype=np.float32)


def write_source(tmp_path: Path, text: str = "# Başlık\n\nParagraf.\n") -> Path:
    source = tmp_path / "source.md"
    source.write_bytes(text.encode())
    return source


def read_cues(output: Path):
    path = output.with_suffix(".cues.json")
    assert path.exists(), "Preparation did not write a matching cue document"
    return json.loads(path.read_text(encoding="utf-8"))


def test_cues_record_actual_chunk_frame_boundaries_and_original_source(tmp_path):
    source = write_source(tmp_path)
    output = tmp_path / "audio.wav"
    assert (
        AudioPreparer(TinyModel).prepare(source, output, cancel_event=threading.Event()) == output
    )
    assert read_cues(output) == {
        "schema_version": 1,
        "sample_rate": 48000,
        "source_text": "# Başlık\n\nParagraf.\n",
        "cues": [
            {
                "text": "Başlık",
                "kind": "heading",
                "line_start": 0,
                "line_end": 1,
                "start_frame": 0,
                "end_frame": 5,
            },
            {
                "text": "Paragraf.",
                "kind": "paragraph",
                "line_start": 2,
                "line_end": 3,
                "start_frame": 5,
                "end_frame": 10,
            },
        ],
    }
    with wave.open(str(output), "rb") as wav:
        assert wav.getnframes() == 10


def test_source_changes_during_synthesis_do_not_change_audio_or_cue_snapshot(tmp_path):
    source_text = "# İlk\n\nEski metin.\n"
    source = write_source(tmp_path, source_text)

    class ChangingSourceModel:
        def stream(self, text, *, speed, sample_rate):
            if text == "İlk":
                source.write_text("# Yeni\n\nYeni metin.", encoding="utf-8")
                yield np.zeros(4, dtype=np.float32)
            elif text == "Eski metin.":
                yield np.zeros(6, dtype=np.float32)
            else:
                raise ValueError("Speech source changed during preparation")

    output = tmp_path / "snapshot.wav"
    AudioPreparer(ChangingSourceModel).prepare(source, output, cancel_event=threading.Event())
    cues = read_cues(output)
    assert cues["source_text"] == source_text
    assert [cue["text"] for cue in cues["cues"]] == ["İlk", "Eski metin."]
    assert [(cue["start_frame"], cue["end_frame"]) for cue in cues["cues"]] == [(0, 4), (4, 10)]


def test_speed_and_code_option_generate_cues_for_the_new_audio(tmp_path):
    class SpeedModel:
        def stream(self, text, *, speed, sample_rate):
            yield np.zeros(3 if speed == 2.0 else 6, dtype=np.float32)

    source = write_source(tmp_path, "# Başlık\n\n```py\nx = 1\n```\n")
    preparer = AudioPreparer(SpeedModel)
    normal = tmp_path / "normal.wav"
    changed = tmp_path / "changed.wav"
    preparer.prepare(source, normal, cancel_event=threading.Event())
    preparer.prepare(source, changed, speed=2.0, include_code=True, cancel_event=threading.Event())
    assert [
        (cue["kind"], cue["start_frame"], cue["end_frame"]) for cue in read_cues(normal)["cues"]
    ] == [("heading", 0, 6)]
    assert [
        (cue["kind"], cue["start_frame"], cue["end_frame"]) for cue in read_cues(changed)["cues"]
    ] == [("heading", 0, 3), ("code", 3, 6)]


def test_existing_cue_document_is_preserved_without_creating_audio(tmp_path):
    output = tmp_path / "audio.wav"
    cue_path = output.with_suffix(".cues.json")
    cue_path.write_text("keep me", encoding="utf-8")
    with pytest.raises(FileExistsError):
        AudioPreparer(TinyModel).prepare(
            write_source(tmp_path), output, cancel_event=threading.Event()
        )
    assert cue_path.read_text(encoding="utf-8") == "keep me"
    assert not output.exists()


def test_sidecar_write_failure_removes_both_created_files(tmp_path, monkeypatch):
    def broken_dump(payload, destination, **kwargs):
        destination.write("partial document")
        raise OSError("Disk full")

    monkeypatch.setattr("mascot_reader.synthesis.json.dump", broken_dump)
    output = tmp_path / "broken.wav"
    with pytest.raises(OSError, match="Disk full"):
        AudioPreparer(TinyModel).prepare(
            write_source(tmp_path), output, cancel_event=threading.Event()
        )
    assert not output.exists()
    assert not output.with_suffix(".cues.json").exists()


def test_cancellation_after_sidecar_write_removes_both_created_files(tmp_path, monkeypatch):
    cancel = threading.Event()
    real_dump = json.dump

    def cancelling_dump(payload, destination, **kwargs):
        real_dump(payload, destination, **kwargs)
        cancel.set()

    monkeypatch.setattr("mascot_reader.synthesis.json.dump", cancelling_dump)
    output = tmp_path / "cancelled.wav"
    with pytest.raises(PreparationCancelled):
        AudioPreparer(TinyModel).prepare(write_source(tmp_path), output, cancel_event=cancel)
    assert not output.exists()
    assert not output.with_suffix(".cues.json").exists()
