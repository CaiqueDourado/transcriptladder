"""YouTube ids, yt-dlp calls and video metadata."""

from __future__ import annotations

import json
import shutil
import subprocess
import threading
from dataclasses import dataclass, field
from urllib.parse import parse_qs, urlparse

_ID_CHARS = set("ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789-_")


def video_id(url_or_id: str) -> str | None:
    """Video id from any YouTube URL form (watch, youtu.be, shorts, live, embed, m.) or a bare id."""
    if not url_or_id:
        return None
    s = url_or_id.strip()
    if len(s) == 11 and set(s) <= _ID_CHARS:
        return s
    p = urlparse(s if "://" in s else "https://" + s)
    host = (p.hostname or "").lower().removeprefix("www.").removeprefix("m.").removeprefix("music.")
    if host == "youtu.be":
        vid = p.path.strip("/").split("/")[0]
    elif host.endswith("youtube.com") or host.endswith("youtube-nocookie.com"):
        parts = p.path.strip("/").split("/")
        if parts and parts[0] in ("shorts", "live", "embed", "v") and len(parts) > 1:
            vid = parts[1]
        else:
            vid = parse_qs(p.query).get("v", [""])[0]
    else:
        return None
    return vid if len(vid) == 11 and set(vid) <= _ID_CHARS else None


def watch_url(vid: str) -> str:
    return f"https://www.youtube.com/watch?v={vid}"


class RateLimited(RuntimeError):
    """YouTube answered HTTP 429."""


@dataclass
class YtDlp:
    """Runs the ``yt-dlp`` command line.

    - Adds ``--js-runtimes node|deno`` when one is installed (YouTube needs a JS runtime to
      read some formats).
    - ``impersonate`` (e.g. ``"chrome"``) uses yt-dlp's own browser impersonation.
    - ``extra_args`` go to every call as given.
    - One call at a time per process (``YtDlp.lock``): parallel yt-dlp calls are the fastest
      way to a 429.
    """

    binary: str = "yt-dlp"
    impersonate: str | None = None
    extra_args: list[str] = field(default_factory=list)
    timeout: float = 180.0
    lock = threading.Lock()

    def available(self) -> bool:
        return shutil.which(self.binary) is not None

    def _base(self) -> list[str]:
        args = [self.binary, "--no-playlist", "--no-warnings"]
        for rt in ("deno", "node"):
            if shutil.which(rt):
                args += ["--js-runtimes", rt]
                break
        if self.impersonate:
            args += ["--impersonate", self.impersonate]
        return args + list(self.extra_args)

    def run(self, args: list[str], cwd: str | None = None) -> subprocess.CompletedProcess:
        cmd = self._base() + args
        with self.lock:
            res = subprocess.run(cmd, capture_output=True, text=True, cwd=cwd, timeout=self.timeout,
                                 stdin=subprocess.DEVNULL)
        err = (res.stderr or "").lower()
        if res.returncode != 0 and ("http error 429" in err or "too many requests" in err):
            raise RateLimited(res.stderr.strip().splitlines()[-1] if res.stderr.strip() else "429")
        return res

    def info(self, url: str) -> dict:
        res = self.run(["--dump-json", "--skip-download", url])
        if res.returncode != 0:
            raise RuntimeError((res.stderr or "yt-dlp failed").strip().splitlines()[-1])
        return json.loads(res.stdout)


def caption_tracks(info: dict, languages: list[str]) -> list[tuple[str, str, str, bool]]:
    """(language, format, url, automatic) of the caption tracks in ``info``, best first.

    Order: the requested languages in order, manual captions before automatic ones, json3
    before vtt before the rest. Languages not requested are left out.
    """
    fmt_rank = {"json3": 0, "vtt": 1, "srv3": 2, "srt": 3}
    found = []
    for automatic, field_name in ((False, "subtitles"), (True, "automatic_captions")):
        for lang, tracks in (info.get(field_name) or {}).items():
            for t in tracks if isinstance(tracks, list) else [tracks]:
                if isinstance(t, dict) and t.get("url"):
                    found.append((lang, t.get("ext", ""), t["url"], automatic))

    def lang_rank(lang: str) -> int:
        base = lang.split("-")[0]
        for i, want in enumerate(languages):
            if lang == want or base == want.split("-")[0]:
                return i
        return len(languages)

    found = [f for f in found if lang_rank(f[0]) < len(languages)]
    found.sort(key=lambda f: (lang_rank(f[0]), f[3], fmt_rank.get(f[1], 9)))
    return found


def best_audio(info: dict) -> dict | None:
    """Best audio-only format in ``info`` (highest bitrate), or any format with audio."""
    fmts = [f for f in info.get("formats") or [] if f.get("acodec") not in (None, "none") and f.get("url")]
    audio_only = [f for f in fmts if f.get("vcodec") in (None, "none")]
    pool = audio_only or fmts
    if not pool:
        return None
    return max(pool, key=lambda f: (f.get("abr") or 0, f.get("tbr") or 0, f.get("filesize") or 0))
