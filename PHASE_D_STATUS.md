# Phase D Status — UADL closed-loop LLM-aware optimization

Last updated: 2026-05-04. This document captures the full state of the Phase D
work-in-progress so anyone (or future-you) can pick it up cold.

---

## TL;DR

The infrastructure for closed-loop, telemetry-guided LLM code optimization is
**fully built and partially validated**. A single smoke test produced
**33.7× speedup in one LLM iteration** (fibonacci/small/both/-O0:
9 847 → 292 cycles). The full matrix run on `gemini-2.5-pro` then **failed
across most combos** with a now-understood failure mode (empty LLM responses
caused by output-token-budget exhaustion). The matrix process has been
stopped to avoid burning further API credits. Fixing this and re-running is
the immediate next step.

---

## What was built (all merged into the worktree)

### Bug fixes that landed first
The infra had to be made correct before Phase D had any meaning. Fixed in
this branch:

| Bug | File | Effect |
|---|---|---|
| Template name mismatch | `src/sim_template.j2` → `sim_universal.j2` | All five callers were referencing a missing file |
| `branch_penalty` read from wrong YAML path | `src/sim_universal.j2:236` | Fresh builds wouldn't compile |
| **Forwarding never actually worked** | `src/sim_universal.j2:198,204` | Every prior Phase B/C result ran with forwarding disabled regardless of YAML |
| `small.yaml` cache geometry self-contradictory | `src/experiments/architectures/small.yaml` | L1 was being read as 16 B not 256 B |
| Missing `instruction_count` / IPC in sim output | `src/sim_universal.j2`, parser in `run_experiment.py` | CSVs always reported 0 |
| `pyelftools` and `google-genai` missing from `requirements.txt` | | Fresh-clone setup broken |
| `find_llvm_tool` ignored Intel-Mac brew paths | `run_experiment.py` | Toolchain auto-detect broken on x86 macs |

**Implication for prior published numbers:** any Phase B / Phase C result
predating this branch was generated with forwarding silently disabled —
the "disable forwarding for area savings" finding in `present.md` is an
artifact of a stale template, not a real result. Re-run before publishing.

### New Phase D components

| Component | File | Role |
|---|---|---|
| Per-PC telemetry | `src/sim_universal.j2` | Tracks `dispatched / stall_cycles / flushes / mem_accesses / cache_misses` keyed by PC; dumps as `<bin>.telem.json` |
| DWARF symtab sidecar | `src/elf2mem.py` | Emits `<bin>.symtab.json` (`pc_hex → [file, line]`) |
| Telemetry annotator | `src/annotate_telemetry.py` | Joins the two; produces hot-line digest for LLM prompts |
| Architectural brief | `src/arch_brief.py` | Derives actionable bullets from ISA + microarch YAML (no-MUL fact, cache lines, branch overhead, register count) |
| Feedback loop driver | `src/experiments/run_feedback_loop.py` | 4 modes (`naive`/`brief`/`telemetry`/`both`), iter persistence, plateau detection, `--dry-run` for previewing prompts without API calls |
| Matrix runner | `src/experiments/run_phase_d_matrix.py` | Resumable sweep over `(bench, arch, mode, opt)` |
| Summarizer / plots | `src/experiments/summarize_phase_d.py` | CSV + paper-ready markdown + convergence PNG |
| `__mulsi3` software multiply | `src/crt0_rv32i.s` | RV32I has no MUL — slow software multiply makes the cost visible in telemetry, which the LLM should respond to |
| `memcpy` / `memset` stubs | `src/crt0_rv32i.s` | Required by clang -O0 for stack-array initializers |
| Byte / halfword load + store | `src/isa/rv32i.yaml`, `rv32im.yaml`, `src/codegen.py` | LB/LBU/LH/LHU/SB/SH (needed by `memcpy`) |
| RV32IM ISA | `src/isa/rv32im.yaml` | RV32I + M extension. Same hardware, mul/div added — used for "spec drives strategy" ablation |
| 2D convolution benchmark | `src/experiments/benchmarks/conv2d_baseline.c` | 16×16 image, 3×3 Gaussian. Stresses cache locality + exposes no-MUL on rv32i. Verified correct (out[0]=17) |

### What end-to-end works (verified)

- Simulator builds for all `(rv32i, rv32im) × (small, large)` configs.
- Per-PC telemetry attribution: fibonacci baseline correctly identifies
  `return fib(n-1) + fib(n-2)` as the hottest line (1142 cycles, 438 stalls,
  176 flushes from recursion).
- Architectural brief generates visibly different content for small vs large
  (forwarding off / on, branch penalty 3 / 1, cache 256 B / 4 KB).
- Conv2d output verified correct (out[0]=17 matches hand-computed).
- **Smoke test (the only successful Phase D LLM run so far):**
  `fibonacci/small/both/-O0` — 9847 → 292 cycles (33.72×) in **one** iteration.
  The LLM eliminated recursion *and* fully unrolled the 9-step computation;
  its rationale named the actual bottlenecks ("function call overhead and
  loop branches"). DataMem[400] = 55 (correct fib(10)).

### Conv2d baseline numbers (from smoke tests, no LLM yet)

Same C source, only the ISA differs:

| ISA | Arch | Cycles | Insns | Flushes | What dominates |
|---|---|---|---|---|---|
| rv32i  | large | 166 784 | 110 122 | 19 503 | software multiply |
| rv32im | large | 122 096 |  78 370 | 10 095 | branch + cache only |
| rv32i  | small | 307 173 | 110 122 | 19 503 | mul + no-forwarding stalls |
| rv32im | small | 234 441 |  78 370 | 10 095 | branch + cache + stalls |

Adding only `mul` to the spec saves 25–30% of baseline cycles on the same
hardware. That's the foundation for the "spec drives LLM strategy" ablation.

---

## What's broken (must fix before next matrix run)

### Primary: gemini-2.5-pro returns empty responses on most prompts

**Symptom:** every matrix combo except fibonacci/small/both/-O0 reported
`baseline → baseline (1.00× at iter 0)`. Inspecting `iter_01/response.txt`
across runs:

```
$ wc -c .../*/iter_01/response.txt | head
   960  fibonacci/...both/O0   ← the one that worked
     0  matmul/...naive/O0
     0  matmul/...naive/O3
     0  matmul/...brief/O0
     0  matmul/...brief/O3
   ... (all other matmul/sort runs: 0 bytes)
```

**Root cause (high confidence):** `gemini-2.5-pro` performs internal "thinking"
that consumes the same output-token budget as the visible response. The
driver was set to `max_output_tokens=8192`, which thinking exhausts before
any visible output is emitted. Larger prompts (matmul C source ≈ 40 lines,
sort ≈ 30 lines, plus brief + telemetry) trigger more thinking, leaving zero
budget for the answer. Fibonacci is small enough to fit.

The driver does handle this gracefully (`_extract_c` returns None → loop
breaks → trace records iter 0 only) — but it silently looks like "no
improvement," which is misleading.

**Fix (when resuming):** in `run_feedback_loop.py:_call_llm`:
- Bump `max_output_tokens` to 32 768 or higher.
- Pass `thinking_config={"thinking_budget": -1}` (or a small explicit
  budget) via `GenerateContentConfig` to keep thinking from eating the
  whole budget. See Google's docs for `genai.types.ThinkingConfig`.
- Surface empty-response errors more loudly in the loop output (currently
  printed once, then the loop just exits the iteration).
- Consider a single retry with bumped budget if first response is empty.

### Secondary: matmul at -O3 reports 0 cycles

`matmul/*/*/-O3` traces all show `baseline_cycles = 0`. Almost certainly
because `matmul_baseline.c` uses `N=64`, which makes the data layout
`A=400`, `B=16784`, `C=33168` exceed the 16 KB DataMem (DataMem ends at
16384). At `-O0` the writes still execute (clipped silently); at `-O3`
clang likely hoists/elides the loops in a way that makes the simulator
finish without entering the kernel. Two options:

- Bump DataMem in the architecture YAMLs, or
- Reduce N to 32 (working set 32×32×4×3 = 12 288 B, fits) — also makes
  the kernel run in seconds rather than minutes on every iter.

### Tertiary: matmul/rv32i runs are extremely slow

Software multiply at ~150 cycles per multiply turns matmul into a 43–75M
cycle kernel. Each iter takes ~10–30 s to *simulate*, and the LLM call
adds another ~60 s. That made the matrix expensive both in API budget and
wall-clock time. Either:
- Drop matmul/rv32i from the headline matrix (rv32im replaces it cleanly), or
- Bound iterations more aggressively for matmul, or
- Use a smaller N.

### Pre-existing benchmark issues (independent of Phase D)

- `matmul_naive_llm.c` has `int B_transposed[N*N]` = 16 KB stack array that
  collides with the SP-base layout. Already noted.
- `fibonacci_uadl_aware_llm.c`, `sort_uadl_aware_llm.c`, `vec_add_uadl_aware_llm.c`
  exist in only one variant each (the experiment runner expects per-arch
  files like `_uadl_aware_small.c` / `_uadl_aware_large.c`). Phase D
  generates per-iter code so this only affects the legacy Phase C runner.

---

## What didn't get done

| Item | Status |
|---|---|
| Full matrix LLM run (64 combos) | **Aborted** because of the empty-response bug — only matmul (rv32i/small + rv32i/large) and sort (rv32i/small + rv32i/large/naive/-O3) ran, mostly with no LLM iteration |
| Conv2d added to matrix | YAML, codegen, and benchmark are all in place; just hasn't been run |
| RV32IM matrix combos | Same — staged but not run |
| Convergence plots, summary CSV/MD | Generator exists; no real data to feed it |
| Re-validation of Phase B numbers with corrected forwarding | Not done. `present.md`'s Phase B narrative may need updating |

---

## Cost so far

Roughly **15–20 LLM calls** at gemini-2.5-pro pricing — most returned empty
output (still billed for thinking tokens). Order of magnitude: a few dollars.
Continuing the matrix as-configured would have added more for no useful
data; that's why it was stopped.

---

## Next session: concrete first steps

1. **Fix `_call_llm`** in `src/experiments/run_feedback_loop.py`:
   - Pass `thinking_config={"thinking_budget": 0}` (or a small budget) via
     `GenerateContentConfig` so thinking doesn't eat the response budget.
     With 2.5-pro this is critical.
   - Bump `max_output_tokens` to 16 384 or 32 768 anyway.
   - Add a single retry on empty response.
   - Print a loud warning when response is empty, so it's not mistaken
     for "no improvement."

2. **Re-run the smoke test** to confirm the fix:
   `python run_feedback_loop.py --benchmark matmul --arch large --isa rv32im --mode both --max-iters 1 --opt-flag=-O0`
   Expected outcome: non-empty response, observable cycle improvement.

3. **Tighten the matmul benchmark** — either reduce N to 32 or bump DataMem
   in `experiments/architectures/*.yaml` and `crt0_rv32i.s` (stack base) so
   `-O3` doesn't behave pathologically.

4. **Re-launch matrix** — start small: `--benchmarks fibonacci conv2d sort
   vec_add --isa rv32i --opt-flags -O0` (skip rv32im until -O0 works), then
   widen.

5. **Then the ablation:** same kernels under rv32i vs rv32im to demonstrate
   the spec-drives-strategy story.

---

## Files added / changed in this branch

```
new:    PHASE_D_STATUS.md                                  (this file)
new:    src/annotate_telemetry.py
new:    src/arch_brief.py
new:    src/experiments/benchmarks/conv2d_baseline.c
new:    src/experiments/run_feedback_loop.py
new:    src/experiments/run_phase_d_matrix.py
new:    src/experiments/summarize_phase_d.py
new:    src/isa/rv32im.yaml
modified: requirements.txt                                  (+pyelftools, note for google-genai)
modified: src/codegen.py                                    (+M-ext ops, +byte/half loads/stores)
modified: src/crt0_rv32i.s                                  (+memcpy, +memset, +__mulsi3)
modified: src/elf2mem.py                                    (+DWARF symtab sidecar)
modified: src/experiments/architectures/small.yaml          (cache geometry fix)
modified: src/experiments/run_experiment.py                 (-g, opt_flag, work_dir, rv32im, parser)
modified: src/isa/rv32i.yaml                                (+LB/LBU/LH/LHU/SB/SH)
modified: src/sim_universal.j2 (renamed from sim_template.j2)  (per-PC telemetry, IPC, DWARF-friendly dump, infra fixes)
```

Generated artifacts under `src/experiments/results/feedback/` are not
committed — they are now gitignored.
