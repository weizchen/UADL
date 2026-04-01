#define N 32
int main() {
  volatile int *A = (volatile int *)400; 
  volatile int *B = (volatile int *)(400 + (N * N * 4)); 
  volatile int *C = (volatile int *)(400 + 2 * (N * N * 4)); 
  int v = 1;
  for (int i = 0; i < N; i++) {
    for (int j = 0; j < N; j++) {
      A[i * N + j] = v;
      v = v + 1;
    }
  }
  return 0; // exit safely
}
