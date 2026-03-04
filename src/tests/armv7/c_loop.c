// Sum of first N integers using a loop
// Expected: 1+2+...+10 = 55, stored at DataMem[200]

int main() {
  int sum = 0;
  for (int i = 1; i <= 10; i++) {
    sum += i;
  }
  *(volatile int *)200 = sum;
  return sum;
}
