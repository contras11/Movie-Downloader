"""
formats.py のテスト
"""

import subprocess
import sys

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


def test_fetch_info_json_raises_error_when_command_times_out():
    """フォーマット取得がタイムアウトした場合にFormatFetchErrorへ変換する"""
    with patch("subprocess.run", side_effect=subprocess.TimeoutExpired("yt-dlp", 60)):
        with pytest.raises(FormatFetchError, match="タイムアウト"):
            fetch_info_json("https://example.com/video")


def test_fetch_info_json_raises_error_for_invalid_json():
    """yt-dlpのJSONが壊れている場合にFormatFetchErrorへ変換する"""
    mock_result = Mock(returncode=0, stdout="not-json", stderr="")

    with patch("subprocess.run", return_value=mock_result):
        with pytest.raises(FormatFetchError, match="解析"):
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


def test_format_fetch_treats_option_like_url_as_positional_argument():
    result = Mock(returncode=0, stdout='{"formats": []}', stderr="")
    with patch("subprocess.run", return_value=result) as run:
        fetch_info_json("--exec=unexpected-command")

    assert run.call_args.args[0][-2:] == ["--", "--exec=unexpected-command"]


def test_invalid_bytes_in_fetch_error_are_reported_without_decode_failure():
    run_process = subprocess.run

    def emit_invalid_error(command, **kwargs):
        return run_process(
            [sys.executable, "-c", "import os; os.write(2, b'error: \\xff'); raise SystemExit(1)"],
            **kwargs,
        )

    with patch("ytdlpcli.formats.subprocess.run", side_effect=emit_invalid_error):
        with pytest.raises(FormatFetchError, match="error:"):
            fetch_info_json("https://example.com/video")
