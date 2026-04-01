"""UADL Test Runner — Runs tests for a specified ISA using LLVM toolchain."""

import subprocess
import os
import sys
import json
import shutil
import argparse

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))

def find_llvm_tool(name):
    """Find LLVM tool in PATH or fallback to Homebrew."""
    path = shutil.which(name)
    if path: return path
    hb_path = f"/opt/homebrew/opt/llvm/bin/{name}"
    if os.path.exists(hb_path): return hb_path
    return name

CLANG = find_llvm_tool('clang')
LLD = find_llvm_tool('ld.lld')


def parse_output(output):
    """Parse simulator output into registers and memory dicts."""
    result = {'registers': {}, 'memory': {}}
    section = None
    for line in output.split('\n'):
        if '--- Final CPU State ---' in line:
            section = 'regs'
        elif '--- Data Memory Dump ---' in line:
            section = 'mem'
        elif '--- Performance Data ---' in line or '--- Pipeline Diagram ---' in line:
            section = None
        elif section == 'regs':
            line = line.strip()
            if line.startswith('x[') or line.startswith('r['):
                parts = line.split(':')
                if len(parts) == 2:
                    result['registers'][parts[0].strip()] = int(parts[1].strip())
        elif section == 'mem':
            line = line.strip()
            if line.startswith('DataMem['):
                # Extract: DataMem[100]: 42 → key='100', val=42
                import re
                m = re.match(r'DataMem\[(\d+)\]:\s*(-?\d+)', line)
                if m:
                    result['memory'][m.group(1)] = int(m.group(2))
    return result

def check_output(test_name, stdout, expected_path):
    """Compare simulator output against expected values."""
    actual = parse_output(stdout)
    with open(expected_path, 'r') as f:
        expected = json.load(f)
    
    for k, v in expected.get('registers', {}).items():
        actual_v = actual['registers'].get(k)
        if actual_v != v:
            print(f"FAIL {test_name}: Register {k} expected={v} actual={actual_v}")
            return False
    
    for k, v in expected.get('memory', {}).items():
        actual_v = actual['memory'].get(k)
        if actual_v != v:
            print(f"FAIL {test_name}: DataMem[{k}] expected={v} actual={actual_v}")
            return False
    
    for line in stdout.split('\n'):
        if 'Total Workload Cycles' in line:
            cycles = line.split(':')[1].strip()
            print(f"PASS {test_name} ({cycles} cycles)")
            return True
    
    print(f"PASS {test_name}")
    return True

def build_simulator(isa):
    """Build the simulator for a given ISA."""
    isa_yaml = os.path.join(SCRIPT_DIR, 'isa', f'{isa}.yaml')
    
    # Select microarch based on ISA
    if isa == 'gpu':
        microarch_yaml = os.path.join(SCRIPT_DIR, 'microarch', 'gpu_simt.yaml')
    else:
        microarch_yaml = os.path.join(SCRIPT_DIR, 'microarch', 'default.yaml')
    
    # Always use the universal template
    template = os.path.join(SCRIPT_DIR, 'sim_universal.j2')
    
    cpp = os.path.join(SCRIPT_DIR, f'generated_sim_{isa}.cpp')
    sim = os.path.join(SCRIPT_DIR, f'sim_{isa}')
    
    needs_build = not os.path.exists(sim)
    for src in [isa_yaml, microarch_yaml, template]:
        if os.path.exists(src) and (not os.path.exists(sim) or os.path.getmtime(src) > os.path.getmtime(sim)):
            needs_build = True
    
    if needs_build:
        print(f"Building {isa} simulator...")
        r = subprocess.run(
            f"python {os.path.join(SCRIPT_DIR, 'uadl_compiler.py')} {isa_yaml} {microarch_yaml} {template} {cpp}",
            shell=True, capture_output=True, text=True
        )
        if r.returncode != 0:
            print(f"Codegen error: {r.stderr}")
            sys.exit(1)
        print(r.stdout.strip())
        
        r = subprocess.run(f"g++ -O2 -std=c++17 {cpp} -o {sim}", shell=True, capture_output=True, text=True)
        if r.returncode != 0:
            print(f"Build error: {r.stderr}")
            sys.exit(1)
    
    return sim

def get_toolchain(isa):
    """Get ISA-specific toolchain config."""
    if isa == 'rv32i':
        return {
            'clang_target': '--target=riscv32 -march=rv32i -mabi=ilp32',
            'ld_cmd': f'{LLD} -m elf32lriscv --image-base=0',
            'crt0': os.path.join(SCRIPT_DIR, 'crt0_rv32i.s'),
            'opt': '-O1',
        }
    elif isa == 'armv7':
        return {
            'clang_target': '--target=armv7-none-eabi -mcpu=cortex-a9',
            'ld_cmd': f'{LLD} --image-base=0',
            'crt0': os.path.join(SCRIPT_DIR, 'crt0_armv7.s'),
            'opt': '-O1',
        }
    raise ValueError(f"Unknown ISA: {isa}")

def assemble_test(name, asm_path, isa, tc):
    """Assemble an .s file to flat binary."""
    base = asm_path.rsplit('.', 1)[0]
    obj = base + '.o'
    elf = base + '.elf'
    bin_path = base + '.bin'
    
    r = subprocess.run(
        f"{CLANG} {tc['clang_target']} -c -o {obj} {asm_path}",
        shell=True, capture_output=True, text=True
    )
    if r.returncode != 0:
        print(f"FAIL {name}: Assembly error\n{r.stderr}")
        return None
    
    r = subprocess.run(
        f"{tc['ld_cmd']} -Ttext=0 -o {elf} {obj}",
        shell=True, capture_output=True, text=True
    )
    if r.returncode != 0:
        print(f"FAIL {name}: Link error\n{r.stderr}")
        return None
    
    r = subprocess.run(
        f"{sys.executable} {os.path.join(SCRIPT_DIR, 'elf2mem.py')} {elf} {bin_path}",
        shell=True, capture_output=True, text=True
    )
    if r.returncode != 0:
        print(f"FAIL {name}: objcopy error\n{r.stderr}")
        return None
    
    for f in [obj, elf]:
        if os.path.exists(f): os.remove(f)
    return bin_path

def compile_c_test(name, c_path, isa, tc):
    """Compile a C file to flat binary using crt0 + clang."""
    base = c_path.rsplit('.', 1)[0]
    obj = base + '.o'
    crt0_o = base + '_crt0.o'
    elf = base + '.elf'
    bin_path = base + '.bin'
    
    # Assemble crt0
    r = subprocess.run(
        f"{CLANG} {tc['clang_target']} -c -o {crt0_o} {tc['crt0']}",
        shell=True, capture_output=True, text=True
    )
    if r.returncode != 0:
        print(f"FAIL {name}: crt0 error\n{r.stderr}")
        return None
    
    # Compile C
    r = subprocess.run(
        f"{CLANG} {tc['clang_target']} -c {tc['opt']} -fno-builtin -nostdlib -o {obj} {c_path}",
        shell=True, capture_output=True, text=True
    )
    if r.returncode != 0:
        print(f"FAIL {name}: compile error\n{r.stderr}")
        return None
    
    # Link
    r = subprocess.run(
        f"{tc['ld_cmd']} -Ttext=0 -o {elf} {crt0_o} {obj}",
        shell=True, capture_output=True, text=True
    )
    if r.returncode != 0:
        print(f"FAIL {name}: link error\n{r.stderr}")
        return None
    
    # Extract binary
    r = subprocess.run(
        f"{sys.executable} {os.path.join(SCRIPT_DIR, 'elf2mem.py')} {elf} {bin_path}",
        shell=True, capture_output=True, text=True
    )
    if r.returncode != 0:
        print(f"FAIL {name}: objcopy error\n{r.stderr}")
        return None
    
    for f in [obj, crt0_o, elf]:
        if os.path.exists(f): os.remove(f)
    return bin_path

def run_sim(name, sim_path, bin_path, expected_path):
    """Run simulator and check output."""
    try:
        r = subprocess.run(f"{sim_path} {bin_path}", shell=True, capture_output=True, text=True, timeout=30)
    except subprocess.TimeoutExpired:
        print(f"FAIL {name}: Simulation timed out (30s)")
        return False
    if r.returncode != 0:
        print(f"FAIL {name}: Simulation error\n{r.stderr}")
        return False
    return check_output(name, r.stdout, expected_path)

def assemble_gpu_test(name, gpu_path, isa):
    """Assemble a .gpu file to flat binary via gpu_assembler.py."""
    base = gpu_path.rsplit('.', 1)[0]
    bin_path = base + '.bin'
    
    r = subprocess.run(
        f"{sys.executable} {os.path.join(SCRIPT_DIR, 'gpu_assembler.py')} {gpu_path} {bin_path}",
        shell=True, capture_output=True, text=True
    )
    if r.returncode != 0:
        print(f"FAIL {name}: GPU assembly error\n{r.stderr}")
        return None
    return bin_path


def main():
    parser = argparse.ArgumentParser(description='UADL Test Runner')
    parser.add_argument('--isa', default='rv32i', choices=['rv32i', 'armv7', 'gpu'])
    args = parser.parse_args()
    
    isa = args.isa
    tests_dir = os.path.join(SCRIPT_DIR, 'tests', isa)
    
    if not os.path.exists(tests_dir):
        print(f"No tests directory: {tests_dir}")
        sys.exit(1)
    
    sim = build_simulator(isa)
    
    # Discover tests
    tests = []
    if isa == 'gpu':
        # GPU tests: .gpu assembly files
        for f in sorted(os.listdir(tests_dir)):
            if f.endswith('.gpu'):
                name = f[:-4]
                exp = os.path.join(tests_dir, f"{name}.expected")
                if os.path.exists(exp):
                    tests.append((name, 'gpu', os.path.join(tests_dir, f), exp))
    else:
        tc = get_toolchain(isa)
        for f in sorted(os.listdir(tests_dir)):
            if f.endswith('.c'):
                name = f[:-2]
                exp = os.path.join(tests_dir, f"{name}.expected")
                if os.path.exists(exp):
                    tests.append((name, 'c', os.path.join(tests_dir, f), exp))
            elif f.endswith('.s'):
                name = f[:-2]
                if os.path.exists(os.path.join(tests_dir, f"{name}.c")):
                    continue
                exp = os.path.join(tests_dir, f"{name}.expected")
                if os.path.exists(exp):
                    tests.append((name, 'asm', os.path.join(tests_dir, f), exp))
    
    if not tests:
        print(f"No tests found for {isa}!")
        return
    
    passed = 0
    for name, kind, path, exp in tests:
        if kind == 'gpu':
            bin_path = assemble_gpu_test(name, path, isa)
        elif kind == 'c':
            bin_path = compile_c_test(name, path, isa, tc)
        else:
            bin_path = assemble_test(name, path, isa, tc)
        
        if bin_path and run_sim(name, sim, bin_path, exp):
            passed += 1
    
    print(f"\n{passed}/{len(tests)} tests passed ({isa})")
    if passed < len(tests):
        sys.exit(1)
    else:
        print("All tests passed!")

if __name__ == "__main__":
    main()
