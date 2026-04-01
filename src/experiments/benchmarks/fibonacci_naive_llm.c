// Phase C Benchmark: Fibonacci sequence
// Optimized - iterative implementation

int fib(int n) {
  if (n <= 1)
    return n;
  int a = 0;
  int b = 1;
  for (int i = 2; i <= n; i++) {
    int next = a + b;
    a = b;
    b = next;
  }
  return b;
}

int main() {
  volatile int *result = (volatile int *)400;

  *result = fib(10);

  return *result;
}