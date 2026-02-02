from __future__ import annotations

import json
import subprocess
from dataclasses import dataclass
from typing import List, Optional


@dataclass(frozen=True)
class VideoFormat:
    format_id: str
    ext: str
    width: Optional[int]
    height: Optional[int]
    fps: Optional[float]
    vcodec: str
    tbr: Optional[float]  # total bitrate (kbps)
    filesize: Optional[int]  # bytes (may be None)

    @property
    def label(self) -> str:
        # UI向けに簡潔なラベルを作る
        res = (
            f"{self.width}x{self.height}"
            if self.width and self.height
            else (f"{self.height}p" if self.height else "unknown")
        )
        fps = f"{int(self.fps)}fps" if self.fps else ""
        tbr = f"{int(self.tbr)}kbps" if self.tbr else ""
        size = f"{self.filesize/1024/1024:.0f}MiB" if self.filesize else ""
        parts = [part for part in [res, fps, self.ext, self.vcodec, tbr, size] if part]
        return " / ".join(parts)


def fetch_info_json(url: str) -> dict:
    # -J はJSON、--no-playlistで単体、--no-warningsでノイズ低減
    cmd = ["yt-dlp", "-J", "--no-playlist", "--no-warnings", url]
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        raise RuntimeError(result.stderr.strip() or "yt-dlp -J failed")
    return json.loads(result.stdout)


def list_video_formats(url: str) -> List[VideoFormat]:
    info = fetch_info_json(url)
    formats = info.get("formats", [])
    out: List[VideoFormat] = []

    for fmt in formats:
        vcodec = fmt.get("vcodec")
        acodec = fmt.get("acodec")
        # 映像のみ候補：vcodecあり、acodecなし
        if not vcodec or vcodec == "none":
            continue
        if acodec and acodec != "none":
            # 統合フォーマットはスキップし、映像のみを優先
            continue

        out.append(
            VideoFormat(
                format_id=str(fmt.get("format_id")),
                ext=str(fmt.get("ext") or ""),
                width=fmt.get("width"),
                height=fmt.get("height"),
                fps=fmt.get("fps"),
                vcodec=str(vcodec),
                tbr=fmt.get("tbr"),
                filesize=fmt.get("filesize") or fmt.get("filesize_approx"),
            )
        )

    # 高画質優先でソート：height -> fps -> tbr
    def key(fmt: VideoFormat):
        return (
            fmt.height or 0,
            fmt.fps or 0,
            fmt.tbr or 0,
        )

    out.sort(key=key, reverse=True)
    return out
