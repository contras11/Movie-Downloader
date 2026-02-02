from __future__ import annotations

import json
import os
from dataclasses import dataclass, asdict
from typing import Any

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


def _coerce_config(data: dict[str, Any]) -> AppConfig:
    cfg = AppConfig()
    for key, value in data.items():
        if hasattr(cfg, key):
            setattr(cfg, key, value)
    # 値の正規化
    cfg.download_dir = os.path.expanduser(cfg.download_dir)
    return cfg


def load_config(path: str = DEFAULT_CONFIG_PATH) -> AppConfig:
    if not os.path.exists(path):
        cfg = AppConfig()
        save_config(cfg, path)
        return cfg
    with open(path, "r", encoding="utf-8") as file_handle:
        data = json.load(file_handle)
    return _coerce_config(data)


def save_config(cfg: AppConfig, path: str = DEFAULT_CONFIG_PATH) -> None:
    # 親ディレクトリがあれば作る
    os.makedirs(os.path.dirname(path), exist_ok=True) if os.path.dirname(path) else None
    with open(path, "w", encoding="utf-8") as file_handle:
        json.dump(asdict(cfg), file_handle, ensure_ascii=False, indent=2)
