import sys
import re

def transpile(c_path, asm_path):
    with open(c_path, 'r') as f:
        lines = f.readlines()
        
    asm_lines = ["# Auto-generated UADL Accumulator ASM from C"]
    variables = {}  # var_name -> memory_addr
    functions = {}  # func_name -> instruction_addr
    next_data_addr = 100 
    
    current_inst_addr = 1 # Reserve PC 0 for JMP to main
    in_function = None
    for line in lines:
        line = line.strip()
        if not line or line.startswith('//'):
            continue
            
        if line.startswith('void ') and line.endswith('() {'):
            func_name = line.replace('void ', '').replace('() {', '').strip()
            functions[func_name] = current_inst_addr
            in_function = func_name
            asm_lines.append(f"# Function {func_name}")
            continue
        
        # `int main() {` is a special entrypoint
        if line.startswith('int main()'):
            in_function = 'main'
            functions['main'] = current_inst_addr
            asm_lines.append(f"# Function main")
            continue
            
        if line == '}':
            if in_function != 'main' and in_function is not None:
                # Functions must Halt to exit their thread gracefully
                asm_lines.append("HALT")
                current_inst_addr += 1
            in_function = None
            continue
            
        # Match `int a = 10;`
        m1 = re.match(r'^int\s+([a-zA-Z_]\w*)\s*=\s*(\d+)\s*;$', line)
        if m1:
            var_name = m1.group(1)
            val = m1.group(2)
            variables[var_name] = next_data_addr
            asm_lines.append(f"LOAD_IMM {val}")
            asm_lines.append(f"STORE {next_data_addr}")
            next_data_addr += 1
            current_inst_addr += 2
            continue
            
        # Match `int c = a + b;`
        m2 = re.match(r'^int\s+([a-zA-Z_]\w*)\s*=\s*([a-zA-Z_]\w*)\s*\+\s*([a-zA-Z_]\w*)\s*;$', line)
        if m2:
            new_var = m2.group(1)
            op1 = m2.group(2)
            op2 = m2.group(3)
            
            addr1 = variables[op1]
            addr2 = variables[op2]
            
            variables[new_var] = next_data_addr
            asm_lines.append(f"LOAD_MEM {addr1}")
            asm_lines.append(f"ADD_MEM {addr2}")
            asm_lines.append(f"STORE {next_data_addr}")
            next_data_addr += 1
            current_inst_addr += 3
            continue
            
        # Match `__fork(func_name);`
        m4 = re.match(r'^__fork\s*\(\s*([a-zA-Z_]\w*)\s*\)\s*;$', line)
        if m4:
            target_func = m4.group(1)
            # Due to this naive single-pass compiler, ensure functions are defined BEFORE main()
            if target_func not in functions:
                print(f"ERROR: Function '{target_func}' not found before __fork() call.")
                sys.exit(1)
            target_addr = functions[target_func]
            asm_lines.append(f"FORK {target_addr}")
            current_inst_addr += 1
            continue
            
        # Match `return c;`
        m3 = re.match(r'^return\s+([a-zA-Z_]\w*)\s*;$', line)
        if m3:
            ret_var = m3.group(1)
            addr = variables[ret_var]
            asm_lines.append(f"LOAD_MEM {addr}")
            asm_lines.append("HALT")
            current_inst_addr += 2
            continue
            
        print(f"ERROR: Unsupported C syntax: {line}")
        sys.exit(1)

    # Inject JMP main at address 0
    if 'main' not in functions:
        print("ERROR: No main() function defined.")
        sys.exit(1)
    
    asm_lines.insert(1, f"JMP {functions['main']}")

    with open(asm_path, 'w') as f:
        f.write('\n'.join(asm_lines) + '\n')
        
if __name__ == '__main__':
    transpile(sys.argv[1], sys.argv[2])
