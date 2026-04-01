"""
UADL Phase B: LLM Architecture Search

Genetic-style architecture exploration:
1. Start with a base microarchitecture YAML
2. LLM reads YAML + benchmark scores → proposes YAML mutations
3. Simulator is regenerated, benchmarks rerun, configs scored
4. Top-k configs retained, repeat for N generations

Supports two modes:
  - Auto mode: uses an LLM API (set UADL_LLM_API_KEY env var)
  - Manual mode: prints prompt, user pastes LLM response

Usage:
  python llm_search.py                          # Manual mode
  python llm_search.py --generations 5          # 5 generations
  python llm_search.py --auto                   # API mode (needs key)
  python llm_search.py --base-config custom.yaml
"""

import subprocess
import os
import sys
import json
import yaml
import copy
from google import genai

def call_llm_api(prompt):
    """Call Google Gemini API using official SDK. Returns YAML text."""
    try:
        client = genai.Client() # Automatically uses GEMINI_API_KEY env var
        response = client.models.generate_content(
            model="gemini-3.1-flash-lite-preview",
            contents=prompt,
        )
        text = response.text
        if not text:
            return None
        
        # Extract just the YAML from markdown blocks
        if '```yaml' in text:
            return text.split('```yaml')[1].split('```')[0].strip()
        elif '```' in text:
            return text.split('```')[1].split('```')[0].strip()
        return text.strip()
        
    except Exception as e:
        print(f"\nAPI Error: {e}")
        return None

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
ISA_YAML = os.path.join(SCRIPT_DIR, 'isa', 'rv32i.yaml')
TEMPLATE = os.path.join(SCRIPT_DIR, 'sim_universal.j2')
RESULTS_DIR = os.path.join(SCRIPT_DIR, 'search_results')

# Default base configuration
DEFAULT_BASE = os.path.join(SCRIPT_DIR, 'microarch', 'default.yaml')

# Benchmark suite — each stresses different micro-architectural features
BENCHMARKS = {
    'fibonacci': {
        'source': os.path.join(SCRIPT_DIR, 'tests', 'rv32i', 'fibonacci.s'),
        'type': 'asm',
        'stresses': 'branch prediction, data hazards',
    },
    'c_sort': {
        'source': os.path.join(SCRIPT_DIR, 'tests', 'rv32i', 'c_sort.c'),
        'type': 'c',
        'stresses': 'branch-heavy, memory access patterns',
    },
    'c_loop': {
        'source': os.path.join(SCRIPT_DIR, 'tests', 'rv32i', 'c_loop.c'),
        'type': 'c',
        'stresses': 'loop overhead, pipeline throughput',
    },
    'function_call': {
        'source': os.path.join(SCRIPT_DIR, 'tests', 'rv32i', 'function_call.s'),
        'type': 'asm',
        'stresses': 'function call overhead, stack, branching',
    },
    'memory': {
        'source': os.path.join(SCRIPT_DIR, 'tests', 'rv32i', 'memory.s'),
        'type': 'asm',
        'stresses': 'load/store, cache hierarchy',
    },
}


def find_llvm_tool(name):
    import shutil
    tool = shutil.which(name)
    if tool:
        return tool
    for v in range(20, 12, -1):
        tool = shutil.which(f'{name}-{v}')
        if tool:
            return tool
    brew_path = f'/opt/homebrew/opt/llvm/bin/{name}'
    if os.path.exists(brew_path):
        return brew_path
    return name


def build_simulator(microarch_yaml, sim_name='tmp_search_sim'):
    """Build a simulator from a microarch YAML config."""
    cpp_out = os.path.join(RESULTS_DIR, f'{sim_name}.cpp')
    sim_out = os.path.join(RESULTS_DIR, sim_name)
    
    r = subprocess.run(
        ['python', os.path.join(SCRIPT_DIR, 'uadl_compiler.py'),
         ISA_YAML, microarch_yaml, TEMPLATE, cpp_out],
        capture_output=True, text=True
    )
    if r.returncode != 0:
        return None, f'Compiler: {r.stderr[:200]}'
    
    r = subprocess.run(
        f'g++ -O2 -std=c++17 {cpp_out} -o {sim_out}',
        shell=True, capture_output=True, text=True
    )
    if r.returncode != 0:
        return None, f'g++: {r.stderr[:200]}'
    
    return sim_out, None


def compile_benchmark(bench_name, bench_info):
    """Compile a benchmark to binary. Returns path to .bin or None."""
    clang = find_llvm_tool('clang')
    lld = find_llvm_tool('ld.lld')
    clang_target = '--target=riscv32 -march=rv32i -mabi=ilp32'
    crt0 = os.path.join(SCRIPT_DIR, 'crt0_rv32i.s')
    
    base = os.path.join(RESULTS_DIR, f'bench_{bench_name}')
    bin_path = base + '.bin'
    
    if os.path.exists(bin_path):
        return bin_path  # Already compiled
    
    source = bench_info['source']
    
    if bench_info['type'] == 'asm':
        obj = base + '.o'
        r = subprocess.run(
            f'{clang} {clang_target} -c -o {obj} {source}',
            shell=True, capture_output=True, text=True
        )
        if r.returncode != 0:
            return None
        
        elf = base + '.elf'
        r = subprocess.run(
            f'{lld} -m elf32lriscv --image-base=0 -Ttext=0 -o {elf} {obj}',
            shell=True, capture_output=True, text=True
        )
        if r.returncode != 0:
            return None
        
        r = subprocess.run(
            f'{sys.executable} {os.path.join(SCRIPT_DIR, "elf2mem.py")} {elf} {bin_path}',
            shell=True, capture_output=True, text=True
        )
        for f in [obj, elf]:
            if os.path.exists(f): os.remove(f)
        return bin_path if r.returncode == 0 else None
    
    elif bench_info['type'] == 'c':
        crt0_o = base + '_crt0.o'
        obj = base + '.o'
        elf = base + '.elf'
        
        r = subprocess.run(
            f'{clang} {clang_target} -c -o {crt0_o} {crt0}',
            shell=True, capture_output=True, text=True
        )
        if r.returncode != 0:
            return None
        
        r = subprocess.run(
            f'{clang} {clang_target} -c -O1 -fno-builtin -nostdlib -o {obj} {source}',
            shell=True, capture_output=True, text=True
        )
        if r.returncode != 0:
            return None
        
        r = subprocess.run(
            f'{lld} -m elf32lriscv --image-base=0 -Ttext=0 -o {elf} {crt0_o} {obj}',
            shell=True, capture_output=True, text=True
        )
        if r.returncode != 0:
            return None
        
        r = subprocess.run(
            f'{sys.executable} {os.path.join(SCRIPT_DIR, "elf2mem.py")} {elf} {bin_path}',
            shell=True, capture_output=True, text=True
        )
        for f in [crt0_o, obj, elf]:
            if os.path.exists(f): os.remove(f)
        return bin_path if r.returncode == 0 else None
    
    return None


def run_benchmark(sim_path, bin_path):
    """Run a benchmark and extract cycle count."""
    try:
        r = subprocess.run(
            [sim_path, bin_path], capture_output=True, text=True, timeout=30
        )
    except subprocess.TimeoutExpired:
        return None
    
    for line in r.stdout.split('\n'):
        m = re.search(r'Total (?:Workload )?Cycles:\s*(\d+)', line)
        if m:
            return int(m.group(1))
    return None


def score_config(microarch_yaml, compiled_benchmarks):
    """Build sim from config, run all benchmarks, return score dict."""
    sim_path, err = build_simulator(microarch_yaml)
    if not sim_path:
        return {'error': err, 'total_cycles': float('inf'), 'cost': float('inf')}
    
    results = {}
    total_cycles = 0
    
    for name, bin_path in compiled_benchmarks.items():
        if bin_path:
            cycles = run_benchmark(sim_path, bin_path)
            results[name] = cycles
            if cycles:
                total_cycles += cycles
            else:
                total_cycles += 999999  # Penalty for failure
        else:
            results[name] = None
            total_cycles += 999999
    
    # Compute area/cost from YAML
    with open(microarch_yaml) as f:
        cfg = yaml.safe_load(f)
    ma = cfg['microarch']
    
    cost = 0
    # Cache cost
    for node in ma.get('memory_hierarchy', {}).get('nodes', []):
        if node.get('type') == 'cache':
            cost += (node.get('size', 0) / 1024) * 10  # $10/KB
            cost += node.get('associativity', 1) * 2     # complexity
    
    # Pipeline cost
    stages = ma.get('pipeline', {}).get('stages', [])
    cost += len(stages) * 5
    
    # Forwarding cost
    if ma.get('pipeline', {}).get('hazards', {}).get('data', {}).get('forwarding', False):
        cost += 10  # Forwarding hardware cost
    
    score = total_cycles + cost * 100  # Weighted sum
    
    return {
        'benchmarks': results,
        'total_cycles': total_cycles,
        'cost': cost,
        'score': score,
    }


def generate_llm_prompt(current_yaml, current_score, history, generation):
    """Generate the prompt to send to the LLM."""
    prompt = f"""You are an expert computer architect. You are optimizing a processor's microarchitecture to minimize total execution cycles across a benchmark suite while keeping hardware cost reasonable.

## Current Microarchitecture (YAML):
```yaml
{current_yaml}
```

## Current Performance:
- Total cycles: {current_score['total_cycles']}
- Hardware cost: {current_score['cost']:.1f}
- Composite score: {current_score['score']:.1f} (lower is better)
- Per-benchmark cycles:
"""
    for name, cycles in current_score.get('benchmarks', {}).items():
        prompt += f"  - {name}: {cycles} cycles\n"
    
    if history:
        prompt += "\n## Previous Attempts (best → worst):\n"
        for i, h in enumerate(sorted(history, key=lambda x: x['score'])[:5]):
            prompt += f"  {i+1}. Score={h['score']:.0f} (cycles={h['total_cycles']}, cost={h['cost']:.1f})\n"
    
    prompt += f"""
## Generation {generation} — Your Task:

Propose a MODIFIED microarchitecture YAML that will achieve a LOWER score.

Tunable knobs:
1. **Pipeline hazards**: forwarding (true/false), forward_from stage, forward_latency
2. **Branch penalty**: 0-5 cycles
3. **Cache L1**: size (64-4096B), line_size (8-64B), associativity (1-8), hit_latency, miss_penalty
4. **Cache L2**: add/remove L2 cache, configure size and timing
5. **Pipeline stages**: add/remove stages, change latencies

Rules:
- Output ONLY valid YAML (the full microarch section)
- Keep `execution_model.type: "scalar"` and `cores: 1`
- Keep `memory_hierarchy.spaces` unchanged
- The YAML must be parseable by the UADL compiler

Return ONLY the YAML between ```yaml and ``` markers. No explanation."""

    return prompt


def parse_llm_response(response_text):
    """Extract YAML from LLM response."""
    # Find YAML between markers
    m = re.search(r'```ya?ml\s*\n(.*?)```', response_text, re.DOTALL)
    if m:
        yaml_text = m.group(1)
    else:
        yaml_text = response_text
    
    # Validate it parses
    try:
        cfg = yaml.safe_load(yaml_text)
        if 'microarch' not in cfg:
            return None, "Missing 'microarch' key"
        return yaml_text, None
    except yaml.YAMLError as e:
        return None, f"YAML parse error: {e}"


def run_search(base_config, generations=5, top_k=3, auto_mode=False):
    """Run the architecture search loop."""
    os.makedirs(RESULTS_DIR, exist_ok=True)
    
    # Step 1: Compile all benchmarks (only once)
    print("Compiling benchmarks...")
    compiled = {}
    for name, info in BENCHMARKS.items():
        bin_path = compile_benchmark(name, info)
        compiled[name] = bin_path
        status = "OK" if bin_path else "FAIL"
        print(f"  {name}: {status}")
    
    # Step 2: Score baseline config
    print(f"\nScoring baseline config: {base_config}")
    baseline_score = score_config(base_config, compiled)
    if 'error' in baseline_score:
        print(f"ERROR: {baseline_score['error']}")
        return
    
    print(f"  Total cycles: {baseline_score['total_cycles']}")
    print(f"  Cost: {baseline_score['cost']:.1f}")
    print(f"  Score: {baseline_score['score']:.1f}")
    for name, cycles in baseline_score['benchmarks'].items():
        print(f"    {name}: {cycles}")
    
    with open(base_config) as f:
        current_yaml = f.read()
    current_score = baseline_score
    
    history = [{'score': baseline_score['score'], 
                'total_cycles': baseline_score['total_cycles'],
                'cost': baseline_score['cost'],
                'generation': 0, 'label': 'baseline'}]
    
    best_score = baseline_score['score']
    best_yaml = current_yaml
    best_gen = 0
    
    # Step 3: Search loop
    for gen in range(1, generations + 1):
        print(f"\n{'='*60}")
        print(f"GENERATION {gen}/{generations}")
        print(f"{'='*60}")
        
        prompt = generate_llm_prompt(current_yaml, current_score, history, gen)
        
        if auto_mode:
            # API mode
            print("  [AUTO MODE] Requesting new architecture from Gemini API...")
            response = call_llm_api(prompt)
            if not response:
                print("  API failed. Falling back to manual mode...")
                auto_mode = False
        
        if not auto_mode:
            # Manual mode — print prompt, wait for input
            prompt_file = os.path.join(RESULTS_DIR, f'prompt_gen{gen}.txt')
            with open(prompt_file, 'w') as f:
                f.write(prompt)
            
            print(f"\nPrompt saved to: {prompt_file}")
            print("\nPaste the LLM's YAML response below (end with 'END' on a new line):")
            
            lines = []
            while True:
                try:
                    line = input()
                    if line.strip() == 'END':
                        break
                    lines.append(line)
                except EOFError:
                    break
            
            response = '\n'.join(lines)
        
        # Parse response
        yaml_text, err = parse_llm_response(response)
        if err:
            print(f"  Parse error: {err}")
            print("  Skipping this generation.")
            continue
        
        # Save and score the proposed config
        config_file = os.path.join(RESULTS_DIR, f'config_gen{gen}.yaml')
        with open(config_file, 'w') as f:
            f.write(yaml_text)
        
        print(f"  Scoring proposed config...")
        new_score = score_config(config_file, compiled)
        
        if 'error' in new_score:
            print(f"  ERROR: {new_score['error']}")
            continue
        
        print(f"  Total cycles: {new_score['total_cycles']} (was {current_score['total_cycles']})")
        print(f"  Cost: {new_score['cost']:.1f} (was {current_score['cost']:.1f})")
        print(f"  Score: {new_score['score']:.1f} (was {current_score['score']:.1f})")
        
        improvement = current_score['score'] - new_score['score']
        if improvement > 0:
            print(f"  ✅ Improvement: {improvement:.1f} ({improvement/current_score['score']*100:.1f}%)")
        else:
            print(f"  ❌ Worse by: {-improvement:.1f}")
        
        for name in BENCHMARKS:
            old = current_score['benchmarks'].get(name, '?')
            new = new_score['benchmarks'].get(name, '?')
            delta = ""
            if isinstance(old, int) and isinstance(new, int):
                d = new - old
                delta = f" ({'+' if d > 0 else ''}{d})"
            print(f"    {name}: {old} → {new}{delta}")
        
        history.append({
            'score': new_score['score'],
            'total_cycles': new_score['total_cycles'],
            'cost': new_score['cost'],
            'generation': gen,
        })
        
        # Accept if better (greedy)
        if new_score['score'] < current_score['score']:
            current_yaml = yaml_text
            current_score = new_score
            
            if new_score['score'] < best_score:
                best_score = new_score['score']
                best_yaml = yaml_text
                best_gen = gen
    
    # Final summary
    print(f"\n{'='*60}")
    print(f"SEARCH COMPLETE — {generations} generations")
    print(f"{'='*60}")
    print(f"Baseline score: {baseline_score['score']:.1f}")
    print(f"Best score:     {best_score:.1f} (gen {best_gen})")
    print(f"Improvement:    {(baseline_score['score'] - best_score)/baseline_score['score']*100:.1f}%")
    
    # Save best config
    best_file = os.path.join(RESULTS_DIR, 'best_config.yaml')
    with open(best_file, 'w') as f:
        f.write(best_yaml)
    print(f"\nBest config saved: {best_file}")
    
    # Save full history
    history_file = os.path.join(RESULTS_DIR, 'search_history.json')
    with open(history_file, 'w') as f:
        json.dump(history, f, indent=2)
    print(f"History saved: {history_file}")

def demo_mutations(base_config):
    """Run a demo search with predefined mutations (no LLM needed)."""
    os.makedirs(RESULTS_DIR, exist_ok=True)
    
    print("=" * 60)
    print("DEMO MODE: Predefined architecture mutations")
    print("=" * 60)
    
    # Compile benchmarks once
    print("\nCompiling benchmarks...")
    compiled = {}
    for name, info in BENCHMARKS.items():
        bin_path = compile_benchmark(name, info)
        compiled[name] = bin_path
        print(f"  {name}: {'OK' if bin_path else 'FAIL'}")
    
    # Load and score baseline
    print(f"\nScoring baseline: {base_config}")
    baseline = score_config(base_config, compiled)
    with open(base_config) as f:
        base_yaml = yaml.safe_load(f)
    
    # Define mutations that an LLM might propose
    mutations = [
        {
            'name': 'Disable forwarding (save hardware cost)',
            'changes': lambda cfg: _set_nested(cfg, 
                ['microarch', 'pipeline', 'hazards', 'data', 'forwarding'], False),
        },
        {
            'name': 'Branch penalty 1 (better predictor)',
            'changes': lambda cfg: _set_nested(cfg,
                ['microarch', 'pipeline', 'hazards', 'control', 'branch_penalty'], 1),
        },
        {
            'name': 'Smaller L1 cache (128B, direct-mapped)',
            'changes': lambda cfg: _set_cache(cfg, 'L1', size=128, associativity=1),
        },
        {
            'name': 'Larger L1 cache (2048B, 4-way)',
            'changes': lambda cfg: _set_cache(cfg, 'L1', size=2048, associativity=4),
        },
        {
            'name': 'Optimal: forwarding + penalty 1 + 512B 2-way L1',
            'changes': lambda cfg: [
                _set_nested(cfg, ['microarch', 'pipeline', 'hazards', 'data', 'forwarding'], True),
                _set_nested(cfg, ['microarch', 'pipeline', 'hazards', 'control', 'branch_penalty'], 1),
                _set_cache(cfg, 'L1', size=512, associativity=2, line_size=16),
            ],
        },
    ]
    
    # Score each mutation
    results = [{'name': 'baseline', 'score': baseline}]
    
    print(f"\n{'Variant':<45} {'Cycles':>8} {'Cost':>8} {'Score':>10}")
    print("-" * 75)
    print(f"{'baseline':<45} {baseline['total_cycles']:>8} {baseline['cost']:>8.1f} {baseline['score']:>10.1f}")
    
    for mut in mutations:
        cfg = copy.deepcopy(base_yaml)
        mut['changes'](cfg)
        
        mut_file = os.path.join(RESULTS_DIR, f"demo_{mut['name'][:20].replace(' ', '_')}.yaml")
        with open(mut_file, 'w') as f:
            yaml.dump(cfg, f, default_flow_style=False)
        
        score = score_config(mut_file, compiled)
        results.append({'name': mut['name'], 'score': score})
        
        if 'error' in score:
            print(f"{mut['name']:<45} {'ERR':>8} {'ERR':>8} {'ERR':>10}")
        else:
            delta = baseline['score'] - score['score']
            marker = '✅' if delta > 0 else '❌'
            print(f"{mut['name']:<45} {score['total_cycles']:>8} {score['cost']:>8.1f} {score['score']:>10.1f}  {marker} {delta:+.0f}")
    
    # Find best
    valid = [r for r in results if 'error' not in r['score']]
    best = min(valid, key=lambda x: x['score']['score'])
    
    print(f"\n{'='*75}")
    print(f"Best: {best['name']} (score={best['score']['score']:.1f})")
    improvement = (baseline['score'] - best['score']['score']) / baseline['score'] * 100
    print(f"Improvement over baseline: {improvement:.1f}%")
    
    # Print per-benchmark breakdown for best
    print(f"\nPer-benchmark breakdown (best vs baseline):")
    for name in BENCHMARKS:
        bc = baseline['benchmarks'].get(name, '?')
        mc = best['score']['benchmarks'].get(name, '?')
        if isinstance(bc, int) and isinstance(mc, int):
            d = mc - bc
            print(f"  {name}: {bc} → {mc} ({'+' if d > 0 else ''}{d})")
    
    # Save history
    history = [{'name': r['name'], 'total_cycles': r['score'].get('total_cycles'),
                'cost': r['score'].get('cost'), 'score': r['score'].get('score')} 
               for r in valid]
    with open(os.path.join(RESULTS_DIR, 'demo_results.json'), 'w') as f:
        json.dump(history, f, indent=2)
    print(f"\nResults saved: {os.path.join(RESULTS_DIR, 'demo_results.json')}")


def _set_nested(d, keys, value):
    """Set a nested dict value by key path."""
    for k in keys[:-1]:
        d = d.setdefault(k, {})
    d[keys[-1]] = value


def _set_cache(cfg, cache_name, **kwargs):
    """Modify a cache node's parameters."""
    nodes = cfg.get('microarch', {}).get('memory_hierarchy', {}).get('nodes', [])
    for node in nodes:
        if node.get('name') == cache_name:
            node.update(kwargs)
            break
    # Also update resources.caches if present
    caches = cfg.get('microarch', {}).get('resources', {}).get('caches', [])
    for c in caches:
        if c.get('level') == cache_name:
            c.update(kwargs)
            break


if __name__ == '__main__':
    import argparse
    parser = argparse.ArgumentParser(description='UADL Phase B: LLM Architecture Search')
    parser.add_argument('--base-config', default=DEFAULT_BASE,
                        help='Base microarch YAML to start from')
    parser.add_argument('--generations', type=int, default=5,
                        help='Number of search generations')
    parser.add_argument('--no-auto', action='store_true',
                        help='Disable LLM API and use manual mode')
    parser.add_argument('--score-only', action='store_true',
                        help='Score the base config and exit')
    parser.add_argument('--demo', action='store_true',
                        help='Run demo with predefined mutations (no LLM needed)')
    args = parser.parse_args()
    
    if args.demo:
        demo_mutations(args.base_config)
    elif args.score_only:
        os.makedirs(RESULTS_DIR, exist_ok=True)
        print("Compiling benchmarks...")
        compiled = {}
        for name, info in BENCHMARKS.items():
            bin_path = compile_benchmark(name, info)
            compiled[name] = bin_path
            print(f"  {name}: {'OK' if bin_path else 'FAIL'}")
        
        print(f"\nScoring: {args.base_config}")
        score = score_config(args.base_config, compiled)
        if 'error' in score:
            print(f"ERROR: {score['error']}")
        else:
            print(f"  Total cycles: {score['total_cycles']}")
            print(f"  Cost: {score['cost']:.1f}")
            print(f"  Score: {score['score']:.1f}")
            for name, cycles in score['benchmarks'].items():
                print(f"    {name}: {cycles}")
    else:
        run_search(args.base_config, args.generations, auto_mode=not args.no_auto)

