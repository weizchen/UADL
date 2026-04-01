// Phase C Benchmark: Fibonacci sequence
// Baseline - recursive implementation

int fib(int n) {
  if (n <= 1)
    return n;
  return fib(n - 1) + fib(n - 2);
}

int main() {
  volatile int *result = (volatile int *)400;

  *result = fib(10);

  return *result;
}
