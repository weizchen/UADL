"""Phase D: derive an actionable architectural brief from UADL YAML.

This is the LLM-facing distillation of the spec — instead of pasting raw YAML,
we emit a short list of optimization-relevant facts. Pairing this with
simulator telemetry is the core Phase D contribution.

Usage:
    python arch_brief.py isa/rv32i.yaml experiments/architectures/small.yaml
"""
from __future__ import annotations

import sys
from typing import Dict, List, Optional

import yaml


_MUL_OPS = {"mul", "mulu", "mulh", "mulhsu", "mulhu", "mla"}
_DIV_OPS = {"div", "divu", "rem", "remu", "mod"}


def _load(path: str) -> dict:
    with open(path) as f:
        return yaml.safe_load(f)


def _detect_op(instructions: List[dict], op_set: set) -> List[str]:
    """Return names of instructions whose behavior uses one of the listed ops."""
    found = []
    for inst in instructions:
        for step in inst.get("behavior", []) or []:
            if step.get("op") in op_set:
                found.append(inst["name"])
                break
    return found


def derive(isa_path: str, microarch_path: str) -> Dict:
    isa = _load(isa_path)["isa"]
    microarch = _load(microarch_path)["microarch"]

    facts: Dict[str, object] = {}
    bullets: List[str] = []

    # ---- ISA / register file ----
    instructions = isa.get("instructions", [])
    inst_names = {i["name"] for i in instructions}
    gp = next((r for r in isa.get("registers", []) if r.get("count")), None)
    reg_count = gp.get("count") if gp else None
    facts["isa_name"] = isa.get("name", "?")
    facts["register_count"] = reg_count

    # ---- Multiply / divide ----
    has_mul_op = bool(_detect_op(instructions, _MUL_OPS))
    has_div_op = bool(_detect_op(instructions, _DIV_OPS))
    facts["has_hw_mul"] = has_mul_op
    facts["has_hw_div"] = has_div_op
    if not has_mul_op:
        bullets.append(
            "NO HARDWARE MULTIPLY in the ISA. Every `*` becomes a software shift-add "
            "loop costing ~150 cycles per multiply. Strongly prefer: (a) replace "
            "`x * k` with `(x << log2(k)) + ...` for constant k, (b) precompute "
            "or hoist multiplies out of inner loops, (c) iterate with `+= stride` "
            "instead of `i * stride`."
        )
    if not has_div_op:
        bullets.append(
            "NO HARDWARE DIVIDE/MODULO. Avoid `/` and `%` in hot loops; use shifts "
            "for power-of-two divisors and bitmasks for modulo of power-of-two."
        )

    # ---- Pipeline ----
    pipeline = microarch.get("pipeline", {})
    pipeline_enabled = pipeline.get("enabled", False)
    stages = pipeline.get("stages", [])
    hazards = pipeline.get("hazards", {})
    data_h = hazards.get("data", {})
    ctrl_h = hazards.get("control", {})
    forwarding = data_h.get("forwarding", False)
    branch_penalty = ctrl_h.get("branch_penalty", 0)
    facts["pipeline_depth"] = len(stages)
    facts["forwarding"] = bool(forwarding)
    facts["branch_penalty"] = int(branch_penalty)

    if pipeline_enabled:
        # Loop overhead: a back-edge branch costs `branch_penalty` cycles every iter.
        # Without forwarding, dependent ALU ops also pay ~2 cycles. The combined
        # overhead is what unrolling amortizes.
        loop_overhead = branch_penalty + (2 if not forwarding else 0)
        bullets.append(
            f"Pipeline depth {len(stages)}, branch penalty {branch_penalty} cyc, "
            f"forwarding {'ENABLED' if forwarding else 'DISABLED (RAW deps stall ~2 cyc)'}. "
            f"Estimated per-iter loop overhead ≈ {loop_overhead} cycles. "
            f"Unrolling tight inner loops {max(2, loop_overhead)}× amortizes this."
        )
        if not forwarding:
            bullets.append(
                "Without forwarding, consecutive dependent ALU ops stall. Reorder/"
                "interleave independent work between dependent instructions where "
                "possible to hide RAW latency."
            )

    # ---- Memory hierarchy / cache ----
    mem_hier = microarch.get("memory_hierarchy", {})
    nodes = [n for n in mem_hier.get("nodes", []) if n.get("type") == "cache"]
    if not nodes:
        nodes = microarch.get("resources", {}).get("caches", [])
    cache_facts = []
    for c in nodes:
        size = c.get("size") or c.get("size_bytes") or 0
        line = c.get("line_size", 0) or 0
        assoc = c.get("associativity", 1)
        miss = c.get("miss_penalty", 0)
        if size and line:
            lines_count = size // line
            cache_facts.append({
                "name": c.get("name") or c.get("level"),
                "size": size,
                "line_size": line,
                "associativity": assoc,
                "miss_penalty": miss,
                "lines": lines_count,
            })
    facts["caches"] = cache_facts
    if cache_facts:
        # Bullet for the smallest cache (typically L1) — that's the binding constraint.
        l1 = cache_facts[0]
        bullets.append(
            f"L1 cache: {l1['size']} B in {l1['lines']} lines × {l1['line_size']} B "
            f"({l1['associativity']}-way), miss penalty {l1['miss_penalty']} cyc. "
            f"Working sets > {l1['size']} B will thrash. For nested loops over "
            f"arrays larger than this, prefer transposes / loop blocking so the "
            f"inner loop walks contiguous memory and reuses cache lines."
        )

    # ---- Register pressure ----
    if reg_count:
        bullets.append(
            f"{reg_count} general-purpose registers. Hoist loop-invariant values, "
            f"keep accumulators in locals, and avoid spilling in inner loops."
        )

    # ---- Misc helpful instructions ----
    extras = []
    if "MLA" in inst_names:
        extras.append("MLA (multiply-accumulate) is available — use for dot products.")
    if any(n.startswith("LD") and "M" in n for n in inst_names):
        extras.append("Load-multiple instructions exist — consider for array copies.")
    if extras:
        bullets.append("ISA niceties: " + " ".join(extras))

    return {"facts": facts, "bullets": bullets}


def render(brief: Dict) -> str:
    lines = ["=== Architectural Brief ==="]
    f = brief["facts"]
    lines.append(
        f"ISA: {f['isa_name']}, {f['register_count']} GP regs, "
        f"HW mul: {'yes' if f['has_hw_mul'] else 'no'}, "
        f"HW div: {'yes' if f['has_hw_div'] else 'no'}, "
        f"pipeline: {f['pipeline_depth']}-stage, "
        f"forwarding: {'on' if f['forwarding'] else 'off'}, "
        f"branch penalty: {f['branch_penalty']} cyc"
    )
    lines.append("")
    lines.append("Optimization opportunities (act on these specifically):")
    for i, b in enumerate(brief["bullets"], 1):
        lines.append(f"  {i}. {b}")
    return "\n".join(lines)


if __name__ == "__main__":
    if len(sys.argv) != 3:
        print("Usage: arch_brief.py <isa.yaml> <microarch.yaml>")
        sys.exit(1)
    print(render(derive(sys.argv[1], sys.argv[2])))
