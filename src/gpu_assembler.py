#!/usr/bin/env python3
"""
GPU Kernel Assembler for UADL

Assembles .gpu text files into UADL .mem binary format.
Supports an optional .data section for pre-loading global memory.

Encoding (32-bit):
  [31:24] opcode (8 bits)
  [23:20] rd     (4 bits)
  [19:16] rs1    (4 bits)
  [15:12] rs2    (4 bits)
  [11:0]  imm12  (12 bits, signed)

Syntax:
  VADD  rd, rs1, rs2       # ALU register-register
  VADD_IMM rd, rs1, imm    # ALU register-immediate
  VMOV_IMM rd, imm          # Move immediate
  LD_GLOBAL rd, rs1, imm   # Load from global memory
  ST_GLOBAL rd, rs1, imm   # Store to global memory
  LD_SHARED rd, rs1, imm   # Load from shared memory
  ST_SHARED rd, rs1, imm   # Store to shared memory
  BAR_SYNC                  # Barrier synchronization
  HALT                      # Terminate kernel

.data section:
  .data
  .word <addr> <value>     # Store 32-bit value at addr in global memory
"""

import sys
import struct
import re

# Instruction opcodes (must match gpu.yaml)
OPCODES = {
    'VADD':      0x01,
    'VSUB':      0x02,
    'VMUL':      0x03,
    'VAND':      0x04,
    'VOR':       0x05,
    'VSHL':      0x06,
    'VSHR':      0x07,
    'VADD_IMM':  0x11,
    'VMUL_IMM':  0x13,
    'VMOV_IMM':  0x20,
    'LD_GLOBAL': 0x30,
    'ST_GLOBAL': 0x31,
    'LD_SHARED': 0x32,
    'ST_SHARED': 0x33,
    'BAR_SYNC':  0x40,
    'HALT':      0xFF,
}

# Instruction formats
RRR_OPS  = {'VADD', 'VSUB', 'VMUL', 'VAND', 'VOR', 'VSHL', 'VSHR'}
RRI_OPS  = {'VADD_IMM', 'VMUL_IMM'}
RI_OPS   = {'VMOV_IMM'}
MEM_OPS  = {'LD_GLOBAL', 'ST_GLOBAL', 'LD_SHARED', 'ST_SHARED'}
SYNC_OPS = {'BAR_SYNC'}
CTRL_OPS = {'HALT'}


def parse_reg(s):
    """Parse register name like 'r0', 'r15' -> integer."""
    s = s.strip().rstrip(',')
    m = re.match(r'^r(\d+)$', s, re.IGNORECASE)
    if not m:
        raise ValueError(f"Invalid register: '{s}'")
    idx = int(m.group(1))
    if idx < 0 or idx > 15:
        raise ValueError(f"Register out of range: r{idx}")
    return idx


def parse_imm(s):
    """Parse immediate value (decimal or hex)."""
    s = s.strip().rstrip(',')
    if s.startswith('0x') or s.startswith('0X'):
        return int(s, 16)
    return int(s)


def encode_inst(opcode, rd=0, rs1=0, rs2=0, imm=0):
    """Encode a 32-bit GPU instruction."""
    imm12 = imm & 0xFFF
    return (opcode << 24) | (rd << 20) | (rs1 << 16) | (rs2 << 12) | imm12


def assemble(source):
    """Assemble GPU assembly text into (instructions, data_entries) tuple."""
    instructions = []
    data_entries = []  # List of (addr, value) tuples
    in_data_section = False
    
    for line_no, line in enumerate(source.split('\n'), 1):
        # Strip comments and whitespace
        line = line.split('#')[0].strip()
        if not line:
            continue
        
        # Check for .data section
        if line.lower() == '.data':
            in_data_section = True
            continue
        
        if line.lower() == '.text':
            in_data_section = False
            continue
        
        if in_data_section:
            # .word <addr> <value>
            if line.lower().startswith('.word'):
                parts = line.split()
                if len(parts) != 3:
                    raise ValueError(f"Line {line_no}: .word expects <addr> <value>")
                addr = parse_imm(parts[1])
                val = parse_imm(parts[2])
                data_entries.append((addr, val))
            continue
        
        # Parse instruction
        parts = line.replace(',', ' ').split()
        mnemonic = parts[0].upper()
        
        if mnemonic not in OPCODES:
            raise ValueError(f"Line {line_no}: Unknown instruction '{mnemonic}'")
        
        opcode = OPCODES[mnemonic]
        
        if mnemonic in RRR_OPS:
            if len(parts) != 4:
                raise ValueError(f"Line {line_no}: {mnemonic} expects rd, rs1, rs2")
            rd  = parse_reg(parts[1])
            rs1 = parse_reg(parts[2])
            rs2 = parse_reg(parts[3])
            instructions.append(encode_inst(opcode, rd, rs1, rs2))
            
        elif mnemonic in RRI_OPS:
            if len(parts) != 4:
                raise ValueError(f"Line {line_no}: {mnemonic} expects rd, rs1, imm")
            rd  = parse_reg(parts[1])
            rs1 = parse_reg(parts[2])
            imm = parse_imm(parts[3])
            instructions.append(encode_inst(opcode, rd, rs1, imm=imm))
            
        elif mnemonic in RI_OPS:
            if len(parts) != 3:
                raise ValueError(f"Line {line_no}: {mnemonic} expects rd, imm")
            rd  = parse_reg(parts[1])
            imm = parse_imm(parts[2])
            instructions.append(encode_inst(opcode, rd, imm=imm))
            
        elif mnemonic in MEM_OPS:
            if len(parts) != 4:
                raise ValueError(f"Line {line_no}: {mnemonic} expects rd, rs1, imm")
            rd  = parse_reg(parts[1])
            rs1 = parse_reg(parts[2])
            imm = parse_imm(parts[3])
            instructions.append(encode_inst(opcode, rd, rs1, imm=imm))
            
        elif mnemonic in SYNC_OPS:
            instructions.append(encode_inst(opcode))
            
        elif mnemonic in CTRL_OPS:
            instructions.append(encode_inst(opcode))
        
        else:
            raise ValueError(f"Line {line_no}: Unhandled instruction '{mnemonic}'")
    
    return instructions, data_entries


def write_mem(instructions, data_entries, out_path):
    """Write UADL .mem format binary file."""
    with open(out_path, 'wb') as f:
        # Magic
        f.write(b'UADL')
        
        # Segment 1: Instructions at address 0
        inst_data = b''.join(struct.pack('<I', inst) for inst in instructions)
        f.write(struct.pack('<I', 0))                  # vaddr = 0
        f.write(struct.pack('<I', len(inst_data)))     # size
        f.write(inst_data)
        
        # Segment 2: Pre-initialized global data (if any)
        if data_entries:
            # Find address range of data
            min_addr = min(addr for addr, _ in data_entries)
            max_addr = max(addr for addr, _ in data_entries) + 4
            buf_size = max_addr - min_addr
            data_buf = bytearray(buf_size)
            for addr, val in data_entries:
                struct.pack_into('<i', data_buf, addr - min_addr, val)
            
            f.write(struct.pack('<I', min_addr))       # vaddr = actual base
            f.write(struct.pack('<I', buf_size))
            f.write(bytes(data_buf))


def main():
    if len(sys.argv) != 3:
        print(f"Usage: {sys.argv[0]} <input.gpu> <output.mem>")
        sys.exit(1)
    
    in_file = sys.argv[1]
    out_file = sys.argv[2]
    
    with open(in_file, 'r') as f:
        source = f.read()
    
    instructions, data_entries = assemble(source)
    write_mem(instructions, data_entries, out_file)
    print(f"Assembled {len(instructions)} instructions to {out_file}")


if __name__ == '__main__':
    main()
