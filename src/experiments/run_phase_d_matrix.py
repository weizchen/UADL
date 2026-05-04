"""Phase D matrix runner: sweep (benchmark, arch, mode, opt_flag) with the
feedback loop and write all trace.json files into a single results directory.

Default sweep is the headline matrix:
  benchmarks: matmul, sort, vec_add, fibonacci
  isa:        rv32i
  archs:      small, large
  modes:      naive, brief, telemetry, both
  opt_flags:  -O0, -O3
  max_iters:  5

That's 4 * 2 * 4 * 2 = 64 traces, ≤320 LLM calls (≤5 per trace; many will plateau early).

Resumable: if a trace.json already exists for a given (bench, arch, mode, opt) under
--out, that combination is skipped. Use --force to re-run.

Usage:
  python run_phase_d_matrix.py
  python run_phase_d_matrix.py --benchmarks fibonacci sort --opt-flags -O0
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
import traceback
from datetime import datetime
from typing import List

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, SCRIPT_DIR)

from run_feedback_loop import run_loop, DEFAULT_MODEL  # noqa: E402

DEFAULT_BENCHMARKS = ["matmul", "sort", "vec_add", "fibonacci", "conv2d"]
DEFAULT_ARCHS = ["small", "large"]
DEFAULT_MODES = ["naive", "brief", "telemetry", "both"]
DEFAULT_OPT_FLAGS = ["-O0", "-O3"]


def _existing_trace(out_root: str, bench: str, isa: str, arch: str, mode: str, opt: str):
    """Return path to an already-written trace.json for this combination, or None."""
    if not os.path.isdir(out_root):
        return None
    suffix = f"_{bench}_{isa}_{arch}_{mode}_{opt.lstrip('-')}"
    for entry in sorted(os.listdir(out_root)):
        if entry.endswith(suffix):
            tp = os.path.join(out_root, entry, "trace.json")
            if os.path.exists(tp):
                return tp
    return None


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--isa", default="rv32i", choices=["rv32i", "rv32im", "armv7"])
    p.add_argument("--benchmarks", nargs="+", default=DEFAULT_BENCHMARKS)
    p.add_argument("--archs", nargs="+", default=DEFAULT_ARCHS)
    p.add_argument("--modes", nargs="+", default=DEFAULT_MODES,
                   choices=["naive", "brief", "telemetry", "both"])
    p.add_argument("--opt-flags", nargs="+", default=DEFAULT_OPT_FLAGS,
                   choices=["-O0", "-O1", "-O2", "-O3"])
    p.add_argument("--max-iters", type=int, default=5)
    p.add_argument("--model", default=DEFAULT_MODEL)
    p.add_argument("--out", default=os.path.join(SCRIPT_DIR, "results", "feedback"))
    p.add_argument("--force", action="store_true",
                   help="Re-run combinations even if a trace.json already exists.")
    args = p.parse_args()

    os.makedirs(args.out, exist_ok=True)
    log_path = os.path.join(args.out, f"matrix_log_{datetime.now().strftime('%Y%m%d_%H%M%S')}.jsonl")

    combos = []
    for bench in args.benchmarks:
        for arch in args.archs:
            for mode in args.modes:
                for opt in args.opt_flags:
                    combos.append((bench, arch, mode, opt))

    print(f"Sweep: {len(combos)} combinations  →  {args.out}")
    print(f"Log:   {log_path}")
    t_start = time.time()
    done = 0
    skipped = 0
    failed = 0

    for (bench, arch, mode, opt) in combos:
        existing = _existing_trace(args.out, bench, args.isa, arch, mode, opt)
        if existing and not args.force:
            print(f"[skip] {bench}/{arch}/{mode}/{opt} — trace exists ({os.path.dirname(existing)})")
            skipped += 1
            continue

        microarch = os.path.join(SCRIPT_DIR, "architectures", f"{arch}.yaml")
        print(f"\n{'=' * 60}\n[run] {bench}/{arch}/{mode}/{opt}\n{'=' * 60}")
        try:
            summary = run_loop(
                benchmark=bench,
                isa=args.isa,
                microarch_path=microarch,
                mode=mode,
                max_iters=args.max_iters,
                opt_flag=opt,
                model=args.model,
                out_root=args.out,
            )
            done += 1
            with open(log_path, "a") as f:
                f.write(json.dumps({
                    "ts": datetime.now().isoformat(timespec="seconds"),
                    "bench": bench, "arch": arch, "mode": mode, "opt": opt,
                    "baseline": summary["baseline_cycles"],
                    "best": summary["best_cycles"],
                    "speedup": summary["speedup"],
                    "best_iter": summary["best_iter"],
                }) + "\n")
        except Exception as e:
            failed += 1
            print(f"[fail] {bench}/{arch}/{mode}/{opt}: {e}")
            traceback.print_exc()
            with open(log_path, "a") as f:
                f.write(json.dumps({
                    "ts": datetime.now().isoformat(timespec="seconds"),
                    "bench": bench, "arch": arch, "mode": mode, "opt": opt,
                    "error": str(e),
                }) + "\n")

    elapsed = time.time() - t_start
    print(f"\n{'=' * 60}")
    print(f"Matrix done in {elapsed/60:.1f} min — {done} ran, {skipped} skipped, {failed} failed")
    print(f"Aggregate with: python summarize_phase_d.py {args.out}")


if __name__ == "__main__":
    main()
