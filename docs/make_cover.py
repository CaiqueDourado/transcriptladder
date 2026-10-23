"""Cover and logo for transcriptladder (same visual family as scrapladder)."""
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import FancyBboxPatch, Rectangle, FancyArrowPatch
from pathlib import Path

OUT = Path(__file__).parent / "img"
INK, MUTED, LINE, BG = "#111111", "#555555", "#d9dde3", "#fdfdfc"
BLUE, ORANGE, AQUA, GRAY = "#2a78d6", "#eb6834", "#1baf7a", "#8a94a3"
RUNG_COLORS = ["#9cc2ef", "#5e9be2", "#2a78d6", "#1d5aa6"]
for fam in ("Inter", "DejaVu Sans"):
    try:
        matplotlib.font_manager.findfont(fam, fallback_to_default=False); plt.rcParams["font.family"] = fam; break
    except ValueError:
        pass


def mark(ax, x, y, w, h, lw=5):
    ax.plot([x, x], [y, y + h], color=INK, lw=lw, solid_capstyle="round")
    ax.plot([x + w, x + w], [y, y + h], color=INK, lw=lw, solid_capstyle="round")
    for i in range(4):
        yy = y + h * (i + 0.6) / 4.2
        ax.plot([x, x + w], [yy, yy], color=ORANGE if i == 1 else BLUE, lw=lw * 0.9, solid_capstyle="round")
    # caption bubble
    ax.add_patch(FancyBboxPatch((x + w + 1.2, y + h * 0.62), 5.2, 3.2, boxstyle="round,pad=0,rounding_size=0.8",
                                fc=AQUA, ec="none"))
    ax.text(x + w + 3.8, y + h * 0.62 + 1.6, "CC", color="white", fontsize=9, weight="bold", ha="center", va="center")


TEXT = {
    "": dict(tag="YouTube transcripts\nthat keep working", sub="captions first, speech recognition last,\nlearning which method works",
             rungs=[("youtube-transcript-api", "reads the caption track"), ("caption URL from yt-dlp", "one metadata call, plain HTTP"),
                    ("yt-dlp subtitles", "--write-subs --write-auto-subs"), ("faster-whisper · Whisper", "audio → text, when there are no captions")],
             cost="time and CPU", out="output", outrows=["text", "timed segments", "SRT", "language"],
             foot="also: private/removed videos, silent videos, 429 pause, rolling auto-captions de-duplicated"),
    ".pt-BR": dict(tag="Transcrições do YouTube\nque continuam funcionando", sub="legenda primeiro, reconhecimento de fala por último,\naprendendo qual método funciona",
                   rungs=[("youtube-transcript-api", "lê a faixa de legenda"), ("URL da legenda via yt-dlp", "uma chamada de metadados, HTTP comum"),
                          ("legendas do yt-dlp", "--write-subs --write-auto-subs"), ("faster-whisper · Whisper", "áudio → texto, quando não há legenda")],
                   cost="tempo e CPU", out="saída", outrows=["texto", "trechos com tempo", "SRT", "idioma"],
                   foot="também: vídeo privado/removido, vídeo sem fala, pausa no 429, legenda automática sem repetição"),
}
OUT.mkdir(parents=True, exist_ok=True)
for suf, t in TEXT.items():
    fig = plt.figure(figsize=(11, 5.6), dpi=110); fig.patch.set_facecolor(BG)
    ax = fig.add_axes([0, 0, 1, 1]); ax.set_xlim(0, 110); ax.set_ylim(0, 56); ax.axis("off")
    mark(ax, 5, 40, 4.2, 11)
    ax.text(17.5, 45.5, "transcriptladder", fontsize=20.5, weight="bold", color=INK, va="center")
    ax.text(5, 31.5, t["tag"], fontsize=15.5, color=INK, va="center", linespacing=1.25)
    ax.text(5, 23.5, t["sub"], fontsize=10.8, color=MUTED, va="center", linespacing=1.3)
    x0, w = 51, 30
    ax.add_patch(Rectangle((x0 - 0.6, 6), 0.9, 44, color=INK)); ax.add_patch(Rectangle((x0 + w - 0.3, 6), 0.9, 44, color=INK))
    for i, (name, desc) in enumerate(t["rungs"]):
        y = 9 + i * 10.5
        c = RUNG_COLORS[i] if i < 3 else "#e9edf2"
        ax.add_patch(FancyBboxPatch((x0 + 1.2, y), w - 2.4, 6.4, boxstyle="round,pad=0,rounding_size=1.2", fc=c, ec="none"))
        col = "white" if i in (1, 2) else INK
        ax.text(x0 + 3, y + 4.3, name, fontsize=10.3, weight="bold", color=col, va="center")
        ax.text(x0 + 3, y + 1.9, desc, fontsize=8.6, color=col if i in (1, 2) else MUTED, va="center")
    ax.add_patch(FancyArrowPatch((x0 - 4, 9), (x0 - 4, 49), arrowstyle="-|>", mutation_scale=14, color=GRAY, lw=1.4))
    ax.text(x0 - 5.6, 29, t["cost"], fontsize=9, color=GRAY, rotation=90, va="center", ha="center")
    mx, my = 86, 19
    ax.add_patch(FancyBboxPatch((mx, my), 20, 22, boxstyle="round,pad=0,rounding_size=1.4", fc="white", ec=LINE, lw=1.2))
    ax.text(mx + 2, my + 19, t["out"], fontsize=11, weight="bold", color=INK)
    for j, row in enumerate(t["outrows"]):
        ax.text(mx + 2, my + 14.5 - j * 3.8, "✓  " + row, fontsize=9, color=INK)
    ax.add_patch(FancyArrowPatch((x0 + w + 1.5, 30), (mx - 0.5, 30), arrowstyle="-|>", mutation_scale=12, color=GRAY, lw=1.2,
                                 linestyle=(0, (3, 2))))
    ax.text(5, 3.2, t["foot"], fontsize=8.6, color=MUTED)
    ax.text(105, 3.2, "github.com/CaiqueDourado", fontsize=8.6, color=MUTED, ha="right")
    fig.savefig(OUT / f"cover{suf}.png", facecolor=BG); plt.close(fig)
print("ok")
