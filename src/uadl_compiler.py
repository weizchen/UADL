"""UADL Compiler — Generates C++ simulator from ISA YAML + Microarch YAML + Jinja2 template."""

import yaml
from jinja2 import Environment, FileSystemLoader
import sys
import os
from codegen import generate_behavior_cpp, analyze_behavior

def load_yaml(file_path):
    with open(file_path, 'r') as f:
        return yaml.safe_load(f)

def construct_simulator(isa_path, microarch_path, template_path, output_path):
    isa_model = load_yaml(isa_path)
    microarch_model = load_yaml(microarch_path)
    
    isa = isa_model['isa']
    microarch = microarch_model['microarch']
    
    # Execution model (new universal schema)
    exec_model = microarch.get('execution_model', {'type': 'scalar', 'cores': 1})
    
    # Memory hierarchy (new universal schema)
    mem_hier = microarch.get('memory_hierarchy', {})
    if not mem_hier:
        # Construct from legacy resources for backward compat
        mem_hier = {
            'spaces': [
                {'name': 'instruction', 'size': 16384, 'width': 8},
                {'name': 'data', 'size': 16384, 'width': 8},
            ],
            'nodes': [
                {
                    'name': c['level'], 'type': 'cache',
                    'size': c['size'], 'line_size': c['line_size'],
                    'associativity': c['associativity'],
                    'hit_latency': c['hit_latency'], 'miss_penalty': c['miss_penalty']
                }
                for c in microarch.get('resources', {}).get('caches', [])
            ],
            'scratchpads': [],
            'connections': [],
        }
    
    # Pipeline config
    pipeline_cfg = microarch.get('pipeline', {})
    pipeline_enabled = pipeline_cfg.get('enabled', False)
    
    # Compute pipeline timing from YAML stage definitions
    stages = pipeline_cfg.get('stages', [])
    hazards = pipeline_cfg.get('hazards', {})
    data_hazards = hazards.get('data', {})
    control_hazards = hazards.get('control', {})
    
    num_stages = len(stages) if stages else 5
    
    # Build stage name → index map
    stage_map = {s['name']: i for i, s in enumerate(stages)} if stages else {
        'fetch': 0, 'decode': 1, 'execute': 2, 'memory': 3, 'writeback': 4
    }
    
    execute_idx = stage_map.get('execute', 2)
    memory_idx = stage_map.get('memory', 3)
    writeback_idx = stage_map.get('writeback', num_stages - 1)
    
    # Forwarding source stage (where result is available early)
    forward_from = data_hazards.get('forward_from', 'execute')
    forward_stage_idx = stage_map.get(forward_from, execute_idx)
    forward_latency = data_hazards.get('forward_latency', 0)
    
    # With forwarding: result available at (forward_stage_idx - decode_idx) cycles
    # after instruction enters pipeline. Without: available at writeback.
    forwarding_enabled = data_hazards.get('forwarding', False)
    
    # ALU result availability (cycles after pipeline_cycle):
    #   With forwarding: forward_latency (typically 0)
    #   Without: writeback_idx - execute_idx (typically 2)
    alu_result_ready_fwd = forward_latency
    alu_result_ready_nofwd = writeback_idx - execute_idx
    
    # Load result availability (1 cycle later than ALU due to memory stage):
    #   With forwarding: forward_latency + 1
    #   Without: writeback_idx - execute_idx (same as ALU without fwd)
    load_result_ready_fwd = forward_latency + 1
    load_result_ready_nofwd = writeback_idx - execute_idx
    
    branch_penalty = control_hazards.get('branch_penalty', 2)
    branch_strategy = control_hazards.get('strategy', 'flush')
    
    pipeline_timing = {
        'num_stages': num_stages,
        'stage_map': stage_map,
        'stages': stages,
        'execute_idx': execute_idx,
        'memory_idx': memory_idx,
        'writeback_idx': writeback_idx,
        'forwarding_enabled': forwarding_enabled,
        'alu_result_ready': alu_result_ready_fwd if forwarding_enabled else alu_result_ready_nofwd,
        'load_result_ready': load_result_ready_fwd if forwarding_enabled else load_result_ready_nofwd,
        'branch_penalty': branch_penalty,
        'branch_strategy': branch_strategy,
    }
    
    # Process memory hierarchy connections into cache chains
    connections = mem_hier.get('connections', [])
    node_map = {n['name']: n for n in mem_hier.get('nodes', [])}
    
    # Build adjacency list from connections
    adj = {}
    for conn in connections:
        adj.setdefault(conn['from'], []).append(conn['to'])
    
    # For each address space, find the chain of cache nodes it traverses
    cache_chains = {}
    for space in mem_hier.get('spaces', []):
        chain = []
        current = space['name']
        visited = set()
        while current in adj and current not in visited:
            visited.add(current)
            nexts = adj[current]
            for n in nexts:
                if n in node_map:   # it's a cache/memory node
                    chain.append(n)
                    current = n
                    break
            else:
                break
        cache_chains[space['name']] = chain
    
    mem_hier['_cache_chains'] = cache_chains
    
    # Merge into architecture dict
    architecture = {
        'name': isa['name'],
        'encoding': isa.get('encoding', 'riscv32'),
        'encoding_fields': isa.get('encoding_fields', None),
        'word_size': isa.get('word_size', 32),
        'execution_model': exec_model,
        'memory_hierarchy': mem_hier,
        'pipeline': pipeline_cfg,
        'pipeline_timing': pipeline_timing,
        'resources': {
            'cores': microarch.get('resources', {}).get('cores', exec_model.get('cores', 1)),
            'caches': microarch.get('resources', {}).get('caches', []),
            'registers': isa.get('registers', []),
            'memory': microarch.get('resources', {}).get('memory', []),
        },
        'instructions': isa.get('instructions', []),
    }
    
    # Legacy GPU compat
    if exec_model.get('type') == 'simt':
        architecture['gpu'] = microarch.get('gpu', {
            'sm_count': exec_model.get('compute_units', 2),
            'warps_per_sm': exec_model.get('warps_per_unit', 4),
            'warp_size': exec_model.get('threads_per_warp', 8),
            'registers_per_thread': exec_model.get('registers_per_thread', 16),
            'scheduler': exec_model.get('scheduler', 'round_robin'),
        })
    
    # Pipeline flag
    architecture['_pipeline_enabled'] = pipeline_enabled
    
    # Pre-generate C++ and pipeline metadata for each instruction
    for inst in architecture['instructions']:
        fmt = inst.get('format', '')
        
        # Determine operands based on format (ISA-agnostic via format type)
        if fmt == 'R':
            operands = ['rd', 'rs1', 'rs2']
        elif fmt in ('I', 'IR'):
            operands = ['rd', 'rs1', 'imm']
        elif fmt == 'S':
            operands = ['rs1', 'rs2', 'imm']
        elif fmt == 'B':
            operands = ['rs1', 'rs2', 'imm']
        elif fmt in ('U', 'J'):
            operands = ['rd', 'imm']
        # ARM formats
        elif fmt == 'DP':
            operands = ['rd', 'rn', 'rm']
        elif fmt == 'DPI':
            operands = ['rd', 'rn', 'imm']
        elif fmt == 'LS':
            operands = ['rd', 'rn', 'imm']
        elif fmt in ('BR',):
            operands = ['imm']
        elif fmt == 'BX':
            operands = ['rm']
        elif fmt == 'SVC':
            operands = []
        # GPU formats
        elif fmt == 'RRR':
            operands = ['rd', 'rs1', 'rs2']
        elif fmt == 'RRI':
            operands = ['rd', 'rs1', 'imm']
        elif fmt == 'RI':
            operands = ['rd', 'imm']
        elif fmt == 'MEM':
            operands = ['rd', 'rs1', 'imm']
        elif fmt in ('SYNC', 'CTRL'):
            operands = []
        else:
            operands = []
        
        inst['_generated_cpp'] = generate_behavior_cpp(
            inst.get('behavior', []), operands
        )
        inst['_pipeline'] = analyze_behavior(
            inst.get('behavior', []), operands
        )
    
    # Generate C++ — always use the universal template
    template_dir = os.path.dirname(template_path)
    env = Environment(loader=FileSystemLoader(template_dir))
    template = env.get_template('sim_universal.j2')
    rendered = template.render(architecture=architecture)
    
    with open(output_path, 'w') as f:
        f.write(rendered)
    
    print(f"Simulator generated: {output_path}")
def construct_from_architecture(arch_path, output_path):
    """Build simulator from a single architecture.yaml linker file."""
    arch_model = load_yaml(arch_path)
    arch = arch_model['architecture']
    
    # ISA and microarch paths are relative to the src/ directory (parent of architectures/)
    base_dir = os.path.dirname(os.path.dirname(os.path.abspath(arch_path)))
    isa_path = os.path.join(base_dir, arch['isa'])
    microarch_path = os.path.join(base_dir, arch['microarch'])
    template_path = os.path.join(base_dir, 'sim_universal.j2')
    
    construct_simulator(isa_path, microarch_path, template_path, output_path)

if __name__ == "__main__":
    if len(sys.argv) == 3:
        # Single architecture.yaml mode
        construct_from_architecture(sys.argv[1], sys.argv[2])
    elif len(sys.argv) >= 5:
        # Legacy mode: isa.yaml microarch.yaml template.j2 output.cpp
        construct_simulator(sys.argv[1], sys.argv[2], sys.argv[3], sys.argv[4])
    else:
        print("Usage:")
        print("  python uadl_compiler.py <architecture.yaml> <output.cpp>")
        print("  python uadl_compiler.py <isa.yaml> <microarch.yaml> <template.j2> <output.cpp>")
        sys.exit(1)
