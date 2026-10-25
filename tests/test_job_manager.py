"""
job_manager.py のテスト
"""

import signal
import threading

import pytest
from ytdlpcli.config import AppConfig
from ytdlpcli.job_manager import (
    CancelController,
    DownloadSpec,
    JobManager,
    _format_string_for_mode,
    _run_one,
    managed_signal_handlers,
)
from ytdlpcli.runner import ProgressSnapshot, YtDlpJob
from ytdlpcli.exceptions import YtdlpNotFoundError
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


def test_run_one_cancels_process_created_during_cancellation():
    """起動処理の途中でキャンセルされても、生成後のプロセスを停止する"""
    controller = CancelController()
    job = Mock(spec=YtDlpJob, output_path=None, stderr_tail="")
    job.start.side_effect = lambda: controller.cancel_all("user")
    job.wait.return_value = -signal.SIGTERM

    assert _run_one(job, controller) == (130, None, "")
    assert job.terminate.call_count >= 1


def test_failure_cancels_queue_before_worker_returns():
    """主スレッドのポーリングを待たず、失敗直後に開始待ちを中断する"""
    controller = CancelController()
    failed = Mock(spec=YtDlpJob, output_path=None, stderr_tail="failure")
    failed.wait.return_value = 1
    queued = Mock(spec=YtDlpJob)

    assert _run_one(failed, controller, continue_on_error=False) == (1, None, "failure")
    assert controller.cancel_event.is_set()
    assert controller.reason == "error"
    assert _run_one(queued, controller) == (130, None, "Cancelled before start")
    queued.start.assert_not_called()


@pytest.mark.parametrize("dependency_error", [False, True])
def test_worker_stops_queued_jobs_before_polling(monkeypatch, dependency_error):
    """失敗が発生したワーカー自身が、待機中ジョブの開始を止める"""
    controller = CancelController()
    manager = JobManager(AppConfig(max_workers=1, continue_on_error=dependency_error), controller)
    instances = []

    def make_job(**kwargs):
        job = Mock(spec=YtDlpJob, output_path=None, stderr_tail="failure")
        job.wait.return_value = 1
        job.poll_progress.return_value = ProgressSnapshot()
        if dependency_error:
            job.start.side_effect = YtdlpNotFoundError()
        instances.append(job)
        return job

    monkeypatch.setattr("ytdlpcli.job_manager.YtDlpJob", make_job)
    specs = [DownloadSpec(f"https://example.invalid/{i}", "best", False) for i in range(3)]
    results = manager.execute_parallel(specs, Mock())

    instances[0].start.assert_called_once()
    for job in instances[1:]:
        job.start.assert_not_called()
    assert sorted(rc for _, rc, _, _ in results) == ([2, 130, 130] if dependency_error else [1, 130, 130])


def test_cancel_all_does_not_hold_registry_lock_while_stopping_jobs():
    """停止処理中も、別ワーカーが登録を完了できる"""
    controller = CancelController()
    registered = threading.Event()
    job = Mock(spec=YtDlpJob)
    worker = threading.Thread(target=lambda: (controller.register(Mock()), registered.set()))

    def stop():
        worker.start()
        assert registered.wait(timeout=1)

    job.terminate.side_effect = stop
    controller.register(job)
    try:
        controller.cancel_all("user")
    finally:
        worker.join(timeout=2)


def test_completed_jobs_are_not_terminated_again():
    """完了したジョブを登録から外し、後続のキャンセル対象にしない"""
    controller = CancelController()
    job = Mock(spec=YtDlpJob, output_path=None, stderr_tail="")
    job.wait.return_value = 0

    assert _run_one(job, controller) == (0, None, "")
    controller.cancel_all("user")

    job.terminate.assert_not_called()
