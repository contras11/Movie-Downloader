"""
ui.py のテスト
"""

from ytdlpcli.ui import Formatter


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
