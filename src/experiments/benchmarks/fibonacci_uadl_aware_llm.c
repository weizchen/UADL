int main() {
  volatile int *result = (volatile int *)400;

  int a = 0;
  int b = 1;
  int n = 10;

  if (n > 1) {
    int temp;
    for (int i = 2; i <= n; i++) {
      temp = a + b;
      a = b;
      b = temp;
    }
    *result = b;
  } else {
    *result = n;
  }

  return *result;
}