"""Transcribe a list of YouTube URLs into one SRT file per video.

    python examples/transcribe_list.py urls.txt out/
"""
import sys
from pathlib import Path

from transcriptladder import RATE_LIMITED, Transcriber

urls = [u.strip() for u in Path(sys.argv[1]).read_text().splitlines() if u.strip()]
out = Path(sys.argv[2]); out.mkdir(parents=True, exist_ok=True)

with Transcriber(["pt", "en"], memory=out / "transcriptladder.json", log=print) as t:
    for url in urls:
        r = t.transcribe(url)
        print(url, "->", r.summary())
        if r.ok:
            (out / f"{r.video_id}.srt").write_text(r.srt(), encoding="utf-8")
        elif r.outcome == RATE_LIMITED:
            print(f"YouTube asked to slow down; stopping. Try again in {r.retry_after / 60:.0f} min.")
            break
