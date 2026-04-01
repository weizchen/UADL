// Phase C Benchmark: Matrix multiply (N x N)
// Baseline — straightforward triple-nested loop, no optimizations
// Uses native multiplication (Targeting ARM)

#define N 64

int main() {
  volatile int *A = (volatile int *)400; 
  volatile int *B = (volatile int *)(400 + (N * N * 4)); 
  volatile int *C = (volatile int *)(400 + 2 * (N * N * 4)); 

  // Initialize A
  int v = 1;
  for (int i = 0; i < N; i++) {
    for (int j = 0; j < N; j++) {
      A[i * N + j] = v;
      v = v + 1;
    }
  }

  // Initialize B
  v = 1;
  for (int i = 0; i < N; i++) {
    for (int j = 0; j < N; j++) {
      B[i * N + j] = v;
      v = v + 1;
    }
  }

  // C = A * B
  for (int i = 0; i < N; i++) {
    for (int j = 0; j < N; j++) {
      int sum = 0;
      for (int k = 0; k < N; k++) {
        sum = sum + A[i * N + k] * B[k * N + j];
      }
      C[i * N + j] = sum;
    }
  }

  return C[0]; 
}
