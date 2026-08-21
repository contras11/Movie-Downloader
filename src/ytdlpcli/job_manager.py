"""
ytdlpcli.job_manager
~~~~~~~~~~~~~~~~~~~~

ジョブの作成、実行、進捗管理を行います。
"""

from __future__ import annotations

import signal
import threading
import time
from contextlib import contextmanager
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from typing import Iterator, List, Tuple, Optional

from rich.progress import Progress, TaskID
from rich.panel import Panel
from rich.markup import escape
from rich.text import Text

from .runner import YtDlpJob
from .config import AppConfig
from .exceptions import YtdlpNotFoundError
from .ui import Formatter, FormatSelector, console


@dataclass(frozen=True)
class DownloadSpec:
    """1件のダウンロードに必要な入力を明示的に保持する。"""

    url: str
    format_selector: str
    audio_only: bool


class CancelController:
    """キャンセル制御を管理するクラス"""

    def __init__(self):
        self.cancel_event = threading.Event()
        self.reason: Optional[str] = None
        self._jobs: List[YtDlpJob] = []
        self._lock = threading.Lock()

    def register(self, job: YtDlpJob) -> None:
        """ジョブを登録"""
        with self._lock:
            self._jobs.append(job)

    def cancel_all(self, reason: str = "user") -> None:
        """全てのジョブをキャンセル"""
        if self.reason is None:
            self.reason = reason
        self.cancel_event.set()
        with self._lock:
            for job in self._jobs:
                job.terminate()


@contextmanager
def managed_signal_handlers(controller: CancelController) -> Iterator[None]:
    """実行中だけシグナルハンドラーを差し替え、終了時に復元する。"""
    def handler(sig, frame):
        controller.cancel_all("user")

    previous_handlers = {
        sig: signal.getsignal(sig)
        for sig in (signal.SIGINT, signal.SIGTERM)
    }
    try:
        for sig in previous_handlers:
            signal.signal(sig, handler)
        yield
    finally:
        for sig, previous in previous_handlers.items():
            signal.signal(sig, previous)


def _run_one(job: YtDlpJob, controller: CancelController) -> Tuple[int, Optional[str], str]:
    """
    1ジョブの実行（別スレッドで呼ばれる）
    """
    controller.register(job)
    if controller.cancel_event.is_set():
        return (130, None, "Cancelled before start")

    job.start()
    if controller.cancel_event.is_set():
        # process生成とキャンセルが競合しても、起動後にもう一度停止を保証する。
        job.terminate()
    rc = job.wait()
    return (rc, job.output_path, job.stderr_tail)


def _format_string_for_mode(mode: str) -> str:
    """モードに対応するyt-dlpフォーマット文字列を返す"""
    if mode == "auto":
        return "bestvideo+bestaudio/best"
    if mode == "mp4":
        return "bestvideo[ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]/best"
    if mode == "audio":
        return "bestaudio/best"
    raise ValueError(mode)


class JobManager:
    """ジョブの作成、実行、進捗管理を行うクラス"""

    def __init__(self, cfg: AppConfig, controller: CancelController):
        self.cfg = cfg
        self.controller = controller

    def create_jobs(self, urls: List[str], mode: str) -> List[DownloadSpec]:
        """
        各URLに対してフォーマットと音声モードを決定して返す。
        """
        jobs: List[DownloadSpec] = []
        if mode in ("auto", "mp4", "audio"):
            fmt = _format_string_for_mode(mode)
            for url in urls:
                jobs.append(DownloadSpec(url=url, format_selector=fmt, audio_only=mode == "audio"))
            return jobs

        # mode == ask: URLごとに番号選択
        selector = FormatSelector(console)
        for url in urls:
            console.print(Panel.fit(Text(f"フォーマット選択: {url}"), title="選択", border_style="cyan"))
            fmt = selector.select_by_number(url, self.cfg.format_list_limit)
            jobs.append(DownloadSpec(url=url, format_selector=fmt, audio_only=False))
        return jobs

    def execute_parallel(
        self,
        jobs: List[DownloadSpec],
        progress: Progress
    ) -> List[Tuple[str, int, Optional[str], str]]:
        """並列実行とリアルタイム進捗表示"""
        results: List[Tuple[str, int, Optional[str], str]] = []
        tasks: List[Tuple[TaskID, YtDlpJob]] = []
        futures = []

        with ThreadPoolExecutor(max_workers=self.cfg.max_workers) as ex:
            # job構築とtask登録
            for spec in jobs:
                url = spec.url
                job = YtDlpJob(
                    url=url,
                    fmt=spec.format_selector,
                    download_dir=self.cfg.download_dir,
                    merge_output_format=self.cfg.merge_output_format,
                    retries=self.cfg.retries,
                    audio_only=spec.audio_only,
                    audio_format=self.cfg.audio_format,
                )
                task_id = progress.add_task(
                    description=escape(Formatter.short_url(url)),
                    total=1.0,
                    pct="--.-%",
                    dl="-- / --",
                    speed="--",
                    eta="--",
                )
                tasks.append((task_id, job))

                future = ex.submit(_run_one, job, self.controller)
                futures.append((url, task_id, job, future))

            # 進捗ポーリングループ（完了まで回す）
            unfinished = set(future for (_, _, _, future) in futures)

            cancel_marked = False
            while unfinished:
                if self.controller.cancel_event.is_set():
                    # 取消後、残タスクを「中断」表示に寄せる
                    if not cancel_marked:
                        for (url, task_id, job, future) in futures:
                            if not future.done():
                                progress.update(task_id, description=escape(Formatter.short_url(url)) + " (cancelled)")
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
                        pct=Formatter.percent(downloaded, total),
                        dl=Formatter.download(downloaded, total),
                        speed=Formatter.speed(snap.speed),
                        eta=Formatter.eta(snap.eta),
                    )

                # 完了future収集
                for (url, task_id, job, future) in futures:
                    if future in unfinished and future.done():
                        try:
                            rc, out, tail = future.result()
                        except YtdlpNotFoundError as exc:
                            console.print(Text(str(exc), style="red"))
                            self.controller.cancel_all("dependency_error")
                            rc, out, tail = (2, None, str(exc))
                        except Exception as exc:
                            rc, out, tail = (1, None, str(exc))
                        results.append((url, rc, out, tail))
                        unfinished.remove(future)

                        if rc == 0:
                            progress.update(task_id, completed=1.0, description=escape(Formatter.short_url(url)) + " (done)")
                        elif rc == 130:
                            progress.update(task_id, description=escape(Formatter.short_url(url)) + " (cancelled)")
                        else:
                            progress.update(task_id, description=escape(Formatter.short_url(url)) + f" (error {rc})")
                            if not self.cfg.continue_on_error:
                                self.controller.cancel_all("error")

                time.sleep(0.2)

        return results
