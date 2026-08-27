"""Tests for filename sanitization."""

from splitaudio.naming import sanitize_filename


class TestSanitizeFilename:
    def test_normal_name(self):
        assert sanitize_filename("hello") == "hello"

    def test_chinese_preserved(self):
        result = sanitize_filename("我想大概是你变了")
        assert result == "我想大概是你变了"

    def test_illegal_chars_replaced(self):
        result = sanitize_filename('file<>:"/\\|?*name')
        assert "<" not in result
        assert ">" not in result
        assert ":" not in result
        assert '"' not in result
        assert "/" not in result
        assert "\\" not in result
        assert "|" not in result
        assert "?" not in result
        assert "*" not in result

    def test_control_chars_replaced(self):
        result = sanitize_filename("file\x00name\x1f")
        assert "\x00" not in result
        assert "\x1f" not in result

    def test_windows_reserved_con(self):
        result = sanitize_filename("CON")
        assert result == "CON_file"

    def test_windows_reserved_com1(self):
        result = sanitize_filename("com1")
        assert result == "com1_file"

    def test_windows_reserved_nul(self):
        result = sanitize_filename("NUL.txt")
        assert result.startswith("NUL")
        assert "file" in result

    def test_trailing_dots_stripped(self):
        result = sanitize_filename("name...")
        assert not result.endswith(".")

    def test_trailing_spaces_stripped(self):
        result = sanitize_filename("name   ")
        assert not result.endswith(" ")

    def test_max_length(self):
        long_name = "a" * 200
        result = sanitize_filename(long_name, max_len=120)
        assert len(result) <= 120

    def test_empty_becomes_untitled(self):
        assert sanitize_filename("") == "untitled"

    def test_only_dots_becomes_untitled(self):
        assert sanitize_filename("...") == "untitled"

    def test_mixed_content(self):
        result = sanitize_filename("Test: Song <v2> (feat. Artist)")
        assert ":" not in result
        assert "<" not in result
        assert ">" not in result
