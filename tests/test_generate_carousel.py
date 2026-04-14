from pathlib import Path

import pytest

from generate_carousel import _parse_tokens_line, find_images, parse_texts_md


class TestParseTextsMd:
    def test_parses_single_section(self, tmp_path):
        md = tmp_path / "texts.md"
        md.write_text("# 1\nHello World\n")
        result = parse_texts_md(md)
        assert result == {1: "Hello World"}

    def test_parses_multiple_sections(self, tmp_path):
        md = tmp_path / "texts.md"
        md.write_text("# 1\nFirst slide\n\n# 2\nSecond slide\n")
        result = parse_texts_md(md)
        assert result == {1: "First slide", 2: "Second slide"}

    def test_strips_leading_trailing_blank_lines(self, tmp_path):
        md = tmp_path / "texts.md"
        md.write_text("# 1\n\nHello\n\n")
        result = parse_texts_md(md)
        assert result[1] == "Hello"

    def test_empty_section_returns_empty_string(self, tmp_path):
        md = tmp_path / "texts.md"
        md.write_text("# 1\n\n# 2\nSomething\n")
        result = parse_texts_md(md)
        assert result[1] == ""
        assert result[2] == "Something"

    def test_multiline_text_in_section(self, tmp_path):
        md = tmp_path / "texts.md"
        md.write_text("# 1\nLine one\nLine two\n")
        result = parse_texts_md(md)
        assert result[1] == "Line one\nLine two"

    def test_non_numeric_headings_are_ignored(self, tmp_path):
        md = tmp_path / "texts.md"
        md.write_text("# Introduction\nSome text\n\n# 1\nReal slide\n")
        result = parse_texts_md(md)
        assert 1 in result
        assert "Introduction" not in str(result.keys())


class TestFindImages:
    def test_finds_png_files(self, tmp_path):
        (tmp_path / "1.png").touch()
        (tmp_path / "2.png").touch()
        result = find_images(tmp_path)
        assert len(result) == 2
        names = [p.name for p in result]
        assert "1.png" in names
        assert "2.png" in names

    def test_returns_sorted_by_number(self, tmp_path):
        (tmp_path / "3.jpg").touch()
        (tmp_path / "1.png").touch()
        (tmp_path / "2.jpeg").touch()
        result = find_images(tmp_path)
        indices = [int(p.stem) for p in result]
        assert indices == sorted(indices)

    def test_ignores_non_image_files(self, tmp_path):
        (tmp_path / "1.png").touch()
        (tmp_path / "readme.txt").touch()
        (tmp_path / "data.json").touch()
        result = find_images(tmp_path)
        assert len(result) == 1
        assert result[0].name == "1.png"

    def test_supports_webp(self, tmp_path):
        (tmp_path / "1.webp").touch()
        result = find_images(tmp_path)
        assert len(result) == 1

    def test_empty_directory_returns_empty_list(self, tmp_path):
        result = find_images(tmp_path)
        assert result == []


class TestParseTokensLine:
    def test_plain_text_is_normal(self):
        tokens = _parse_tokens_line("Hello World")
        assert tokens == [("Hello", "normal"), ("World", "normal")]

    def test_bold_text(self):
        tokens = _parse_tokens_line("**bold** word")
        assert ("bold", "bold") in tokens
        assert ("word", "normal") in tokens

    def test_italic_text(self):
        tokens = _parse_tokens_line("*italic* word")
        assert ("italic", "italic") in tokens
        assert ("word", "normal") in tokens

    def test_mixed_bold_and_normal(self):
        tokens = _parse_tokens_line("Before **bolded** after")
        styles = {word: style for word, style in tokens}
        assert styles["Before"] == "normal"
        assert styles["bolded"] == "bold"
        assert styles["after"] == "normal"

    def test_empty_line_returns_empty(self):
        tokens = _parse_tokens_line("")
        assert tokens == []

    def test_only_bold_markers_returns_empty(self):
        tokens = _parse_tokens_line("****")
        assert tokens == []

    def test_multiple_words_in_bold(self):
        tokens = _parse_tokens_line("**hello world**")
        assert all(style == "bold" for _, style in tokens)
        assert len(tokens) == 2
