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
        parts = [p for p in [res, fps, self.ext, self.vcodec, tbr, size] if p]
        return " / ".join(parts)


def fetch_info_json(url: str) -> dict:
    # -J はJSON、--no-playlistで単体、--no-warningsでノイズ低減
    cmd = ["yt-dlp", "-J", "--no-playlist", "--no-warnings", url]
    p = subprocess.run(cmd, capture_output=True, text=True)
    if p.returncode != 0:
        raise RuntimeError(p.stderr.strip() or "yt-dlp -J failed")
    return json.loads(p.stdout)


def list_video_formats(url: str) -> List[VideoFormat]:
    info = fetch_info_json(url)
    formats = info.get("formats", [])
    out: List[VideoFormat] = []

    for f in formats:
        vcodec = f.get("vcodec")
        acodec = f.get("acodec")
        # 映像のみ候補：vcodecあり、acodecなし
        if not vcodec or vcodec == "none":
            continue
        if acodec and acodec != "none":
            # 統合フォーマットはスキップし、映像のみを優先
            continue

        out.append(
            VideoFormat(
                format_id=str(f.get("format_id")),
                ext=str(f.get("ext") or ""),
                width=f.get("width"),
                height=f.get("height"),
                fps=f.get("fps"),
                vcodec=str(vcodec),
                tbr=f.get("tbr"),
                filesize=f.get("filesize") or f.get("filesize_approx"),
            )
        )

    # 高画質優先でソート：height -> fps -> tbr
    def key(x: VideoFormat):
        return (
            x.height or 0,
            x.fps or 0,
            x.tbr or 0,
        )

    out.sort(key=key, reverse=True)
    return out
