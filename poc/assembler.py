import sys
import yaml
import struct

def parse_register(s):
    """Parse a register name like 'R3' or 'ACC' to its index."""
    s = s.strip().rstrip(',')
    if s.upper() == 'ACC':
        return 0
    if s.upper().startswith('R'):
        return int(s[1:])
    raise ValueError(f"Unknown register: {s}")

def assemble(schema_path, cpu_path, asm_path, out_path):
    with open(cpu_path, 'r') as f:
        model = yaml.safe_load(f)
    
    inst_map = {inst['name']: inst for inst in model['architecture']['instructions']}
    
    with open(asm_path, 'r') as f:
        lines = f.readlines()
    
    # === Pass 1: Collect labels and count instruction addresses ===
    labels = {}
    instruction_lines = []
    addr = 0
    
    for line in lines:
        line = line.strip()
        if not line or line.startswith('#'):
            continue
        
        # Check for label: "label_name:"
        if line.endswith(':') and not line.startswith(' '):
            label_name = line[:-1].strip()
            labels[label_name] = addr
            continue
        
        instruction_lines.append((addr, line))
        addr += 1
    
    # === Pass 2: Assemble instructions, resolving labels ===
    binary_data = bytearray()
    
    for addr, line in instruction_lines:
        parts = line.replace(',', ' ').split()
        mnemonic = parts[0]
        
        if mnemonic not in inst_map:
            print(f"Error: Unknown instruction '{mnemonic}' at address {addr}")
            sys.exit(1)
            
        inst = inst_map[mnemonic]
        opcode = inst['opcode']
        inst_type = inst['type']
        
        def resolve_operand(s):
            """Resolve a string to an integer — could be a number or a label."""
            s = s.strip().rstrip(',')
            if s in labels:
                return labels[s]
            try:
                return int(s, 0)
            except ValueError:
                print(f"Error: Unknown operand '{s}' at address {addr} (not a number or label)")
                sys.exit(1)
        
        if inst_type in ['I', 'J']:
            operand_val = 0
            if len(parts) > 1:
                operand_val = resolve_operand(parts[1])
            encoded = (opcode << 24) | (operand_val & 0xFFFFFF)
            
        elif inst_type == 'R':
            rd = parse_register(parts[1]) if len(parts) > 1 else 0
            rs1 = parse_register(parts[2]) if len(parts) > 2 else 0
            rs2 = parse_register(parts[3]) if len(parts) > 3 else 0
            encoded = (opcode << 24) | ((rd & 0xF) << 20) | ((rs1 & 0xF) << 16) | ((rs2 & 0xF) << 12)
            
        elif inst_type == 'RI':
            reg = parse_register(parts[1]) if len(parts) > 1 else 0
            imm = resolve_operand(parts[2]) if len(parts) > 2 else 0
            encoded = (opcode << 24) | ((reg & 0xF) << 20) | (imm & 0xFFFFF)
            
        elif inst_type == 'Z':
            encoded = (opcode << 24)
            
        else:
            print(f"Unknown instruction type: {inst_type}")
            sys.exit(1)
                
        binary_data.extend(struct.pack('<I', encoded))
        
    with open(out_path, 'wb') as f:
        f.write(binary_data)
        
    print(f"Assembled {asm_path} -> {out_path}")

if __name__ == "__main__":
    if len(sys.argv) < 5:
        print("Usage: python assembler.py <schema.yaml> <cpu.yaml> <input.asm> <output.bin>")
        sys.exit(1)
    assemble(sys.argv[1], sys.argv[2], sys.argv[3], sys.argv[4])
