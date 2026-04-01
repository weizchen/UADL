// Phase C Benchmark: Vector Addition
// Optimized

int main() {
  volatile int *A = (volatile int *)400;
  volatile int *B = (volatile int *)464;
  volatile int *C = (volatile int *)528;
  int n = 16;

  // Combined initialization and addition loop
  // Loop unrolling to reduce branching overhead
  for (int i = 0; i < n; i += 4) {
    A[i] = i;
    B[i] = i * 2;
    C[i] = A[i] + B[i];

    A[i + 1] = i + 1;
    B[i + 1] = (i + 1) * 2;
    C[i + 1] = A[i + 1] + B[i + 1];

    A[i + 2] = i + 2;
    B[i + 2] = (i + 2) * 2;
    C[i + 2] = A[i + 2] + B[i + 2];

    A[i + 3] = i + 3;
    B[i + 3] = (i + 3) * 2;
    C[i + 3] = A[i + 3] + B[i + 3];
  }

  return C[n - 1];
}