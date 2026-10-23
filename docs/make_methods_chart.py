"""Which method produced the transcripts in production (4,633 videos)."""
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from pathlib import Path

OUT = Path(__file__).parent / "img"
INK, MUTED, LINE, BG, BLUE, GRAY = "#111111", "#555555", "#e6e6e6", "#fdfdfc", "#2a78d6", "#b8b8b8"
DATA = [("yt-dlp + logged-in cookies*", 1880), ("yt-dlp", 1766), ("Whisper", 745), ("youtube-transcript-api (since May 2026)", 242)]
PT = {"yt-dlp + logged-in cookies*": "yt-dlp + cookies de sessão logada*", "youtube-transcript-api (since May 2026)": "youtube-transcript-api (desde maio de 2026)"}
TXT = {"": ("Which method produced each transcript", "4,633 YouTube videos in a product-research crawler, Sep 2025 to Sep 2026",
            "* opt-in here: the yt_dlp_subs_cookies rung, only when you set cookies"),
       ".pt-BR": ("Qual método gerou cada transcrição", "4.633 vídeos do YouTube num crawler de pesquisa de produtos, set. 2025 a set. 2026",
                  "* opcional aqui: o degrau yt_dlp_subs_cookies, só quando você configura cookies")}
for suf, (t, s, n) in TXT.items():
    fig, ax = plt.subplots(figsize=(10, 4.2), dpi=110); fig.patch.set_facecolor(BG); ax.set_facecolor(BG)
    fig.subplots_adjust(left=0.36, right=0.93, top=0.76, bottom=0.14)
    fig.text(0.02, 0.9, t, fontsize=16, weight="bold", color=INK); fig.text(0.02, 0.83, s, fontsize=10, color=MUTED)
    fig.text(0.02, 0.03, n, fontsize=8.5, color=MUTED)
    labels = [PT.get(l, l) if suf else l for l, _ in DATA][::-1]; vals = [v for _, v in DATA][::-1]
    ax.barh(labels, vals, color=["#9cc2ef" if "*" in l else BLUE for l in labels], height=0.62)
    tot = 4633
    for y, v in enumerate(vals):
        ax.text(v + 25, y, f"{v:,}".replace(",", "." if suf else ",") + f"  ({v/tot:.0%})", va="center", fontsize=9.5, color=INK)
    for k in ("top", "right", "bottom"): ax.spines[k].set_visible(False)
    ax.spines["left"].set_color(LINE); ax.set_xticks([]); ax.tick_params(colors=INK, length=0, labelsize=10); ax.set_xlim(0, 2300)
    fig.savefig(OUT / f"methods{suf}.png", facecolor=BG); plt.close(fig)
print("ok")
