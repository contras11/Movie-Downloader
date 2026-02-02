"""
job_manager.py のテスト
"""

import pytest
from ytdlpcli.job_manager import CancelController, _format_string_for_mode
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
