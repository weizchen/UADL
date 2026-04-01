#define N 64

int main() {
  volatile int *A = (volatile int *)400; 
  volatile int *B = (volatile int *)(400 + (N * N * 4)); 
  volatile int *C = (volatile int *)(400 + 2 * (N * N * 4)); 

  int v = 1;
  int size = N * N;
  for (int i = 0; i < size; i++) {
    A[i] = v;
    B[i] = v;
    v++;
  }

  for (int i = 0; i < N; i++) {
    int iN = i * N;
    for (int j = 0; j < N; j++) {
      int sum = 0;
      for (int k = 0; k < N; k++) {
        sum += A[iN + k] * B[k * N + j];
      }
      C[iN + j] = sum;
    }
  }

  return C[0]; 
}