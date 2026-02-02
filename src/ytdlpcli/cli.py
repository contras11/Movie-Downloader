from __future__ import annotations

import argparse
import os
import signal
import threading
from concurrent.futures import ThreadPoolExecutor
from typing import List, Optional, Tuple

from rich.console import Console
from rich.table import Table
from rich.progress import Progress, BarColumn, TextColumn, TaskID
from rich.prompt import Prompt, IntPrompt
from rich.panel import Panel

from .config import load_config, save_config, DEFAULT_CONFIG_PATH, AppConfig
from .formats import list_video_formats
from .runner import YtDlpJob

console = Console()


def _format_bytes(byte_count: int) -> str:
    # バイト数を人間が読める単位に変換
    if byte_count < 0:
        return "--"
    units = ["B", "KiB", "MiB", "GiB", "TiB"]
    value = float(byte_count)
    for unit in units:
        if value < 1024 or unit == units[-1]:
            if unit == "B":
                return f"{int(value)}{unit}"
            return f"{value:.1f}{unit}"
        value /= 1024
    return f"{int(value)}B"


def _format_speed(bytes_per_second: int) -> str:
    # 速度の表示（未確定は--）
    if bytes_per_second <= 0:
        return "--"
    return f"{_format_bytes(bytes_per_second)}/s"


def _format_eta(seconds: int) -> str:
    # ETAの表示（未確定は--）
    if seconds < 0:
        return "--"
    total_seconds = int(seconds)
    minutes, sec = divmod(total_seconds, 60)
    hours, minutes = divmod(minutes, 60)
    if hours > 0:
        return f"{hours}h{minutes:02d}m"
    if minutes > 0:
        return f"{minutes}m{sec:02d}s"
    return f"{sec}s"


def _format_download(downloaded: int, total: int) -> str:
    # DL量を「downloaded / total」で表示
    if downloaded < 0 and total <= 0:
        return "-- / --"
    if total <= 0:
        return f"{_format_bytes(downloaded)} / --"
    if downloaded < 0:
        return f"-- / {_format_bytes(total)}"
    return f"{_format_bytes(downloaded)} / {_format_bytes(total)}"


def _format_percent(downloaded: int, total: int) -> str:
    # 総容量が不明な場合は割合を表示しない
    if total > 0 and downloaded >= 0:
        return f"{(downloaded / total) * 100:>5.1f}%"
    return "--.-%"


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


def _choose_mode(cfg: AppConfig) -> str:
    # 既定はcfg.format_mode。起動時に切り替え可能にする
    console.print("\nダウンロード方式:")
    console.print("1) 最高品質（自動）")
    console.print("2) mp4優先（互換性重視）")
    console.print("3) 今回だけフォーマットを選ぶ（番号選択）")
    default_map = {"auto": "1", "mp4": "2", "ask": "3"}
    default = default_map.get(cfg.format_mode, "1")
    choice = Prompt.ask("> ", choices=["1", "2", "3"], default=default)
    return {"1": "auto", "2": "mp4", "3": "ask"}[choice]


def _format_string_for_mode(mode: str) -> str:
    if mode == "auto":
        return "bestvideo+bestaudio/best"
    if mode == "mp4":
        return "bestvideo[ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]/best"
    raise ValueError(mode)


def _select_format_by_number(url: str, limit: int) -> str:
    """
    自動でフォーマットを取得→上位N件を表示→番号選択。
    返り値はyt-dlp -f に渡す format 文字列（video_id + bestaudio）。
    """
    formats = list_video_formats(url)
    if not formats:
        console.print("[yellow]フォーマット取得に失敗、最高品質（自動）にフォールバックします。[/yellow]")
        return "bestvideo+bestaudio/best"

    top_formats = formats[:limit]

    table = Table(title="映像フォーマット候補（上位）", show_lines=True)
    table.add_column("No", justify="right")
    table.add_column("format_id", justify="right")
    table.add_column("概要")

    for index, fmt in enumerate(top_formats, start=1):
        table.add_row(str(index), fmt.format_id, fmt.label)

    console.print(table)
    selected_index = IntPrompt.ask("選択番号", default=1)
    if selected_index < 1 or selected_index > len(top_formats):
        console.print("[yellow]範囲外のため 1 を採用します。[/yellow]")
        selected_index = 1

    chosen = top_formats[selected_index - 1]
    # 音声は bestaudio を付与（安定）
    return f"{chosen.format_id}+bestaudio/best"


def _make_jobs(urls: List[str], mode: str, cfg: AppConfig) -> List[Tuple[str, str]]:
    """
    各URLに対して format 文字列を決定して返す（URL, fmt）
    """
    jobs: List[Tuple[str, str]] = []
    if mode in ("auto", "mp4"):
        fmt = _format_string_for_mode(mode)
        for url in urls:
            jobs.append((url, fmt))
        return jobs

    # mode == ask: URLごとに番号選択
    for url in urls:
        console.print(Panel.fit(f"フォーマット選択: {url}", title="選択", border_style="cyan"))
        fmt = _select_format_by_number(url, cfg.format_list_limit)
        jobs.append((url, fmt))
    return jobs


class CancelController:
    def __init__(self):
        self.cancel_event = threading.Event()
        self.reason: Optional[str] = None
        self._jobs: List[YtDlpJob] = []
        self._lock = threading.Lock()

    def register(self, job: YtDlpJob) -> None:
        with self._lock:
            self._jobs.append(job)

    def cancel_all(self, reason: str = "user") -> None:
        if self.reason is None:
            self.reason = reason
        self.cancel_event.set()
        with self._lock:
            for job in self._jobs:
                job.terminate()


def _run_one(job: YtDlpJob, controller: CancelController) -> Tuple[int, Optional[str], str]:
    """
    1ジョブの実行（別スレッドで呼ばれる）
    """
    if controller.cancel_event.is_set():
        return (130, None, "Cancelled before start")

    controller.register(job)
    job.start()
    rc = job.wait()
    return (rc, job.output_path, job.stderr_tail)


def _install_signal_handlers(controller: CancelController) -> None:
    def handler(sig, frame):
        controller.cancel_all("user")

    signal.signal(signal.SIGINT, handler)
    signal.signal(signal.SIGTERM, handler)


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

    urls = _read_urls_from_args(args)
    if not urls:
        urls = _read_urls_interactive()
    if not urls:
        console.print("URLが入力されていません。終了します。")
        return 0

    mode = args.mode if args.mode is not None else _choose_mode(cfg)
    # “通常は自動、必要時だけ手動”の意思に沿い、今回だけ切替可能

    # ジョブ作成（URL, format）
    url_fmt_list = _make_jobs(urls, mode, cfg)

    # スリープ防止
    caffeinate_proc = None
    if cfg.prevent_sleep:
        caffeinate_proc = _prevent_sleep_start()
        if caffeinate_proc:
            console.print("スリープ防止: 有効")
        else:
            console.print("スリープ防止: 有効化に失敗（caffeinateが使えない可能性）")

    controller = CancelController()
    _install_signal_handlers(controller)

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

    # 各ジョブにtaskを割り当て、別スレッドの進捗をポーリングで反映
    tasks: List[Tuple[TaskID, YtDlpJob]] = []

    # 実行結果
    results: List[Tuple[str, int, Optional[str], str]] = []

    try:
        with progress:
            with ThreadPoolExecutor(max_workers=cfg.max_workers) as ex:
                futures = []

                # job構築とtask登録
                for (url, fmt) in url_fmt_list:
                    job = YtDlpJob(
                        url=url,
                        fmt=fmt,
                        download_dir=cfg.download_dir,
                        merge_output_format=cfg.merge_output_format,
                        retries=cfg.retries,
                    )
                    task_id = progress.add_task(
                        description=_short_url(url),
                        total=1.0,
                        pct="--.-%",
                        dl="-- / --",
                        speed="--",
                        eta="--",
                    )
                    tasks.append((task_id, job))

                    future = ex.submit(_run_one, job, controller)
                    futures.append((url, task_id, job, future))

                # 進捗ポーリングループ（完了まで回す）
                unfinished = set(future for (_, _, _, future) in futures)

                import time

                cancel_marked = False
                while unfinished:
                    if controller.cancel_event.is_set():
                        # 取消後、残タスクを「中断」表示に寄せる
                        if not cancel_marked:
                            for (url, task_id, job, future) in futures:
                                if not future.done():
                                    progress.update(task_id, description=_short_url(url) + " (cancelled)")
                            cancel_marked = True

                    # 全taskの進捗反映
                    for (task_id, job) in tasks:
                        snap = job.poll_progress()
                        total = snap.total
                        downloaded = snap.downloaded
                        if total > 0 and downloaded >= 0:
                            pct = min(downloaded / total, 1.0)
                        else:
                            pct = 0.0
                        progress.update(
                            task_id,
                            completed=pct,
                            total=1.0,
                            pct=_format_percent(downloaded, total),
                            dl=_format_download(downloaded, total),
                            speed=_format_speed(snap.speed),
                            eta=_format_eta(snap.eta),
                        )

                    # 完了future収集
                    for (url, task_id, job, future) in futures:
                        if future in unfinished and future.done():
                            try:
                                rc, out, tail = future.result()
                            except Exception as exc:
                                rc, out, tail = (1, None, str(exc))
                            results.append((url, rc, out, tail))
                            unfinished.remove(future)

                            if rc == 0:
                                progress.update(task_id, completed=1.0, description=_short_url(url) + " (done)")
                            elif rc == 130:
                                progress.update(task_id, description=_short_url(url) + " (cancelled)")
                            else:
                                progress.update(task_id, description=_short_url(url) + f" (error {rc})")
                                if not cfg.continue_on_error:
                                    controller.cancel_all("error")

                    time.sleep(0.2)
    finally:
        _prevent_sleep_stop(caffeinate_proc)

    # 結果表示
    _print_summary(results, cfg.continue_on_error)

    # 終了コード方針：全成功なら0、失敗ありなら1、ユーザーキャンセルは130
    if controller.cancel_event.is_set() and controller.reason == "user":
        return 130
    if any(rc != 0 for (_, rc, _, _) in results):
        return 1
    return 0


def _short_url(url: str) -> str:
    # UIの見やすさ優先で短縮
    if "watch?v=" in url:
        vid = url.split("watch?v=", 1)[1].split("&", 1)[0]
        return f"youtube:{vid}"
    if len(url) > 40:
        return url[:37] + "..."
    return url


def _print_summary(results: List[Tuple[str, int, Optional[str], str]], continue_on_error: bool) -> None:
    if not continue_on_error and any(rc not in (0, 130) for (_, rc, _, _) in results):
        console.print("[yellow]エラーが発生したため残りを中断しました。[/yellow]")

    table = Table(title="結果サマリ", show_lines=True)
    table.add_column("URL/ID")
    table.add_column("RC", justify="right")
    table.add_column("出力（推定）")
    table.add_column("メモ")

    for url, rc, out, tail in results:
        memo = "OK" if rc == 0 else ("CANCEL" if rc == 130 else "ERROR")
        out_disp = out or ""
        tail_disp = ""
        if rc not in (0, 130):
            # 失敗時のみ末尾ログを少し出す
            tail_disp = (tail[-120:] if tail else "")
        table.add_row(_short_url(url), str(rc), out_disp, memo + (f" {tail_disp}" if tail_disp else ""))

    console.print(table)


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
        if args.set_mode not in ("auto", "mp4", "ask"):
            console.print("modeは auto/mp4/ask のいずれかです。")
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
    run_parser.add_argument("--mode", type=str, choices=["auto", "mp4", "ask"], default=None, help="auto/mp4/ask")
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
    config_parser.add_argument("--set-mode", type=str, default=None, help="auto/mp4/ask")
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
    config_parser.set_defaults(func=_cmd_config)

    return parser


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()
    rc = args.func(args)
    raise SystemExit(rc)
