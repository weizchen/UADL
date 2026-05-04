"""Phase D summarizer: aggregate trace.json files into tables and plots.

Outputs (relative to results dir):
  phase_d_summary.csv      one row per (bench, arch, mode, opt)
  phase_d_summary.md       paper-ready markdown table
  phase_d_convergence.png  cycles-vs-iteration curves, faceted by benchmark

Usage:
  python summarize_phase_d.py [results/feedback]
"""
from __future__ import annotations

import csv
import json
import os
import sys
from collections import defaultdict
from typing import Dict, List


def _load_traces(root: str) -> List[dict]:
    out = []
    if not os.path.isdir(root):
        return out
    for entry in sorted(os.listdir(root)):
        tp = os.path.join(root, entry, "trace.json")
        if os.path.exists(tp):
            try:
                with open(tp) as f:
                    out.append(json.load(f))
            except (json.JSONDecodeError, OSError):
                pass
    return out


def _key(t: dict) -> tuple:
    return (t["benchmark"], t["isa"], t["microarch"], t["mode"], t["opt_flag"])


def write_csv(traces: List[dict], path: str):
    fields = [
        "benchmark", "isa", "microarch", "mode", "opt_flag", "model",
        "baseline_cycles", "best_cycles", "speedup", "best_iter", "iters_run",
    ]
    with open(path, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        for t in traces:
            w.writerow({
                "benchmark": t["benchmark"],
                "isa": t["isa"],
                "microarch": t["microarch"],
                "mode": t["mode"],
                "opt_flag": t["opt_flag"],
                "model": t.get("model", ""),
                "baseline_cycles": t["baseline_cycles"],
                "best_cycles": t["best_cycles"],
                "speedup": f"{t['speedup']:.2f}",
                "best_iter": t["best_iter"],
                "iters_run": len(t["iterations"]) - 1,
            })
    print(f"  wrote {path}")


def write_markdown(traces: List[dict], path: str):
    """One table per (opt_flag, isa). Columns = modes. Rows = (bench, arch).
    Cell shows speedup over the in-cell baseline (same opt_flag)."""
    by_grp: Dict[tuple, Dict[tuple, Dict[str, dict]]] = defaultdict(lambda: defaultdict(dict))
    for t in traces:
        grp = (t["isa"], t["opt_flag"])
        row = (t["benchmark"], t["microarch"])
        by_grp[grp][row][t["mode"]] = t

    lines = ["# Phase D Summary", ""]
    for (isa, opt), rows in sorted(by_grp.items()):
        lines.append(f"## ISA={isa}, {opt}")
        lines.append("")
        modes = ["naive", "brief", "telemetry", "both"]
        header = "| Benchmark | Arch | Baseline cyc | " + " | ".join(
            f"{m} (×)" for m in modes
        ) + " |"
        sep = "|" + "|".join(["---"] * (3 + len(modes))) + "|"
        lines.append(header)
        lines.append(sep)
        for row_key in sorted(rows.keys()):
            bench, arch = row_key
            cells = [bench, arch]
            traces_in_row = rows[row_key]
            baseline_cycles = next(
                (t["baseline_cycles"] for t in traces_in_row.values()), None
            )
            cells.append(str(baseline_cycles) if baseline_cycles else "—")
            for m in modes:
                t = traces_in_row.get(m)
                cells.append(f"{t['speedup']:.2f}" if t else "—")
            lines.append("| " + " | ".join(cells) + " |")
        lines.append("")

    with open(path, "w") as f:
        f.write("\n".join(lines))
    print(f"  wrote {path}")


def write_convergence_plot(traces: List[dict], path: str):
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
    except ImportError:
        print("  matplotlib not available; skipping plot")
        return

    # One subplot per benchmark; lines = modes; one panel per (arch, opt).
    benches = sorted({t["benchmark"] for t in traces})
    archs = sorted({t["microarch"] for t in traces})
    opts = sorted({t["opt_flag"] for t in traces})
    panels = [(a, o) for a in archs for o in opts]
    if not benches or not panels:
        return

    fig, axes = plt.subplots(
        len(panels), len(benches),
        figsize=(3.5 * len(benches), 2.6 * len(panels)),
        squeeze=False, sharey=False,
    )
    mode_colors = {"naive": "#888", "brief": "#1f77b4", "telemetry": "#ff7f0e", "both": "#2ca02c"}

    for r, (arch, opt) in enumerate(panels):
        for c, bench in enumerate(benches):
            ax = axes[r][c]
            relevant = [t for t in traces
                        if t["benchmark"] == bench and t["microarch"] == arch and t["opt_flag"] == opt]
            for t in relevant:
                xs = [it["iter"] for it in t["iterations"]]
                ys = [it["metrics"].get("cycles") if isinstance(it["metrics"], dict) else None
                      for it in t["iterations"]]
                # Replace None / errors with NaN to skip plotting them.
                xy = [(x, y) for x, y in zip(xs, ys) if isinstance(y, int)]
                if not xy:
                    continue
                xs2, ys2 = zip(*xy)
                ax.plot(xs2, ys2, marker="o", color=mode_colors.get(t["mode"], "k"),
                        label=t["mode"], linewidth=1.5, markersize=4)
            ax.set_title(f"{bench}\n{arch} / {opt}", fontsize=9)
            ax.set_yscale("log")
            ax.grid(True, alpha=0.3)
            if r == len(panels) - 1:
                ax.set_xlabel("iteration")
            if c == 0:
                ax.set_ylabel("cycles (log)")

    # One legend for the whole figure.
    handles, labels = axes[0][0].get_legend_handles_labels()
    if handles:
        # Dedup labels.
        seen = {}
        for h, l in zip(handles, labels):
            seen.setdefault(l, h)
        fig.legend(list(seen.values()), list(seen.keys()),
                   loc="upper center", bbox_to_anchor=(0.5, 0.0),
                   ncol=len(seen), frameon=False, fontsize=9)

    fig.tight_layout()
    fig.savefig(path, dpi=150, bbox_inches="tight")
    plt.close(fig)
    print(f"  wrote {path}")


def main():
    root = sys.argv[1] if len(sys.argv) > 1 else os.path.join(
        os.path.dirname(os.path.abspath(__file__)), "results", "feedback"
    )
    if not os.path.isdir(root):
        sys.exit(f"results dir not found: {root}")

    traces = _load_traces(root)
    if not traces:
        sys.exit(f"no trace.json files under {root}")
    print(f"loaded {len(traces)} traces from {root}")

    out_dir = os.path.dirname(root.rstrip("/")) if os.path.basename(root.rstrip("/")) == "feedback" else root
    csv_path = os.path.join(out_dir, "phase_d_summary.csv")
    md_path = os.path.join(out_dir, "phase_d_summary.md")
    plot_path = os.path.join(out_dir, "phase_d_convergence.png")

    write_csv(traces, csv_path)
    write_markdown(traces, md_path)
    write_convergence_plot(traces, plot_path)


if __name__ == "__main__":
    main()
