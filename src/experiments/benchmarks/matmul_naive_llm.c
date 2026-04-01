#define N 64

int main() {
  volatile int *A = (volatile int *)400; 
  volatile int *B = (volatile int *)(400 + (N * N * 4)); 
  volatile int *C = (volatile int *)(400 + 2 * (N * N * 4)); 

  int v = 1;
  for (int i = 0; i < N * N; i++) {
    A[i] = v++;
  }

  v = 1;
  for (int i = 0; i < N * N; i++) {
    B[i] = v++;
  }

  int B_transposed[N * N];
  for (int i = 0; i < N; i++) {
    for (int j = 0; j < N; j++) {
      B_transposed[j * N + i] = B[i * N + j];
    }
  }

  for (int i = 0; i < N; i++) {
    int *rowA = (int *)&A[i * N];
    for (int j = 0; j < N; j++) {
      int *rowBT = (int *)&B_transposed[j * N];
      int sum = 0;
      for (int k = 0; k < N; k++) {
        sum += rowA[k] * rowBT[k];
      }
      C[i * N + j] = sum;
    }
  }

  return C[0]; 
}