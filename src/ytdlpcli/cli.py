from __future__ import annotations

import argparse
import os
from typing import List, Optional

from rich.progress import Progress, BarColumn, TextColumn

from .config import load_config, save_config, DEFAULT_CONFIG_PATH, AppConfig
from .exceptions import YtdlpNotFoundError
from .ui import FormatSelector, print_summary, console
from .job_manager import JobManager, CancelController, install_signal_handlers


def _prevent_sleep_start() -> Optional["subprocess.Popen"]:
    # caffeinateを使ってスリープ防止（macOS）
    import subprocess

    try:
        return subprocess.Popen(["caffeinate", "-dimsu"])
    except Exception:
        return None


def _prevent_sleep_stop(proc) -> None:
    try:
        if proc and proc.poll() is None:
            proc.terminate()
    except Exception:
        pass


def _read_urls_interactive() -> List[str]:
    console.print("URLを入力してください（空行で開始）:")
    urls: List[str] = []
    while True:
        line = input("> ").strip()
        if not line:
            break
        urls.append(line)
    return urls


def _read_urls_from_args(args) -> List[str]:
    # 直接指定 or ファイル指定をまとめて取得
    urls: List[str] = []
    if args.url:
        urls.extend(args.url)
    if args.url_file:
        try:
            with open(args.url_file, "r", encoding="utf-8") as file_handle:
                for line in file_handle:
                    line = line.strip()
                    if not line or line.startswith("#"):
                        continue
                    urls.append(line)
        except Exception as exc:
            console.print(f"[red]URLファイルの読み込みに失敗しました: {exc}[/red]")
    return urls




def _cmd_init_config(args) -> int:
    cfg = load_config(DEFAULT_CONFIG_PATH)
    save_config(cfg, DEFAULT_CONFIG_PATH)
    console.print(f"設定ファイルを作成/更新しました: {DEFAULT_CONFIG_PATH}")
    return 0


def _cmd_run(args) -> int:
    cfg = load_config(DEFAULT_CONFIG_PATH)

    # 引数で上書き
    if args.workers is not None:
        cfg.max_workers = args.workers
    if args.prevent_sleep is not None:
        cfg.prevent_sleep = args.prevent_sleep
    if args.download_dir is not None:
        cfg.download_dir = os.path.expanduser(args.download_dir)
    if args.retries is not None:
        cfg.retries = args.retries
    if args.format_list_limit is not None:
        cfg.format_list_limit = args.format_list_limit
    if args.continue_on_error is not None:
        cfg.continue_on_error = args.continue_on_error
    if args.merge_output_format is not None:
        cfg.merge_output_format = args.merge_output_format
    if args.audio_format is not None:
        cfg.audio_format = args.audio_format

    urls = _read_urls_from_args(args)
    if not urls:
        urls = _read_urls_interactive()
    if not urls:
        console.print("URLが入力されていません。終了します。")
        return 0

    selector = FormatSelector(console)
    mode = args.mode if args.mode is not None else selector.choose_mode(cfg)

    # スリープ防止
    caffeinate_proc = None
    if cfg.prevent_sleep:
        caffeinate_proc = _prevent_sleep_start()
        if caffeinate_proc:
            console.print("スリープ防止: 有効")
        else:
            console.print("スリープ防止: 有効化に失敗（caffeinateが使えない可能性）")

    controller = CancelController()
    install_signal_handlers(controller)
    manager = JobManager(cfg, controller)

    # Rich Progress（複数タスク表示）
    progress = Progress(
        TextColumn("[bold]DL[/bold]"),
        BarColumn(),
        TextColumn("{task.fields[pct]}"),
        TextColumn("{task.fields[dl]}"),
        TextColumn("{task.fields[speed]}"),
        TextColumn("{task.fields[eta]}"),
        TextColumn("•"),
        TextColumn("{task.description}"),
        console=console,
        transient=False,
        refresh_per_second=8,
    )

    try:
        with progress:
            jobs = manager.create_jobs(urls, mode)
            results = manager.execute_parallel(jobs, progress)
    finally:
        _prevent_sleep_stop(caffeinate_proc)

    # 結果表示
    print_summary(results, cfg.continue_on_error)

    # 終了コード方針：全成功なら0、失敗ありなら1、ユーザーキャンセルは130
    if controller.cancel_event.is_set() and controller.reason == "user":
        return 130
    if any(rc != 0 for (_, rc, _, _) in results):
        return 1
    return 0


def _cmd_config(args) -> int:
    cfg = load_config(DEFAULT_CONFIG_PATH)

    changed = False
    if args.set_download_dir is not None:
        cfg.download_dir = os.path.expanduser(args.set_download_dir)
        changed = True
    if args.set_workers is not None:
        cfg.max_workers = args.set_workers
        changed = True
    if args.set_mode is not None:
        if args.set_mode not in ("auto", "mp4", "ask", "audio"):
            console.print("modeは auto/mp4/ask/audio のいずれかです。")
            return 2
        cfg.format_mode = args.set_mode
        changed = True
    if args.set_prevent_sleep is not None:
        cfg.prevent_sleep = args.set_prevent_sleep
        changed = True
    if args.set_format_list_limit is not None:
        cfg.format_list_limit = args.set_format_list_limit
        changed = True
    if args.set_retries is not None:
        cfg.retries = args.set_retries
        changed = True
    if args.set_continue_on_error is not None:
        cfg.continue_on_error = args.set_continue_on_error
        changed = True
    if args.set_merge_output_format is not None:
        cfg.merge_output_format = args.set_merge_output_format
        changed = True
    if args.set_audio_format is not None:
        if args.set_audio_format not in ("mp3", "m4a", "opus", "flac", "wav"):
            console.print("audio_formatは mp3/m4a/opus/flac/wav のいずれかです。")
            return 2
        cfg.audio_format = args.set_audio_format
        changed = True

    if changed:
        save_config(cfg, DEFAULT_CONFIG_PATH)
        console.print(f"設定を更新しました: {DEFAULT_CONFIG_PATH}")
    else:
        console.print(f"設定ファイル: {DEFAULT_CONFIG_PATH}")
        console.print(cfg)

    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="ytdlpcli", description="Interactive yt-dlp CLI (macOS) with Rich progress.")
    subparsers = parser.add_subparsers(dest="cmd", required=True)

    init_parser = subparsers.add_parser("init-config", help="~/.ytdlpcli.json を作成（存在していても正規化して保存）")
    init_parser.set_defaults(func=_cmd_init_config)

    run_parser = subparsers.add_parser("run", help="対話形式でURL入力→並列ダウンロード")
    run_parser.add_argument("--workers", type=int, default=None, help="並列数（設定を上書き）")
    run_parser.add_argument("--download-dir", type=str, default=None, help="保存先（設定を上書き）")
    run_parser.add_argument(
        "--prevent-sleep",
        action=argparse.BooleanOptionalAction,
        default=None,
        help="スリープ防止（設定を上書き）",
    )
    run_parser.add_argument("--mode", type=str, choices=["auto", "mp4", "ask", "audio"], default=None, help="auto/mp4/ask/audio")
    run_parser.add_argument("--audio-format", type=str, choices=["mp3", "m4a", "opus", "flac", "wav"], default=None, help="音声フォーマット（audioモード時）")
    run_parser.add_argument("--format-list-limit", type=int, default=None, help="フォーマット一覧の最大件数")
    run_parser.add_argument("--retries", type=int, default=None, help="yt-dlpのリトライ回数")
    run_parser.add_argument(
        "--continue-on-error",
        action=argparse.BooleanOptionalAction,
        default=None,
        help="エラー時に続行するか",
    )
    run_parser.add_argument("--merge-output-format", type=str, default=None, help="結合後のコンテナ形式")
    run_parser.add_argument("--url", type=str, action="append", default=None, help="URLを直接指定（複数可）")
    run_parser.add_argument("--url-file", type=str, default=None, help="URL一覧ファイル（1行1URL）")
    run_parser.set_defaults(func=_cmd_run)

    config_parser = subparsers.add_parser("config", help="設定の表示/変更")
    config_parser.add_argument("--set-download-dir", type=str, default=None, help="保存先")
    config_parser.add_argument("--set-workers", type=int, default=None, help="並列数")
    config_parser.add_argument("--set-mode", type=str, default=None, help="auto/mp4/ask/audio")
    config_parser.add_argument(
        "--set-prevent-sleep",
        dest="set_prevent_sleep",
        action="store_true",
        default=None,
        help="スリープ防止を有効にする",
    )
    config_parser.add_argument(
        "--set-no-prevent-sleep",
        dest="set_prevent_sleep",
        action="store_false",
        help="スリープ防止を無効にする",
    )
    config_parser.add_argument("--set-format-list-limit", type=int, default=None, help="フォーマット一覧の最大件数")
    config_parser.add_argument("--set-retries", type=int, default=None, help="リトライ回数")
    config_parser.add_argument(
        "--set-continue-on-error",
        dest="set_continue_on_error",
        action="store_true",
        default=None,
        help="失敗時に続行する",
    )
    config_parser.add_argument(
        "--set-no-continue-on-error",
        dest="set_continue_on_error",
        action="store_false",
        help="失敗時に中断する",
    )
    config_parser.add_argument("--set-merge-output-format", type=str, default=None, help="結合後のコンテナ形式")
    config_parser.add_argument("--set-audio-format", type=str, default=None, help="音声フォーマット (mp3/m4a/opus/flac/wav)")
    config_parser.set_defaults(func=_cmd_config)

    return parser


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()
    rc = args.func(args)
    raise SystemExit(rc)
