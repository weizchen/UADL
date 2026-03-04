import sys
import os
import subprocess

def print_step(msg):
    print(f"\n[{'*'*10} {msg} {'*'*10}]")

def main():
    if len(sys.argv) < 3:
        print("Usage: python driver.py <cpu.yaml> <program.c | program.asm>")
        sys.exit(1)

    cpu_yaml = sys.argv[1]
    program_file = sys.argv[2]
    
    if not os.path.exists(cpu_yaml):
        print(f"Error: CPU description '{cpu_yaml}' not found.")
        sys.exit(1)
        
    if not os.path.exists(program_file):
        print(f"Error: Program file '{program_file}' not found.")
        sys.exit(1)

    # Base paths
    base_dir = os.path.dirname(os.path.abspath(__file__))
    schema_yaml = os.path.join(base_dir, "uadl_schema.yaml")
    template_j2 = os.path.join(base_dir, "simulator_template.j2")
    gen_cpp = os.path.join(base_dir, "generated_simulator.cpp")
    sim_bin = os.path.join(base_dir, "sim")
    
    print_step("1. GENERATING SIMULATOR C++ CODE")
    cmd_gen = ["python", os.path.join(base_dir, "uadl_compiler.py"), schema_yaml, cpu_yaml, template_j2, gen_cpp]
    print(" ".join(cmd_gen))
    subprocess.run(cmd_gen, check=True)

    print_step("2. COMPILING SIMULATOR")
    cmd_compile_sim = ["g++", "-O3", gen_cpp, "-o", sim_bin]
    print(" ".join(cmd_compile_sim))
    subprocess.run(cmd_compile_sim, check=True)

    # Determine paths for the workload
    prog_dir = os.path.dirname(os.path.abspath(program_file))
    prog_basename = os.path.basename(program_file)
    prog_name, ext = os.path.splitext(prog_basename)
    
    asm_file = os.path.join(prog_dir, f"{prog_name}.asm")
    bin_file = os.path.join(prog_dir, f"{prog_name}.bin")

    if ext == ".c":
        print_step("3. COMPILING C PROGRAM TO ASSEMBLY")
        cmd_c_compile = ["python", os.path.join(base_dir, "c_compiler.py"), program_file, asm_file]
        print(" ".join(cmd_c_compile))
        subprocess.run(cmd_c_compile, check=True)
    elif ext != ".asm":
        print(f"Warning: Unrecognized extension '{ext}'. Assuming it's an assembly file.")
        asm_file = program_file

    print_step("4. ASSEMBLING WORKLOAD INTO BINARY")
    cmd_assemble = ["python", os.path.join(base_dir, "assembler.py"), schema_yaml, cpu_yaml, asm_file, bin_file]
    print(" ".join(cmd_assemble))
    subprocess.run(cmd_assemble, check=True)

    print_step("5. RUNNING SIMULATION")
    cmd_run = [sim_bin, bin_file]
    print(" ".join(cmd_run))
    result = subprocess.run(cmd_run, capture_output=True, text=True)
    
    print("\n--- SIMULATION OUTPUT ---")
    print(result.stdout)
    if result.stderr:
        print("--- ERRORS ---")
        print(result.stderr)

if __name__ == "__main__":
    main()
