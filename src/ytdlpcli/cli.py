from __future__ import annotations

import argparse
import os
import signal
import threading
from concurrent.futures import ThreadPoolExecutor
from typing import List, Optional, Tuple

from rich.console import Console
from rich.table import Table
from rich.progress import (
    Progress,
    BarColumn,
    TextColumn,
    TimeRemainingColumn,
    DownloadColumn,
    TransferSpeedColumn,
    TaskID,
)
from rich.prompt import Prompt, IntPrompt
from rich.panel import Panel

from .config import load_config, save_config, DEFAULT_CONFIG_PATH, AppConfig
from .formats import list_video_formats
from .runner import YtDlpJob

console = Console()


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
        s = input("> ").strip()
        if not s:
            break
        urls.append(s)
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
    fmts = list_video_formats(url)
    if not fmts:
        console.print("[yellow]フォーマット取得に失敗、最高品質（自動）にフォールバックします。[/yellow]")
        return "bestvideo+bestaudio/best"

    top = fmts[:limit]

    table = Table(title="映像フォーマット候補（上位）", show_lines=True)
    table.add_column("No", justify="right")
    table.add_column("format_id", justify="right")
    table.add_column("概要")

    for i, f in enumerate(top, start=1):
        table.add_row(str(i), f.format_id, f.label)

    console.print(table)
    n = IntPrompt.ask("選択番号", default=1)
    if n < 1 or n > len(top):
        console.print("[yellow]範囲外のため 1 を採用します。[/yellow]")
        n = 1

    chosen = top[n - 1]
    # 音声は bestaudio を付与（安定）
    return f"{chosen.format_id}+bestaudio/best"


def _make_jobs(urls: List[str], mode: str, cfg: AppConfig) -> List[Tuple[str, str]]:
    """
    各URLに対して format 文字列を決定して返す（URL, fmt）
    """
    jobs: List[Tuple[str, str]] = []
    if mode in ("auto", "mp4"):
        fmt = _format_string_for_mode(mode)
        for u in urls:
            jobs.append((u, fmt))
        return jobs

    # mode == ask: URLごとに番号選択
    for u in urls:
        console.print(Panel.fit(f"フォーマット選択: {u}", title="選択", border_style="cyan"))
        fmt = _select_format_by_number(u, cfg.format_list_limit)
        jobs.append((u, fmt))
    return jobs


class CancelController:
    def __init__(self):
        self.cancel_event = threading.Event()
        self._jobs: List[YtDlpJob] = []
        self._lock = threading.Lock()

    def register(self, job: YtDlpJob) -> None:
        with self._lock:
            self._jobs.append(job)

    def cancel_all(self) -> None:
        self.cancel_event.set()
        with self._lock:
            for j in self._jobs:
                j.terminate()


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
        controller.cancel_all()

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

    urls = _read_urls_interactive()
    if not urls:
        console.print("URLが入力されていません。終了します。")
        return 0

    mode = _choose_mode(cfg)
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
        TextColumn("{task.percentage:>5.1f}%"),
        DownloadColumn(binary_units=True),
        TransferSpeedColumn(),
        TimeRemainingColumn(),
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
                    task_id = progress.add_task(description=_short_url(url), total=1.0)
                    tasks.append((task_id, job))

                    fut = ex.submit(_run_one, job, controller)
                    futures.append((url, task_id, job, fut))

                # 進捗ポーリングループ（完了まで回す）
                unfinished = set(fut for (_, _, _, fut) in futures)

                import time

                while unfinished:
                    if controller.cancel_event.is_set():
                        # 取消後、残タスクを「中断」表示に寄せる
                        for (url, task_id, job, fut) in futures:
                            if not fut.done():
                                progress.update(task_id, description=_short_url(url) + " (cancelled)")
                        break

                    # 全taskの進捗反映
                    for (task_id, job) in tasks:
                        snap = job.poll_progress()
                        total = snap.total if snap.total > 0 else 0
                        downloaded = snap.downloaded if snap.downloaded >= 0 else 0

                        if total > 0:
                            pct = min(downloaded / total, 1.0)
                            progress.update(task_id, completed=pct, total=1.0)
                        else:
                            # totalが推定不可の間は0で維持
                            progress.update(task_id, completed=0.0, total=1.0)

                    # 完了future収集
                    for (url, task_id, job, fut) in futures:
                        if fut in unfinished and fut.done():
                            try:
                                rc, out, tail = fut.result()
                            except Exception as e:
                                rc, out, tail = (1, None, str(e))
                            results.append((url, rc, out, tail))
                            unfinished.remove(fut)

                            if rc == 0:
                                progress.update(task_id, completed=1.0, description=_short_url(url) + " (done)")
                            elif rc == 130:
                                progress.update(task_id, description=_short_url(url) + " (cancelled)")
                            else:
                                progress.update(task_id, description=_short_url(url) + f" (error {rc})")

                    time.sleep(0.2)
    finally:
        _prevent_sleep_stop(caffeinate_proc)

    # 結果表示
    _print_summary(results, cfg.continue_on_error)

    # 終了コード方針：全成功なら0、失敗ありなら1、キャンセルは130
    if any(rc == 130 for (_, rc, _, _) in results) or controller.cancel_event.is_set():
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

    if changed:
        save_config(cfg, DEFAULT_CONFIG_PATH)
        console.print(f"設定を更新しました: {DEFAULT_CONFIG_PATH}")
    else:
        console.print(f"設定ファイル: {DEFAULT_CONFIG_PATH}")
        console.print(cfg)

    return 0


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="ytdlpcli", description="Interactive yt-dlp CLI (macOS) with Rich progress.")
    sub = p.add_subparsers(dest="cmd", required=True)

    s_init = sub.add_parser("init-config", help="~/.ytdlpcli.json を作成（存在していても正規化して保存）")
    s_init.set_defaults(func=_cmd_init_config)

    s_run = sub.add_parser("run", help="対話形式でURL入力→並列ダウンロード")
    s_run.add_argument("--workers", type=int, default=None, help="並列数（設定を上書き）")
    s_run.add_argument("--download-dir", type=str, default=None, help="保存先（設定を上書き）")
    s_run.add_argument(
        "--prevent-sleep",
        action=argparse.BooleanOptionalAction,
        default=None,
        help="スリープ防止（設定を上書き）",
    )
    s_run.set_defaults(func=_cmd_run)

    s_cfg = sub.add_parser("config", help="設定の表示/変更")
    s_cfg.add_argument("--set-download-dir", type=str, default=None)
    s_cfg.add_argument("--set-workers", type=int, default=None)
    s_cfg.add_argument("--set-mode", type=str, default=None, help="auto/mp4/ask")
    s_cfg.add_argument(
        "--set-prevent-sleep",
        action=argparse.BooleanOptionalAction,
        default=None,
    )
    s_cfg.set_defaults(func=_cmd_config)

    return p


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()
    rc = args.func(args)
    raise SystemExit(rc)
