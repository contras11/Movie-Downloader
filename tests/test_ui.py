"""ui.py のテスト"""

from io import StringIO
from unittest.mock import patch

import pytest
from rich.console import Console

from ytdlpcli.exceptions import FormatFetchError, YtdlpNotFoundError
from ytdlpcli.ui import Formatter, FormatSelector, print_summary


def test_format_bytes():
    """バイト数のフォーマットが正しく動作する"""
    assert Formatter.bytes(0) == "0B"
    assert Formatter.bytes(1024) == "1.0KiB"
    assert Formatter.bytes(1048576) == "1.0MiB"
    assert Formatter.bytes(1073741824) == "1.0GiB"
    assert Formatter.bytes(-1) == "--"


def test_format_speed():
    """速度のフォーマットが正しく動作する"""
    assert Formatter.speed(0) == "--"
    assert Formatter.speed(-1) == "--"
    assert Formatter.speed(1024) == "1.0KiB/s"
    assert Formatter.speed(1048576) == "1.0MiB/s"


def test_format_eta():
    """ETAのフォーマットが正しく動作する"""
    assert Formatter.eta(-1) == "--"
    assert Formatter.eta(30) == "30s"
    assert Formatter.eta(90) == "1m30s"
    assert Formatter.eta(3661) == "1h01m"


def test_format_download():
    """ダウンロード量のフォーマットが正しく動作する"""
    assert Formatter.download(-1, -1) == "-- / --"
    assert Formatter.download(1024, -1) == "1.0KiB / --"
    assert Formatter.download(-1, 1024) == "-- / 1.0KiB"
    assert Formatter.download(512, 1024) == "512B / 1.0KiB"


def test_format_percent():
    """パーセント表示が正しく動作する"""
    assert Formatter.percent(-1, -1) == "--.-%"
    assert Formatter.percent(-1, 1024) == "--.-%"
    assert Formatter.percent(512, 1024) == " 50.0%"
    assert Formatter.percent(1024, 1024) == "100.0%"


def test_short_url_youtube():
    """YouTube URLが短縮される"""
    url = "https://www.youtube.com/watch?v=dQw4w9WgXcQ&feature=share"
    assert Formatter.short_url(url) == "youtube:dQw4w9WgXcQ"


def test_short_url_long():
    """長いURLが短縮される"""
    url = "https://example.com/very/long/path/to/video/file.mp4"
    shortened = Formatter.short_url(url)
    assert len(shortened) <= 40
    assert shortened.endswith("...")


def test_short_url_short():
    """短いURLはそのまま"""
    url = "https://example.com/video"
    assert Formatter.short_url(url) == url


def test_error_detail_keeps_last_meaningful_lines_and_limits_length():
    """失敗ログは空行を除き末尾の意味ある行へ絞る"""
    detail = Formatter.error_detail("first\n\nsecond\nthird\nfourth", max_lines=3)

    assert detail == "second\nthird\nfourth"


def test_format_selector_falls_back_when_format_fetch_fails():
    """askモードの通信失敗時に自動フォーマットへフォールバックする"""
    output = StringIO()
    selector = FormatSelector(Console(file=output, force_terminal=False))

    with patch("ytdlpcli.ui.list_video_formats", side_effect=FormatFetchError("network error")):
        selected = selector.select_by_number("https://example.com/video", 12)

    assert selected == "bestvideo+bestaudio/best"
    assert "最高品質" in output.getvalue()


def test_format_selector_does_not_hide_missing_ytdlp():
    """依存不足は自動フォールバックせず上位へ伝える"""
    selector = FormatSelector(Console(file=StringIO(), force_terminal=False))

    with patch("ytdlpcli.ui.list_video_formats", side_effect=YtdlpNotFoundError()):
        with pytest.raises(YtdlpNotFoundError):
            selector.select_by_number("https://example.com/video", 12)


def test_summary_displays_log_markup_as_plain_text():
    """URLやログ内の角括弧をRichマークアップとして解釈しない"""
    output = StringIO()

    with patch("ytdlpcli.ui.console", Console(file=output, force_terminal=False, width=120)):
        print_summary([("https://example.com/[video]", 1, None, "[error] denied")], True)

    rendered = output.getvalue()
    assert "[video]" in rendered
    assert "[error] denied" in rendered
