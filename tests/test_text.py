import json

from transcriptladder import text as T
from transcriptladder.video import best_audio, caption_tracks, video_id

AUTO_VTT = """WEBVTT
Kind: captions
Language: pt

00:00:00.320 --> 00:00:02.869 align:start position:0%

olá<00:00:00.640><c> pessoal</c><00:00:01.040><c> hoje</c>

00:00:02.869 --> 00:00:02.879 align:start position:0%
olá pessoal hoje


00:00:02.879 --> 00:00:05.150 align:start position:0%
olá pessoal hoje
vamos<00:00:03.200><c> testar</c><00:00:03.600><c> o</c><00:00:03.900><c> fone</c>
"""

SRT = """1
00:00:01,000 --> 00:00:03,500
Primeira linha

2
00:00:03,500 --> 00:00:06,000
Segunda <i>linha</i>
"""


def test_auto_vtt_rolling_captions_appear_once():
    segs = T.to_segments(AUTO_VTT)
    assert T.join(segs) == "olá pessoal hoje\nvamos testar o fone"
    assert segs[0].start == 0.32


def test_srt():
    segs = T.to_segments(SRT)
    assert [s.text for s in segs] == ["Primeira linha", "Segunda linha"]
    assert segs[1].start == 3.5 and segs[1].end == 6.0


def test_json3():
    data = {"wireMagic": "pb3", "events": [
        {"tStartMs": 0, "dDurationMs": 1500, "segs": [{"utf8": "bom "}, {"utf8": "dia"}]},
        {"tStartMs": 1500, "dDurationMs": 10, "segs": [{"utf8": "\n"}]},
        {"tStartMs": 1600, "dDurationMs": 2000, "segs": [{"utf8": "tudo bem"}]}]}
    segs = T.to_segments(json.dumps(data))
    assert [(s.start, s.text) for s in segs] == [(0.0, "bom dia"), (1.6, "tudo bem")]


def test_check_rejects_what_is_not_speech():
    assert T.check("") == "empty"
    assert T.check("<!DOCTYPE html><html><body>erro</body></html>") == "html"
    assert T.check("Traceback (most recent call last):\n  File x") == "stack_trace"
    assert T.check('{\n "events": []\n}') == "json"
    assert T.check("[Música]\n[Música]").startswith("few_words")
    good = "\n".join(["hoje vamos falar do fone de ouvido que chegou aqui"] * 3)
    assert T.check(good) == ""


def test_video_id_forms():
    vid = "dQw4w9WgXcQ"
    for u in [vid, f"https://www.youtube.com/watch?v={vid}&t=30", f"https://youtu.be/{vid}?si=x",
              f"https://m.youtube.com/watch?v={vid}", f"https://www.youtube.com/shorts/{vid}",
              f"https://www.youtube.com/live/{vid}", f"https://www.youtube.com/embed/{vid}", f"youtube.com/watch?v={vid}"]:
        assert video_id(u) == vid, u
    assert video_id("https://vimeo.com/123") is None
    assert video_id("https://www.youtube.com/watch?v=short") is None


def test_caption_tracks_order():
    info = {"subtitles": {"en": [{"ext": "vtt", "url": "m-en"}]},
            "automatic_captions": {"pt": [{"ext": "vtt", "url": "a-pt-vtt"}, {"ext": "json3", "url": "a-pt-json3"}],
                                   "de": [{"ext": "json3", "url": "a-de"}]}}
    urls = [t[2] for t in caption_tracks(info, ["pt", "en"])]
    assert urls == ["a-pt-json3", "a-pt-vtt", "m-en"]


def test_best_audio_prefers_audio_only_highest_bitrate():
    info = {"formats": [{"format_id": "v", "acodec": "mp4a", "vcodec": "avc1", "abr": 128, "url": "v"},
                        {"format_id": "a1", "acodec": "opus", "vcodec": "none", "abr": 70, "url": "a1"},
                        {"format_id": "a2", "acodec": "opus", "vcodec": "none", "abr": 160, "url": "a2"}]}
    assert best_audio(info)["format_id"] == "a2"
