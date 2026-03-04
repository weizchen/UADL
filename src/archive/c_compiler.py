#!/usr/bin/env python
"""
UADL C Compiler — Compiles C programs to RISC-V for the UADL simulator.

Pipeline:
    1. riscv64-elf-gcc -march=rv32i → .s (GCC RISC-V assembly)
    2. Filter: strip GCC directives, keep only instructions + labels
    3. Add ECALL (halt) after main returns
    4. Our assembler → .bin (flat binary)

Usage:
    python c_compiler.py <input.c> <output.s>
"""

import sys
import os
import subprocess
import re

# Instructions we support in our assembler
SUPPORTED_MNEMONICS = {
    'add', 'sub', 'and', 'or', 'xor', 'slt', 'sltu', 'sll', 'srl', 'sra',
    'addi', 'andi', 'ori', 'xori', 'slti', 'sltiu',
    'lw', 'sw',
    'beq', 'bne', 'blt', 'bge', 'bltu', 'bgeu',
    'lui', 'auipc',
    'jal', 'jalr',
    'ecall',
    # Pseudo-instructions
    'li', 'mv', 'nop', 'j', 'ret', 'call', 'beqz', 'bnez',
    'blez', 'bgtz', 'neg', 'not', 'seqz', 'snez',
}

def compile_c(c_path, asm_out):
    """Compile C to RISC-V assembly using GCC cross-compiler, then filter."""
    
    # Step 1: Run GCC
    gcc_asm = asm_out + '.gcc.s'
    cmd = (
        f"riscv64-elf-gcc -march=rv32i -mabi=ilp32 "
        f"-S -O1 -fno-builtin -nostdlib "
        f"-o {gcc_asm} {c_path}"
    )
    r = subprocess.run(cmd, shell=True, capture_output=True, text=True)
    if r.returncode != 0:
        print(f"GCC error:\n{r.stderr}")
        sys.exit(1)
    
    # Step 2: Filter GCC output
    with open(gcc_asm, 'r') as f:
        gcc_lines = f.readlines()
    
    filtered = []
    filtered.append("# Auto-compiled from: " + os.path.basename(c_path))
    filtered.append("# Startup: init stack, call main, halt")
    filtered.append("li sp, 8192")
    filtered.append("call main")
    filtered.append("ecall")
    filtered.append("")
    
    in_text = True  # Start assuming .text section
    
    for line in gcc_lines:
        line = line.rstrip()
        stripped = line.strip()
        
        # Skip empty lines
        if not stripped:
            continue
        
        # Handle .L labels (GCC local labels) — rename to _L
        if stripped.startswith('.L') and stripped.endswith(':'):
            renamed = stripped.replace('.L', '_L')
            filtered.append(renamed)
            continue
        
        # Skip other assembler directives
        if stripped.startswith('.'):
            if stripped.startswith('.text'):
                in_text = True
            elif stripped.startswith('.data') or stripped.startswith('.section') or stripped.startswith('.bss'):
                in_text = False
            continue
        
        if not in_text:
            continue
        
        # Keep function labels
        if stripped.endswith(':'):
            filtered.append(stripped)
            continue
        
        # Rename .L references in instructions
        processed = stripped.replace('.L', '_L')
        
        # Keep instructions
        parts = processed.replace(',', ' ').split()
        if not parts:
            continue
        mnemonic = parts[0].lower()
        
        # Handle GCC pseudo-instructions not in our set
        if mnemonic == 'ble':
            # ble rs1, rs2, label → bge rs2, rs1, label (swap operands)
            filtered.append(f"bge {parts[2]}, {parts[1]}, {parts[3]}")
            continue
        elif mnemonic == 'bgt':
            # bgt rs1, rs2, label → blt rs2, rs1, label
            filtered.append(f"blt {parts[2]}, {parts[1]}, {parts[3]}")
            continue
        elif mnemonic == 'bgtz':
            filtered.append(f"blt zero, {parts[1]}, {parts[2]}")
            continue
        elif mnemonic in ('slli', 'srli', 'srai'):
            # Shift immediate: slli rd, rs1, shamt
            # Our ISA handles these as I-type with special encoding
            # Map to our addi-based approach or handle in assembler
            # For now, emit as-is — we'll add these to the assembler
            filtered.append(processed)
            continue
        
        if mnemonic in SUPPORTED_MNEMONICS:
            filtered.append(processed)
            continue
        
        # Skip anything else

    
    # Step 3: No halt manipulation needed — startup code does `call main; ecall`
    result_lines = filtered
    
    with open(asm_out, 'w') as f:
        f.write('\n'.join(result_lines) + '\n')
    
    # Clean up temp file
    os.remove(gcc_asm)
    
    print(f"Compiled {c_path} -> {asm_out}")

if __name__ == '__main__':
    if len(sys.argv) < 3:
        print("Usage: python c_compiler.py <input.c> <output.s>")
        sys.exit(1)
    compile_c(sys.argv[1], sys.argv[2])
