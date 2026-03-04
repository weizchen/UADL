import os
import subprocess
import json
import sys

def parse_sim_output(output):
    state = {'registers': {}, 'memory': {}}
    lines = output.split('\n')
    mode = None
    for line in lines:
        if line.startswith('--- Final CPU State ---'):
            mode = 'regs'
            continue
        if line.startswith('--- Data Memory'):
            mode = 'mem'
            continue
        elif line.startswith('--- Performance'):
            mode = 'perf'
            continue
            
        if mode == 'regs':
            if '[Core 1]' in line:
                mode = None
                continue
            if ':' in line:
                if 'Total Cycles' in line:
                    continue
                k, v = line.split(':')
                state['registers'][k.strip()] = int(v.strip())
        elif mode == 'mem' and ':' in line:
            if line.startswith('DataMem['):
                idx = line[8:line.find(']')]
                v = line.split(':')[1]
                state['memory'][idx] = int(v.strip())
        elif mode == 'perf' and line.startswith('Total Workload Cycles:'):
            state['cycles'] = int(line.split(':')[1].strip())
    return state

def run_tests():
    # 1. Generate simulator
    subprocess.run(['python', 'poc/uadl_compiler.py', 'poc/uadl_schema.yaml', 'poc/cpu.yaml', 'poc/simulator_template.j2', 'poc/generated_simulator.cpp'], check=True)
    
    # 2. Compile simulator
    subprocess.run(['g++', '-O3', 'poc/generated_simulator.cpp', '-o', 'poc/sim'], check=True)
    
    tests_dir = 'poc/tests'
    if not os.path.exists(tests_dir):
        print("No tests found.")
        return
        
    failures = 0
    test_files = [f for f in os.listdir(tests_dir) if f.endswith('.asm') or f.endswith('.c')]
    test_files = []
    all_files = os.listdir(tests_dir)
    for f in all_files:
        if f.endswith('.c'):
            test_files.append(f)
        elif f.endswith('.asm'):
            # only add .asm if a matching .c doesn't exist
            if f[:-4] + '.c' not in all_files:
                test_files.append(f)
                
    for file in test_files:
        is_c_file = file.endswith('.c')
        test_name = file[:-2] if is_c_file else file[:-4]
        
        c_path = os.path.join(tests_dir, file) if is_c_file else None
        asm_path = os.path.join(tests_dir, f"{test_name}.asm")
        bin_path = os.path.join(tests_dir, f"{test_name}.bin")
        exp_path = os.path.join(tests_dir, f"{test_name}.expected")
        
        if is_c_file:
            print(f"Compiling C code: {file}")
            subprocess.run(['python', 'poc/c_compiler.py', c_path, asm_path], check=True)
            
        print(f"Assembling: {asm_path}")
        subprocess.run(['python', 'poc/assembler.py', 'poc/uadl_schema.yaml', 'poc/cpu.yaml', asm_path, bin_path], check=True)
            
        # Run sim
        res = subprocess.run(['./poc/sim', bin_path], capture_output=True, text=True)
        if res.returncode != 0:
            print(f"Error executing {test_name}:\n{res.stderr}")
            failures += 1
            continue
            
        # Verify
        if os.path.exists(exp_path):
            with open(exp_path, 'r') as f:
                expected = json.load(f)
                
            actual = parse_sim_output(res.stdout)
            
            passed = True
            if 'registers' in expected:
                for k, v in expected['registers'].items():
                    if actual['registers'].get(k) != v:
                        print(f"FAIL {test_name}: Expected register {k}={v}, got {actual['registers'].get(k)}")
                        passed = False
            if 'memory' in expected:
                for k, v in expected['memory'].items():
                    if actual['memory'].get(str(k)) != v:
                        print(f"FAIL {test_name}: Expected memory[{k}]={v}, got {actual['memory'].get(str(k))}")
                        passed = False
                        
            if passed:
                cycles = actual.get('cycles', 'Unknown')
                print(f"PASS {test_name} (Completed in {cycles} cycles)")
            else:
                failures += 1
        else:
            print(f"WARN: No expected output for {test_name}. Output was:\n{res.stdout}")
                
    if failures > 0:
        sys.exit(1)
    else:
        print("All tests passed!")

if __name__ == '__main__':
    run_tests()
