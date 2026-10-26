"""Figures for the full-size experiments, drawn directly from the raw run logs.

Usage:  python3 analysis/plot_fullscale.py [results/fullscale] [output_dir]
Writes (as .pdf and .png):
  fs_latency   mean, P95 and P99 latency and read amplification per workload
  fs_writes    write-back bytes, total bytes written, write-back efficiency (eta) and compaction debt
  fs_cdf       latency distribution (CDF) per workload
  fs_timeline  rolling median latency over the run, per workload
  fs_heat      share of range queries HA-RR admitted over the run
"""
import csv
import pathlib
import sys

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import fullscale as fs  # noqa: E402

ROOT = pathlib.Path(sys.argv[1]) if len(sys.argv) > 1 else pathlib.Path(__file__).resolve().parent.parent / "results" / "fullscale"
OUT = pathlib.Path(sys.argv[2]) if len(sys.argv) > 2 else pathlib.Path(__file__).resolve().parent.parent / "figures"
OUT.mkdir(parents=True, exist_ok=True)
plt.rcParams.update({"font.family": "serif", "font.size": 7.5, "axes.spines.top": False, "axes.spines.right": False,
                     "axes.titlesize": 7.8, "xtick.labelsize": 6.0, "ytick.labelsize": 6.8, "axes.labelsize": 7.2})
COL = {"RocksDB": "#8c8c8c", "RangeReduce": "#d9822b", "HA-RR": "#1f6fb5", "HA-RR_theta2": "#7fb3e0"}
HATCH = {"RocksDB": "", "RangeReduce": "", "HA-RR": "", "HA-RR_theta2": "////"}
LABEL = {"RocksDB": "RocksDB", "RangeReduce": "RangeReduce", "HA-RR": "HA-RR ($\\theta$ = 1)",
         "HA-RR_theta2": "HA-RR ($\\theta$ = 2)"}
LS = {"RocksDB": ":", "RangeReduce": "--", "HA-RR": "-", "HA-RR_theta2": "-."}


def done(run):
    log = run / "workload.log"
    return (run / "range_queries.csv").exists() and log.exists() and "END HERE" in log.read_text(errors="ignore")


runs = {}
for s in fs.SETTINGS:
    for name in fs.SYSTEMS:
        run = ROOT / s / name
        if done(run):
            runs[(s, name)] = fs.summarise(run)
systems = [n for n in fs.SYSTEMS if any((s, n) in runs for s in fs.SETTINGS)]
settings = [s for s in fs.SETTINGS if any((s, n) in runs for n in systems)]

# eta needs the paired RocksDB run of the same workload
for s in settings:
    if (s, "RocksDB") not in runs:
        continue
    base = runs[(s, "RocksDB")][1]
    for n in systems:
        if n != "RocksDB" and (s, n) in runs:
            row, q = runs[(s, n)]
            saved = sum(b["read"] - r["read"] for b, r in zip(base, q)) * fs.ENTRY
            row["eta"] = saved / (row["writeback_GB"] * fs.GB) if row["writeback_GB"] else 0.0


def save(fig, name):
    fig.savefig(OUT / f"{name}.pdf", bbox_inches="tight", pad_inches=0.02)
    fig.savefig(OUT / f"{name}.png", bbox_inches="tight", pad_inches=0.02, dpi=300)
    plt.close(fig)


def legend(fig, ncol=None):
    handles = [plt.Rectangle((0, 0), 1, 1, facecolor=COL[n], hatch=HATCH[n], edgecolor="white") for n in systems]
    fig.legend(handles, [LABEL[n] for n in systems], ncol=ncol or len(systems), frameon=False,
               loc="upper center", bbox_to_anchor=(0.5, 1.07), fontsize=7.2)


def bars(ax, key, title, fmt="{:.2f}", skip=()):
    shown = [n for n in systems if n not in skip]
    w = 0.84 / len(shown)
    top = 0
    for i, n in enumerate(shown):
        for j, s in enumerate(settings):
            if (s, n) not in runs:
                continue
            x = j + (i - (len(shown) - 1) / 2) * w
            y = runs[(s, n)][0].get(key) or 0.0
            top = max(top, y)
            ax.bar(x, y, w, color=COL[n], hatch=HATCH[n], edgecolor="white", linewidth=0.3)
            ax.text(x, y, fmt.format(y), ha="center", va="bottom", fontsize=4.6, rotation=90)
    ax.set_xticks(range(len(settings)), [fs.NAMES[s] for s in settings], fontsize=5.6)
    ax.set_xlim(-0.55, len(settings) - 0.45)
    ax.set_ylim(0, top * 1.28)
    ax.set_title(title)


# 1. Latency and read amplification
fig, axs = plt.subplots(1, 4, figsize=(7.16, 1.45))
bars(axs[0], "mean_s", "(a) Mean latency (s)")
bars(axs[1], "p95_s", "(b) P95 latency (s)")
bars(axs[2], "p99_s", "(c) P99 latency (s)", fmt="{:.1f}")
bars(axs[3], "read_amp", "(d) Read amplification", fmt="{:.3f}")
axs[3].set_ylim(1.0, 1.24)
legend(fig)
fig.tight_layout(w_pad=0.6)
save(fig, "fs_latency")

# 2. Writes and their value
fig, axs = plt.subplots(1, 4, figsize=(7.16, 1.45))
bars(axs[0], "writeback_GB", "(a) Write-back (GB)", fmt="{:.1f}")
bars(axs[1], "total_write_GB", "(b) Total bytes written (GB)", fmt="{:.1f}")
bars(axs[2], "eta", "(c) Reads saved per byte written", fmt="{:.1f}", skip=("RocksDB",))
bars(axs[3], "debt_GB", "(d) Compaction debt (GB)", fmt="{:.1f}")
legend(fig)
fig.tight_layout(w_pad=0.6)
save(fig, "fs_writes")

# 3. Latency distribution
fig, axs = plt.subplots(1, len(settings), figsize=(7.16, 1.4), sharey=True)
for j, s in enumerate(settings):
    for n in systems:
        if (s, n) not in runs:
            continue
        lat = sorted(r["ns"] / 1e9 for r in runs[(s, n)][1])
        ys = [100 * (i + 1) / len(lat) for i in range(len(lat))]
        axs[j].plot(lat, ys, color=COL[n], ls=LS[n], lw=1.0, label=LABEL[n])
    axs[j].set_xlim(0, 14)
    axs[j].set_title(f"({'abcd'[j]}) {fs.NAMES[s]}")
    axs[j].set_xlabel("latency (s)")
    axs[j].grid(alpha=0.25, lw=0.4)
axs[0].set_ylabel("queries (%)")
fig.legend(*axs[1].get_legend_handles_labels(), ncol=len(systems), frameon=False, loc="upper center",
           bbox_to_anchor=(0.5, 1.07), fontsize=7.2)
fig.tight_layout(w_pad=0.6)
save(fig, "fs_cdf")

# 4. Rolling median latency over the run
fig, axs = plt.subplots(1, len(settings), figsize=(7.16, 1.4), sharey=True)
k = 300
for j, s in enumerate(settings):
    for n in systems:
        if (s, n) not in runs:
            continue
        lat = [r["ns"] / 1e9 for r in runs[(s, n)][1]]
        starts = range(0, len(lat) - k, 25)
        axs[j].plot([i + k // 2 for i in starts], [sorted(lat[i:i + k])[k // 2] for i in starts],
                    color=COL[n], ls=LS[n], lw=0.9, label=LABEL[n])
    if s == "s3_shifting":
        for m in (3000, 6000):
            axs[j].axvline(m, color="black", lw=0.5, ls=":")
    axs[j].set_title(f"({'abcd'[j]}) {fs.NAMES[s]}")
    axs[j].set_xlabel("range query number")
    axs[j].set_xticks([0, 3000, 6000, 9000], ["0", "3k", "6k", "9k"])
axs[0].set_ylabel("median latency (s)")
fig.legend(*axs[1].get_legend_handles_labels(), ncol=len(systems), frameon=False, loc="upper center",
           bbox_to_anchor=(0.5, 1.07), fontsize=7.2)
fig.tight_layout(w_pad=0.6)
save(fig, "fs_timeline")

# 5. HA-RR admission over the run
fig, ax = plt.subplots(figsize=(3.45, 1.2))
k = 500
for s in settings:
    for n in ("HA-RR", "HA-RR_theta2"):
        f = ROOT / s / n / "heat.csv"
        if (s, n) not in runs or not f.exists():
            continue
        adm = [int(r["admitted"]) for r in csv.DictReader(open(f))]
        starts = range(0, len(adm) - k, 50)
        ax.plot([i + k // 2 for i in starts], [100 * sum(adm[i:i + k]) / k for i in starts], lw=0.9,
                ls="--" if n == "HA-RR_theta2" else "-",
                label=fs.NAMES[s] + (", $\\theta$ = 2" if n == "HA-RR_theta2" else ""))
ax.set_xlabel("range query number")
ax.set_ylabel("admitted (% of last 500)")
ax.set_xticks([0, 3000, 6000, 9000], ["0", "3k", "6k", "9k"])
ax.set_ylim(0, 105)
ax.legend(frameon=False, fontsize=5.8, ncol=2, loc="lower left")
fig.tight_layout()
save(fig, "fs_heat")
print("wrote", sorted(p.name for p in OUT.glob("fs_*.png")))
