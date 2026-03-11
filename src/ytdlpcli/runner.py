"""
ytdlpcli.runner
~~~~~~~~~~~~~~~

yt-dlpをsubprocessで起動し、進捗を取得します。
"""

from __future__ import annotations

import os
import re
import subprocess
import threading
from dataclasses import dataclass
from typing import Optional

from .exceptions import YtdlpNotFoundError

_PROGRESS_RE = re.compile(
    r"^\[ytdlpcli\]\s+downloaded=(?P<downloaded>\S+)\s+total=(?P<total>\S+)\s+eta=(?P<eta>\S+)\s+speed=(?P<speed>\S+)\s*$"
)


def _parse_progress_value(value: str) -> int:
    # yt-dlpの進捗はNAが混じるため、安全に数値化
    try:
        return int(float(value))
    except Exception:
        return -1


@dataclass
class ProgressSnapshot:
    downloaded: int = 0
    total: int = 0
    eta: int = -1
    speed: int = -1


class YtDlpJob:
    """
    yt-dlpをsubprocessで起動し、--progress-templateの行をパースして進捗を取得する。
    複数並列でも安全に扱えるよう、終了/停止制御を明示的に持つ。
    """

    def __init__(self, url: str, fmt: str, download_dir: str, merge_output_format: str, retries: int,
                 audio_only: bool = False, audio_format: str = "mp3"):
        self.url = url
        self.fmt = fmt
        self.download_dir = download_dir
        self.merge_output_format = merge_output_format
        self.retries = retries
        self.audio_only = audio_only
        self.audio_format = audio_format

        self._proc: Optional[subprocess.Popen] = None
        self._lock = threading.Lock()
        self._progress = ProgressSnapshot()

        self.output_path: Optional[str] = None  # 成功時に推定される最終出力（完全保証はしない）
        self.returncode: Optional[int] = None
        self.stderr_tail: str = ""

    def start(self) -> None:
        os.makedirs(self.download_dir, exist_ok=True)

        # 進捗を機械可読な形式で出す（行単位）
        # total_bytes（実際の値）を優先、なければtotal_bytes_estimate（推定値）を使用
        progress_template = (
            "[ytdlpcli] downloaded=%(progress.downloaded_bytes)s "
            "total=%(progress.total_bytes,progress.total_bytes_estimate)s "
            "eta=%(progress.eta)s "
            "speed=%(progress.speed)s"
        )

        # 出力名（タイトルを使う）
        outtmpl = os.path.join(self.download_dir, "%(title)s [%(id)s].%(ext)s")

        cmd = [
            "yt-dlp",
            "--newline",
            "--no-warnings",
            "--retries",
            str(self.retries),
            "-f",
            self.fmt,
        ]
        if self.audio_only:
            cmd += ["-x", "--audio-format", self.audio_format, "--audio-quality", "0"]
        else:
            cmd += ["--merge-output-format", self.merge_output_format]
        cmd += [
            "-o",
            outtmpl,
            "--progress-template",
            f"download:{progress_template}",
            self.url,
        ]

        try:
            self._proc = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                bufsize=1,
            )
        except FileNotFoundError as e:
            raise YtdlpNotFoundError() from e

    def poll_progress(self) -> ProgressSnapshot:
        with self._lock:
            return ProgressSnapshot(
                downloaded=self._progress.downloaded,
                total=self._progress.total,
                eta=self._progress.eta,
                speed=self._progress.speed,
            )

    def terminate(self) -> None:
        with self._lock:
            if self._proc and self._proc.poll() is None:
                self._proc.terminate()

    def wait(self) -> int:
        if not self._proc or not self._proc.stdout:
            raise RuntimeError("Process not started")

        # stdoutを読みながら進捗更新（stderrはSTDOUTにリダイレクト済み）
        tail_lines = []
        for line in self._proc.stdout:
            line = line.strip()
            if not line:
                continue

            # 進捗行
            match = _PROGRESS_RE.match(line)
            if match:
                with self._lock:
                    self._progress.downloaded = _parse_progress_value(match.group("downloaded"))
                    self._progress.total = _parse_progress_value(match.group("total"))
                    self._progress.eta = _parse_progress_value(match.group("eta"))
                    self._progress.speed = _parse_progress_value(match.group("speed"))
                continue

            # 結合後の最終ファイル名推定（ログから取れる場合がある）
            # 例: [Merger] Merging formats into "....mp4"
            if 'Merging formats into "' in line:
                try:
                    merged_part = line.split('Merging formats into "', 1)[1]
                    output_path = merged_part.rsplit('"', 1)[0]
                    self.output_path = output_path
                except Exception:
                    pass

            # 音声抽出時の出力ファイル検出
            if "[ExtractAudio] Destination:" in line:
                try:
                    self.output_path = line.split("[ExtractAudio] Destination:", 1)[1].strip()
                except Exception:
                    pass

            # エラー解析用に末尾を保持
            tail_lines.append(line)
            if len(tail_lines) > 30:
                tail_lines.pop(0)

        rc = self._proc.wait()
        self.returncode = rc
        self.stderr_tail = "\n".join(tail_lines)
        return rc
