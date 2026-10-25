"""
runner.py のテスト
"""

import os
import signal
import sys
import threading

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
    assert _parse_progress_value("nan") == -1
    assert _parse_progress_value("inf") == -1


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


def test_terminate_signals_process_group():
    """ffmpeg等の子プロセスも同じグループとして停止する"""
    job = YtDlpJob(
        url="https://example.com/video",
        fmt="best",
        download_dir="/tmp",
        merge_output_format="mp4",
        retries=3
    )

    mock_proc = Mock()
    mock_proc.pid = 12345
    mock_proc.poll.return_value = None
    job._proc = mock_proc

    with patch("ytdlpcli.runner.os.killpg") as killpg, patch("threading.Timer"):
        job.terminate()
        killpg.assert_called_once_with(mock_proc.pid, signal.SIGTERM)


@pytest.mark.parametrize("audio_only", [False, True])
def test_build_command_disables_playlist_for_video_and_audio(audio_only):
    """動画・音声の両モードでプレイリストを無効化する"""
    job = YtDlpJob(
        url="https://example.com/video?list=playlist",
        fmt="best",
        download_dir="/tmp",
        merge_output_format="mp4",
        retries=3,
        audio_only=audio_only,
    )

    assert "--no-playlist" in job._build_command()


@pytest.mark.parametrize("audio_only", [False, True])
def test_url_cannot_be_interpreted_as_an_option(audio_only):
    """URL欄から--exec等のyt-dlpオプションを指定できない"""
    job = YtDlpJob("--exec=echo injected", "best", "/tmp", "mp4", 3, audio_only)

    assert job._build_command()[-2:] == ["--", job.url]


@pytest.fixture
def local_job(tmp_path, monkeypatch):
    """ネットワークや設定を使わず、実際の子プロセスを検証する。"""
    job = YtDlpJob("https://example.invalid", "best", str(tmp_path), "mp4", 0)
    job.waiters = []
    monkeypatch.setattr(job, "_build_command", lambda: [sys.executable, "-u", "-c", job.script])
    yield job
    if job._proc is not None:
        try:
            os.killpg(job._proc.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
        if job._proc.poll() is None:
            job._proc.kill()
        job._proc.wait(timeout=5)
        for waiter in job.waiters:
            waiter.join(timeout=5)
            assert not waiter.is_alive()
        if job._proc.stdout:
            job._proc.stdout.close()


def test_wait_replaces_invalid_output_and_parses_progress(local_job):
    """不正な文字がログに混ざっても進捗と終了を取得する"""
    local_job.script = (
        "import os; os.write(1, b'bad byte: \\xff\\n'); "
        "print('[ytdlpcli] downloaded=512 total=1024 eta=NA speed=32.5')"
    )
    local_job.start()

    assert local_job.wait() == 0
    assert local_job.poll_progress() == ProgressSnapshot(512, 1024, -1, 32)
    assert "bad byte:" in local_job.stderr_tail
    assert local_job._proc.stdout.closed


def test_terminate_escalates_when_sigterm_is_ignored(local_job):
    """SIGTERMを無視されても終了待ちが続かない"""
    local_job.script = (
        "import signal, time; signal.signal(signal.SIGTERM, signal.SIG_IGN); "
        "print('ready'); time.sleep(30)"
    )
    local_job.start()
    assert local_job._proc.stdout.readline().strip() == "ready"
    assert os.getpgid(local_job._proc.pid) == local_job._proc.pid
    assert os.getpgid(local_job._proc.pid) != os.getpgrp()
    result = []
    waiter = threading.Thread(target=lambda: result.append(local_job.wait()), daemon=True)
    local_job.waiters.append(waiter)
    waiter.start()

    local_job.terminate()
    local_job.terminate()
    waiter.join(timeout=5)

    assert not waiter.is_alive()
    assert result == [-signal.SIGKILL]


def test_terminate_stops_child_after_parent_exit(local_job, tmp_path):
    """本体が先に終了しても、標準出力を継承した子を停止する"""
    child_pid_file = tmp_path / "child.pid"
    local_job.script = (
        "import os, signal, time; pid = os.fork(); "
        "\nif pid == 0:\n"
        " signal.signal(signal.SIGTERM, signal.SIG_IGN)\n"
        f" open({str(child_pid_file)!r}, 'w').write(str(os.getpid()))\n"
        " time.sleep(30)\n"
        "else:\n"
        " while not os.path.exists(" + repr(str(child_pid_file)) + "): time.sleep(0.01)\n"
        " print('ready')\n"
    )
    local_job.start()
    assert local_job._proc.stdout.readline().strip() == "ready"
    assert local_job._proc.wait(timeout=5) == 0
    result = []
    waiter = threading.Thread(target=lambda: result.append(local_job.wait()), daemon=True)
    local_job.waiters.append(waiter)
    waiter.start()
    try:
        local_job.terminate()
        waiter.join(timeout=5)
        assert not waiter.is_alive()
        assert result == [0]
    finally:
        try:
            os.kill(int(child_pid_file.read_text()), signal.SIGKILL)
        except ProcessLookupError:
            pass
        waiter.join(timeout=5)


def test_wait_stops_and_reaps_process_when_output_processing_fails(local_job, monkeypatch):
    """ログ処理が例外になってもプロセスとパイプを残さない"""
    local_job.script = (
        "import time; print('[ytdlpcli] downloaded=1 total=2 eta=0 speed=1'); "
        "time.sleep(30)"
    )
    monkeypatch.setattr("ytdlpcli.runner._parse_progress_value", Mock(side_effect=ValueError("parse")))
    local_job.start()

    with pytest.raises(ValueError, match="parse"):
        local_job.wait()

    assert local_job.returncode == -signal.SIGTERM
    assert local_job._proc.stdout.closed
