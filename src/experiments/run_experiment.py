"""
UADL Phase C: LLM Code Optimization Experiment Runner

Compares three code optimization strategies:
  1. Baseline: unoptimized C code
  2. Naive LLM: "optimize this code" (no architecture info)
  3. UADL-aware LLM: "optimize for this architecture" + full YAML spec

For each (benchmark × architecture × variant), this script:
  1. Compiles the C code using the UADL toolchain
  2. Runs it on the simulated architecture
  3. Extracts performance metrics (cycles, cache stats, stalls)
  4. Produces a comparison table

Usage:
  python run_experiment.py                     # Run all experiments
  python run_experiment.py --benchmark matmul  # Run one benchmark
  python run_experiment.py --arch small        # Run one architecture
  python run_experiment.py --generate-prompts  # Generate LLM prompts only
"""

import subprocess
import os
import sys
import json
import re
import yaml
import csv
from datetime import datetime

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
SRC_DIR = os.path.dirname(SCRIPT_DIR)  # src/
BENCH_DIR = os.path.join(SCRIPT_DIR, 'benchmarks')
ARCH_DIR = os.path.join(SCRIPT_DIR, 'architectures')
RESULTS_DIR = os.path.join(SCRIPT_DIR, 'results')
PROMPTS_DIR = os.path.join(SCRIPT_DIR, 'prompts')

# Import from parent
sys.path.insert(0, SRC_DIR)

BENCHMARKS = ['matmul', 'sort', 'vec_add', 'fibonacci']
ARCHITECTURES = ['small', 'large']
VARIANTS = ['baseline', 'naive_llm', 'uadl_aware_llm']

def find_llvm_tool(name):
    """Find LLVM tool, preferring Homebrew over Apple's stub clang.

    Apple's /usr/bin/clang lacks cross-compile backends (riscv32, arm-none-eabi)
    and lld, so we must check Homebrew kegs first.
    """
    import shutil
    # Homebrew prefixes: ARM (/opt/homebrew) and Intel (/usr/local).
    # `lld` is its own keg, so check both llvm/ and lld/ subtrees.
    for prefix in ('/opt/homebrew', '/usr/local'):
        for keg in ('llvm', 'lld'):
            candidate = f'{prefix}/opt/{keg}/bin/{name}'
            if os.path.exists(candidate):
                return candidate
    tool = shutil.which(name)
    if tool:
        return tool
    for v in range(22, 12, -1):
        tool = shutil.which(f'{name}-{v}')
        if tool:
            return tool
    return name

def parse_sim_output(output):
    """Parse simulator output to extract performance metrics."""
    metrics = {
        'cycles': 0,
        'stalls': 0,
        'flushes': 0,
        'instruction_count': 0,
        'cache_hits': {},
        'cache_misses': {},
        'cache_hit_rate': {},
        'ipc': 0.0,
        'data_mem': {},
    }

    for line in output.split('\n'):
        line = line.strip()

        # Cycle count
        m = re.search(r'Total (?:Workload )?Cycles:\s*(\d+)', line)
        if m:
            metrics['cycles'] = int(m.group(1))

        # Pipeline stalls
        m = re.search(r'Pipeline Stalls:\s*(\d+)', line)
        if m:
            metrics['stalls'] = int(m.group(1))

        # Pipeline flushes
        m = re.search(r'Pipeline Flushes:\s*(\d+)', line)
        if m:
            metrics['flushes'] = int(m.group(1))

        # Instruction count (workload-wide)
        m = re.search(r'Total Instructions:\s*(\d+)', line)
        if m:
            metrics['instruction_count'] = int(m.group(1))

        # IPC
        m = re.search(r'^IPC:\s*([\d.]+)', line)
        if m:
            metrics['ipc'] = float(m.group(1))
        
        # Cache stats
        m = re.search(r'(\w+) Cache:\s*(\d+)\s*hits,\s*(\d+)\s*misses\s*\(([\d.]+)%', line)
        if m:
            name = m.group(1)
            metrics['cache_hits'][name] = int(m.group(2))
            metrics['cache_misses'][name] = int(m.group(3))
            metrics['cache_hit_rate'][name] = float(m.group(4))
        
        # Data memory values
        m = re.search(r'DataMem\[(\d+)\]:\s*(-?\d+)', line)
        if m:
            metrics['data_mem'][int(m.group(1))] = int(m.group(2))
    
    return metrics


def compile_and_run(c_file, microarch_yaml, isa='rv32i', opt_flag='-O0', work_dir=None):
    """Compile a C file and run it on the given architecture. Returns metrics dict.

    `opt_flag` is the -O level passed to clang (default -O0).
    `work_dir` overrides where intermediate .cpp/.bin/.elf files are written
    (default: RESULTS_DIR). Use a per-run dir to avoid collisions when running
    multiple feedback iterations in parallel.
    """
    
    out_dir = work_dir or RESULTS_DIR
    os.makedirs(out_dir, exist_ok=True)

    # Step 1: Build simulator for this architecture
    isa_yaml = os.path.join(SRC_DIR, 'isa', f'{isa}.yaml')
    template = os.path.join(SRC_DIR, 'sim_universal.j2')
    cpp_out = os.path.join(out_dir, 'tmp_sim.cpp')
    sim_out = os.path.join(out_dir, 'tmp_sim')
    
    result = subprocess.run(
        ['python', os.path.join(SRC_DIR, 'uadl_compiler.py'),
         isa_yaml, microarch_yaml, template, cpp_out],
        capture_output=True, text=True
    )
    if result.returncode != 0:
        return {'error': f'Compiler failed: {result.stderr}'}
    
    result = subprocess.run(
        f'g++ -O2 -std=c++17 {cpp_out} -o {sim_out}',
        shell=True, capture_output=True, text=True
    )
    if result.returncode != 0:
        return {'error': f'g++ failed: {result.stderr}'}
    
    # Step 2: Compile C → binary using selected toolchain
    clang = find_llvm_tool('clang')
    lld = find_llvm_tool('ld.lld')
    
    if isa == 'rv32i':
        crt0 = os.path.join(SRC_DIR, 'crt0_rv32i.s')
        clang_target = '--target=riscv32 -march=rv32i -mabi=ilp32'
        ld_cmd = f'{lld} -m elf32lriscv --image-base=0'
    elif isa == 'rv32im':
        # Same crt0 (the __mulsi3 helper is harmless dead code when MUL is
        # available; clang will emit native MUL and never call it).
        crt0 = os.path.join(SRC_DIR, 'crt0_rv32i.s')
        clang_target = '--target=riscv32 -march=rv32im -mabi=ilp32'
        ld_cmd = f'{lld} -m elf32lriscv --image-base=0'
    elif isa == 'armv7':
        crt0 = os.path.join(SRC_DIR, 'crt0_armv7.s')
        clang_target = '--target=armv7-none-eabi -mcpu=cortex-a9'
        ld_cmd = f'{lld} --image-base=0'
    else:
        return {'error': f'Unsupported ISA for experiment runner: {isa}'}
    
    base = os.path.join(out_dir, 'tmp_test')
    obj = base + '.o'
    crt0_o = base + '_crt0.o'
    elf = base + '.elf'
    bin_path = base + '.bin'
    
    # Assemble crt0
    r = subprocess.run(
        f'{clang} {clang_target} -c -o {crt0_o} {crt0}',
        shell=True, capture_output=True, text=True
    )
    if r.returncode != 0:
        return {'error': f'crt0 failed: {r.stderr}'}
    
    # Compile C; -g embeds DWARF for per-PC source-line telemetry (used in Phase D).
    r = subprocess.run(
        f'{clang} {clang_target} -c {opt_flag} -g -fno-builtin -nostdlib -o {obj} {c_file}',
        shell=True, capture_output=True, text=True
    )
    if r.returncode != 0:
        return {'error': f'C compile failed: {r.stderr}'}
    
    # Link
    r = subprocess.run(
        f'{ld_cmd} -Ttext=0 -o {elf} {crt0_o} {obj}',
        shell=True, capture_output=True, text=True
    )
    if r.returncode != 0:
        return {'error': f'Link failed: {r.stderr}'}
    
    # Convert ELF → UADL binary format
    elf2mem = os.path.join(SRC_DIR, 'elf2mem.py')
    r = subprocess.run(
        f'{sys.executable} {elf2mem} {elf} {bin_path}',
        shell=True, capture_output=True, text=True
    )
    if r.returncode != 0:
        return {'error': f'elf2mem failed: {r.stderr}'}
    
    # Cleanup intermediate files
    for f_path in [obj, crt0_o, elf]:
        if os.path.exists(f_path):
            os.remove(f_path)
    
    # Step 3: Run simulator
    try:
        result = subprocess.run(
            [sim_out, bin_path], capture_output=True, text=True, timeout=30
        )
    except subprocess.TimeoutExpired:
        return {'error': 'Simulation timed out (30s)'}
    
    output = result.stdout
    metrics = parse_sim_output(output)
    metrics['raw_output'] = output
    
    # Count instructions from binary size
    try:
        bin_size = os.path.getsize(bin_path)
        metrics['code_size_bytes'] = bin_size
    except:
        metrics['code_size_bytes'] = 0

    # Sidecar paths for Phase D
    metrics['bin_path'] = bin_path
    metrics['symtab_path'] = bin_path + '.symtab.json'
    metrics['telemetry_path'] = bin_path + '.telem.json'
    return metrics


def generate_prompts(benchmark, isa='rv32i'):
    """Generate the three prompt variants for a benchmark. Returns a dict of the prompts."""
    os.makedirs(PROMPTS_DIR, exist_ok=True)
    
    prompts = {}
    
    baseline_file = os.path.join(BENCH_DIR, f'{benchmark}_baseline.c')
    if not os.path.exists(baseline_file):
        print(f"  Benchmark not found: {baseline_file}")
        return prompts
    
    with open(baseline_file) as f:
        code = f.read()
    
    # Naive prompt (no architecture info)
    naive_prompt = f"""Optimize the following C code for performance. Focus on reducing execution time.
Do not change the function signatures, memory addresses, or return values.
The code must remain functionally equivalent.

```c
{code}
```

Return only the optimized C code, no explanation."""

    prompts['naive'] = naive_prompt

    # UADL-aware prompts (one per architecture)
    for arch_name in ARCHITECTURES:
        arch_file = os.path.join(ARCH_DIR, f'{arch_name}.yaml')
        with open(arch_file) as f:
            arch_yaml = f.read()
        
        # Also load ISA info
        isa_file = os.path.join(SRC_DIR, 'isa', f'{isa}.yaml')
        with open(isa_file) as f:
            isa_yaml = f.read()
        
        uadl_prompt = f"""Optimize the following C code for a specific processor architecture described below.
The code will run on a cycle-accurate simulator. Your goal is to minimize execution cycles.

## Target Architecture (YAML specification)

### ISA:
```yaml
{isa_yaml}
```

### Microarchitecture:
```yaml
{arch_yaml}
```

## Key Architecture Details to Consider:
"""
        # Add architecture-specific hints derived from YAML
        with open(arch_file) as f:
            arch = yaml.safe_load(f)
        ma = arch['microarch']
        pipeline = ma.get('pipeline', {})
        hazards = pipeline.get('hazards', {})
        data_h = hazards.get('data', {})
        ctrl_h = hazards.get('control', {})
        mem_hier = ma.get('memory_hierarchy', {})
        caches = mem_hier.get('nodes', [])
        
        uadl_prompt += f"""- Pipeline: {len(pipeline.get('stages', []))}-stage in-order
- Data forwarding: {'enabled' if data_h.get('forwarding', False) else 'DISABLED (stalls on data dependencies)'}
- Branch penalty: {ctrl_h.get('branch_penalty', 2)} cycles
"""
        for c in caches:
            if c.get('type') == 'cache':
                uadl_prompt += f"- {c['name']} cache: {c['size']}B, {c['line_size']}B lines, {c['associativity']}-way, hit={c['hit_latency']}cy, miss={c['miss_penalty']}cy\n"
        
        uadl_prompt += f"""
## Optimization Goals:
1. Minimize memory accesses (use registers/locals where possible)
2. Reduce data dependencies between consecutive instructions (avoid stalls)
3. Minimize branch-dependent control flow
4. Optimize memory access patterns for the cache configuration
5. Reduce total instruction count

## Code to optimize:
```c
{code}
```

Return only the optimized C code, no explanation. Do not change memory addresses or return values."""

        # Save prompts
        with open(os.path.join(PROMPTS_DIR, f'{benchmark}_naive_{isa}.txt'), 'w') as f:
            f.write(naive_prompt)
        with open(os.path.join(PROMPTS_DIR, f'{benchmark}_uadl_{arch_name}_{isa}.txt'), 'w') as f:
            f.write(uadl_prompt)
        
        prompts[f'uadl_{arch_name}'] = uadl_prompt
    
    print(f"  Generated prompts for {benchmark} ({isa})")
    return prompts


def run_experiment(benchmark, arch_name, variant, isa='rv32i'):
    """Run a single experiment point."""
    if variant == 'uadl_aware_llm':
        c_file = os.path.join(BENCH_DIR, f'{benchmark}_uadl_aware_{arch_name}.c')
    else:
        c_file = os.path.join(BENCH_DIR, f'{benchmark}_{variant}.c')
    microarch = os.path.join(ARCH_DIR, f'{arch_name}.yaml')
    
    if not os.path.exists(c_file):
        return None
    if not os.path.exists(microarch):
        return None
    
    metrics = compile_and_run(c_file, microarch, isa=isa)
    return metrics


def call_llm_api(prompt):
    """Call Google Gemini API using official SDK. Returns C code."""
    try:
        from google import genai
        client = genai.Client() # Automatically uses GEMINI_API_KEY env var
        response = client.models.generate_content(
            model="gemini-3.1-flash-lite-preview",
            contents=prompt,
        )
        text = response.text
        if not text:
            return None
        
        # Extract just the C code from markdown blocks
        if '```c' in text:
            return text.split('```c')[1].split('```')[0].strip()
        elif '```' in text:
            return text.split('```')[1].split('```')[0].strip()
        return text.strip()
        
    except Exception as e:
        print(f"\nAPI Error: {e}")
        return None


def run_all_experiments(isa='rv32i', auto=False):
    """Run the full experiment matrix and produce results."""
    os.makedirs(RESULTS_DIR, exist_ok=True)
    
    results = []
    
    for benchmark in BENCHMARKS:
        print(f"\n=== Benchmark: {benchmark} (ISA: {isa}) ===")
        # Always generate prompts so we have them loaded in memory / on disk
        # We modify generate_prompts to return a dict of the prompts
        prompts = generate_prompts(benchmark, isa=isa)
        
        # If auto is enabled, call the LLM to generate the files first
        if auto:
            print("\n  [AUTO MODE] Generating optimized code via Gemini API...")
            
            # Generate Naive LLM code
            if 'naive' in prompts:
                print(f"    Requesting 'naive_llm' code...")
                naive_code = call_llm_api(prompts['naive'])
                if naive_code:
                    with open(os.path.join(BENCH_DIR, f'{benchmark}_naive_llm.c'), 'w') as f:
                        f.write(naive_code)
                    print("    -> Saved naive_llm.c")
                else:
                    print("    -> Failed to generate naive_llm.c")
            
            # Generate UADL Aware code (one per architecture)
            for arch_name in ARCHITECTURES:
                prompt_key = f'uadl_{arch_name}'
                if prompt_key in prompts:
                    print(f"    Requesting 'uadl_aware_llm' code for {arch_name} arch...")
                    uadl_code = call_llm_api(prompts[prompt_key])
                    if uadl_code:
                        # Note: Phase C currently only has ONE uadl_aware_llm file slot. 
                        # In a true matrix we'd have `benchmark_uadl_aware_small.c`. 
                        # To keep it simple, we overwrite the `benchmark_uadl_aware_llm.c` 
                        # just before we simulate it for that specific architecture, or we just generate it once.
                        # For now, let's just generate the one for 'large' and use it, or generate it per architecture.
                        pass # handled inside the architecture loop below
        
        for arch_name in ARCHITECTURES:
            print(f"\n  Architecture: {arch_name}")
            
            if auto and f'uadl_{arch_name}' in prompts:
                print(f"    [AUTO MODE] Requesting 'uadl_aware_llm' code optimized specifically for {arch_name}...")
                uadl_code = call_llm_api(prompts[f'uadl_{arch_name}'])
                if uadl_code:
                    with open(os.path.join(BENCH_DIR, f'{benchmark}_uadl_aware_{arch_name}.c'), 'w') as f:
                        f.write(uadl_code)
                    print(f"    -> Specially generated and saved {benchmark}_uadl_aware_{arch_name}.c")
            
            for variant in VARIANTS:
                if variant == 'uadl_aware_llm':
                    c_file = os.path.join(BENCH_DIR, f'{benchmark}_uadl_aware_{arch_name}.c')
                else:
                    c_file = os.path.join(BENCH_DIR, f'{benchmark}_{variant}.c')
                if not os.path.exists(c_file):
                    print(f"    {variant}: SKIPPED (file not found)")
                    continue
                
                print(f"    {variant}: ", end='', flush=True)
                metrics = run_experiment(benchmark, arch_name, variant, isa=isa)
                
                if metrics and 'error' not in metrics:
                    print(f"{metrics['cycles']} cycles, "
                          f"stalls={metrics['stalls']}, "
                          f"flushes={metrics['flushes']}, "
                          f"code_size={metrics.get('instruction_count', '?')} insns")
                    
                    result = {
                        'benchmark': benchmark,
                        'architecture': arch_name,
                        'variant': variant,
                        'isa': isa,
                        'cycles': metrics['cycles'],
                        'stalls': metrics['stalls'],
                        'flushes': metrics['flushes'],
                        'instruction_count': metrics.get('instruction_count', 0),
                        'ipc': f"{metrics.get('ipc', 0):.3f}",
                        'code_size_bytes': metrics.get('code_size_bytes', 0),
                    }
                    
                    # Add cache stats
                    for cache_name in metrics.get('cache_hit_rate', {}):
                        result[f'{cache_name}_hit_rate'] = f"{metrics['cache_hit_rate'][cache_name]:.1f}%"
                        result[f'{cache_name}_hits'] = metrics['cache_hits'][cache_name]
                        result[f'{cache_name}_misses'] = metrics['cache_misses'][cache_name]
                    
                    results.append(result)
                elif metrics and 'error' in metrics:
                    print(f"ERROR: {metrics['error'][:80]}")
                else:
                    print("SKIPPED")
    
    # Write results to CSV
    if results:
        # Collect all possible field names
        all_fields = []
        seen = set()
        for r in results:
            for k in r.keys():
                if k not in seen:
                    all_fields.append(k)
                    seen.add(k)
        
        csv_path = os.path.join(RESULTS_DIR, f'experiment_{isa}_{datetime.now().strftime("%Y%m%d_%H%M%S")}.csv')
        with open(csv_path, 'w', newline='') as f:
            writer = csv.DictWriter(f, fieldnames=all_fields, extrasaction='ignore')
            writer.writeheader()
            for r in results:
                writer.writerow({k: r.get(k, '') for k in all_fields})
        print(f"\nResults saved to: {csv_path}")
        
        # Print summary table
        print_summary(results, isa)
    
    # Write results as JSON too
    json_path = os.path.join(RESULTS_DIR, f'latest_results_{isa}.json')
    with open(json_path, 'w') as f:
        json.dump(results, f, indent=2)
    
    return results


def print_summary(results, isa='rv32i'):
    """Print a formatted summary table."""
    print("\n" + "=" * 80)
    print(f"PHASE C EXPERIMENT RESULTS ({isa.upper()})")
    print("=" * 80)
    
    for bench in BENCHMARKS:
        bench_results = [r for r in results if r['benchmark'] == bench]
        if not bench_results:
            continue
        
        print(f"\n--- {bench.upper()} ---")
        print(f"{'Variant':<20} {'Arch':<8} {'Cycles':>8} {'Stalls':>8} {'Flushes':>8} {'Insns':>8} {'IPC':>8}")
        print("-" * 78)
        
        for r in sorted(bench_results, key=lambda x: (x['architecture'], x['variant'])):
            print(f"{r['variant']:<20} {r['architecture']:<8} {r['cycles']:>8} "
                  f"{r['stalls']:>8} {r['flushes']:>8} "
                  f"{r.get('instruction_count', '?'):>8} {r.get('ipc', '?'):>8}")
        
        # Compute speedups
        for arch in ARCHITECTURES:
            arch_results = [r for r in bench_results if r['architecture'] == arch]
            baseline = next((r for r in arch_results if r['variant'] == 'baseline'), None)
            if baseline:
                print(f"\n  Speedup vs baseline ({arch}):")
                for r in arch_results:
                    if r['variant'] != 'baseline':
                        speedup = baseline['cycles'] / r['cycles'] if r['cycles'] > 0 else 0
                        print(f"    {r['variant']}: {speedup:.2f}x")


if __name__ == '__main__':
    import argparse
    parser = argparse.ArgumentParser(description='UADL Phase C Experiment Runner')
    parser.add_argument('--benchmark', choices=BENCHMARKS, help='Run one benchmark')
    parser.add_argument('--arch', choices=ARCHITECTURES, help='Run one architecture')
    parser.add_argument('--generate-prompts', action='store_true', help='Generate LLM prompts only')
    parser.add_argument('--isa', choices=['rv32i', 'armv7'], default='armv7', help='Target ISA to compile and simulate for')
    parser.add_argument('--auto', action='store_true', help='Automatically call Gemini API to generate optimized code')
    args = parser.parse_args()
    
    if args.generate_prompts:
        for b in BENCHMARKS:
            generate_prompts(b, isa=args.isa)
        print("\nPrompts generated in:", PROMPTS_DIR)
    else:
        if args.benchmark:
            BENCHMARKS[:] = [args.benchmark]
        if args.arch:
            ARCHITECTURES[:] = [args.arch]
        run_all_experiments(isa=args.isa, auto=args.auto)

