#!/usr/bin/env python
"""
RISC-V RV32I Assembler

A simple two-pass assembler for RV32I instructions.
Supports standard RISC-V mnemonics, labels, and common pseudo-instructions.

Uses the riscv-assembler pip package for instruction encoding where possible,
with a custom implementation as fallback for full control.
"""

import sys
import struct
import re

# === RISC-V Register ABI Names ===
REG_MAP = {
    'zero': 0, 'ra': 1, 'sp': 2, 'gp': 3, 'tp': 4,
    't0': 5, 't1': 6, 't2': 7,
    's0': 8, 'fp': 8, 's1': 9,
    'a0': 10, 'a1': 11, 'a2': 12, 'a3': 13, 'a4': 14, 'a5': 15, 'a6': 16, 'a7': 17,
    's2': 18, 's3': 19, 's4': 20, 's5': 21, 's6': 22, 's7': 23, 's8': 24, 's9': 25, 's10': 26, 's11': 27,
    't3': 28, 't4': 29, 't5': 30, 't6': 31,
}

def parse_reg(s):
    """Parse register name: 'x5', 't0', 'zero', etc."""
    s = s.strip().rstrip(',')
    if s in REG_MAP:
        return REG_MAP[s]
    if s.startswith('x'):
        return int(s[1:])
    raise ValueError(f"Unknown register: {s}")

def parse_imm(s, labels, current_addr):
    """Parse immediate: number or label (resolved to PC-relative offset for branches)."""
    s = s.strip().rstrip(',')
    if s in labels:
        return labels[s] - current_addr  # PC-relative
    try:
        return int(s, 0)
    except ValueError:
        raise ValueError(f"Unknown immediate/label: {s}")

def parse_mem(s):
    """Parse memory operand like '0(x1)' -> (offset, base_reg)."""
    m = re.match(r'(-?\d+)\((\w+)\)', s.strip())
    if m:
        return int(m.group(1)), parse_reg(m.group(2))
    raise ValueError(f"Bad memory operand: {s}")

# === Instruction Encoding ===
def encode_r(funct7, rs2, rs1, funct3, rd, opcode):
    return (funct7 << 25) | (rs2 << 20) | (rs1 << 15) | (funct3 << 12) | (rd << 7) | opcode

def encode_i(imm, rs1, funct3, rd, opcode):
    return ((imm & 0xFFF) << 20) | (rs1 << 15) | (funct3 << 12) | (rd << 7) | opcode

def encode_s(imm, rs2, rs1, funct3, opcode):
    return (((imm >> 5) & 0x7F) << 25) | (rs2 << 20) | (rs1 << 15) | (funct3 << 12) | ((imm & 0x1F) << 7) | opcode

def encode_b(imm, rs2, rs1, funct3, opcode):
    return (((imm >> 12) & 1) << 31) | (((imm >> 5) & 0x3F) << 25) | (rs2 << 20) | (rs1 << 15) | (funct3 << 12) | (((imm >> 1) & 0xF) << 8) | (((imm >> 11) & 1) << 7) | opcode

def encode_u(imm, rd, opcode):
    return (imm & 0xFFFFF000) | (rd << 7) | opcode

def encode_j(imm, rd, opcode):
    return (((imm >> 20) & 1) << 31) | (((imm >> 1) & 0x3FF) << 21) | (((imm >> 11) & 1) << 20) | (((imm >> 12) & 0xFF) << 12) | (rd << 7) | opcode

# === Instruction Table ===
# mnemonic -> (format, opcode, funct3, funct7_or_None)
INST_TABLE = {
    # R-type
    'add':  ('R', 0x33, 0x0, 0x00),
    'sub':  ('R', 0x33, 0x0, 0x20),
    'and':  ('R', 0x33, 0x7, 0x00),
    'or':   ('R', 0x33, 0x6, 0x00),
    'xor':  ('R', 0x33, 0x4, 0x00),
    'slt':  ('R', 0x33, 0x2, 0x00),
    'sltu': ('R', 0x33, 0x3, 0x00),
    'sll':  ('R', 0x33, 0x1, 0x00),
    'srl':  ('R', 0x33, 0x5, 0x00),
    'sra':  ('R', 0x33, 0x5, 0x20),
    # I-type arithmetic
    'addi':  ('I', 0x13, 0x0, None),
    'andi':  ('I', 0x13, 0x7, None),
    'ori':   ('I', 0x13, 0x6, None),
    'xori':  ('I', 0x13, 0x4, None),
    'slti':  ('I', 0x13, 0x2, None),
    'sltiu': ('I', 0x13, 0x3, None),
    # Load
    'lw':   ('IL', 0x03, 0x2, None),
    # Store
    'sw':   ('S', 0x23, 0x2, None),
    # Branch
    'beq':  ('B', 0x63, 0x0, None),
    'bne':  ('B', 0x63, 0x1, None),
    'blt':  ('B', 0x63, 0x4, None),
    'bge':  ('B', 0x63, 0x5, None),
    'bltu': ('B', 0x63, 0x6, None),
    'bgeu': ('B', 0x63, 0x7, None),
    # Upper immediate
    'lui':   ('U', 0x37, None, None),
    'auipc': ('U', 0x17, None, None),
    # Jump
    'jal':  ('J', 0x6F, None, None),
    'jalr': ('I', 0x67, 0x0, None),
    # System
    'ecall': ('SYS', 0x73, None, None),
    # Shift immediate (I-type with funct7 in upper imm bits)
    'slli': ('IS', 0x13, 0x1, 0x00),
    'srli': ('IS', 0x13, 0x5, 0x00),
    'srai': ('IS', 0x13, 0x5, 0x20),
}

# === Pseudo-instructions ===
def expand_pseudo(mnemonic, parts, labels, addr):
    """Expand pseudo-instructions to real instructions. Returns list of (mnemonic, parts) tuples."""
    if mnemonic == 'li':
        # li rd, imm
        rd = parts[1]
        imm_str = parts[2].strip().rstrip(',')
        imm = int(imm_str, 0)
        if -2048 <= imm <= 2047:
            return [('addi', ['addi', rd, 'zero', str(imm)])]
        else:
            # LUI + ADDI for large immediates
            upper = (imm + 0x800) >> 12  # sign-adjust for ADDI
            lower = imm - (upper << 12)
            result = [('lui', ['lui', rd, str(upper)])]
            if lower != 0:
                result.append(('addi', ['addi', rd, rd, str(lower)]))
            return result
    elif mnemonic == 'mv':
        # mv rd, rs -> addi rd, rs, 0
        return [('addi', ['addi', parts[1], parts[2], '0'])]
    elif mnemonic == 'nop':
        return [('addi', ['addi', 'zero', 'zero', '0'])]
    elif mnemonic == 'j':
        # j label -> jal zero, label
        return [('jal', ['jal', 'zero', parts[1]])]
    elif mnemonic == 'ret':
        # ret -> jalr zero, ra, 0
        return [('jalr', ['jalr', 'zero', '0(ra)'])]  # special handling below
    elif mnemonic == 'call':
        # call label -> jal ra, label
        return [('jal', ['jal', 'ra', parts[1]])]
    elif mnemonic == 'beqz':
        return [('beq', ['beq', parts[1], 'zero', parts[2]])]
    elif mnemonic == 'bnez':
        return [('bne', ['bne', parts[1], 'zero', parts[2]])]
    elif mnemonic == 'blez':
        return [('bge', ['bge', 'zero', parts[1], parts[2]])]
    elif mnemonic == 'bgtz':
        return [('blt', ['blt', 'zero', parts[1], parts[2]])]
    elif mnemonic == 'neg':
        return [('sub', ['sub', parts[1], 'zero', parts[2]])]
    elif mnemonic == 'not':
        return [('xori', ['xori', parts[1], parts[2], '-1'])]
    elif mnemonic == 'seqz':
        return [('sltiu', ['sltiu', parts[1], parts[2], '1'])]
    elif mnemonic == 'snez':
        return [('sltu', ['sltu', parts[1], 'zero', parts[2]])]
    return None

PSEUDO_INSTRUCTIONS = {'li', 'mv', 'nop', 'j', 'ret', 'call', 'beqz', 'bnez',
                       'blez', 'bgtz', 'neg', 'not', 'seqz', 'snez'}

def assemble(asm_path, out_path):
    with open(asm_path, 'r') as f:
        lines = f.readlines()
    
    # === Pass 1: Collect labels ===
    labels = {}
    addr = 0
    for line in lines:
        line = line.split('#')[0].strip()  # remove comments
        if not line:
            continue
        if line.endswith(':'):
            labels[line[:-1].strip()] = addr
            continue
        parts = line.replace(',', ' ').split()
        mnemonic = parts[0].lower()
        if mnemonic in PSEUDO_INSTRUCTIONS:
            expanded = expand_pseudo(mnemonic, parts, labels, addr)
            if expanded:
                addr += len(expanded) * 4
                continue
        addr += 4
    
    # === Pass 2: Encode ===
    binary = bytearray()
    addr = 0
    
    for line in lines:
        line = line.split('#')[0].strip()
        if not line:
            continue
        if line.endswith(':'):
            continue
        
        parts = line.replace(',', ' ').split()
        mnemonic = parts[0].lower()
        
        # Expand pseudo-instructions
        if mnemonic in PSEUDO_INSTRUCTIONS:
            expanded = expand_pseudo(mnemonic, parts, labels, addr)
            if expanded:
                for real_mnem, real_parts in expanded:
                    enc = encode_instruction(real_mnem, real_parts, labels, addr)
                    binary.extend(struct.pack('<I', enc))
                    addr += 4
                continue
        
        enc = encode_instruction(mnemonic, parts, labels, addr)
        binary.extend(struct.pack('<I', enc))
        addr += 4
    
    with open(out_path, 'wb') as f:
        f.write(binary)
    print(f"Assembled {asm_path} -> {out_path} ({len(binary)} bytes)")

def encode_instruction(mnemonic, parts, labels, addr):
    """Encode a single real (non-pseudo) instruction."""
    if mnemonic == 'ret':
        # ret -> jalr x0, x1, 0
        return encode_i(0, 1, 0, 0, 0x67)
    
    if mnemonic not in INST_TABLE:
        raise ValueError(f"Unknown instruction: {mnemonic}")
    
    fmt, opcode, funct3, funct7 = INST_TABLE[mnemonic]
    
    if fmt == 'R':
        rd = parse_reg(parts[1])
        rs1 = parse_reg(parts[2])
        rs2 = parse_reg(parts[3])
        return encode_r(funct7, rs2, rs1, funct3, rd, opcode)
    
    elif fmt == 'I':
        # Format: instr rd, rs1, imm  OR  jalr rd, offset(rs1)
        if mnemonic == 'jalr' and '(' in parts[2]:
            offset, base = parse_mem(parts[2])
            rd = parse_reg(parts[1])
            return encode_i(offset, base, funct3, rd, opcode)
        rd = parse_reg(parts[1])
        rs1 = parse_reg(parts[2])
        imm = parse_imm(parts[3], labels, addr)
        return encode_i(imm, rs1, funct3, rd, opcode)
    
    elif fmt == 'IL':
        # Load format: lw rd, offset(base)
        rd = parse_reg(parts[1])
        offset, base = parse_mem(parts[2])
        return encode_i(offset, base, funct3, rd, opcode)
    
    elif fmt == 'S':
        # Store format: sw rs2, offset(base)
        rs2 = parse_reg(parts[1])
        offset, base = parse_mem(parts[2])
        return encode_s(offset, rs2, base, funct3, opcode)
    
    elif fmt == 'B':
        # Branch format: beq rs1, rs2, label/offset
        rs1 = parse_reg(parts[1])
        rs2 = parse_reg(parts[2])
        imm = parse_imm(parts[3], labels, addr)
        return encode_b(imm, rs2, rs1, funct3, opcode)
    
    elif fmt == 'U':
        rd = parse_reg(parts[1])
        imm = int(parts[2], 0) if parts[2] not in labels else labels[parts[2]]
        return encode_u(imm << 12 if imm < 0x100000 else imm, rd, opcode)
    
    elif fmt == 'J':
        rd = parse_reg(parts[1])
        imm = parse_imm(parts[2], labels, addr)
        return encode_j(imm, rd, opcode)
    
    elif fmt == 'SYS':
        return encode_i(0, 0, 0, 0, opcode)
    
    elif fmt == 'IS':
        # Shift immediate: slli rd, rs1, shamt (shamt in lower 5 bits, funct7 in upper 7)
        rd = parse_reg(parts[1])
        rs1 = parse_reg(parts[2])
        shamt = int(parts[3].strip().rstrip(','), 0)
        imm = (funct7 << 5) | (shamt & 0x1F)
        return encode_i(imm, rs1, funct3, rd, opcode)
    
    raise ValueError(f"Unhandled format: {fmt}")

if __name__ == "__main__":
    if len(sys.argv) < 3:
        print("Usage: python assembler.py <input.s> <output.bin>")
        sys.exit(1)
    assemble(sys.argv[1], sys.argv[2])
