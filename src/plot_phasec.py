import sys
import os

try:
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    import numpy as np
except ImportError:
    import subprocess
    subprocess.check_call([sys.executable, "-m", "pip", "install", "matplotlib", "numpy"])
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    import numpy as np

def plot_results():
    data = {}
    current_bench = None
    current_arch = None
    
    with open("phasec.txt", "r") as f:
        for line in f:
            line = line.strip()
            if line.startswith('--- ') and line.endswith(' ---'):
                current_bench = line.replace('-', '').strip()
                data[current_bench] = {'small': {}, 'large': {}}
            elif line.startswith('Speedup vs baseline (small):'):
                current_arch = 'small'
            elif line.startswith('Speedup vs baseline (large):'):
                current_arch = 'large'
            elif current_arch and line.startswith('naive_llm:'):
                val = float(line.split(':')[1].replace('x', '').strip())
                data[current_bench][current_arch]['naive_llm'] = val
            elif current_arch and line.startswith('uadl_aware_llm:'):
                val = float(line.split(':')[1].replace('x', '').strip())
                data[current_bench][current_arch]['uadl_aware_llm'] = val

    if not data:
        print("No data parsed.")
        return

    benchmarks = list(data.keys())
    
    # Plot for Small Architecture
    fig, axes = plt.subplots(2, 1, figsize=(10, 12))
    
    x = np.arange(len(benchmarks))
    width = 0.35
    
    for i, arch in enumerate(['small', 'large']):
        naive = [data[b].get(arch, {}).get('naive_llm', 0) for b in benchmarks]
        aware = [data[b].get(arch, {}).get('uadl_aware_llm', 0) for b in benchmarks]
        
        ax = axes[i]
        rects1 = ax.bar(x - width/2, naive, width, label='Naive LLM', color='#72b6e1')
        rects2 = ax.bar(x + width/2, aware, width, label='UADL-Aware LLM', color='#ff977a')
        
        # Add baseline = 1.0 line
        ax.axhline(y=1.0, color='gray', linestyle='--', alpha=0.7, label='Baseline (1.0x)')
        
        ax.set_ylabel('Speedup (Higher is Better)')
        ax.set_title(f'Performance Speedup on {arch.capitalize()} Architecture')
        ax.set_xticks(x)
        ax.set_xticklabels(benchmarks)
        ax.legend()
        
        # Add labels on top of bars
        ax.bar_label(rects1, padding=3, fmt='%.2fx')
        ax.bar_label(rects2, padding=3, fmt='%.2fx')

    fig.tight_layout()
    output_path = '/Users/enzoc/code/grad/UADL/phasec_results.png'
    plt.savefig(output_path, dpi=300, bbox_inches='tight')
    print(f"Saved {output_path}")

if __name__ == '__main__':
    plot_results()
