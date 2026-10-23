from transcriptladder import FAILED, OK, RATE_LIMITED, SILENT, UNAVAILABLE, Transcriber
from transcriptladder.rungs import Got, NoCaptions, Rung, Silent
from transcriptladder.text import Segment
from transcriptladder.video import RateLimited

VID = "dQw4w9WgXcQ"
SPEECH = [Segment(i, i + 1, f"parte {i}: hoje vamos falar do fone de ouvido que chegou") for i in range(3)]


class Fake(Rung):
    def __init__(self, name, tier, prio, outcome):
        self.name, self.tier, self.default_priority, self.outcome, self.calls = name, tier, prio, outcome, 0

    def run(self, job):
        self.calls += 1
        if isinstance(self.outcome, Exception):
            raise self.outcome
        return self.outcome


def make(rungs, **kw):
    return Transcriber(["pt"], rungs=rungs, min_interval=0, sleep=lambda s: None, **kw)


def test_captions_first_then_whisper():
    api = Fake("api", 1, 0.95, RuntimeError("boom"))
    subs = Fake("subs", 1, 0.9, Got(SPEECH, "pt"))
    whisper = Fake("whisper", 2, 0.8, Got(SPEECH, "pt"))
    r = make([whisper, subs, api]).transcribe(f"https://youtu.be/{VID}")
    assert r.outcome == OK and r.method == "subs" and whisper.calls == 0
    assert [a.outcome for a in r.attempts] == ["error", "ok"]
    assert "00:00:00,000 --> 00:00:01,000" in r.srt()


def test_no_captions_skips_the_other_caption_rungs():
    api = Fake("api", 1, 0.95, NoCaptions("TranscriptsDisabled"))
    subs = Fake("subs", 1, 0.9, Got(SPEECH))
    whisper = Fake("whisper", 2, 0.8, Got(SPEECH, "pt"))
    r = make([api, subs, whisper]).transcribe(VID)
    assert r.method == "whisper" and subs.calls == 0
    assert [(a.rung, a.outcome) for a in r.attempts] == [("api", "no_captions"), ("subs", "skipped"), ("whisper", "ok")]


def test_silence_is_a_result():
    r = make([Fake("api", 1, 0.9, NoCaptions("x")), Fake("whisper", 2, 0.8, Silent("no speech"))]).transcribe(VID)
    assert r.outcome == SILENT


def test_whisper_output_that_is_not_speech_counts_as_silence():
    r = make([Fake("whisper", 2, 0.8, Got([Segment(0, 1, "[Música]")]))]).transcribe(VID)
    assert r.outcome == SILENT


def test_rejected_caption_falls_through():
    junk = Fake("api", 1, 0.95, Got([Segment(0, 1, "<html><body>consent</body></html>")]))
    good = Fake("subs", 1, 0.9, Got(SPEECH))
    r = make([junk, good]).transcribe(VID)
    assert r.method == "subs" and r.attempts[0].reason == "html"


def test_429_pauses_every_later_call():
    t = [0.0]
    api = Fake("api", 1, 0.95, RateLimited("HTTP Error 429"))
    whisper = Fake("whisper", 2, 0.8, Got(SPEECH))
    tr = make([api, whisper], clock=lambda: t[0], rate_limit_pause=600)
    r = tr.transcribe(VID)
    assert r.outcome == RATE_LIMITED and whisper.calls == 0
    t[0] = 100
    r2 = tr.transcribe("https://youtu.be/aaaaaaaaaaa")
    assert r2.outcome == RATE_LIMITED and r2.retry_after == 500 and api.calls == 1


def test_private_video_is_unavailable():
    r = make([Fake("subs", 1, 0.9, RuntimeError("ERROR: [youtube] x: Private video. Sign in"))]).transcribe(VID)
    assert r.outcome == UNAVAILABLE


def test_all_fail():
    r = make([Fake("a", 1, 0.9, RuntimeError("x"))]).transcribe(VID)
    assert r.outcome == FAILED


def test_invalid_url():
    assert make([Fake("a", 1, 0.9, Got(SPEECH))]).transcribe("https://vimeo.com/1").outcome == "invalid_url"


def test_learned_priority_reorders_inside_a_tier(tmp_path):
    a, b = Fake("a", 1, 0.9, RuntimeError("x")), Fake("b", 1, 0.85, Got(SPEECH))
    tr = make([a, b], memory=str(tmp_path / "m.json"))
    for _ in range(6):
        tr.transcribe(VID)
    assert [r.name for r in tr.order()] == ["b", "a"]


def test_cookies_are_opt_in_and_only_in_the_cookies_rung(monkeypatch):
    from transcriptladder.video import YtDlp
    from transcriptladder.rungs import YtDlpSubs, YtDlpSubsCookies
    import shutil
    monkeypatch.setattr(shutil, "which", lambda b: "/usr/bin/" + b if b == "yt-dlp" else None)
    plain = YtDlp()
    assert "--cookies" not in plain._base(with_cookies=True)
    y = YtDlp(cookies="c.txt")
    assert "--cookies" not in y._base() and y._base(with_cookies=True)[3:5] == ["--cookies", "c.txt"]
    assert YtDlp(cookies_from_browser="chrome")._base(with_cookies=True)[3:5] == ["--cookies-from-browser", "chrome"]
    assert not YtDlpSubs.with_cookies and YtDlpSubsCookies.with_cookies
    t = Transcriber(["pt"], ytdlp=y)
    assert "yt_dlp_subs_cookies" in [r.name for r in t.rungs]
    assert "yt_dlp_subs_cookies" not in [r.name for r in Transcriber(["pt"]).rungs]


def test_age_gate_is_not_final_when_cookies_are_set():
    from transcriptladder.video import YtDlp
    gate = Fake("subs", 1, 0.9, RuntimeError("Sign in to confirm your age"))
    with_cookies = Fake("subs_cookies", 1, 0.85, Got(SPEECH))
    with_cookies.with_cookies = True
    tr = Transcriber(["pt"], rungs=[gate, with_cookies], ytdlp=YtDlp(cookies="c.txt"), min_interval=0, sleep=lambda s: None)
    r = tr.transcribe(VID)
    assert r.ok and r.method == "subs_cookies"
