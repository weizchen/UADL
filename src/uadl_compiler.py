"""UADL Compiler — Generates C++ simulator from ISA YAML + Microarch YAML + Jinja2 template."""

import yaml
from jinja2 import Environment, FileSystemLoader
import sys
import os
from codegen import generate_behavior_cpp, analyze_behavior

def load_yaml(file_path):
    with open(file_path, 'r') as f:
        return yaml.safe_load(f)

def construct_simulator(isa_path, microarch_path, template_path, output_path):
    isa_model = load_yaml(isa_path)
    microarch_model = load_yaml(microarch_path)
    
    isa = isa_model['isa']
    microarch = microarch_model['microarch']
    
    # Merge into a single 'architecture' dict for template compatibility
    architecture = {
        'name': isa['name'],
        'encoding': isa.get('encoding', 'riscv32'),
        'word_size': isa.get('word_size', 32),
        'pipeline': microarch.get('pipeline', {}),
        'resources': {
            'cores': microarch['resources'].get('cores', 1),
            'caches': microarch['resources'].get('caches', []),
            'registers': isa.get('registers', []),
            'memory': microarch['resources'].get('memory', []),
        },
        'instructions': isa.get('instructions', []),
    }
    
    # Pipeline flag
    pipeline_cfg = architecture.get('pipeline', {})
    architecture['_pipeline_enabled'] = pipeline_cfg.get('enabled', False)
    
    # Pre-generate C++ and pipeline metadata for each instruction
    for inst in architecture['instructions']:
        fmt = inst.get('format', '')
        
        # Determine operands based on format (ISA-agnostic via format type)
        if fmt == 'R':
            operands = ['rd', 'rs1', 'rs2']
        elif fmt in ('I', 'IR'):
            operands = ['rd', 'rs1', 'imm']
        elif fmt == 'S':
            operands = ['rs1', 'rs2', 'imm']
        elif fmt == 'B':
            operands = ['rs1', 'rs2', 'imm']
        elif fmt in ('U', 'J'):
            operands = ['rd', 'imm']
        # ARM formats
        elif fmt == 'DP':
            operands = ['rd', 'rn', 'rm']
        elif fmt == 'DPI':
            operands = ['rd', 'rn', 'imm']
        elif fmt == 'LS':
            operands = ['rd', 'rn', 'imm']
        elif fmt in ('BR',):
            operands = ['imm']
        elif fmt == 'BX':
            operands = ['rm']
        elif fmt == 'SVC':
            operands = []
        else:
            operands = []
        
        inst['_generated_cpp'] = generate_behavior_cpp(
            inst.get('behavior', []), operands
        )
        inst['_pipeline'] = analyze_behavior(
            inst.get('behavior', []), operands
        )
    
    # Generate C++
    template_dir = os.path.dirname(template_path)
    env = Environment(loader=FileSystemLoader(template_dir))
    template = env.get_template(os.path.basename(template_path))
    rendered = template.render(architecture=architecture)
    
    with open(output_path, 'w') as f:
        f.write(rendered)
    
    print(f"Simulator generated: {output_path}")

if __name__ == "__main__":
    if len(sys.argv) < 5:
        print("Usage: python uadl_compiler.py <isa.yaml> <microarch.yaml> <template.j2> <output.cpp>")
        sys.exit(1)
    construct_simulator(sys.argv[1], sys.argv[2], sys.argv[3], sys.argv[4])
