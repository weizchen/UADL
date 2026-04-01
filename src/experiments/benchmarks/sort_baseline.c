// Phase C Benchmark: Insertion sort
// Baseline — straightforward implementation, no optimizations
// Sorts 6 integers stored in memory

int main() {
  volatile int *arr = (volatile int *)400;

  // Initialize with unsorted data
  arr[0] = 42;
  arr[1] = 17;
  arr[2] = 5;
  arr[3] = 28;
  arr[4] = 12;
  arr[5] = 33;

  int n = 6;

  // Insertion sort
  for (int i = 1; i < n; i++) {
    int key = arr[i];
    int j = i - 1;
    while (j >= 0) {
      if (arr[j] > key) {
        arr[j + 1] = arr[j];
        j = j - 1;
      } else {
        break;
      }
    }
    arr[j + 1] = key;
  }

  return arr[0]; // Should be 5 (smallest element)
}
