"""
ytdlpcli.ui
~~~~~~~~~~~

ユーザーインターフェース関連の機能を提供します。
"""

from __future__ import annotations

from typing import List, Tuple, Optional

from rich.console import Console
from rich.table import Table
from rich.prompt import Prompt, IntPrompt
from rich.panel import Panel

from .config import AppConfig
from .formats import list_video_formats

console = Console()


class Formatter:
    """UI表示用のフォーマッティングユーティリティ"""

    @staticmethod
    def bytes(byte_count: int) -> str:
        """バイト数を人間が読める単位に変換"""
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

    @staticmethod
    def speed(bytes_per_second: int) -> str:
        """速度の表示（未確定は--）"""
        if bytes_per_second <= 0:
            return "--"
        return f"{Formatter.bytes(bytes_per_second)}/s"

    @staticmethod
    def eta(seconds: int) -> str:
        """ETAの表示（未確定は--）"""
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

    @staticmethod
    def download(downloaded: int, total: int) -> str:
        """DL量を「downloaded / total」で表示"""
        if downloaded < 0 and total <= 0:
            return "-- / --"
        if total <= 0:
            return f"{Formatter.bytes(downloaded)} / --"
        if downloaded < 0:
            return f"-- / {Formatter.bytes(total)}"
        return f"{Formatter.bytes(downloaded)} / {Formatter.bytes(total)}"

    @staticmethod
    def percent(downloaded: int, total: int) -> str:
        """総容量が不明な場合は割合を表示しない"""
        if total > 0 and downloaded >= 0:
            return f"{(downloaded / total) * 100:>5.1f}%"
        return "--.-%"

    @staticmethod
    def short_url(url: str) -> str:
        """UIの見やすさ優先で短縮"""
        if "watch?v=" in url:
            vid = url.split("watch?v=", 1)[1].split("&", 1)[0]
            return f"youtube:{vid}"
        if len(url) > 40:
            return url[:37] + "..."
        return url


class FormatSelector:
    """フォーマット選択UI"""

    def __init__(self, console: Console):
        self.console = console

    def choose_mode(self, cfg: AppConfig) -> str:
        """ダウンロード方式を選択"""
        self.console.print("\nダウンロード方式:")
        self.console.print("1) 最高品質（自動）")
        self.console.print("2) mp4優先（互換性重視）")
        self.console.print("3) 今回だけフォーマットを選ぶ（番号選択）")
        default_map = {"auto": "1", "mp4": "2", "ask": "3"}
        default = default_map.get(cfg.format_mode, "1")
        choice = Prompt.ask("> ", choices=["1", "2", "3"], default=default)
        return {"1": "auto", "2": "mp4", "3": "ask"}[choice]

    def select_by_number(self, url: str, limit: int) -> str:
        """
        自動でフォーマットを取得→上位N件を表示→番号選択。
        返り値はyt-dlp -f に渡す format 文字列（video_id + bestaudio）。
        """
        formats = list_video_formats(url)
        if not formats:
            self.console.print("[yellow]フォーマット取得に失敗、最高品質（自動）にフォールバックします。[/yellow]")
            return "bestvideo+bestaudio/best"

        top_formats = formats[:limit]

        table = Table(title="映像フォーマット候補（上位）", show_lines=True)
        table.add_column("No", justify="right")
        table.add_column("format_id", justify="right")
        table.add_column("概要")

        for index, fmt in enumerate(top_formats, start=1):
            table.add_row(str(index), fmt.format_id, fmt.label)

        self.console.print(table)
        selected_index = IntPrompt.ask("選択番号", default=1)
        if selected_index < 1 or selected_index > len(top_formats):
            self.console.print("[yellow]範囲外のため 1 を採用します。[/yellow]")
            selected_index = 1

        chosen = top_formats[selected_index - 1]
        # 音声は bestaudio を付与（安定）
        return f"{chosen.format_id}+bestaudio/best"


def print_summary(
    results: List[Tuple[str, int, Optional[str], str]],
    continue_on_error: bool
) -> None:
    """結果サマリーを表示"""
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
        table.add_row(Formatter.short_url(url), str(rc), out_disp, memo + (f" {tail_disp}" if tail_disp else ""))

    console.print(table)
