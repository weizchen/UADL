// Phase C Benchmark: Vector Addition
// Baseline - no optimizations

int main() {
  volatile int *A = (volatile int *)400;
  volatile int *B = (volatile int *)464;
  volatile int *C = (volatile int *)528;
  int n = 16;

  // Initialize
  for (int i = 0; i < n; i++) {
    A[i] = i;
    B[i] = i * 2;
  }

  // Add
  for (int i = 0; i < n; i++) {
    C[i] = A[i] + B[i];
  }

  return C[n - 1];
}
