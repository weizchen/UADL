"""Phase D: join per-PC simulator telemetry with DWARF source lines.

Produces a compact text report grouping counters by source line, ranked by
cycle attribution. Intended to be pasted directly into an LLM prompt as the
feedback signal in run_feedback_loop.py.

Inputs:
  - <bin>.telem.json   (emitted by sim_universal.j2)
  - <bin>.symtab.json  (emitted by elf2mem.py from DWARF)
  - source file path (used to inline the actual code line for context)

Output:
  - structured dict for programmatic use
  - render() returns a string suitable for an LLM prompt
"""
from __future__ import annotations

import json
import os
import sys
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple


@dataclass
class LineStats:
    file: str
    line: int
    dispatched: int = 0
    stall_cycles: int = 0
    flushes: int = 0
    mem_accesses: int = 0
    cache_misses: int = 0
    pcs: List[str] = field(default_factory=list)

    @property
    def approx_cycles(self) -> int:
        # Rough approximation: each dispatched insn = 1 base cycle + its stalls
        # + (branch flush penalty implicitly captured in stall accounting elsewhere).
        # We don't have per-PC cycles directly, but dispatched + stalls is a fair proxy
        # for "how much time was spent on this line."
        return self.dispatched + self.stall_cycles


def join(telemetry: dict, symtab: dict, source_root: Optional[str] = None) -> Dict[Tuple[str, int], LineStats]:
    """Aggregate per-PC counters into per-(file, line) stats."""
    by_line: Dict[Tuple[str, int], LineStats] = {}
    for pc_hex, counters in telemetry.get("per_pc", {}).items():
        loc = symtab.get(pc_hex)
        if not loc:
            continue
        fname, lineno = loc[0], int(loc[1])
        if lineno == 0:
            # DWARF line 0 means "no source" — skip.
            continue
        if source_root:
            fname = os.path.relpath(fname, source_root) if os.path.isabs(fname) else fname
        key = (fname, lineno)
        ls = by_line.get(key)
        if ls is None:
            ls = LineStats(file=fname, line=lineno)
            by_line[key] = ls
        ls.dispatched += counters.get("dispatched", 0)
        ls.stall_cycles += counters.get("stall_cycles", 0)
        ls.flushes += counters.get("flushes", 0)
        ls.mem_accesses += counters.get("mem_accesses", 0)
        ls.cache_misses += counters.get("cache_misses", 0)
        ls.pcs.append(pc_hex)
    return by_line


def _read_source_line(path: str, lineno: int) -> str:
    try:
        with open(path) as f:
            for i, line in enumerate(f, start=1):
                if i == lineno:
                    return line.rstrip("\n")
    except OSError:
        pass
    return ""


def render(
    telemetry_path: str,
    symtab_path: str,
    source_path: Optional[str] = None,
    top_n: int = 8,
) -> str:
    """Produce an LLM-friendly digest. Pass `source_path` to inline code text."""
    with open(telemetry_path) as f:
        telemetry = json.load(f)
    with open(symtab_path) as f:
        symtab = json.load(f)

    summary = telemetry.get("summary", {})
    by_line = join(telemetry, symtab)

    # Pick the source file most represented (we expect one user .c per run).
    if source_path is None and by_line:
        # Most-attributed file:
        file_cycles: Dict[str, int] = defaultdict(int)
        for ls in by_line.values():
            file_cycles[ls.file] += ls.approx_cycles
        source_path = max(file_cycles, key=file_cycles.get)

    lines = []
    lines.append("=== Simulator Telemetry ===")
    lines.append(
        f"Total cycles: {summary.get('cycles', '?')}, "
        f"instructions: {summary.get('instructions', '?')}, "
        f"stalls: {summary.get('stalls', '?')}, "
        f"flushes: {summary.get('flushes', '?')}"
    )
    caches = summary.get("caches", {})
    if caches:
        cache_strs = []
        for name, c in caches.items():
            total = c.get("hits", 0) + c.get("misses", 0)
            rate = (100.0 * c.get("hits", 0) / total) if total else 0.0
            cache_strs.append(
                f"{name}: {c.get('hits',0)} hits / {c.get('misses',0)} misses ({rate:.0f}% hit)"
            )
        lines.append("Cache: " + "; ".join(cache_strs))

    if not by_line:
        lines.append("(no per-line attribution — DWARF symtab missing or empty)")
        return "\n".join(lines)

    # Rank by approx cycles (dispatched + stalls). Pull top N.
    ranked = sorted(by_line.values(), key=lambda l: l.approx_cycles, reverse=True)[:top_n]

    lines.append("")
    lines.append(f"--- Hottest source lines (top {len(ranked)}) ---")
    lines.append(
        f"{'cycles~':>8}  {'insns':>6}  {'stalls':>6}  {'flushes':>7}  {'misses':>6}  source"
    )
    for ls in ranked:
        code = _read_source_line(ls.file, ls.line) if source_path else ""
        # Trim long source lines to keep prompt budget under control.
        if len(code) > 80:
            code = code[:77] + "..."
        lines.append(
            f"{ls.approx_cycles:>8}  {ls.dispatched:>6}  {ls.stall_cycles:>6}  "
            f"{ls.flushes:>7}  {ls.cache_misses:>6}  L{ls.line:<4}  {code}"
        )

    return "\n".join(lines)


if __name__ == "__main__":
    import argparse

    p = argparse.ArgumentParser(description="Annotate per-PC telemetry with DWARF source lines.")
    p.add_argument("telemetry", help="path to <bin>.telem.json")
    p.add_argument("symtab", help="path to <bin>.symtab.json")
    p.add_argument("--top", type=int, default=8, help="how many hot lines to report")
    p.add_argument("--source", help="path to the source file (default: inferred)")
    args = p.parse_args()

    print(render(args.telemetry, args.symtab, source_path=args.source, top_n=args.top))
