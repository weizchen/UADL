"""
UADL Micro-Op Code Generator for RISC-V

Walks the structured `behavior` list from rv32i.yaml and emits
correct C++ code for each instruction's execution block.

Ported from POC codegen.py with additional micro-ops for RISC-V:
- Bitwise: and_op, or_op, xor_op
- Shifts: sll, srl, sra
- Comparisons: slt, sltu
- Branches: branch_eq, branch_ne, branch_lt, branch_ge, branch_ltu, branch_geu
- Memory: load_word, store_word (register+offset addressing)
- Jumps: jal, jalr
- Upper imm: lui, auipc
- System: ecall
"""

import re

# Pattern: x[index] or r[index] where index is a register field name or a number
_REG_ARRAY_RE = re.compile(r'^([xr])\[(\w+)\]$')

def _resolve(name, operands):
    """Resolve a YAML name to its C++ expression."""
    m = _REG_ARRAY_RE.match(name)
    if m:
        reg_name = m.group(1)  # 'x' or 'r'
        index = m.group(2)
        return f'core.{reg_name}[{index}]'
    
    if name == 'PC':
        return 'core.PC'
    if name in operands:
        return name
    if name.startswith('_'):
        return name
    return name

def _reg_index(name, operands):
    """Get C++ register index expression for pipeline scoreboard."""
    m = _REG_ARRAY_RE.match(name)
    if m:
        return m.group(2)
    return None

def generate_behavior_cpp(behavior_list, operands, indent='            '):
    """Generate C++ code from a list of behavior micro-ops."""
    lines = []
    declared_temps = set()
    
    for step in behavior_list:
        op = step['op']
        
        if op == 'add':
            dst = _resolve(step['dst'], operands)
            src1 = _resolve(step['src1'], operands)
            src2 = _resolve(step['src2'], operands)
            lines.append(f'{dst} = {src1} + {src2};')
            
        elif op == 'sub':
            dst = _resolve(step['dst'], operands)
            src1 = _resolve(step['src1'], operands)
            src2 = _resolve(step['src2'], operands)
            lines.append(f'{dst} = {src1} - {src2};')
            
        elif op == 'mul':
            dst = _resolve(step['dst'], operands)
            src1 = _resolve(step['src1'], operands)
            src2 = _resolve(step['src2'], operands)
            lines.append(f'{dst} = {src1} * {src2};')

        elif op == 'mulh':
            # signed * signed, take upper 32 bits
            dst = _resolve(step['dst'], operands)
            src1 = _resolve(step['src1'], operands)
            src2 = _resolve(step['src2'], operands)
            lines.append(
                f'{dst} = (int32_t)(((int64_t)(int32_t){src1} * (int64_t)(int32_t){src2}) >> 32);'
            )

        elif op == 'mulhu':
            # unsigned * unsigned, take upper 32 bits
            dst = _resolve(step['dst'], operands)
            src1 = _resolve(step['src1'], operands)
            src2 = _resolve(step['src2'], operands)
            lines.append(
                f'{dst} = (int32_t)(((uint64_t)(uint32_t){src1} * (uint64_t)(uint32_t){src2}) >> 32);'
            )

        elif op == 'mulhsu':
            # signed * unsigned, take upper 32 bits
            dst = _resolve(step['dst'], operands)
            src1 = _resolve(step['src1'], operands)
            src2 = _resolve(step['src2'], operands)
            lines.append(
                f'{dst} = (int32_t)(((int64_t)(int32_t){src1} * (int64_t)(uint32_t){src2}) >> 32);'
            )

        elif op == 'div':
            dst = _resolve(step['dst'], operands)
            src1 = _resolve(step['src1'], operands)
            src2 = _resolve(step['src2'], operands)
            lines.append(
                f'{dst} = ({src2} == 0) ? -1 : (int32_t){src1} / (int32_t){src2};'
            )

        elif op == 'divu':
            dst = _resolve(step['dst'], operands)
            src1 = _resolve(step['src1'], operands)
            src2 = _resolve(step['src2'], operands)
            lines.append(
                f'{dst} = ({src2} == 0) ? -1 : (int32_t)((uint32_t){src1} / (uint32_t){src2});'
            )

        elif op == 'rem':
            dst = _resolve(step['dst'], operands)
            src1 = _resolve(step['src1'], operands)
            src2 = _resolve(step['src2'], operands)
            lines.append(
                f'{dst} = ({src2} == 0) ? {src1} : (int32_t){src1} % (int32_t){src2};'
            )

        elif op == 'remu':
            dst = _resolve(step['dst'], operands)
            src1 = _resolve(step['src1'], operands)
            src2 = _resolve(step['src2'], operands)
            lines.append(
                f'{dst} = ({src2} == 0) ? {src1} : (int32_t)((uint32_t){src1} % (uint32_t){src2});'
            )

        elif op == 'and_op':
            dst = _resolve(step['dst'], operands)
            src1 = _resolve(step['src1'], operands)
            src2 = _resolve(step['src2'], operands)
            lines.append(f'{dst} = {src1} & {src2};')
            
        elif op == 'or_op':
            dst = _resolve(step['dst'], operands)
            src1 = _resolve(step['src1'], operands)
            src2 = _resolve(step['src2'], operands)
            lines.append(f'{dst} = {src1} | {src2};')
            
        elif op == 'xor_op':
            dst = _resolve(step['dst'], operands)
            src1 = _resolve(step['src1'], operands)
            src2 = _resolve(step['src2'], operands)
            lines.append(f'{dst} = {src1} ^ {src2};')
            
        elif op == 'slt':
            dst = _resolve(step['dst'], operands)
            src1 = _resolve(step['src1'], operands)
            src2 = _resolve(step['src2'], operands)
            lines.append(f'{dst} = ((int32_t){src1} < (int32_t){src2}) ? 1 : 0;')
            
        elif op == 'sltu':
            dst = _resolve(step['dst'], operands)
            src1 = _resolve(step['src1'], operands)
            src2 = _resolve(step['src2'], operands)
            lines.append(f'{dst} = ((uint32_t){src1} < (uint32_t){src2}) ? 1 : 0;')
            
        elif op == 'sll':
            dst = _resolve(step['dst'], operands)
            src1 = _resolve(step['src1'], operands)
            src2 = _resolve(step['src2'], operands)
            lines.append(f'{dst} = {src1} << ({src2} & 0x1F);')
            
        elif op == 'srl':
            dst = _resolve(step['dst'], operands)
            src1 = _resolve(step['src1'], operands)
            src2 = _resolve(step['src2'], operands)
            lines.append(f'{dst} = (uint32_t){src1} >> ({src2} & 0x1F);')
            
        elif op == 'sra':
            dst = _resolve(step['dst'], operands)
            src1 = _resolve(step['src1'], operands)
            src2 = _resolve(step['src2'], operands)
            lines.append(f'{dst} = (int32_t){src1} >> ({src2} & 0x1F);')
            
        elif op == 'load_word':
            dst = _resolve(step['dst'], operands)
            base = _resolve(step['base'], operands)
            offset = _resolve(step['offset'], operands)
            lines.append(f'{{ uint32_t _addr = (uint32_t)((int32_t){base} + {offset});')
            lines.append(f'  _mem_addr = _addr;')
            lines.append(f'  memcpy(&{dst}, &DataMem[_addr], 4); }}')
            
        elif op == 'store_word':
            src = _resolve(step['src'], operands)
            base = _resolve(step['base'], operands)
            offset = _resolve(step['offset'], operands)
            lines.append(f'{{ uint32_t _addr = (uint32_t)((int32_t){base} + {offset});')
            lines.append(f'  _mem_addr = _addr;')
            lines.append(f'  memcpy(&DataMem[_addr], &{src}, 4); }}')

        elif op == 'load_byte':
            # signed byte load
            dst = _resolve(step['dst'], operands)
            base = _resolve(step['base'], operands)
            offset = _resolve(step['offset'], operands)
            lines.append(f'{{ uint32_t _addr = (uint32_t)((int32_t){base} + {offset});')
            lines.append(f'  _mem_addr = _addr;')
            lines.append(f'  {dst} = (int32_t)(int8_t)DataMem[_addr]; }}')

        elif op == 'load_byte_unsigned':
            dst = _resolve(step['dst'], operands)
            base = _resolve(step['base'], operands)
            offset = _resolve(step['offset'], operands)
            lines.append(f'{{ uint32_t _addr = (uint32_t)((int32_t){base} + {offset});')
            lines.append(f'  _mem_addr = _addr;')
            lines.append(f'  {dst} = (int32_t)(uint8_t)DataMem[_addr]; }}')

        elif op == 'store_byte':
            src = _resolve(step['src'], operands)
            base = _resolve(step['base'], operands)
            offset = _resolve(step['offset'], operands)
            lines.append(f'{{ uint32_t _addr = (uint32_t)((int32_t){base} + {offset});')
            lines.append(f'  _mem_addr = _addr;')
            lines.append(f'  DataMem[_addr] = (uint8_t)({src} & 0xFF); }}')

        elif op == 'load_half':
            dst = _resolve(step['dst'], operands)
            base = _resolve(step['base'], operands)
            offset = _resolve(step['offset'], operands)
            lines.append(f'{{ uint32_t _addr = (uint32_t)((int32_t){base} + {offset});')
            lines.append(f'  _mem_addr = _addr;')
            lines.append(f'  uint16_t _hw; memcpy(&_hw, &DataMem[_addr], 2);')
            lines.append(f'  {dst} = (int32_t)(int16_t)_hw; }}')

        elif op == 'load_half_unsigned':
            dst = _resolve(step['dst'], operands)
            base = _resolve(step['base'], operands)
            offset = _resolve(step['offset'], operands)
            lines.append(f'{{ uint32_t _addr = (uint32_t)((int32_t){base} + {offset});')
            lines.append(f'  _mem_addr = _addr;')
            lines.append(f'  uint16_t _hw; memcpy(&_hw, &DataMem[_addr], 2);')
            lines.append(f'  {dst} = (int32_t)(uint32_t)_hw; }}')

        elif op == 'store_half':
            src = _resolve(step['src'], operands)
            base = _resolve(step['base'], operands)
            offset = _resolve(step['offset'], operands)
            lines.append(f'{{ uint32_t _addr = (uint32_t)((int32_t){base} + {offset});')
            lines.append(f'  _mem_addr = _addr;')
            lines.append(f'  uint16_t _hw = (uint16_t)({src} & 0xFFFF);')
            lines.append(f'  memcpy(&DataMem[_addr], &_hw, 2); }}')

        elif op == 'branch_eq':
            src1 = _resolve(step['src1'], operands)
            src2 = _resolve(step['src2'], operands)
            offset = _resolve(step['offset'], operands)
            lines.append(f'if ({src1} == {src2}) {{ core.PC = current_pc + {offset}; _branch_taken = true; }}')
            
        elif op == 'branch_ne':
            src1 = _resolve(step['src1'], operands)
            src2 = _resolve(step['src2'], operands)
            offset = _resolve(step['offset'], operands)
            lines.append(f'if ({src1} != {src2}) {{ core.PC = current_pc + {offset}; _branch_taken = true; }}')
            
        elif op == 'branch_lt':
            src1 = _resolve(step['src1'], operands)
            src2 = _resolve(step['src2'], operands)
            offset = _resolve(step['offset'], operands)
            lines.append(f'if ((int32_t){src1} < (int32_t){src2}) {{ core.PC = current_pc + {offset}; _branch_taken = true; }}')
            
        elif op == 'branch_ge':
            src1 = _resolve(step['src1'], operands)
            src2 = _resolve(step['src2'], operands)
            offset = _resolve(step['offset'], operands)
            lines.append(f'if ((int32_t){src1} >= (int32_t){src2}) {{ core.PC = current_pc + {offset}; _branch_taken = true; }}')
            
        elif op == 'branch_ltu':
            src1 = _resolve(step['src1'], operands)
            src2 = _resolve(step['src2'], operands)
            offset = _resolve(step['offset'], operands)
            lines.append(f'if ((uint32_t){src1} < (uint32_t){src2}) {{ core.PC = current_pc + {offset}; _branch_taken = true; }}')
            
        elif op == 'branch_geu':
            src1 = _resolve(step['src1'], operands)
            src2 = _resolve(step['src2'], operands)
            offset = _resolve(step['offset'], operands)
            lines.append(f'if ((uint32_t){src1} >= (uint32_t){src2}) {{ core.PC = current_pc + {offset}; _branch_taken = true; }}')
            
        elif op == 'lui':
            dst = _resolve(step['dst'], operands)
            src = _resolve(step['src'], operands)
            lines.append(f'{dst} = {src};')
            
        elif op == 'auipc':
            dst = _resolve(step['dst'], operands)
            src = _resolve(step['src'], operands)
            lines.append(f'{dst} = current_pc + {src};')
            
        elif op == 'jal':
            dst = _resolve(step['dst'], operands)
            offset = _resolve(step['offset'], operands)
            lines.append(f'{dst} = core.PC;')  # save return address (PC already incremented)
            lines.append(f'core.PC = current_pc + {offset};')
            lines.append('_branch_taken = true;')
            
        elif op == 'jalr':
            dst = _resolve(step['dst'], operands)
            base = _resolve(step['base'], operands)
            offset = _resolve(step['offset'], operands)
            lines.append(f'{{ int32_t _ret = core.PC;')  # save return address
            lines.append(f'  core.PC = ((int32_t){base} + {offset}) & ~1;')
            lines.append(f'  {dst} = _ret;')
            lines.append(f'  _branch_taken = true; }}')
            
        elif op == 'ecall':
            lines.append('core.halt = true;')
            
        # --- ARM-specific micro-ops ---
        elif op == 'mov':
            dst = _resolve(step['dst'], operands)
            src = _resolve(step['src'], operands)
            lines.append(f'{dst} = {src};')
            
        elif op == 'cmp':
            src1 = _resolve(step['src1'], operands)
            src2 = _resolve(step['src2'], operands)
            lines.append(f'{{ int32_t _result = (int32_t){src1} - (int32_t){src2};')
            lines.append(f'  cpsr_N = (_result < 0) ? 1 : 0;')
            lines.append(f'  cpsr_Z = (_result == 0) ? 1 : 0;')
            lines.append(f'  cpsr_V = (((int32_t){src1} ^ (int32_t){src2}) & ((int32_t){src1} ^ _result)) >> 31;')
            lines.append(f'  cpsr_C = ((uint32_t){src1} >= (uint32_t){src2}) ? 1 : 0; }}')
            
        elif op == 'branch':
            offset = _resolve(step['offset'], operands)
            lines.append(f'core.PC = current_pc + {offset};')
            lines.append('_branch_taken = true;')
            
        elif op == 'branch_link':
            dst = _resolve(step['dst'], operands)
            offset = _resolve(step['offset'], operands)
            lines.append(f'{dst} = core.PC;')  # save return address
            lines.append(f'core.PC = current_pc + {offset};')
            lines.append('_branch_taken = true;')
            
        elif op == 'branch_reg':
            base = _resolve(step['base'], operands)
            lines.append(f'core.PC = {base} & ~1;')  # ARM ignores thumb bit in simplistic model
            lines.append('_branch_taken = true;')
            
        else:
            lines.append(f'// ERROR: Unknown micro-op "{op}"')
    
    return '\n'.join(indent + line for line in lines)


def analyze_behavior(behavior_list, operands):
    """Analyze register reads/writes for pipeline hazard detection."""
    src_indices = []
    dst_index = None
    is_load = False
    is_branch = False
    
    for step in behavior_list:
        op = step['op']
        
        if op in ('add', 'sub', 'mul', 'mulh', 'mulhu', 'mulhsu', 'div', 'divu',
                  'rem', 'remu', 'and_op', 'or_op', 'xor_op',
                  'slt', 'sltu', 'sll', 'srl', 'sra'):
            idx = _reg_index(step['dst'], operands)
            if idx is not None: dst_index = idx
            for key in ('src1', 'src2'):
                idx = _reg_index(step.get(key, ''), operands)
                if idx is not None and idx not in src_indices:
                    src_indices.append(idx)

        elif op in ('load_word', 'load_byte', 'load_byte_unsigned',
                    'load_half', 'load_half_unsigned'):
            is_load = True
            idx = _reg_index(step['dst'], operands)
            if idx is not None: dst_index = idx
            idx = _reg_index(step.get('base', ''), operands)
            if idx is not None and idx not in src_indices:
                src_indices.append(idx)

        elif op in ('store_word', 'store_byte', 'store_half'):
            idx = _reg_index(step.get('src', ''), operands)
            if idx is not None and idx not in src_indices:
                src_indices.append(idx)
            idx = _reg_index(step.get('base', ''), operands)
            if idx is not None and idx not in src_indices:
                src_indices.append(idx)
                
        elif op in ('branch_eq', 'branch_ne', 'branch_lt', 'branch_ge', 'branch_ltu', 'branch_geu'):
            is_branch = True
            for key in ('src1', 'src2'):
                idx = _reg_index(step.get(key, ''), operands)
                if idx is not None and idx not in src_indices:
                    src_indices.append(idx)
                    
        elif op == 'lui':
            idx = _reg_index(step['dst'], operands)
            if idx is not None: dst_index = idx
            
        elif op == 'auipc':
            idx = _reg_index(step['dst'], operands)
            if idx is not None: dst_index = idx
            
        elif op in ('jal', 'jalr', 'branch_link'):
            is_branch = True
            idx = _reg_index(step.get('dst', ''), operands)
            if idx is not None: dst_index = idx
            if op == 'jalr':
                idx = _reg_index(step.get('base', ''), operands)
                if idx is not None and idx not in src_indices:
                    src_indices.append(idx)
                    
        elif op == 'branch_always':
            is_branch = True
            
        elif op == 'branch_reg':
            is_branch = True
            idx = _reg_index(step.get('base', ''), operands)
            if idx is not None and idx not in src_indices:
                src_indices.append(idx)
                
        elif op == 'mov':
            idx = _reg_index(step.get('dst', ''), operands)
            if idx is not None: dst_index = idx
            idx = _reg_index(step.get('src', ''), operands)
            if idx is not None and idx not in src_indices:
                src_indices.append(idx)
                
        elif op == 'cmp':
            for key in ('src1', 'src2'):
                idx = _reg_index(step.get(key, ''), operands)
                if idx is not None and idx not in src_indices:
                    src_indices.append(idx)
    
    return {
        'src_indices': src_indices,
        'dst_index': dst_index,
        'is_load': is_load,
        'is_branch': is_branch,
    }
