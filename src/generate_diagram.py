import sys
import yaml
import os
import subprocess
import tempfile

def generate_mermaid_code(data):
    microarch = data.get('microarch', {})
    mem_hier = microarch.get('memory_hierarchy', {})
    spaces = mem_hier.get('spaces', [])
    nodes = mem_hier.get('nodes', [])
    connections = mem_hier.get('connections', [])

    lines = []
    lines.append("graph TD")
    lines.append("    %% Define Nodes representing memory spaces")
    for space in spaces:
        name = space.get('name')
        size = space.get('size', 'Unknown Size')
        lines.append(f"    {name}[{name.capitalize()} Space<br/>Size: {size}]")

    lines.append("\n    %% Define Nodes representing physical caches/memory")
    for node in nodes:
        name = node.get('name')
        node_type = node.get('type', 'cache').capitalize()
        size = node.get('size', 'Unknown Size')
        lines.append(f"    {name}({name} {node_type}<br/>Size: {size})")

    if connections:
        lines.append("\n    %% Define directed connections mapping the hierarchy")
        for conn in connections:
            from_node = conn.get('from')
            to_node = conn.get('to')
            lines.append(f"    {from_node} --> {to_node}")
            
    return "\n".join(lines)

def generate_diagram(yaml_path, output_path=None):
    try:
        with open(yaml_path, 'r') as f:
            data = yaml.safe_load(f)
    except Exception as e:
        print(f"Error reading YAML file: {e}")
        return

    mermaid_code = generate_mermaid_code(data)

    if not output_path:
        # Default behavior: print markdown
        print("```mermaid")
        print(mermaid_code)
        print("```")
        return

    # Check if mermaid-cli is installed
    mmdc_path = "mmdc"
    try:
        subprocess.run([mmdc_path, "--version"], capture_output=True, check=True)
    except (subprocess.CalledProcessError, FileNotFoundError):
        print("Error: The Mermaid CLI ('mmdc') is not installed or not in your PATH.")
        print("Please install it via npm:")
        print("  npm install -g @mermaid-js/mermaid-cli")
        sys.exit(1)

    # Output to file using temporary .mmd file
    _, ext = os.path.splitext(output_path)
    if ext.lower() not in ['.png', '.svg', '.pdf']:
        print(f"Error: Unsupported output format '{ext}'. Use .png, .svg, or .pdf")
        sys.exit(1)

    print(f"Generating diagram: {output_path} ...")
    
    with tempfile.NamedTemporaryFile(mode='w', suffix='.mmd', delete=False) as temp_mmd:
        temp_mmd.write(mermaid_code)
        temp_mmd_path = temp_mmd.name

    try:
        # Run mermaid CLI
        result = subprocess.run([
            mmdc_path,
            "-i", temp_mmd_path,
            "-o", output_path,
            "-b", "transparent",
            "-t", "neutral"
        ], capture_output=True, text=True)

        if result.returncode == 0:
            print("Successfully generated!")
        else:
            print("Failed to generate diagram:")
            print(result.stderr)
    finally:
        os.remove(temp_mmd_path)

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print(f"Usage:")
        print(f"  Markdown: python3 {sys.argv[0]} <microarch.yaml>")
        print(f"  Image:    python3 {sys.argv[0]} <microarch.yaml> -o <output.png|svg|pdf>")
        sys.exit(1)
    
    yaml_file = sys.argv[1]
    output_file = None
    
    if len(sys.argv) == 4 and sys.argv[2] == "-o":
        output_file = sys.argv[3]
        
    generate_diagram(yaml_file, output_file)
