#define N 64

int main() {
  volatile int *A = (volatile int *)400; 
  volatile int *B = (volatile int *)(400 + (N * N * 4)); 
  volatile int *C = (volatile int *)(400 + 2 * (N * N * 4)); 

  int *restrict rA = (int *)A;
  int *restrict rB = (int *)B;
  int *restrict rC = (int *)C;

  int v = 1;
  for (int i = 0; i < N * N; i++) {
    rA[i] = v++;
  }

  v = 1;
  for (int i = 0; i < N * N; i++) {
    rB[i] = v++;
  }

  for (int i = 0; i < N; i++) {
    int row_offset = i * N;
    for (int j = 0; j < N; j++) {
      int sum = 0;
      for (int k = 0; k < N; k++) {
        sum += rA[row_offset + k] * rB[k * N + j];
      }
      rC[row_offset + j] = sum;
    }
  }

  return rC[0]; 
}