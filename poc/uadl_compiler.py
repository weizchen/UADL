import yaml
import jsonschema
from jinja2 import Environment, FileSystemLoader
import sys
import os
from codegen import generate_behavior_cpp, analyze_behavior

def load_yaml(file_path):
    with open(file_path, 'r') as f:
        return yaml.safe_load(f)

def construct_simulator(schema_path, model_path, template_path, output_path):
    # Load schema and validate
    schema = load_yaml(schema_path)
    model = load_yaml(model_path)
    
    print(f"Validating {model_path} against {schema_path}...")
    try:
        jsonschema.validate(instance=model, schema=schema)
        print("Validation successful.")
    except jsonschema.exceptions.ValidationError as e:
        print(f"Validation failed: {e}")
        sys.exit(1)
        
    architecture = model['architecture']
    
    # Compute pipeline flag for template
    pipeline_cfg = architecture.get('pipeline', {})
    architecture['_pipeline_enabled'] = pipeline_cfg.get('enabled', False)
    
    # Pre-generate C++ code and pipeline metadata for each instruction
    for inst in architecture['instructions']:
        if 'behavior' in inst:
            inst['_generated_cpp'] = generate_behavior_cpp(
                inst['behavior'], 
                inst.get('operands', [])
            )
            inst['_pipeline'] = analyze_behavior(
                inst['behavior'],
                inst.get('operands', [])
            )
        else:
            inst['_generated_cpp'] = '            // WARNING: No behavior defined for this instruction'
            inst['_pipeline'] = {'src_indices': [], 'dst_index': None, 'is_load': False, 'is_branch': False}
    
    # Generate C++ Code using Jinja2
    print(f"Generating C++ simulator code from {template_path}...")
    env = Environment(loader=FileSystemLoader(os.path.dirname(template_path)))
    template = env.get_template(os.path.basename(template_path))
    
    rendered_cpp = template.render(architecture=architecture)
    
    with open(output_path, 'w') as f:
        f.write(rendered_cpp)
        
    print(f"Simulator generated at {output_path}")

if __name__ == "__main__":
    if len(sys.argv) < 5:
        print("Usage: python uadl_compiler.py <schema.yaml> <cpu.yaml> <template.j2> <output.cpp>")
        sys.exit(1)
        
    construct_simulator(sys.argv[1], sys.argv[2], sys.argv[3], sys.argv[4])
