from __future__ import annotations

import json
import os
import tempfile
from dataclasses import dataclass, asdict, fields
from datetime import datetime
from typing import Any, Callable, Optional

from .exceptions import ConfigError

DEFAULT_CONFIG_PATH = os.path.expanduser("~/.ytdlpcli.json")


@dataclass
class AppConfig:
    # 保存先（設定で変更可能）
    download_dir: str = os.path.expanduser("~/Downloads")

    # 既定動作：最高品質（自動）
    # "auto" = 最高品質（bestvideo+bestaudio）
    # "mp4"  = mp4優先（bestvideo[ext=mp4]+bestaudio[ext=m4a]...）
    # "ask"  = 毎回フォーマット番号選択
    format_mode: str = "auto"

    # mp4コンテナに統合（高互換）
    merge_output_format: str = "mp4"

    # 並列数
    max_workers: int = 2

    # スリープ防止（macOS caffeinate）
    prevent_sleep: bool = True

    # フォーマット一覧表示の最大件数（上位だけ見せる）
    format_list_limit: int = 12

    # リトライ（yt-dlp側に渡す）
    retries: int = 3

    # 失敗時に次へ進むか
    continue_on_error: bool = True

    # 音声抽出時のフォーマット（mp3/m4a/opus/flac/wav）
    audio_format: str = "mp3"


@dataclass(frozen=True)
class ConfigLoadResult:
    """設定の読み込み結果と、自動復旧の内容を保持する。"""

    config: AppConfig
    backup_path: Optional[str] = None
    corrected_fields: tuple[str, ...] = ()
    recovery_reason: Optional[str] = None
    created: bool = False


FORMAT_MODES = frozenset({"auto", "mp4", "ask", "audio"})
AUDIO_FORMATS = frozenset({"mp3", "m4a", "opus", "flac", "wav"})


def _is_nonempty_string(value: Any) -> bool:
    return isinstance(value, str) and bool(value.strip())


def _is_int_at_least(minimum: int) -> Callable[[Any], bool]:
    return lambda value: isinstance(value, int) and not isinstance(value, bool) and value >= minimum


_VALIDATORS: dict[str, Callable[[Any], bool]] = {
    "download_dir": _is_nonempty_string,
    "format_mode": lambda value: isinstance(value, str) and value in FORMAT_MODES,
    "merge_output_format": _is_nonempty_string,
    "max_workers": _is_int_at_least(1),
    "prevent_sleep": lambda value: isinstance(value, bool),
    "format_list_limit": _is_int_at_least(1),
    "retries": _is_int_at_least(0),
    "continue_on_error": lambda value: isinstance(value, bool),
    "audio_format": lambda value: isinstance(value, str) and value in AUDIO_FORMATS,
}


def _normalize_config(data: dict[str, Any]) -> tuple[AppConfig, tuple[str, ...]]:
    cfg = AppConfig()
    corrected: list[str] = []
    known_fields = {field.name for field in fields(AppConfig)}
    for key in known_fields:
        if key not in data:
            continue
        value = data[key]
        if _VALIDATORS[key](value):
            setattr(cfg, key, value)
        else:
            corrected.append(key)

    cfg.download_dir = os.path.expanduser(cfg.download_dir)
    cfg.merge_output_format = cfg.merge_output_format.strip()
    return cfg, tuple(sorted(corrected))


def _backup_invalid_config(path: str) -> str:
    timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    candidate = f"{path}.invalid-{timestamp}"
    suffix = 1
    while os.path.exists(candidate):
        candidate = f"{path}.invalid-{timestamp}-{suffix}"
        suffix += 1
    try:
        os.replace(path, candidate)
    except OSError as exc:
        raise ConfigError(f"不正な設定ファイルを退避できませんでした: {exc}") from exc
    return candidate


def load_config_with_recovery(path: str = DEFAULT_CONFIG_PATH) -> ConfigLoadResult:
    """設定を読み込み、破損または不正値があれば退避して正規化する。"""
    if not os.path.exists(path):
        cfg = AppConfig()
        save_config(cfg, path)
        return ConfigLoadResult(config=cfg, created=True)

    try:
        with open(path, "r", encoding="utf-8") as file_handle:
            data = json.load(file_handle)
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        backup_path = _backup_invalid_config(path)
        cfg = AppConfig()
        save_config(cfg, path)
        return ConfigLoadResult(
            config=cfg,
            backup_path=backup_path,
            recovery_reason=str(exc),
        )

    if not isinstance(data, dict):
        backup_path = _backup_invalid_config(path)
        cfg = AppConfig()
        save_config(cfg, path)
        return ConfigLoadResult(
            config=cfg,
            backup_path=backup_path,
            recovery_reason="設定JSONのルートはオブジェクトである必要があります",
        )

    cfg, corrected_fields = _normalize_config(data)
    if corrected_fields:
        backup_path = _backup_invalid_config(path)
        save_config(cfg, path)
        return ConfigLoadResult(
            config=cfg,
            backup_path=backup_path,
            corrected_fields=corrected_fields,
            recovery_reason="不正な設定値を既定値へ補正しました",
        )
    return ConfigLoadResult(config=cfg)


def load_config(path: str = DEFAULT_CONFIG_PATH) -> AppConfig:
    """互換用API。復旧情報が不要な場合は設定だけを返す。"""
    return load_config_with_recovery(path).config


def save_config(cfg: AppConfig, path: str = DEFAULT_CONFIG_PATH) -> None:
    """一時ファイルへ書き込んでから置換し、途中終了による破損を防ぐ。"""
    parent = os.path.dirname(path) or "."
    try:
        os.makedirs(parent, exist_ok=True)
        fd, temporary_path = tempfile.mkstemp(prefix=f".{os.path.basename(path)}.", dir=parent, text=True)
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as file_handle:
                json.dump(asdict(cfg), file_handle, ensure_ascii=False, indent=2)
                file_handle.write("\n")
                file_handle.flush()
                os.fsync(file_handle.fileno())
            os.replace(temporary_path, path)
        except Exception:
            try:
                os.unlink(temporary_path)
            except FileNotFoundError:
                pass
            raise
    except OSError as exc:
        raise ConfigError(f"設定ファイルを保存できませんでした: {exc}") from exc
