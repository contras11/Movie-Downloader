"""
formats.py のテスト
"""

import pytest
from unittest.mock import patch, Mock
from ytdlpcli.formats import fetch_info_json, VideoFormat
from ytdlpcli.exceptions import YtdlpNotFoundError, FormatFetchError


def test_fetch_info_json_raises_error_when_ytdlp_not_found():
    """yt-dlpが見つからない場合にYtdlpNotFoundErrorを発生させる"""
    with patch("subprocess.run") as mock_run:
        mock_run.side_effect = FileNotFoundError("yt-dlp not found")

        with pytest.raises(YtdlpNotFoundError):
            fetch_info_json("https://example.com/video")


def test_fetch_info_json_raises_error_when_command_fails():
    """yt-dlpコマンドが失敗した場合にFormatFetchErrorを発生させる"""
    mock_result = Mock()
    mock_result.returncode = 1
    mock_result.stderr = "Error: Video not found"

    with patch("subprocess.run", return_value=mock_result):
        with pytest.raises(FormatFetchError):
            fetch_info_json("https://example.com/video")


def test_video_format_label():
    """VideoFormat.labelが正しくフォーマットされる"""
    fmt = VideoFormat(
        format_id="137",
        ext="mp4",
        width=1920,
        height=1080,
        fps=30.0,
        vcodec="avc1",
        tbr=2500.0,
        filesize=1024 * 1024 * 100  # 100 MiB
    )

    label = fmt.label
    assert "1920x1080" in label
    assert "30fps" in label
    assert "mp4" in label
    assert "avc1" in label
    assert "2500kbps" in label
    assert "100MiB" in label
