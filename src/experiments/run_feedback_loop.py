"""Phase D: Closed-loop UADL-aware code optimization with telemetry feedback.

For each (benchmark, isa, microarch, mode), this driver:
  iter 0: compile baseline C, run sim, collect cycles + telemetry
  iter k: prompt LLM with (current C, telemetry, arch brief depending on mode)
          → parse C → compile → run → record delta
  stops on: cycle plateau (≤5% improvement over last 2 iters) or max_iters

Modes (for ablation):
  - naive       : "make this faster" only (no UADL context)
  - brief       : architectural brief only (no telemetry feedback)
  - telemetry   : telemetry only (no architectural brief)
  - both        : full Phase D — brief + telemetry

Persistence: results/feedback/<run_id>/
  iter_00_code.c, iter_00_metrics.json, iter_00_telem.json
  iter_01_prompt.txt, iter_01_response.txt, iter_01_code.c, iter_01_metrics.json, ...
  trace.json  (compact summary of all iterations)
"""
from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import sys
import time
from datetime import datetime
from typing import Dict, List, Optional

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
SRC_DIR = os.path.dirname(SCRIPT_DIR)
sys.path.insert(0, SRC_DIR)
sys.path.insert(0, SCRIPT_DIR)

from run_experiment import compile_and_run  # noqa: E402
from arch_brief import derive as derive_brief, render as render_brief  # noqa: E402
from annotate_telemetry import render as render_telemetry  # noqa: E402

DEFAULT_MODEL = "gemini-2.5-pro"
PLATEAU_RATIO = 0.05  # stop if improvement over previous best <5%


def _extract_c(text: str) -> Optional[str]:
    """Pull C source from a markdown-fenced LLM response. Falls back to raw."""
    m = re.search(r"```(?:c|cpp|C)?\s*\n(.*?)```", text, re.DOTALL)
    if m:
        return m.group(1).strip()
    # If the response looks like raw C, accept it.
    if "int main" in text or "#include" in text:
        return text.strip()
    return None


def _build_system_prompt() -> str:
    return (
        "You are an expert systems programmer optimizing C code for a cycle-accurate "
        "simulator of a custom processor. Your output must be a single complete C "
        "translation unit, fenced in a ```c block, with the same `main` signature, "
        "the same volatile pointer addresses, and the same observable behavior "
        "(same return value and same writes to those pointers). "
        "Do NOT allocate large stack arrays (>256 bytes) — only the global "
        "volatile pointers are guaranteed addressable. Do NOT use libc, stdio, "
        "stdlib, or any include — the program runs bare-metal. Output ONLY the "
        "C code, no explanation."
    )


def _build_iter_prompt(
    mode: str,
    current_code: str,
    last_metrics: Dict,
    arch_brief_text: str,
    telemetry_text: str,
    iteration: int,
) -> str:
    parts = []
    parts.append(f"# Optimization iteration {iteration}")
    parts.append(
        f"Previous run: {last_metrics['cycles']} cycles, "
        f"{last_metrics['instruction_count']} insns, "
        f"{last_metrics['stalls']} stalls, "
        f"{last_metrics['flushes']} flushes."
    )
    parts.append("")
    if mode in ("brief", "both"):
        parts.append(arch_brief_text)
        parts.append("")
    if mode in ("telemetry", "both"):
        parts.append(telemetry_text)
        parts.append("")
        parts.append(
            "The hot lines above are where the simulator spent the most time. "
            "Focus your transformations there first. Your goal is to lower the "
            "cycle count of the hottest lines."
        )
        parts.append("")
    parts.append("Current C source:")
    parts.append("```c")
    parts.append(current_code.rstrip())
    parts.append("```")
    parts.append("")
    parts.append(
        "Produce a revised version of the C source. Keep `main`'s signature, "
        "the volatile pointer addresses, and the return value identical. "
        "Apply concrete transformations targeted at the bottlenecks listed above. "
        "Output ONLY the revised C code in a single ```c block."
    )
    return "\n".join(parts)


def _call_llm(prompt: str, system: str, model: str) -> str:
    from google import genai
    from google.genai import types

    client = genai.Client()
    cfg = types.GenerateContentConfig(
        system_instruction=system,
        temperature=0.2,
        max_output_tokens=8192,
    )
    resp = client.models.generate_content(
        model=model,
        contents=prompt,
        config=cfg,
    )
    return resp.text or ""


def _summarize_metrics(metrics: Dict) -> Dict:
    return {
        "cycles": metrics.get("cycles", 0),
        "instruction_count": metrics.get("instruction_count", 0),
        "stalls": metrics.get("stalls", 0),
        "flushes": metrics.get("flushes", 0),
        "ipc": metrics.get("ipc", 0.0),
        "cache_hit_rate": metrics.get("cache_hit_rate", {}),
        "code_size_bytes": metrics.get("code_size_bytes", 0),
    }


def run_loop(
    benchmark: str,
    isa: str,
    microarch_path: str,
    mode: str,
    max_iters: int = 5,
    opt_flag: str = "-O0",
    model: str = DEFAULT_MODEL,
    out_root: Optional[str] = None,
) -> Dict:
    bench_dir = os.path.join(SCRIPT_DIR, "benchmarks")
    src_c = os.path.join(bench_dir, f"{benchmark}_baseline.c")
    if not os.path.exists(src_c):
        raise FileNotFoundError(src_c)
    arch_name = os.path.splitext(os.path.basename(microarch_path))[0]
    run_id = datetime.now().strftime("%Y%m%d_%H%M%S")
    tag = f"{run_id}_{benchmark}_{isa}_{arch_name}_{mode}_{opt_flag.lstrip('-')}"
    out_dir = os.path.join(
        out_root or os.path.join(SCRIPT_DIR, "results", "feedback"),
        tag,
    )
    os.makedirs(out_dir, exist_ok=True)

    # Derive arch brief once — same across iterations.
    isa_yaml = os.path.join(SRC_DIR, "isa", f"{isa}.yaml")
    brief = derive_brief(isa_yaml, microarch_path)
    arch_brief_text = render_brief(brief)
    with open(os.path.join(out_dir, "arch_brief.txt"), "w") as f:
        f.write(arch_brief_text)

    # Iter 0: baseline.
    iter_dir = os.path.join(out_dir, "iter_00")
    os.makedirs(iter_dir, exist_ok=True)
    iter0_c = os.path.join(iter_dir, "code.c")
    shutil.copy(src_c, iter0_c)
    with open(iter0_c) as f:
        current_code = f.read()
    metrics = compile_and_run(iter0_c, microarch_path, isa=isa, opt_flag=opt_flag, work_dir=iter_dir)
    if "error" in metrics:
        raise RuntimeError(f"iter 0 failed: {metrics['error']}")

    history: List[Dict] = []
    history.append({
        "iter": 0,
        "code_path": iter0_c,
        "metrics": _summarize_metrics(metrics),
    })
    print(f"[iter 0] cycles={metrics['cycles']}, insns={metrics['instruction_count']}, "
          f"stalls={metrics['stalls']}, flushes={metrics['flushes']}")
    best_cycles = metrics["cycles"]
    best_iter = 0

    for k in range(1, max_iters + 1):
        # Build telemetry text from the previous iteration's run.
        telem_path = metrics.get("telemetry_path")
        symtab_path = metrics.get("symtab_path")
        if telem_path and os.path.exists(telem_path) and symtab_path and os.path.exists(symtab_path):
            telemetry_text = render_telemetry(telem_path, symtab_path, source_path=history[-1]["code_path"])
        else:
            telemetry_text = "(telemetry unavailable)"

        prompt = _build_iter_prompt(
            mode, current_code, metrics, arch_brief_text, telemetry_text, k
        )
        system = _build_system_prompt()

        iter_dir = os.path.join(out_dir, f"iter_{k:02d}")
        os.makedirs(iter_dir, exist_ok=True)
        with open(os.path.join(iter_dir, "prompt.txt"), "w") as f:
            f.write("[SYSTEM]\n" + system + "\n\n[USER]\n" + prompt)

        t0 = time.time()
        try:
            response = _call_llm(prompt, system, model)
        except Exception as e:
            print(f"[iter {k}] LLM error: {e}; stopping")
            break
        with open(os.path.join(iter_dir, "response.txt"), "w") as f:
            f.write(response)
        new_code = _extract_c(response)
        if not new_code:
            print(f"[iter {k}] could not extract C from response; stopping")
            break

        new_c_path = os.path.join(iter_dir, "code.c")
        with open(new_c_path, "w") as f:
            f.write(new_code)

        new_metrics = compile_and_run(
            new_c_path, microarch_path, isa=isa, opt_flag=opt_flag, work_dir=iter_dir
        )
        elapsed = time.time() - t0
        if "error" in new_metrics:
            # Compile/runtime failure — record and try one more iter; LLM may self-correct.
            print(f"[iter {k}] FAILED ({elapsed:.1f}s): {new_metrics['error'][:120]}")
            history.append({
                "iter": k,
                "code_path": new_c_path,
                "metrics": {"error": new_metrics["error"]},
                "elapsed_s": elapsed,
            })
            # Don't update current_code — feed the broken one back so LLM can fix.
            continue

        new_summary = _summarize_metrics(new_metrics)
        delta = new_summary["cycles"] - history[-1]["metrics"].get("cycles", new_summary["cycles"])
        delta_str = f"{delta:+d}" if isinstance(delta, int) else "?"
        print(f"[iter {k}] cycles={new_summary['cycles']} ({delta_str}), "
              f"insns={new_summary['instruction_count']}, "
              f"stalls={new_summary['stalls']}, flushes={new_summary['flushes']} "
              f"({elapsed:.1f}s)")
        history.append({
            "iter": k,
            "code_path": new_c_path,
            "metrics": new_summary,
            "elapsed_s": elapsed,
        })

        # Always feed the most recent (code, metrics) back to the LLM. This lets
        # the model see and react to its own regressions in the next iteration.
        current_code = new_code
        metrics = new_metrics

        # Track best separately for the trace.
        if new_summary["cycles"] < best_cycles:
            best_cycles = new_summary["cycles"]
            best_iter = k

        # Plateau: best hasn't improved by ≥PLATEAU_RATIO over the last 2 iters.
        if k >= 3:
            cycles_2_ago = history[-3]["metrics"].get("cycles")
            if isinstance(cycles_2_ago, int) and cycles_2_ago > 0:
                gain = (cycles_2_ago - best_cycles) / cycles_2_ago
                if gain < PLATEAU_RATIO:
                    print(f"[stop] plateau: best improved only "
                          f"{gain*100:.1f}% over last 2 iters (< {PLATEAU_RATIO*100:.0f}%)")
                    break

    # Final summary.
    summary = {
        "benchmark": benchmark,
        "isa": isa,
        "microarch": arch_name,
        "mode": mode,
        "opt_flag": opt_flag,
        "model": model,
        "max_iters": max_iters,
        "iterations": history,
        "best_iter": best_iter,
        "best_cycles": best_cycles,
        "baseline_cycles": history[0]["metrics"]["cycles"],
        "speedup": history[0]["metrics"]["cycles"] / best_cycles if best_cycles else 0,
    }
    with open(os.path.join(out_dir, "trace.json"), "w") as f:
        json.dump(summary, f, indent=2)
    print(f"\n[done] {tag}: {summary['baseline_cycles']} -> {summary['best_cycles']} "
          f"({summary['speedup']:.2f}x) at iter {best_iter}")
    print(f"  trace: {out_dir}/trace.json")
    return summary


def _dry_run(benchmark: str, isa: str, microarch_path: str, mode: str, opt_flag: str) -> None:
    """Run iter 0, build the iter-1 prompt, print it. No API call."""
    bench_dir = os.path.join(SCRIPT_DIR, "benchmarks")
    src_c = os.path.join(bench_dir, f"{benchmark}_baseline.c")
    arch_name = os.path.splitext(os.path.basename(microarch_path))[0]
    out_dir = os.path.join(SCRIPT_DIR, "results", "feedback", f"dryrun_{benchmark}_{arch_name}")
    os.makedirs(out_dir, exist_ok=True)
    iter_dir = os.path.join(out_dir, "iter_00")
    os.makedirs(iter_dir, exist_ok=True)
    iter0_c = os.path.join(iter_dir, "code.c")
    shutil.copy(src_c, iter0_c)
    with open(iter0_c) as f:
        current_code = f.read()
    metrics = compile_and_run(iter0_c, microarch_path, isa=isa, opt_flag=opt_flag, work_dir=iter_dir)
    if "error" in metrics:
        sys.exit(f"baseline failed: {metrics['error']}")

    isa_yaml = os.path.join(SRC_DIR, "isa", f"{isa}.yaml")
    arch_brief_text = render_brief(derive_brief(isa_yaml, microarch_path))
    telemetry_text = render_telemetry(
        metrics["telemetry_path"], metrics["symtab_path"], source_path=iter0_c
    )

    prompt = _build_iter_prompt(mode, current_code, metrics, arch_brief_text, telemetry_text, 1)
    system = _build_system_prompt()

    print("=" * 80)
    print("[SYSTEM PROMPT]")
    print("=" * 80)
    print(system)
    print()
    print("=" * 80)
    print("[USER PROMPT — what would be sent to gemini-2.5-pro for iter 1]")
    print("=" * 80)
    print(prompt)
    print()
    print(f"[summary] iter 0: cycles={metrics['cycles']}, "
          f"insns={metrics['instruction_count']}, "
          f"stalls={metrics['stalls']}, flushes={metrics['flushes']}")


def main():
    p = argparse.ArgumentParser(description="Phase D feedback-loop driver")
    p.add_argument("--benchmark", required=True, choices=["matmul", "sort", "vec_add", "fibonacci"])
    p.add_argument("--isa", default="rv32i", choices=["rv32i", "rv32im", "armv7"])
    p.add_argument("--arch", default="small", help="microarch name (small|large) or path to YAML")
    p.add_argument("--mode", default="both", choices=["naive", "brief", "telemetry", "both"])
    p.add_argument("--max-iters", type=int, default=5)
    p.add_argument("--opt-flag", default="-O0", choices=["-O0", "-O1", "-O2", "-O3"])
    p.add_argument("--model", default=DEFAULT_MODEL)
    p.add_argument("--dry-run", action="store_true",
                   help="Run iter 0 (baseline) only, print the iter-1 prompt that "
                        "would be sent to the LLM, then exit. No API call.")
    args = p.parse_args()

    if os.path.exists(args.arch):
        microarch = args.arch
    else:
        microarch = os.path.join(SCRIPT_DIR, "architectures", f"{args.arch}.yaml")
    if not os.path.exists(microarch):
        sys.exit(f"microarch yaml not found: {microarch}")

    if args.dry_run:
        _dry_run(args.benchmark, args.isa, microarch, args.mode, args.opt_flag)
        return

    run_loop(
        benchmark=args.benchmark,
        isa=args.isa,
        microarch_path=microarch,
        mode=args.mode,
        max_iters=args.max_iters,
        opt_flag=args.opt_flag,
        model=args.model,
    )


if __name__ == "__main__":
    main()
