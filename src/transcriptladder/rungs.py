"""The rungs: ways to get the words of a YouTube video, cheapest first.

Tier 1 reads captions (manual or automatic) that YouTube already has: fast, free, exact
timing. Tier 2 downloads the audio and runs speech recognition: slow and CPU-heavy, but works
when a video has no captions.
"""

from __future__ import annotations

import glob
import os
import shutil
import subprocess
import tempfile
from dataclasses import dataclass, field

from . import text as T
from .video import RateLimited, YtDlp, best_audio, caption_tracks, watch_url


class NoCaptions(Exception):
    """The video has no captions in the requested languages (tier 1 can be skipped)."""


class Silent(Exception):
    """Speech recognition ran and found no speech."""


@dataclass
class Job:
    """One video being transcribed: shared by the rungs so metadata is fetched once."""

    video_id: str
    languages: list[str]
    ytdlp: YtDlp
    max_audio_seconds: int = 3600
    workdir: str = field(default_factory=lambda: tempfile.mkdtemp(prefix="transcriptladder-"))
    no_captions: bool = False
    _info: dict | None = None

    @property
    def url(self) -> str:
        return watch_url(self.video_id)

    def info(self) -> dict:
        if self._info is None:
            self._info = self.ytdlp.info(self.url)
        return self._info

    def cleanup(self) -> None:
        shutil.rmtree(self.workdir, ignore_errors=True)


@dataclass
class Got:
    segments: list[T.Segment]
    language: str = ""
    text: str = ""

    def __post_init__(self):
        if not self.text:
            self.text = T.join(self.segments)


class Rung:
    name = "rung"
    tier = 1
    default_priority = 0.5

    def available(self) -> bool:
        return True

    def run(self, job: Job) -> Got:  # pragma: no cover - interface
        raise NotImplementedError


# ---------------------------------------------------------------- tier 1: captions
class TranscriptApi(Rung):
    """``youtube-transcript-api``: reads the caption track without a browser or yt-dlp."""

    name, tier, default_priority = "youtube_transcript_api", 1, 0.95

    def available(self) -> bool:
        import importlib.util
        return importlib.util.find_spec("youtube_transcript_api") is not None

    def run(self, job: Job) -> Got:
        from youtube_transcript_api import YouTubeTranscriptApi
        try:
            fetched = YouTubeTranscriptApi().fetch(job.video_id, languages=job.languages)
        except Exception as e:
            name = type(e).__name__
            if name in ("TranscriptsDisabled", "NoTranscriptFound"):
                raise NoCaptions(name) from e
            if name in ("RequestBlocked", "IpBlocked", "TooManyRequests"):
                raise RateLimited(name) from e
            raise
        segs = [T.Segment(s.start, s.start + s.duration, " ".join(s.text.split())) for s in fetched if s.text.strip()]
        return Got(T.dedupe_rolling(segs), getattr(fetched, "language_code", ""))


class CaptionUrl(Rung):
    """Caption URL from yt-dlp's metadata, downloaded with plain HTTP (no second yt-dlp run)."""

    name, tier, default_priority = "caption_url", 1, 0.92

    def available(self) -> bool:
        import importlib.util
        return YtDlp().available() and importlib.util.find_spec("requests") is not None

    def run(self, job: Job) -> Got:
        import requests
        tracks = caption_tracks(job.info(), job.languages)
        if not tracks:
            raise NoCaptions("no track in the requested languages")
        for lang, _fmt, url, _auto in tracks[:3]:
            r = requests.get(url, timeout=30)
            if r.status_code == 429:
                raise RateLimited("caption url 429")
            if r.ok and r.text.strip():
                segs = T.to_segments(r.text)
                if segs:
                    return Got(segs, lang)
        raise RuntimeError("caption download failed")


class YtDlpSubs(Rung):
    """yt-dlp writes the subtitle file itself (``--write-subs --write-auto-subs``)."""

    name, tier, default_priority = "yt_dlp_subs", 1, 0.9

    def available(self) -> bool:
        return YtDlp().available()

    def run(self, job: Job) -> Got:
        out = os.path.join(job.workdir, "%(id)s.%(ext)s")
        res = job.ytdlp.run(["--skip-download", "--write-subs", "--write-auto-subs",
                             "--sub-langs", ",".join(job.languages), "--sub-format", "json3/vtt/best",
                             "-o", out, job.url])
        if res.returncode != 0:
            raise RuntimeError((res.stderr or "yt-dlp failed").strip().splitlines()[-1])
        files = glob.glob(os.path.join(job.workdir, f"{job.video_id}.*.*"))
        rank = {lang: i for i, lang in enumerate(job.languages)}
        files.sort(key=lambda f: rank.get(f.rsplit(".", 2)[-2], 99))
        for f in files:
            segs = T.to_segments(open(f, encoding="utf-8", errors="ignore").read())
            if segs:
                return Got(segs, f.rsplit(".", 2)[-2])
        raise NoCaptions("yt-dlp wrote no subtitle")


# ---------------------------------------------------------------- tier 2: speech recognition
def fetch_audio(job: Job) -> str:
    """Audio of the first ``max_audio_seconds``, as 16 kHz mono WAV.

    First tries the audio stream URL from the metadata with ffmpeg, which reads only what it
    needs. Falls back to ``yt-dlp -x --download-sections``.
    """
    wav = os.path.join(job.workdir, f"{job.video_id}.wav")
    ffmpeg = shutil.which("ffmpeg")
    if not ffmpeg:
        raise RuntimeError("ffmpeg is not installed")
    try:
        fmt = best_audio(job.info())
    except RateLimited:
        raise
    except Exception:
        fmt = None
    if fmt:
        res = subprocess.run([ffmpeg, "-y", "-loglevel", "error", "-i", fmt["url"], "-t", str(job.max_audio_seconds),
                              "-vn", "-ac", "1", "-ar", "16000", wav],
                             capture_output=True, text=True, timeout=600, stdin=subprocess.DEVNULL)
        if res.returncode == 0 and os.path.getsize(wav) > 1000:
            return wav
    out = os.path.join(job.workdir, f"{job.video_id}.%(ext)s")
    res = job.ytdlp.run(["-x", "--audio-format", "wav", "--postprocessor-args", "ffmpeg:-ac 1 -ar 16000",
                         "--download-sections", f"*0-{job.max_audio_seconds}", "-o", out, job.url])
    if res.returncode != 0 or not os.path.exists(wav):
        raise RuntimeError("audio download failed")
    return wav


class FasterWhisper(Rung):
    name, tier, default_priority = "faster_whisper", 2, 0.8

    def __init__(self, model: str = "base", device: str = "cpu", compute_type: str = "int8"):
        self.model_name, self.device, self.compute_type = model, device, compute_type
        self._model = None

    def available(self) -> bool:
        import importlib.util
        return importlib.util.find_spec("faster_whisper") is not None

    def run(self, job: Job) -> Got:
        if self._model is None:
            from faster_whisper import WhisperModel
            self._model = WhisperModel(self.model_name, device=self.device, compute_type=self.compute_type)
        lang = job.languages[0].split("-")[0] if job.languages else None
        segments, info = self._model.transcribe(fetch_audio(job), language=lang, beam_size=2,
                                                condition_on_previous_text=False)
        segs = [T.Segment(s.start, s.end, s.text.strip()) for s in segments if s.text.strip()]
        if not segs:
            raise Silent("no speech")
        return Got(segs, getattr(info, "language", lang or ""))


class Whisper(Rung):
    name, tier, default_priority = "whisper", 2, 0.65

    def __init__(self, model: str = "base"):
        self.model_name, self._model = model, None

    def available(self) -> bool:
        import importlib.util
        return importlib.util.find_spec("whisper") is not None

    def run(self, job: Job) -> Got:
        if self._model is None:
            import whisper
            self._model = whisper.load_model(self.model_name)
        lang = job.languages[0].split("-")[0] if job.languages else None
        result = self._model.transcribe(fetch_audio(job), language=lang)
        segs = [T.Segment(s["start"], s["end"], s["text"].strip()) for s in result.get("segments", []) if s["text"].strip()]
        if not segs:
            raise Silent("no speech")
        return Got(segs, result.get("language", lang or ""))


ALL = [TranscriptApi, CaptionUrl, YtDlpSubs, FasterWhisper, Whisper]


def default_rungs() -> list[Rung]:
    return [r for r in (cls() for cls in ALL) if r.available()]
