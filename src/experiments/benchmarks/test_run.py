import sys, os
sys.path.insert(0, os.path.abspath('..'))
from run_experiment import compile_and_run

try:
    metrics = compile_and_run('test_n32.c', '../architectures/large.yaml', isa='armv7')
    print("Cycles:", metrics.get('cycles'))
    print("Raw Output:")
    print(metrics.get('raw_output'))
    if 'error' in metrics: print("ERROR:", metrics['error'])
except Exception as e:
    print(f"EXCEPTION: {e}")
