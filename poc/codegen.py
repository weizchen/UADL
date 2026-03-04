"""
UADL Micro-Op Code Generator

Walks the structured `behavior` list from cpu.yaml and emits
correct C++ code for each instruction's case block in the simulator.

This replaces the fragile Jinja2 `replace()` chain that did textual
substitution of register names.
"""

import re

# Mapping from UADL register/resource names to their C++ expressions.
# Registers live on the core struct, memory and thread_queue are global.
RESOURCE_MAP = {
    'PC':    'core.PC',
    'SP':    'core.SP',
    'ACC':   'core.R[0]',   # backward compat: ACC is R[0]
    'halt':  'core.halt',
}

# Pattern: R[index] where index is a number or operand name
_REG_ARRAY_RE = re.compile(r'^R\[(\w+)\]$')

def _resolve(name, operands):
    """Resolve a name to its C++ expression.
    
    - R[N] (literal index) → core.R[N]
    - R[op] (operand name) → core.R[op] (runtime index)
    - Known register name → core-prefixed version
    - Operand name → local variable
    - _tmp → temp variable
    """
    # Check for R[x] pattern (register array access)
    m = _REG_ARRAY_RE.match(name)
    if m:
        index = m.group(1)
        return f'core.R[{index}]'
    
    if name in RESOURCE_MAP:
        return RESOURCE_MAP[name]
    if name in operands:
        return name  # operand local variable
    if name.startswith('_'):
        return name  # temp variable
    return name

def generate_behavior_cpp(behavior_list, operands, indent='            '):
    """Generate C++ code from a list of behavior micro-ops.
    
    Args:
        behavior_list: List of dicts, each with 'op' and op-specific fields.
        operands: List of operand names for this instruction (e.g. ['imm'], ['addr']).
        indent: Whitespace prefix for each generated line.
    
    Returns:
        A string of C++ code implementing the behavior.
    """
    lines = []
    declared_temps = set()
    
    for step in behavior_list:
        op = step['op']
        
        if op == 'set':
            # dst = src
            dst = _resolve(step['dst'], operands)
            src = _resolve(step['src'], operands)
            lines.append(f'{dst} = {src};')
            
        elif op == 'load':
            # dst = DataMem[addr]
            dst = _resolve(step['dst'], operands)
            addr = _resolve(step['addr'], operands)
            # Declare temp variables if needed
            if step['dst'].startswith('_') and step['dst'] not in declared_temps:
                lines.append(f'uint32_t {dst} = DataMem[{addr}];')
                declared_temps.add(step['dst'])
            else:
                lines.append(f'{dst} = DataMem[{addr}];')
            
        elif op == 'store':
            # DataMem[addr] = src
            src = _resolve(step['src'], operands)
            addr = _resolve(step['addr'], operands)
            lines.append(f'DataMem[{addr}] = {src};')
            
        elif op == 'add':
            # dst = src1 + src2
            dst = _resolve(step['dst'], operands)
            src1 = _resolve(step['src1'], operands)
            src2 = _resolve(step['src2'], operands)
            lines.append(f'{dst} = {src1} + {src2};')
            
        elif op == 'sub':
            # dst = src1 - src2
            dst = _resolve(step['dst'], operands)
            src1 = _resolve(step['src1'], operands)
            src2 = _resolve(step['src2'], operands)
            lines.append(f'{dst} = {src1} - {src2};')
            
        elif op == 'mul':
            # dst = src1 * src2
            dst = _resolve(step['dst'], operands)
            src1 = _resolve(step['src1'], operands)
            src2 = _resolve(step['src2'], operands)
            lines.append(f'{dst} = {src1} * {src2};')
            
        elif op == 'branch_if_zero':
            # if (test == 0) { PC = target; _branch_taken; }
            test = _resolve(step['test'], operands)
            target = _resolve(step['target'], operands)
            lines.append(f'if ({test} == 0) {{ core.PC = {target}; _branch_taken = true; }}')
            
        elif op == 'branch_if_not_zero':
            # if (test != 0) { PC = target; _branch_taken; }
            test = _resolve(step['test'], operands)
            target = _resolve(step['target'], operands)
            lines.append(f'if ({test} != 0) {{ core.PC = {target}; _branch_taken = true; }}')
            
        elif op == 'jump':
            # PC = target; (unconditional)
            target = _resolve(step['target'], operands)
            lines.append(f'core.PC = {target};')
            lines.append('_branch_taken = true;')
            
        elif op == 'fork':
            # thread_queue.push_back(target)
            target = _resolve(step['target'], operands)
            lines.append(f'thread_queue.push_back({target});')
            
        elif op == 'halt':
            lines.append('core.halt = true;')
            
        else:
            lines.append(f'// ERROR: Unknown micro-op "{op}"')
    
    return '\n'.join(indent + line for line in lines)


def _reg_index(name, operands):
    """Get the C++ register index expression for pipeline scoreboard.
    
    Returns None if the name is not a register.
    """
    if name == 'ACC':
        return '0'
    m = _REG_ARRAY_RE.match(name)
    if m:
        return m.group(1)  # 'rd', 'rs1', or a literal like '3'
    return None


def analyze_behavior(behavior_list, operands):
    """Analyze register reads/writes for pipeline hazard detection.
    
    Returns a dict with:
        src_indices: list of C++ expressions for source register indices
        dst_index: C++ expression for dest register index, or None
        is_load: True if instruction loads from memory
        is_branch: True if instruction is a branch or jump
    """
    src_indices = []
    dst_index = None
    is_load = False
    is_branch = False
    
    for step in behavior_list:
        op = step['op']
        
        if op == 'set':
            idx = _reg_index(step['dst'], operands)
            if idx is not None:
                dst_index = idx
            idx = _reg_index(step.get('src', ''), operands)
            if idx is not None and idx not in src_indices:
                src_indices.append(idx)
                
        elif op == 'load':
            is_load = True
            idx = _reg_index(step['dst'], operands)
            if idx is not None:
                dst_index = idx
                
        elif op == 'store':
            idx = _reg_index(step['src'], operands)
            if idx is not None and idx not in src_indices:
                src_indices.append(idx)
                
        elif op in ('add', 'sub', 'mul'):
            idx = _reg_index(step['dst'], operands)
            if idx is not None:
                dst_index = idx
            for src_key in ('src1', 'src2'):
                idx = _reg_index(step.get(src_key, ''), operands)
                if idx is not None and idx not in src_indices:
                    src_indices.append(idx)
                    
        elif op in ('branch_if_zero', 'branch_if_not_zero'):
            is_branch = True
            idx = _reg_index(step['test'], operands)
            if idx is not None and idx not in src_indices:
                src_indices.append(idx)
                
        elif op == 'jump':
            is_branch = True
    
    return {
        'src_indices': src_indices,
        'dst_index': dst_index,
        'is_load': is_load,
        'is_branch': is_branch,
    }
