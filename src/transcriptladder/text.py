"""Caption formats to clean text, and the check that a text looks like a transcript.

YouTube serves captions as WebVTT, SRT or its own JSON ("json3"). Auto-generated VTT repeats
each line in the next cue while the text scrolls ("rolling captions"), so a naive conversion
prints every sentence two or three times. :func:`to_segments` removes those repeats and keeps
the timing of each line.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass


@dataclass(frozen=True)
class Segment:
    start: float  # seconds
    end: float
    text: str


_TS = re.compile(r"(?:(\d+):)?(\d{1,2}):(\d{2})[.,](\d{3})")
_CUE_LINE = re.compile(rf"({_TS.pattern})\s*-->\s*({_TS.pattern})")
_INLINE_TS = re.compile(r"<\d{1,2}:\d{2}(?::\d{2})?\.\d{3}>")
_TAG = re.compile(r"</?[^>]+>")


def _seconds(m: re.Match, offset: int = 0) -> float:
    h, mi, s, ms = (m.group(offset + i) for i in range(1, 5))
    return int(h or 0) * 3600 + int(mi) * 60 + int(s) + int(ms) / 1000


def _clean_line(line: str) -> str:
    line = _INLINE_TS.sub("", line)
    line = _TAG.sub("", line)
    line = line.replace("&nbsp;", " ").replace("&amp;", "&").replace("&lt;", "<").replace("&gt;", ">")
    return re.sub(r"\s+", " ", line).strip()


def _timed_cues(text: str) -> list[Segment]:
    """Cues of a VTT or SRT file, with header, cue numbers and settings dropped."""
    out: list[Segment] = []
    start = end = None
    buf: list[str] = []

    def flush():
        if start is not None and buf:
            out.append(Segment(start, end, " ".join(buf)))

    for raw in text.replace("\r\n", "\n").replace("\r", "\n").split("\n"):
        m = _CUE_LINE.search(raw)
        if m:
            flush()
            buf = []
            start = _seconds(_TS.match(m.group(1)))
            end = _seconds(_TS.match(m.group(6)))
            continue
        line = _clean_line(raw)
        if not line and buf:  # blank line ends the cue
            flush()
            buf, start = [], None
            continue
        if not line or start is None:
            continue  # header (WEBVTT, Kind:, Language:, STYLE) or blank line
        if line.isdigit() and not buf:
            continue  # SRT cue number
        buf.append(line)
    flush()
    return out


def _json3(text: str) -> list[Segment]:
    data = json.loads(text)
    out = []
    for ev in data.get("events", []):
        line = "".join(s.get("utf8", "") for s in ev.get("segs") or []).strip()
        if line and line != "\n":
            start = ev.get("tStartMs", 0) / 1000
            out.append(Segment(start, start + ev.get("dDurationMs", 0) / 1000, re.sub(r"\s+", " ", line)))
    return out


def dedupe_rolling(segs: list[Segment]) -> list[Segment]:
    """Auto captions repeat the previous line at the top of the next cue. Keep each line once."""
    out: list[Segment] = []
    for s in segs:
        text = s.text
        if out:
            prev = out[-1].text
            if text == prev:
                out[-1] = Segment(out[-1].start, s.end, prev)
                continue
            if text.startswith(prev + " "):
                text = text[len(prev) + 1:]
        if text:
            out.append(Segment(s.start, s.end, text))
    return out


def to_segments(caption: str) -> list[Segment]:
    """Parse VTT, SRT or YouTube json3 into timed lines, without the rolling repeats."""
    caption = (caption or "").lstrip("﻿")
    if caption.lstrip().startswith("{") and '"events"' in caption:
        segs = _json3(caption)
    else:
        segs = _timed_cues(caption)
    return dedupe_rolling(segs)


def join(segments: list[Segment]) -> str:
    """One line per segment, consecutive duplicates removed."""
    lines, prev = [], None
    for s in segments:
        if s.text != prev:
            lines.append(s.text)
        prev = s.text
    return "\n".join(lines)


_CODE_HINTS = ("<!doctype html", "<html", "<body", "<script", "<style", "<head", "<meta", "<title")
_STACK = re.compile(r"\b(traceback|stacktrace|exception:|error at)\b")


def check(text: str, *, min_words: int = 15, min_lines: int = 2, min_words_per_line: float = 1.1) -> str:
    """Return why ``text`` does not look like a transcript, or ``""`` if it does.

    Catches what a broken method returns instead of speech: an HTML page, a stack trace, raw
    JSON, a handful of words, or a list of one-word lines (music tags, "[Música]").
    """
    if not text or not text.strip():
        return "empty"
    low = text.strip().lower()
    if any(h in low for h in _CODE_HINTS):
        return "html"
    if _STACK.search(low):
        return "stack_trace"
    if re.search(r'^[\s{\[]+"[^"\n]+"\s*:', low, re.M):
        return "json"
    words = re.findall(r"\w+", low)
    lines = [l for l in low.split("\n") if l.strip()]
    if len(words) < min_words:
        return f"few_words:{len(words)}"
    if len(lines) < min_lines and len(words) < 40:
        return f"few_lines:{len(lines)}"
    if len(words) / max(1, len(lines)) < min_words_per_line:
        return "low_density"
    return ""
