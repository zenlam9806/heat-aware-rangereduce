"""Builds the results figures and LaTeX tables from experiments/results (summary.csv and raw run logs)."""
import pathlib
import sys

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

REPORT = pathlib.Path(__file__).resolve().parent.parent
FIG = REPORT / "figures"
TAB = REPORT / "tables"
FIG.mkdir(exist_ok=True)
TAB.mkdir(exist_ok=True)
RESULTS = pathlib.Path(sys.argv[1]).expanduser() if len(sys.argv) > 1 else pathlib.Path.home() / "experiments/results"
MAIN_HEAT = sys.argv[2] if len(sys.argv) > 2 else "heat_rel_1.0"
ENTRY = 128
MB = 2**20

plt.rcParams.update({
    "font.family": "serif", "mathtext.fontset": "cm", "font.size": 7.5,
    "axes.labelsize": 7.5, "xtick.labelsize": 7, "ytick.labelsize": 7, "legend.fontsize": 7,
    "axes.spines.top": False, "axes.spines.right": False, "axes.linewidth": 0.6,
    "xtick.major.width": 0.6, "ytick.major.width": 0.6, "grid.linewidth": 0.4,
})
COLORS = {"rocksdb": "#8c8c8c", "rangereduce": "#d9822b", "ha-rr": "#1f6fb5"}
LABELS = {"rocksdb": "RocksDB", "rangereduce": "RangeReduce", "ha-rr": "HA-RR (ours)"}
WORKLOADS = {"uniform": "Uniform", "hotcold": "Hot/cold", "shifting": "Shifting"}


def load():
    df = pd.read_csv(RESULTS / "summary.csv")
    df = df[df["workload"].str.startswith("main_")].copy()
    df["pattern"] = df["workload"].str.replace("main_", "", regex=False)
    keep = df["system"].isin(["rocksdb", "rangereduce", MAIN_HEAT])
    df = df[keep].copy()
    df["sys"] = df["system"].map(lambda s: "ha-rr" if s.startswith("heat") else s)
    base = df[df["sys"] == "rocksdb"].set_index("pattern")["rq_entries_read"]
    df["saved_read_bytes"] = (df["pattern"].map(base) - df["rq_entries_read"]) * ENTRY
    df["wb_efficiency"] = np.where(df["rr_write_bytes"] > 0,
                                   df["saved_read_bytes"] / df["rr_write_bytes"].replace(0, np.nan), np.nan)
    return df


def save(fig, name):
    fig.savefig(FIG / f"{name}.pdf", bbox_inches="tight", pad_inches=0.02)
    fig.savefig(FIG / f"{name}.png", bbox_inches="tight", pad_inches=0.02, dpi=200)
    plt.close(fig)


def patterns_of(df):
    return [p for p in WORKLOADS if p in set(df["pattern"])]


def bars(ax, df, column, scale=1.0, ylabel="", fmt="{:.0f}", systems=None, ylim0=None):
    pats = patterns_of(df)
    systems = systems or [s for s in COLORS if s in set(df["sys"])]
    width = 0.8 / len(systems)
    x = np.arange(len(pats))
    top = 0
    for i, s in enumerate(systems):
        vals = [df[(df["pattern"] == p) & (df["sys"] == s)][column].mean() * scale for p in pats]
        pos = x + (i - (len(systems) - 1) / 2) * width
        ax.bar(pos, vals, width * 0.92, color=COLORS[s], label=LABELS[s], edgecolor="white", linewidth=0.3)
        for xp, v in zip(pos, vals):
            if not np.isnan(v):
                ax.annotate(fmt.format(v), (xp, v), xytext=(0, 1.5), textcoords="offset points",
                            ha="center", va="bottom", fontsize=5.0, rotation=90)
                top = max(top, v)
    ax.set_xticks(x, [WORKLOADS[p] for p in pats])
    ax.set_ylabel(ylabel)
    ax.grid(axis="y", alpha=0.4)
    ax.set_axisbelow(True)
    lo = ylim0 if ylim0 is not None else 0
    if top:
        ax.set_ylim(lo, lo + (top - lo) * 1.32)


def legend_top(fig, ax):
    handles, labels = ax.get_legend_handles_labels()
    fig.legend(handles, labels, frameon=False, ncol=len(labels), loc="upper center", bbox_to_anchor=(0.5, 1.11))


def fig_latency(df):
    fig, axes = plt.subplots(1, 3, figsize=(7.0, 1.85))
    bars(axes[0], df, "rq_mean_ms", ylabel="mean latency (ms)")
    bars(axes[1], df, "rq_p95_ms", ylabel="P95 latency (ms)")
    bars(axes[2], df, "rq_read_amp", ylabel="read amplification", fmt="{:.3f}", ylim0=1.0)
    for ax, t in zip(axes, ["(a) Mean range query latency", "(b) Tail (P95) latency", "(c) Entries read per entry returned"]):
        ax.set_title(t, fontsize=7.5)
    fig.subplots_adjust(wspace=0.42)
    legend_top(fig, axes[0])
    save(fig, "latency_ra")


def fig_writes(df):
    fig, axes = plt.subplots(1, 3, figsize=(7.0, 1.9))
    pats = patterns_of(df)
    systems = [s for s in COLORS if s in set(df["sys"])]
    width = 0.8 / len(systems)
    x = np.arange(len(pats))
    parts = [("flush_write_bytes", "flush", 1.0), ("compact_write_bytes", "compaction", 0.55),
             ("rr_write_bytes", "query write-back", 0.25)]
    for i, s in enumerate(systems):
        pos = x + (i - (len(systems) - 1) / 2) * width
        bottom = np.zeros(len(pats))
        for col, name, alpha in parts:
            vals = np.array([df[(df["pattern"] == p) & (df["sys"] == s)][col].mean() / MB for p in pats])
            axes[0].bar(pos, vals, width * 0.92, bottom=bottom, color=COLORS[s], alpha=alpha,
                        edgecolor="white", linewidth=0.3, hatch="////" if col == "rr_write_bytes" else None)
            bottom += vals
    axes[0].set_xticks(x, [WORKLOADS[p] for p in pats])
    axes[0].set_ylabel("bytes written (MB)")
    axes[0].grid(axis="y", alpha=0.4)
    axes[0].set_axisbelow(True)
    axes[0].set_ylim(0, axes[0].get_ylim()[1] * 1.08)
    bars(axes[1], df, "rr_write_bytes", 1 / MB, ylabel="query write-back (MB)", systems=["rangereduce", "ha-rr"])
    bars(axes[2], df, "wb_efficiency", ylabel="read bytes saved per\nbyte written back", fmt="{:.2f}",
         systems=["rangereduce", "ha-rr"])
    axes[2].axhline(1.0, color="#555555", linestyle=":", linewidth=0.7)
    for ax, t in zip(axes, ["(a) Writes by source", "(b) Query-driven write-back", "(c) Write-back efficiency"]):
        ax.set_title(t, fontsize=7.5)
    fig.subplots_adjust(wspace=0.45)
    handles = [plt.Rectangle((0, 0), 1, 1, color=COLORS[s]) for s in systems]
    handles += [plt.Rectangle((0, 0), 1, 1, facecolor="white", edgecolor="#444444", hatch="////")]
    fig.legend(handles, [LABELS[s] for s in systems] + ["write-back part"], frameon=False,
               ncol=len(handles), loc="upper center", bbox_to_anchor=(0.5, 1.11))
    save(fig, "writes")


def fig_space_debt(df):
    fig, axes = plt.subplots(1, 2, figsize=(5.4, 1.85))
    bars(axes[0], df, "space_amp", ylabel="space amplification", fmt="{:.3f}", ylim0=1.0)
    bars(axes[1], df, "compaction_debt_bytes", 1 / MB, ylabel="compaction debt (MB)")
    for ax, t in zip(axes, ["(a) Space amplification", "(b) Compaction debt"]):
        ax.set_title(t, fontsize=7.5)
    fig.subplots_adjust(wspace=0.38)
    legend_top(fig, axes[0])
    save(fig, "space_debt")


def fig_timeline():
    wdir = RESULTS / "main_shifting"
    if not (wdir / "rocksdb" / "range_queries.csv").exists():
        return
    fig, ax = plt.subplots(figsize=(3.45, 1.75))
    for name, key in [("rocksdb", "rocksdb"), ("rangereduce", "rangereduce"), (MAIN_HEAT, "ha-rr")]:
        f = wdir / name / "range_queries.csv"
        if f.exists():
            rq = pd.read_csv(f, skipinitialspace=True)
            s = (rq["RQ Total Time"] / 1e6).rolling(40, min_periods=10).median()
            ax.plot(np.arange(1, len(s) + 1), s, color=COLORS[key], label=LABELS[key], linewidth=0.9)
    n = sum(1 for _ in open(wdir / "rocksdb" / "range_queries.csv")) - 1
    for k in (1, 2):
        ax.axvline(n * k / 3, color="#555555", linestyle=":", linewidth=0.7)
    ax.set_xlabel("range query number")
    ax.set_ylabel("latency, rolling\nmedian (ms)")
    ax.grid(alpha=0.4)
    ax.legend(frameon=False, ncol=3, loc="upper center", bbox_to_anchor=(0.5, 1.22))
    save(fig, "timeline_shifting")


def fig_sensitivity():
    rows = pd.read_csv(RESULTS / "summary.csv")
    rows = rows[rows["workload"] == "main_hotcold"]
    heat = rows[rows["system"].str.startswith("heat_rel")].copy()
    if len(heat) < 2:
        return
    heat["theta"] = heat["system"].str.split("_").str[-1].astype(float)
    heat = heat.sort_values("theta")
    rr = rows[rows["system"] == "rangereduce"].iloc[0]
    base = rows[rows["system"] == "rocksdb"].iloc[0]
    rr_saved = (base["rq_entries_read"] - rr["rq_entries_read"])
    fig, ax = plt.subplots(figsize=(3.45, 1.85))
    ax.plot(heat["theta"], heat["rr_write_bytes"] / rr["rr_write_bytes"], marker="o", markersize=3,
            color=COLORS["ha-rr"], label="write-back", linewidth=0.9)
    ax.plot(heat["theta"], (base["rq_entries_read"] - heat["rq_entries_read"]) / rr_saved, marker="s",
            markersize=3, color="#2a9d8f", label="read savings", linewidth=0.9)
    ax.plot(heat["theta"], heat["rq_mean_ms"] / rr["rq_mean_ms"], marker="^", markersize=3,
            color="#6c757d", label="mean latency", linewidth=0.9)
    ax.axhline(1.0, color=COLORS["rangereduce"], linestyle="--", linewidth=0.7)
    ax.text(heat["theta"].min(), 1.03, "RangeReduce = 1", color=COLORS["rangereduce"], fontsize=6, ha="left", va="bottom")
    ax.set_ylim(0, 1.25)
    ax.set_xlabel(r"admission threshold $\theta$")
    ax.set_ylabel("relative to RangeReduce")
    ax.set_xticks(heat["theta"])
    ax.grid(alpha=0.4)
    ax.legend(frameon=False, ncol=3, loc="upper center", bbox_to_anchor=(0.5, 1.2))
    save(fig, "sensitivity_theta")


def latex_table(df):
    pats = patterns_of(df)
    lines = [r"\begin{tabular}{@{}llrrrrrrrr@{}}", r"\toprule",
             r"Workload & System & Mean & P95 & RA & Write-back & Total writes & SA & Debt & Efficiency \\",
             r" & & (ms) & (ms) & & (MB) & (MB) & & (MB) & \\", r"\midrule"]
    for p in pats:
        first = True
        for s in COLORS:
            r = df[(df["pattern"] == p) & (df["sys"] == s)]
            if r.empty:
                continue
            r = r.iloc[0]
            eff = "--" if np.isnan(r["wb_efficiency"]) else f"{r['wb_efficiency']:.2f}"
            lines.append(
                f"{WORKLOADS[p] if first else ''} & {LABELS[s]} & {r['rq_mean_ms']:.0f} & {r['rq_p95_ms']:.0f} & "
                f"{r['rq_read_amp']:.3f} & {r['rr_write_bytes'] / MB:.0f} & {r['total_write_bytes'] / MB:.0f} & "
                f"{r['space_amp']:.3f} & {r['compaction_debt_bytes'] / MB:.0f} & {eff} \\\\")
            first = False
        lines.append(r"\midrule" if p != pats[-1] else r"\bottomrule")
    lines.append(r"\end{tabular}")
    (TAB / "main_results.tex").write_text("\n".join(lines) + "\n")


def main():
    df = load()
    fig_latency(df)
    fig_writes(df)
    fig_space_debt(df)
    fig_timeline()
    fig_sensitivity()
    latex_table(df)
    df.to_csv(TAB / "main_results.csv", index=False)
    print("figures:", sorted(p.name for p in FIG.glob("*.pdf")))


if __name__ == "__main__":
    main()
