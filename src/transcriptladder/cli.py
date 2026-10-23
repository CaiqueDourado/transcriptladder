"""Command line.

    transcriptladder URL [URL ...] [--lang pt,en] [--srt] [--memory F]
    transcriptladder methods
"""

from __future__ import annotations

import argparse
import sys

from . import Transcriber, YtDlp
from .rungs import ALL


def main(argv=None) -> int:
    p = argparse.ArgumentParser(prog="transcriptladder")
    p.add_argument("urls", nargs="+", help="YouTube URLs or ids, or 'methods'")
    p.add_argument("--lang", default="pt,pt-BR,en", help="caption languages, in order")
    p.add_argument("--memory", default=None)
    p.add_argument("--srt", action="store_true", help="print SRT with timestamps instead of plain text")
    p.add_argument("--interval", type=float, default=10.0)
    p.add_argument("--cookies", help="cookies.txt of a logged-in YouTube session (opt-in, see README)")
    p.add_argument("--cookies-from-browser", help="browser to read the session from, e.g. chrome (opt-in)")
    a = p.parse_args(argv)

    if a.urls == ["methods"]:
        for cls in ALL:
            r = cls()
            print(f"{r.name:<24} tier {r.tier}  {'available' if r.available() else 'missing'}")
        print("yt_dlp_subs_cookies      tier 1  only with --cookies or --cookies-from-browser")
        return 0

    code = 0
    ytdlp = YtDlp(cookies=a.cookies, cookies_from_browser=a.cookies_from_browser)
    with Transcriber(a.lang.split(","), memory=a.memory, min_interval=a.interval, ytdlp=ytdlp) as t:
        for url in a.urls:
            r = t.transcribe(url)
            print(f"# {url}: {r.summary()}", file=sys.stderr)
            if r.ok:
                print(r.srt() if a.srt else r.text)
            else:
                code = 1
    return code


if __name__ == "__main__":
    sys.exit(main())
