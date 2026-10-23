# Changelog

## [0.1.0] - 2026-10-22

### Added
- `Transcriber`: captions first (youtube-transcript-api, caption URL from yt-dlp metadata, yt-dlp subtitles), speech recognition last (faster-whisper, Whisper), order learned inside each tier with the scrapladder memory.
- Outcomes: ok, silent, unavailable (private/removed), rate_limited (pause after a 429), failed, invalid_url.
- `text.to_segments`: VTT, SRT and YouTube json3 to timed lines, rolling auto-caption repeats removed; `text.check` rejects HTML, stack traces, JSON and too little text.
- `video_id()` for every YouTube URL form; `Transcript.srt()`.
- Audio for speech recognition read from the stream URL with ffmpeg, first hour only.
- Opt-in `yt_dlp_subs_cookies` rung with `YtDlp(cookies=...)` or `cookies_from_browser`, used only after the rungs without cookies.
- CLI: `transcriptladder URL... [--srt] [--cookies FILE]`, `transcriptladder methods`.
