"""
job_manager.py のテスト
"""

import signal

import pytest
from ytdlpcli.config import AppConfig
from ytdlpcli.job_manager import (
    CancelController,
    JobManager,
    _format_string_for_mode,
    _run_one,
    managed_signal_handlers,
)
from ytdlpcli.runner import YtDlpJob
from unittest.mock import Mock


def test_cancel_controller_initial_state():
    """CancelControllerの初期状態が正しい"""
    controller = CancelController()
    assert not controller.cancel_event.is_set()
    assert controller.reason is None


def test_cancel_controller_cancel_all():
    """cancel_all()が正しく動作する"""
    controller = CancelController()

    mock_job = Mock(spec=YtDlpJob)
    controller.register(mock_job)

    controller.cancel_all("user")

    assert controller.cancel_event.is_set()
    assert controller.reason == "user"
    mock_job.terminate.assert_called_once()


def test_format_string_for_mode_auto():
    """autoモードのフォーマット文字列が正しい"""
    assert _format_string_for_mode("auto") == "bestvideo+bestaudio/best"


def test_format_string_for_mode_mp4():
    """mp4モードのフォーマット文字列が正しい"""
    result = _format_string_for_mode("mp4")
    assert "mp4" in result
    assert "bestvideo" in result


def test_format_string_for_mode_invalid():
    """無効なモードでValueErrorが発生する"""
    with pytest.raises(ValueError):
        _format_string_for_mode("invalid")


def test_create_jobs_keeps_audio_mode_in_each_spec():
    """音声モードが暗黙状態ではなくジョブ仕様へ保持される"""
    manager = JobManager(AppConfig(), CancelController())

    specs = manager.create_jobs(["https://example.com/a", "https://example.com/b"], "audio")

    assert [spec.audio_only for spec in specs] == [True, True]
    assert all(spec.format_selector == "bestaudio/best" for spec in specs)


def test_managed_signal_handlers_restore_previous_handlers():
    """コンテキスト終了時にSIGINT/SIGTERMのハンドラーを復元する"""
    previous_int = signal.getsignal(signal.SIGINT)
    previous_term = signal.getsignal(signal.SIGTERM)

    with managed_signal_handlers(CancelController()):
        assert signal.getsignal(signal.SIGINT) != previous_int
        assert signal.getsignal(signal.SIGTERM) != previous_term

    assert signal.getsignal(signal.SIGINT) == previous_int
    assert signal.getsignal(signal.SIGTERM) == previous_term


def test_run_one_does_not_start_when_already_cancelled():
    """開始待ちジョブはキャンセル後に新規プロセスを起動しない"""
    controller = CancelController()
    controller.cancel_all("user")
    job = Mock(spec=YtDlpJob)

    result = _run_one(job, controller)

    assert result == (130, None, "Cancelled before start")
    job.start.assert_not_called()
