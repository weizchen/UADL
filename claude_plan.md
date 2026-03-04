# UADL: Comprehensive Hardware-Software Co-Design Roadmap

## Thesis Statement
A YAML-based hardware description language, designed for LLM readability, can serve as a single source of truth to auto-generate cycle-accurate simulators, assemblers, and eventually compiler backends — enabling true hardware-software co-design without manually writing simulator engine code.

---

## Phase 1: POC ✅ (Completed)
**What was proved:** YAML → C++ simulator generation works end-to-end. A single `cpu.yaml` file drives the assembler, dynamic simulator instantiation, and execution mapping.

**Artifacts delivered:**
- `cpu.yaml` — Base ISA + resource spec for a multi-core accumulator architecture
- `uadl_schema.yaml` — JSON Schema for architectural validation
- `simulator_template.j2` — Jinja2 template generating a C++ simulator capable of multi-core interleaving
- `assembler.py` — YAML-aware instruction encoder
- `c_compiler.py` — Transpiler migrating a subset of C into UADL assembly payloads
- 6 passing tests (arithmetic, memory, control flow, threading, C compilation, parallelism)

**Key milestones verified:** ISA extensibility (adding `JNZ`, `SUB`, `JMP`), multi-core thread scheduling via `FORK` instructions, and configurable cache latency penalties reacting to YAML changes.

---

## Phase 2: Solidify the Foundation
**Goal:** Before advancing to advanced hardware abstractions, the core POC framework must be hardened into a true architectural engine.

### 2A. Replace String-Based Semantics with a Micro-Op IR
**Problem:** The `semantics: "ACC = ACC + imm;"` field is injected into C++ via Jinja2 `replace()` filters. This breaks silently with naming collisions and doesn't scale past 2 registers.

**Solution:** Define a small intermediate representation for instruction behavior:

```yaml
# BEFORE (fragile string injection)
- name: "ADD_IMM"
  semantics: "ACC = ACC + imm;"

# AFTER (structured micro-ops)
- name: "ADD_IMM"
  behavior:
    - op: "add"
      dst: "ACC"
      src1: "ACC"
      src2: "imm"
```

**Implementation:**
1. Define a `behavior` schema with typed micro-ops: `load`, `store`, `add`, `sub`, `branch_if`, `halt`, `fork`
2. Write a Python `codegen.py` that walks the behavior list and emits correct C++ (with proper `core.` prefixing, scoping, etc.)
3. Replace the Jinja2 template's raw `replace()` chain with calls to `codegen`
4. Keep backward compat: support the old `semantics` string as a fallback during transition

**Deliverable:** All 6 existing tests pass with the new behavior IR. No raw C++ strings in `cpu.yaml`.

**Verification:** Adding a new instruction (e.g., `MUL_IMM`) requires only a YAML entry — no Jinja2 template changes.

---

### 2B. Separate Instruction and Data Memory Spaces
**Problem:** Instructions and data both live in `MainMem`, with a hardcoded `next_data_addr = 100` boundary. Programs > 100 instructions corrupt data.

**Solution:**
1. Add an `address_space` section to the schema:
   ```yaml
   address_spaces:
     - name: "InstructionMem"
       base: 0x0000
       size: 4096
     - name: "DataMem"  
       base: 0x1000
       size: 4096
   ```
2. The simulator loads the binary into `InstructionMem` and fetches from it
3. `LOAD_MEM` / `STORE` / `ADD_MEM` access `DataMem`
4. The C compiler and assembler emit addresses relative to the data segment base

**Deliverable:** Clean Harvard-style separation. Programs can grow without data corruption. Also create a .gitignore file for this project.

**Verification:** A program with >100 instructions executes correctly without corrupting data memory.

---

### 2C. Add a General-Purpose Register File
**Problem:** Single-accumulator architecture can't express real workloads. Every value must go through memory.

**Solution:** Extend `cpu.yaml` with a register file:
```yaml
registers:
  - name: "PC"
    width: 32
  - name: "SP"
    width: 32
  - name: "R"
    width: 32
    count: 8   # R0..R7, R0 is always ACC for backward compat
```

This is a moderate change that enables:
- Register-to-register operations (no memory round-trips)
- A stack pointer for future function call support
- More realistic cycle counting

**Deliverable:** New instruction variants (`ADD R1 R2 R3`, `LOAD R1 addr`). Old accumulator tests still pass (R0 = ACC alias).

**Verification:** A multi-variable C program compiles without memory round-trips for every intermediate value. Existing test suite still green.

---

### 2D. Deterministic Cache Model
**Problem:** Cache simulation uses `random()` to decide hit/miss — cycle counts are meaningless for architecture comparison.

**Solution:** Implement a simple direct-mapped cache:
```yaml
caches:
  - level: "L1"
    size: 256        # bytes
    line_size: 16    # bytes per line → 16 lines
    associativity: 1 # direct-mapped
    hit_latency: 1
    miss_penalty: 10
```

The generated C++ will include a real tag array. On each memory access, it checks address tags, updates on miss, and reports deterministic cycle penalties.

**Deliverable:** Same program with different cache configs produces different (deterministic, explainable) cycle counts. A demo showing how doubling cache size affects a loop's performance.

**Verification:** Same program produces identical cycle counts across 100 consecutive runs. Changing cache size in YAML visibly changes hit/miss ratios in output.

---

## Phase 3: Pipeline Modeling
**Goal:** Move from single-instruction-per-cycle to a realistic multi-stage pipeline. This is the most impactful architectural leap.

### 3A. 5-Stage In-Order Pipeline
Model: **Fetch → Decode → Execute → Memory → Writeback**

Add to `cpu.yaml`:
```yaml
pipeline:
  stages: ["IF", "ID", "EX", "MEM", "WB"]
  hazard_detection: true
  forwarding: true
```

**Implementation:**
1. Replace the `step()` function with a pipeline stage array
2. Each cycle, shift instructions through stages
3. Detect RAW hazards (read-after-write) and insert stalls
4. Optionally enable data forwarding to reduce stalls
5. Track pipeline bubbles and stalls in cycle counts

**Deliverable:** Same program runs with `pipeline: none` (current behavior) vs `pipeline: 5-stage` and shows different, realistic cycle counts. Branch penalty is visible.

**Verification:** A `LOAD` immediately followed by `ADD` using the loaded value inserts exactly 1 stall bubble with forwarding enabled, or 2 without.

### 3B. Pipeline Visualization
Generate a text-based pipeline diagram output:
```
Cycle:  1    2    3    4    5    6    7
LOAD:   IF   ID   EX   MEM  WB
ADD:         IF   ID   --   EX   MEM  WB    ← stall (data hazard)
STORE:            IF   --   ID   EX   MEM
```

This is high-value for educational use and debugging.

**Deliverable:** `--pipeline-trace` flag on the simulator that dumps the diagram.

---

## Phase 4: Real Compiler Integration
**Goal:** Replace `c_compiler.py` with something that can handle real C programs.

### 4A. Practical C Compilation: C → LLVM IR → UADL Assembly
The naive `c_compiler.py` cannot handle loops, arrays, or pointers. Before tackling a full LLVM backend, we use an intermediate approach:
1. Run standard `clang -emit-llvm` to convert any C program to LLVM Intermediate Representation (IR)
2. Write a Python `llvm_to_uadl.py` that pattern-matches LLVM IR instructions to UADL assembly
3. This leverages LLVM's frontend (parsing, type checking, optimization) without building a full backend

**Deliverable:** Compile real C programs (with loops, arrays, function calls) to UADL assembly and simulate them.

**Verification:** Bubble sort and matrix multiply programs produce correct output through the full pipeline.

### 4B. Full LLVM Backend Auto-Generation (Stretch Goal)
Build a translation engine that converts `cpu.yaml` directly into LLVM `.td` (TableGen) specifications (`RegisterInfo.td`, `InstrInfo.td`, `Schedule.td`).

**Deliverable:** `clang -target uadl` seamlessly compiles to dynamically defined architectures.

> [!IMPORTANT]
> This is realistically a 6-12 month effort on its own. Phase 4A is the practical path; this is a long-term stretch goal.

---

## Phase 5: LLM-Driven Architecture Search
**Goal:** Leverage UADL's core differentiator — LLM readability — to enable automated hardware design exploration.

Because UADL configurations are token-efficient YAML schemas rather than complex C++ codebases, an LLM agent can directly read, reason about, and mutate hardware specifications.

### 5A. Benchmark Suite
Create 5-10 representative kernels:
- Matrix multiply
- Sorting algorithm (bubble sort, merge sort)
- FFT butterfly
- Neural network layer (convolution, GEMM)
- Graph traversal (BFS/DFS)

Each with expected output for correctness checking and a baseline cycle count on the default architecture.

### 5B. Agentic Search Loop
```
for each generation:
    1. LLM reads cpu.yaml + benchmark results from previous generation
    2. LLM proposes mutations to the micro-architecture:
       - Changing cache topologies (size, associativity, levels)
       - Adding dedicated instructions (e.g., MAC opcode for neural net kernels)
       - Tweaking pipeline depth or forwarding policies
       - Adjusting register file size
    3. Framework regenerates the simulator instantly from mutated YAML
    4. Runs all benchmark kernels, records cycle counts
    5. Score = weighted_sum(1/cycles, area_penalty, power_penalty)
    6. Select top-k configurations, feed back to LLM for next iteration
```

**Deliverable:** Starting from a baseline `cpu.yaml`, the system discovers that (e.g.) adding a MAC instruction reduces neural network kernel cycles by 40%, or that a 4-way cache eliminates 90% of misses for matrix multiply.

**Verification:** The search converges to a measurably better configuration than the baseline within 10-20 generations.

---

## Milestone Timeline (Suggested)

| Phase | Milestone | Estimated Effort |
|---|---|---|
| 2A | Micro-op IR replaces string semantics | 2-3 weeks |
| 2B | Separate address spaces | 1 week |
| 2C | General-purpose register file | 2 weeks |
| 2D | Deterministic cache model | 2 weeks |
| 3A | 5-stage pipeline | 3-4 weeks |
| 3B | Pipeline visualization | 1 week |
| 4B | LLVM IR → UADL translator | 4-6 weeks |
| 5A-B | LLM architecture search | 4-6 weeks |

**Total estimated:** ~5-6 months of focused work for Phases 2-5.

---

## Design Principles

1. **Concrete over aspirational** — every phase has specific YAML examples, deliverables, and verification criteria
2. **Ordered by impact** — fixing the semantics string injection (2A) comes before adding pipelines (3A)
3. **Scoped aggressively** — no OoO execution, no cache coherence protocols, no full LLVM backend in the core plan (those are stretch goals)
4. **Backward compatible** — each phase extends without breaking existing tests
5. **Builds toward the differentiator** — the LLM architecture search (Phase 5) is what makes UADL unique vs. LISA, so the foundation must support it
