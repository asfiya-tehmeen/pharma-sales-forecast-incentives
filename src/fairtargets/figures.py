"""Static report figures (light mode PNGs for REPORT.md). Palette validated with the dataviz checker:
products = categorical slots 1-3 (blue, orange, aqua); easy/hard = diverging poles (blue, red).
Aqua is below 3:1 contrast on the surface, so every line carries a direct label.
"""
from __future__ import annotations

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

from .config import FIGURES, FLAG_DELTA  # noqa: E402

SURFACE, INK, INK2, GRID = "#fcfcfb", "#0b0b0b", "#52514e", "#e4e3df"
PRODUCT_COLOR = {"GLU": "#2a78d6", "SEM": "#eb6834", "CAR": "#1baf7a"}
PRODUCT_NAME = {"GLU": "Glucora", "SEM": "Semavia", "CAR": "Cardivex"}
EASY, HARD, NEUTRAL = "#2a78d6", "#e34948", "#a8a7a2"

plt.rcParams.update({
    "figure.facecolor": SURFACE, "axes.facecolor": SURFACE, "savefig.facecolor": SURFACE,
    "axes.edgecolor": GRID, "axes.labelcolor": INK2, "xtick.color": INK2, "ytick.color": INK2,
    "text.color": INK, "axes.grid": True, "grid.color": GRID, "grid.linewidth": 0.6,
    "axes.spines.top": False, "axes.spines.right": False, "font.size": 9,
    "axes.titlesize": 11, "axes.titleweight": "bold", "axes.titlelocation": "left",
})


def national_sales(panel: pd.DataFrame, cal: pd.DataFrame, stockouts: dict) -> str:
    nat = panel.groupby(["month_start", "product_code"]).value_net.sum().unstack() / 1e6
    fig, ax = plt.subplots(figsize=(8, 3.6))
    for _, r in cal[cal.ramadan_days > 0].iterrows():
        ax.axvspan(r.month_start, r.month_start + pd.offsets.MonthEnd(0), color="#f0efec", lw=0, zorder=0)
    for p in ("GLU", "SEM", "CAR"):
        ax.plot(nat.index, nat[p], color=PRODUCT_COLOR[p], lw=1.6, label=PRODUCT_NAME[p])
        ax.annotate(PRODUCT_NAME[p], (nat.index[-1], nat[p].iloc[-1]), xytext=(6, 0),
                    textcoords="offset points", va="center", color=INK, fontsize=8)
    for m in stockouts.get("SEM", []):
        ms = nat.index[m - 1]
        ax.plot(ms, nat.loc[ms, "SEM"], "o", ms=6, mfc=SURFACE, mec=PRODUCT_COLOR["SEM"], mew=1.6)
    ax.set_title("National net sales by product (SAR m), simulated", pad=12)
    ax.text(0, 1.01, "Shaded: months with Ramadan days. Open circles: detected Semavia stock-out months.",
            transform=ax.transAxes, color=INK2, fontsize=8)
    ax.set_ylabel("SAR million / month")
    ax.legend(frameon=False, loc="upper left", fontsize=8, ncols=3, bbox_to_anchor=(0, 0.97))
    ax.set_xlim(nat.index[0], nat.index[-1] + pd.DateOffset(months=3))
    fig.tight_layout()
    path = FIGURES / "01_national_sales.png"
    fig.savefig(path, dpi=160)
    plt.close(fig)
    return path.name


def wape_by_model(acc: pd.DataFrame) -> str:
    order = ["seasonal_naive", "ets", "lgbm_gregorian", "lgbm_hijri"]
    labels = {"seasonal_naive": "Seasonal naive", "ets": "ETS", "lgbm_gregorian": "LightGBM (Gregorian)",
              "lgbm_hijri": "LightGBM (Hijri-aware)"}
    fig, axes = plt.subplots(1, 3, figsize=(9, 2.8), sharey=True)
    for ax, p in zip(axes, ("GLU", "SEM", "CAR")):
        d = acc[acc.product_code == p].set_index("model").reindex(order)
        y = np.arange(len(order))
        ax.barh(y, d.wape * 100, color="#2a78d6", height=0.6)
        for yi, v in zip(y, d.wape * 100):
            ax.text(v + 0.8, yi, f"{v:.1f}%", va="center", fontsize=8, color=INK)
        ax.set_yticks(y, [labels[m] for m in order])
        ax.invert_yaxis()
        ax.set_title(PRODUCT_NAME[p], fontsize=10)
        ax.set_xlabel("WAPE, %")
        ax.grid(axis="y", visible=False)
        ax.set_xlim(0, max(d.wape * 100) * 1.3)
    fig.suptitle("Backtest WAPE by model and product (origins Dec-2024 to Oct-2025, 1-3 months ahead)",
                 x=0.01, ha="left", fontsize=10, fontweight="bold")
    fig.tight_layout()
    path = FIGURES / "02_wape_by_model.png"
    fig.savefig(path, dpi=160)
    plt.close(fig)
    return path.name


def target_percentiles(fair: pd.DataFrame) -> str:
    d = fair.sort_values("target_percentile").reset_index()
    med = d.target_percentile.median()
    fig, ax = plt.subplots(figsize=(8, 5.6))
    ax.axvspan((med - FLAG_DELTA) * 100, (med + FLAG_DELTA) * 100, color="#f0efec", lw=0, zorder=0)
    ax.axvline(med * 100, color=INK2, lw=0.8, ls="--")
    col = d.direction.map({"easy": EASY, "hard": HARD}).fillna(NEUTRAL)
    ax.scatter(d.target_percentile * 100, np.arange(len(d)), c=col, s=36, zorder=3,
               edgecolors=SURFACE, linewidths=1.2)
    for i, r in d.iterrows():
        if r.flag:
            ax.annotate(f"{r.territory_code} ({r.direction})", (r.target_percentile * 100, i),
                        xytext=(7, 0), textcoords="offset points", va="center", fontsize=7.5, color=INK)
    ax.set_yticks([])
    ax.set_xlim(-2, 102)
    ax.set_xlabel("Target percentile = estimated probability of MISSING the 2025 target (%)")
    ax.set_title("Where each issued 2025 target sits in its territory's forecast distribution", pad=12)
    ax.text(0, 1.01, f"Dashed: median territory. Shaded band: median +/- {int(FLAG_DELTA * 100)} pp "
            "(outside = flagged). Blue = easy, red = hard.", transform=ax.transAxes, color=INK2, fontsize=8)
    ax.grid(axis="y", visible=False)
    fig.tight_layout()
    path = FIGURES / "03_target_percentiles.png"
    fig.savefig(path, dpi=160)
    plt.close(fig)
    return path.name


def rule_comparison(costs: dict[str, np.ndarray], spread: dict[str, float]) -> str:
    names = {"issued": "As issued", "last_year_plus_x": "Last year + X%", "potential_based": "Potential-based"}
    rules = list(names)
    fig, (a1, a2) = plt.subplots(1, 2, figsize=(9, 2.6), sharey=True)
    y = np.arange(len(rules))
    for yi, r in zip(y, rules):
        c = costs[r]
        lo, mid, hi = np.percentile(c, [10, 50, 90])
        a1.plot([lo, hi], [yi, yi], color="#2a78d6", lw=2, solid_capstyle="round")
        a1.plot(mid, yi, "o", color="#2a78d6", ms=7, mec=SURFACE, mew=1.5)
        a1.text(hi + 1, yi, f"P50 {mid:.0f}%  (P10-P90 {lo:.0f}-{hi:.0f}%)", va="center", fontsize=8)
    a1.set_yticks(y, [names[r] for r in rules])
    a1.invert_yaxis()
    a1.set_xlabel("Total payout, % of on-target bonus budget")
    a1.set_title("Payout cost (10,000 simulated years)", fontsize=10)
    a1.grid(axis="y", visible=False)
    xmax = max(np.percentile(costs[r], 90) for r in rules)
    a1.set_xlim(min(np.percentile(costs[r], 10) for r in rules) - 5, xmax + 45)
    a2.barh(y, [spread[r] for r in rules], color="#2a78d6", height=0.55)
    for yi, r in zip(y, rules):
        a2.text(spread[r] + 0.8, yi, f"{spread[r]:.0f} pp", va="center", fontsize=8)
    a2.set_xlabel("IQR of target percentiles across territories (pp)")
    a2.set_title("Fairness spread (lower = fairer)", fontsize=10)
    a2.grid(axis="y", visible=False)
    a2.set_xlim(0, max(spread.values()) * 1.3)
    fig.tight_layout()
    path = FIGURES / "04_rule_comparison.png"
    fig.savefig(path, dpi=160)
    plt.close(fig)
    return path.name
