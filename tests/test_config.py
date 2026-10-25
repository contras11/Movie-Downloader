"""config.py の復旧・検証テスト"""

import json
import os
from datetime import datetime
from pathlib import Path
from unittest.mock import patch

import pytest

from ytdlpcli.config import AppConfig, load_config_with_recovery, save_config
from ytdlpcli.exceptions import ConfigError


def test_malformed_json_is_backed_up_and_recreated(tmp_path):
    config_path = tmp_path / "config.json"
    config_path.write_text("{broken", encoding="utf-8")

    result = load_config_with_recovery(str(config_path))

    assert result.config == AppConfig()
    assert result.backup_path is not None
    assert config_path.exists()
    assert json.loads(config_path.read_text(encoding="utf-8"))["max_workers"] == 2
    assert Path(result.backup_path).read_text(encoding="utf-8") == "{broken"


def test_non_object_json_is_backed_up_and_recreated(tmp_path):
    config_path = tmp_path / "config.json"
    config_path.write_text("[]", encoding="utf-8")

    result = load_config_with_recovery(str(config_path))

    assert result.backup_path is not None
    assert result.config == AppConfig()


def test_backup_name_is_collision_safe(tmp_path):
    config_path = tmp_path / "config.json"
    fixed_time = datetime(2026, 8, 22, 12, 34, 56)

    with patch("ytdlpcli.config.datetime") as mock_datetime:
        mock_datetime.now.return_value = fixed_time
        config_path.write_text("{first", encoding="utf-8")
        first = load_config_with_recovery(str(config_path))
        config_path.write_text("{second", encoding="utf-8")
        second = load_config_with_recovery(str(config_path))

    assert first.backup_path.endswith(".invalid-20260822-123456")
    assert second.backup_path.endswith(".invalid-20260822-123456-1")


def test_invalid_values_are_corrected_while_valid_values_are_kept(tmp_path):
    config_path = tmp_path / "config.json"
    config_path.write_text(
        json.dumps({
            "download_dir": "/tmp/movies",
            "max_workers": 0,
            "retries": True,
            "format_mode": "audio",
            "audio_format": "invalid",
        }),
        encoding="utf-8",
    )

    result = load_config_with_recovery(str(config_path))

    assert result.backup_path is not None
    assert result.corrected_fields == ("audio_format", "max_workers", "retries")
    assert result.config.download_dir == "/tmp/movies"
    assert result.config.format_mode == "audio"
    assert result.config.max_workers == 2
    assert result.config.retries == 3
    assert result.config.audio_format == "mp3"


def test_all_config_value_types_and_ranges_are_validated(tmp_path):
    config_path = tmp_path / "config.json"
    invalid_values = {
        "download_dir": "   ",
        "format_mode": "invalid",
        "merge_output_format": "",
        "max_workers": True,
        "prevent_sleep": 1,
        "format_list_limit": 0,
        "retries": -1,
        "continue_on_error": "yes",
        "audio_format": "aac",
    }
    config_path.write_text(json.dumps(invalid_values), encoding="utf-8")

    result = load_config_with_recovery(str(config_path))

    assert result.corrected_fields == tuple(sorted(invalid_values))
    assert result.config == AppConfig()


def test_valid_config_is_not_rewritten_and_unknown_keys_are_ignored(tmp_path):
    config_path = tmp_path / "config.json"
    config_path.write_text(
        json.dumps({"max_workers": 4, "future_key": "preserve-source"}),
        encoding="utf-8",
    )

    with patch("ytdlpcli.config.save_config") as mock_save:
        result = load_config_with_recovery(str(config_path))

    assert result.config.max_workers == 4
    assert result.backup_path is None
    mock_save.assert_not_called()


def test_save_config_replaces_file_without_leaving_temporary_file(tmp_path):
    config_path = tmp_path / "config.json"

    with patch("ytdlpcli.config.os.replace", wraps=os.replace) as mock_replace:
        save_config(AppConfig(max_workers=5), str(config_path))

    assert json.loads(config_path.read_text(encoding="utf-8"))["max_workers"] == 5
    assert list(tmp_path.iterdir()) == [config_path]
    mock_replace.assert_called_once()


def test_read_error_does_not_replace_existing_config(tmp_path):
    config_path = tmp_path / "config.json"
    original = '{"max_workers": 5}'
    config_path.write_text(original, encoding="utf-8")

    with patch("builtins.open", side_effect=PermissionError("permission denied")):
        with pytest.raises(ConfigError, match="読み込"):
            load_config_with_recovery(str(config_path))

    assert config_path.read_text(encoding="utf-8") == original
    assert list(tmp_path.iterdir()) == [config_path]


def test_directory_at_config_path_is_preserved(tmp_path):
    config_path = tmp_path / "config.json"
    config_path.mkdir()
    marker = config_path / "keep.txt"
    marker.write_text("keep", encoding="utf-8")

    with pytest.raises(ConfigError, match="読み込"):
        load_config_with_recovery(str(config_path))

    assert marker.read_text(encoding="utf-8") == "keep"
    assert list(tmp_path.iterdir()) == [config_path]
