"""Transcriber: climb the rungs until one returns a usable transcript."""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Callable, Iterable

from scrapladder.memory import Memory

from . import text as T
from .rungs import Job, NoCaptions, Rung, Silent, default_rungs
from .video import RateLimited, YtDlp, video_id

OK = "ok"
SILENT = "silent"            # speech recognition ran: the video has no speech
UNAVAILABLE = "unavailable"  # private, removed, age- or region-restricted
RATE_LIMITED = "rate_limited"
FAILED = "failed"
INVALID = "invalid_url"

MEMORY_KEY = "youtube.com"
_UNAVAILABLE_HINTS = ("private video", "video unavailable", "this video has been removed", "members-only",
                      "sign in to confirm your age", "not available in your country", "account associated with this video has been terminated")


@dataclass
class Attempt:
    rung: str
    outcome: str  # ok, no_captions, rejected, silent, error, rate_limited, skipped
    reason: str = ""
    seconds: float = 0.0


@dataclass
class Transcript:
    video_id: str | None
    outcome: str
    text: str = ""
    segments: list[T.Segment] = field(default_factory=list)
    language: str = ""
    method: str = ""
    attempts: list[Attempt] = field(default_factory=list)
    retry_after: float = 0.0

    @property
    def ok(self) -> bool:
        return self.outcome == OK

    def summary(self) -> str:
        steps = " > ".join(f"{a.rung}:{a.outcome}" + (f"({a.reason})" if a.reason else "") for a in self.attempts)
        return f"{self.outcome} via {self.method or '-'} [{steps}]"

    def srt(self) -> str:
        def ts(s: float) -> str:
            ms = int(round(s * 1000))
            return f"{ms // 3600000:02d}:{ms // 60000 % 60:02d}:{ms // 1000 % 60:02d},{ms % 1000:03d}"
        return "\n".join(f"{i}\n{ts(s.start)} --> {ts(s.end)}\n{s.text}\n" for i, s in enumerate(self.segments, 1))


class Transcriber:
    """Get the transcript of YouTube videos, trying captions first and speech recognition last.

    >>> with Transcriber(languages=["pt", "en"], memory="transcriptladder.json") as t:
    ...     r = t.transcribe("https://youtu.be/VIDEO_ID")
    ...     print(r.method, r.language, r.text[:200])

    Parameters
    ----------
    languages:
        Caption languages wanted, in order. The first one is also the language given to
        speech recognition.
    rungs:
        Methods to use. Default: every one installed here.
    memory:
        A ``scrapladder.Memory``, a JSON path, or ``None``. Keeps each rung's success rate, so
        a rung that keeps failing moves down inside its tier.
    min_interval:
        Seconds between two videos (default 10).
    rate_limit_pause:
        After a 429, how long every call returns ``rate_limited`` without touching YouTube
        (default 15 minutes).
    max_audio_seconds:
        Speech recognition reads at most this much audio (default 1 hour).
    ytdlp:
        A :class:`YtDlp` (``impersonate``, ``extra_args``, ``binary``).
    """

    def __init__(self, languages: Iterable[str] = ("pt", "pt-BR", "en"), *, rungs: Iterable[Rung] | None = None,
                 memory: Memory | str | None = None, min_interval: float = 10.0, rate_limit_pause: float = 900.0,
                 max_audio_seconds: int = 3600, ytdlp: YtDlp | None = None,
                 clock: Callable[[], float] = time.monotonic, sleep: Callable[[float], None] = time.sleep,
                 log: Callable[[str], None] | None = None) -> None:
        self.languages = list(languages)
        self.rungs = list(rungs) if rungs is not None else default_rungs()
        if not self.rungs:
            raise ValueError("no method available: pip install 'transcriptladder[api]' or install yt-dlp")
        self.memory = memory if isinstance(memory, Memory) else Memory(memory)
        self.min_interval, self.rate_limit_pause = min_interval, rate_limit_pause
        self.max_audio_seconds = max_audio_seconds
        self.ytdlp = ytdlp or YtDlp()
        self._clock, self._sleep = clock, sleep
        self._next_ok = 0.0
        self._paused_until = 0.0
        self.log = log or (lambda m: None)

    def order(self) -> list[Rung]:
        """Captions before speech recognition; inside each tier, by learned priority."""
        return sorted(self.rungs, key=lambda r: (r.tier, -self.memory.priority(r.name, r.default_priority)))

    def transcribe(self, url_or_id: str) -> Transcript:
        vid = video_id(url_or_id)
        if not vid:
            return Transcript(None, INVALID)
        now = self._clock()
        if now < self._paused_until:
            return Transcript(vid, RATE_LIMITED, retry_after=self._paused_until - now)
        if now < self._next_ok:
            self._sleep(self._next_ok - now)
        self._next_ok = self._clock() + self.min_interval

        job = Job(vid, self.languages, self.ytdlp, self.max_audio_seconds)
        result = Transcript(vid, FAILED)
        try:
            for rung in self.order():
                if rung.tier == 1 and job.no_captions:
                    result.attempts.append(Attempt(rung.name, "skipped", "no_captions"))
                    continue
                start = time.monotonic()
                att = Attempt(rung.name, "ok")
                result.attempts.append(att)
                try:
                    got = rung.run(job)
                except NoCaptions as e:
                    job.no_captions = True
                    att.outcome, att.reason = "no_captions", str(e)
                    continue
                except Silent:
                    att.outcome = "silent"
                    self.memory.record_success(MEMORY_KEY, rung.name)  # finding silence is a result
                    result.outcome, result.method = SILENT, rung.name
                    return result
                except RateLimited as e:
                    att.outcome, att.reason = "rate_limited", str(e)[:80]
                    self._paused_until = self._clock() + self.rate_limit_pause
                    result.outcome, result.retry_after = RATE_LIMITED, self.rate_limit_pause
                    return result
                except Exception as e:
                    msg = str(e).lower()
                    if any(h in msg for h in _UNAVAILABLE_HINTS):
                        att.outcome, att.reason = "unavailable", str(e)[:120]
                        result.outcome = UNAVAILABLE
                        return result
                    att.outcome, att.reason = "error", f"{type(e).__name__}: {str(e)[:100]}"
                    self.memory.record_failure(rung.name)
                    continue
                finally:
                    att.seconds = round(time.monotonic() - start, 2)
                    self.log(f"{vid} {rung.name}: {att.outcome} {att.reason}".rstrip())

                why = T.check(got.text)
                if why:
                    att.outcome, att.reason = "rejected", why
                    self.memory.record_failure(rung.name)
                    if rung.tier == 2:
                        # Speech recognition found almost nothing: treat the video as without speech.
                        result.outcome, result.method = SILENT, rung.name
                        return result
                    continue
                self.memory.record_success(MEMORY_KEY, rung.name)
                self.memory.save()
                result.outcome, result.method = OK, rung.name
                result.text, result.segments, result.language = got.text, got.segments, got.language
                return result
            return result
        finally:
            job.cleanup()

    def close(self) -> None:
        self.memory.save()

    def __enter__(self) -> "Transcriber":
        return self

    def __exit__(self, *exc) -> None:
        self.close()

