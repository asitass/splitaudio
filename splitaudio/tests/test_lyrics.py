"""Tests for lyrics parsing."""

from splitaudio.metadata import parse_sections, _pick_lyrics


class TestParseSections:
    def test_with_markers(self):
        text = "[Verse 1]\nLine 1\nLine 2\n[Chorus]\nLine 3"
        sections = parse_sections(text)
        assert len(sections) >= 2
        markers = [s.marker for s in sections if s.marker]
        assert any("verse" in m.lower() for m in markers)
        assert any("chorus" in m.lower() for m in markers)

    def test_mixed_case(self):
        text = "[VERSE]\nLine\n[Chorus]\nLine"
        sections = parse_sections(text)
        assert len(sections) >= 2

    def test_no_markers(self):
        text = "Line 1\nLine 2\nLine 3"
        sections = parse_sections(text)
        assert len(sections) >= 1
        all_lines = " ".join(" ".join(s.lines) for s in sections)
        assert "Line 1" in all_lines

    def test_empty_string(self):
        sections = parse_sections("")
        assert len(sections) >= 1

    def test_chinese_markers(self):
        text = "[verse]\n歌词1\n[chorus]\n歌词2"
        sections = parse_sections(text)
        assert len(sections) >= 2

    def test_marker_with_number(self):
        text = "[Verse 1]\nLine\n[Verse 2]\nLine"
        sections = parse_sections(text)
        markers = [s.marker for s in sections if s.marker]
        assert len(markers) >= 2

    def test_bridge_marker(self):
        text = "[Bridge]\nTransition line"
        sections = parse_sections(text)
        assert any("bridge" in s.marker.lower() for s in sections if s.marker)


class TestPickLyrics:
    def test_lyrics_eng(self):
        tags = {"lyrics-eng": "Test lyrics", "title": "Song"}
        assert _pick_lyrics(tags) == "Test lyrics"

    def test_lyrics_underscore(self):
        tags = {"lyrics_eng": "Test", "title": "Song"}
        assert _pick_lyrics(tags) == "Test"

    def test_lyrics_lowercase(self):
        tags = {"LYRICS": "Test", "title": "Song"}
        assert _pick_lyrics(tags) == "Test"

    def test_no_lyrics(self):
        tags = {"title": "Song"}
        assert _pick_lyrics(tags) == ""

    def test_unsynclyrics(self):
        tags = {"unsynclyrics": "Test"}
        assert _pick_lyrics(tags) == "Test"
