"""
runner.py のテスト
"""

import pytest
from unittest.mock import Mock, patch
from ytdlpcli.runner import YtDlpJob, _parse_progress_value, ProgressSnapshot
from ytdlpcli.exceptions import YtdlpNotFoundError


def test_parse_progress_value():
    """進捗値のパースが正しく動作する"""
    assert _parse_progress_value("1024") == 1024
    assert _parse_progress_value("1024.5") == 1024
    assert _parse_progress_value("NA") == -1
    assert _parse_progress_value("") == -1


def test_start_raises_error_when_ytdlp_not_found():
    """yt-dlpが見つからない場合にYtdlpNotFoundErrorを発生させる"""
    job = YtDlpJob(
        url="https://example.com/video",
        fmt="best",
        download_dir="/tmp",
        merge_output_format="mp4",
        retries=3
    )

    with patch("subprocess.Popen") as mock_popen:
        mock_popen.side_effect = FileNotFoundError("yt-dlp not found")

        with pytest.raises(YtdlpNotFoundError):
            job.start()


def test_poll_progress_returns_snapshot():
    """poll_progress()がProgressSnapshotを返す"""
    job = YtDlpJob(
        url="https://example.com/video",
        fmt="best",
        download_dir="/tmp",
        merge_output_format="mp4",
        retries=3
    )

    snapshot = job.poll_progress()
    assert isinstance(snapshot, ProgressSnapshot)
    assert snapshot.downloaded == 0
    assert snapshot.total == 0
    assert snapshot.eta == -1
    assert snapshot.speed == -1


def test_terminate_calls_proc_terminate():
    """terminate()がプロセスを終了させる"""
    job = YtDlpJob(
        url="https://example.com/video",
        fmt="best",
        download_dir="/tmp",
        merge_output_format="mp4",
        retries=3
    )

    mock_proc = Mock()
    mock_proc.poll.return_value = None
    job._proc = mock_proc

    job.terminate()
    mock_proc.terminate.assert_called_once()
