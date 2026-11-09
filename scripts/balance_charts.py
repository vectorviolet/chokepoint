"""Static PNG charts for the balance report (issue #107), drawn by
scripts/balance_sim.py next to report.md.

Four charts, wave on the x axis: lives left, income, enemy threat and
pressure (threat divided by the money spent on defense so far). Every
strategy keeps one fixed color across all of them. The files are
deterministic: fixed size and dpi, a fixed font (matplotlib's bundled
one), no timestamp or version in the PNG metadata.
"""

from __future__ import annotations

import sys
from dataclasses import dataclass
from pathlib import Path

import matplotlib

matplotlib.use("Agg")  # no window: the charts are only written to files

import matplotlib.pyplot as plt  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
# threat_per_wave() imports gen_stats and the game from these.
for _path in (ROOT / "scripts", ROOT / "src", ROOT / "src" / "pygamine"):
    if str(_path) not in sys.path:
        sys.path.insert(0, str(_path))

WIDTH_PX, HEIGHT_PX, DPI = 1200, 600, 100
LINE_PX = 2  # line width in pixels

SURFACE = "#fcfcfb"
TEXT = "#0b0b0b"
TEXT_SECONDARY = "#52514e"
GRID = "#e6e5e1"
BAR = "#8f8e8a"

# One fixed color per strategy, in every chart.
COLORS = {
    "gun_spam": "#2a78d6",
    "gun_cannon": "#eb6834",
    "missile": "#1baf7a",
    "plane_spam": "#eda100",
    "mixed": "#e87ba4",
    "minimal": "#008300",
}


@dataclass(frozen=True)
class Chart:
    file: str
    title: str
    caption: str


LIVES = Chart(
    "lives_left.png",
    "Lives left per wave",
    "Each line is one strategy: read where it steps down (a wave that leaked) "
    "and where it ends in a cross (the run was lost there); runs that play "
    "alike draw on top of each other.",
)
INCOME = Chart(
    "income.png",
    "Income per wave",
    "Money earned in each wave, all of it kill money: read how fast the "
    "payout grows and where a line stops because that run was lost.",
)
THREAT = Chart(
    "threat.png",
    "Enemy threat per wave",
    "The difficulty curve: the total HP of every enemy a wave spawns, after "
    "the game's +25% HP per wave scaling, the same for every strategy.",
)
PRESSURE = Chart(
    "pressure.png",
    "Pressure per wave",
    "A wave's threat divided by all the money spent on towers so far (a "
    "proxy for the defense built): a rising line means the defense is "
    "falling behind, a falling one that it is pulling ahead.",
)
CHARTS = [LIVES, INCOME, THREAT, PRESSURE]


def threat_per_wave(waves: int) -> list[int]:
    """Total enemy HP spawned in each of waves 1..`waves`: the groups the
    game's wave manager builds, each enemy at its scaled HP (the same code
    docs/stats uses). Imported here, not at the top, because gen_stats picks
    the dummy video driver, which would keep a --watch window from opening."""
    from gen_stats import all_waves, scaled_enemy
    from util.config_loader import load_wave_compositions

    authored = load_wave_compositions()
    return [
        sum(count * scaled_enemy(enemy_type, wave)[0] for enemy_type, count in groups)
        for wave, (groups, _interval, _authored) in all_waves(authored, waves).items()
    ]


def _spent_total(row: dict) -> int:
    return sum(v for k, v in row.items() if k.startswith("spent_total_"))


def _new_axes(chart: Chart, waves: int):
    fig = plt.figure(figsize=(WIDTH_PX / DPI, HEIGHT_PX / DPI), dpi=DPI)
    fig.patch.set_facecolor(SURFACE)
    ax = fig.add_axes((0.1, 0.12, 0.81, 0.68))
    ax.set_facecolor(SURFACE)
    fig.text(
        0.1, 0.95, chart.title, color=TEXT, fontsize=16, fontweight="bold", va="top"
    )
    for side in ("top", "right"):
        ax.spines[side].set_visible(False)
    for side in ("left", "bottom"):
        ax.spines[side].set_color(TEXT_SECONDARY)
    ax.tick_params(colors=TEXT_SECONDARY, labelsize=11)
    ax.grid(axis="y", color=GRID, linewidth=0.8)
    ax.set_axisbelow(True)
    # Room on the right for the end-of-line labels.
    ax.set_xlim(0.5, waves + max(2.0, waves * 0.08))
    ax.set_xticks([1, *range(5, waves + 1, 5)])
    ax.set_xlabel("Wave", color=TEXT_SECONDARY, fontsize=12)
    if waves >= 25:
        ax.axvline(25, color=TEXT_SECONDARY, linestyle="--", linewidth=0.9, zorder=1)
        ax.annotate(
            "win",
            (25, 1),
            xycoords=ax.get_xaxis_transform(),
            xytext=(4, -3),
            textcoords="offset points",
            color=TEXT_SECONDARY,
            fontsize=10,
            va="top",
        )
    return fig, ax


def _label_ends(fig, ax, ends: list[tuple[str, float, float, bool]]) -> None:
    """Names each line at its end, skipping a label that would touch one
    already placed (the legend names every line anyway)."""
    fig.canvas.draw()
    renderer = fig.canvas.get_renderer()
    placed = []
    for name, x, y, died in ends:
        text = ax.annotate(
            name,
            (x, y),
            xytext=(16 if died else 8, 0),
            textcoords="offset points",
            color=COLORS[name],
            fontsize=10,
            fontweight="bold",
            va="center",
            bbox={"facecolor": SURFACE, "edgecolor": "none", "pad": 1.5},
            zorder=5,
        )
        box = text.get_window_extent(renderer).expanded(1.05, 1.3)
        if any(box.overlaps(other) for other in placed):
            text.remove()
        else:
            placed.append(box)


def _save(fig, path: Path) -> None:
    fig.savefig(path, dpi=DPI, facecolor=SURFACE, metadata={"Software": None})
    plt.close(fig)


def _line_chart(
    chart: Chart,
    results: list,
    waves: int,
    path: Path,
    ylabel: str,
    value,
    *,
    ylim: tuple[float, float | None] = (0, None),
    drawstyle: str = "default",
) -> None:
    """One line per strategy of `value(result, row)` by wave. A run that
    was lost ends in a cross on its last wave."""
    fig, ax = _new_axes(chart, waves)
    line_pt = LINE_PX * 72 / DPI
    ends = []
    for r in results:
        if not r.rows:
            continue
        xs = [row["wave"] for row in r.rows]
        ys = [value(r, row) for row in r.rows]
        ax.plot(
            xs,
            ys,
            color=COLORS[r.strategy],
            linewidth=line_pt,
            label=r.strategy,
            drawstyle=drawstyle,
        )
        if r.died_at is not None:
            ax.plot(
                [xs[-1]],
                [ys[-1]],
                marker="x",
                markersize=8,
                markeredgewidth=2,
                color=COLORS[r.strategy],
                linestyle="none",
            )
        ends.append((r.strategy, xs[-1], ys[-1], r.died_at is not None))
    ax.set_ylabel(ylabel, color=TEXT_SECONDARY, fontsize=12)
    ax.set_ylim(*ylim)
    ax.yaxis.set_major_formatter(lambda v, _pos: f"{v:,.0f}" if v >= 10 else f"{v:g}")
    _label_ends(fig, ax, ends)
    legend = ax.legend(
        loc="lower left",
        bbox_to_anchor=(0, 1.02),
        ncol=len(ends),
        frameon=False,
        fontsize=11,
        handlelength=1.6,
    )
    for text in legend.get_texts():
        text.set_color(TEXT)
    _save(fig, path)


def _threat_chart(waves: int, path: Path) -> None:
    fig, ax = _new_axes(THREAT, waves)
    ax.bar(range(1, waves + 1), threat_per_wave(waves), width=0.7, color=BAR)
    ax.set_ylabel("Enemy HP spawned per wave (HP)", color=TEXT_SECONDARY, fontsize=12)
    ax.yaxis.set_major_formatter(lambda v, _pos: f"{v:,.0f}")
    _save(fig, path)


def write_charts(results: list, waves: int, out: Path) -> list[Chart]:
    """Writes the four PNGs into `out` for `results` (RunResults: a
    `strategy`, `died_at` and `rows`) and returns their CHARTS entries."""
    out = Path(out)
    waves = max(waves, 2)
    plt.rcParams["font.family"] = "DejaVu Sans"  # matplotlib's own font
    threat = threat_per_wave(waves)

    def pressure(result, row) -> float:
        spent = _spent_total(row)
        assert spent > 0, f"{result.strategy}: nothing spent by wave {row['wave']}"
        return threat[row["wave"] - 1] / spent

    _line_chart(
        LIVES,
        results,
        waves,
        out / LIVES.file,
        "Lives left",
        lambda _r, row: row["lives"],
        ylim=(0, 10.5),
        drawstyle="steps-post",
    )
    _line_chart(
        INCOME,
        results,
        waves,
        out / INCOME.file,
        "Money earned per wave (coins)",
        lambda _r, row: row["earned"],
    )
    _threat_chart(waves, out / THREAT.file)
    _line_chart(
        PRESSURE,
        results,
        waves,
        out / PRESSURE.file,
        "Enemy HP per coin spent on towers (HP/coin)",
        pressure,
    )
    return CHARTS
