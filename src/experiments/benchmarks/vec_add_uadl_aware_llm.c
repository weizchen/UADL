int main() {
  volatile int *A = (volatile int *)400;
  volatile int *B = (volatile int *)464;
  volatile int *C = (volatile int *)528;
  
  int i;
  for (i = 0; i < 16; i++) {
    A[i] = i;
    B[i] = i << 1;
  }

  for (i = 0; i < 16; i++) {
    C[i] = A[i] + B[i];
  }

  return C[15];
}