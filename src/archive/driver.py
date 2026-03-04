#!/usr/bin/env python
"""
UADL Driver — Build and run the RISC-V simulator.

Usage:
    python driver.py <rv32i.yaml> <program.s>
    
Steps:
    1. Generate simulator C++ from YAML + Jinja2 template
    2. Compile the simulator with g++
    3. Assemble the RISC-V program to binary
    4. Run the simulator on the binary
"""

import sys
import os
import subprocess

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))

def run(cmd, label=""):
    if label:
        print(f"\n[*** {label} ***]")
    print(cmd)
    result = subprocess.run(cmd, shell=True, capture_output=False)
    if result.returncode != 0:
        print(f"FAILED: {label}")
        sys.exit(1)

def main():
    if len(sys.argv) < 3:
        print("Usage: python driver.py <rv32i.yaml> <program.s>")
        sys.exit(1)
    
    yaml_path = sys.argv[1]
    asm_path = sys.argv[2]
    
    template_path = os.path.join(SCRIPT_DIR, "sim_template.j2")
    cpp_path = os.path.join(SCRIPT_DIR, "generated_sim.cpp")
    sim_path = os.path.join(SCRIPT_DIR, "sim")
    bin_path = asm_path.replace('.s', '.bin')
    
    # 1. Generate simulator
    run(f"python {os.path.join(SCRIPT_DIR, 'uadl_compiler.py')} {yaml_path} {template_path} {cpp_path}",
        "GENERATING SIMULATOR")
    
    # 2. Compile
    run(f"g++ -O2 -std=c++17 {cpp_path} -o {sim_path}",
        "COMPILING SIMULATOR")
    
    # 3. Assemble
    run(f"python {os.path.join(SCRIPT_DIR, 'assembler.py')} {asm_path} {bin_path}",
        "ASSEMBLING PROGRAM")
    
    # 4. Run
    run(f"{sim_path} {bin_path}",
        "RUNNING SIMULATION")

if __name__ == "__main__":
    main()
