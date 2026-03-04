// Bubble sort — ARM-compatible (no globals, avoids MOVW/MOVT)
// Result: sorted array at DataMem[400..416], return arr[0] (smallest)

int main() {
  volatile int *p = (volatile int *)400;
  p[0] = 5;
  p[1] = 3;
  p[2] = 8;
  p[3] = 1;
  p[4] = 4;

  int n = 5;
  int i, j, tmp;
  for (i = 0; i < n - 1; i++) {
    for (j = 0; j < n - 1 - i; j++) {
      if (p[j] > p[j + 1]) {
        tmp = p[j];
        p[j] = p[j + 1];
        p[j + 1] = tmp;
      }
    }
  }
  return p[0];
}
