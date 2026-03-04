// Bubble sort of a small array stored in memory
// Stores sorted values at consecutive addresses

void swap(int *a, int *b) {
  int tmp = *a;
  *a = *b;
  *b = tmp;
}

void bubble_sort(int *arr, int n) {
  for (int i = 0; i < n - 1; i++) {
    for (int j = 0; j < n - 1 - i; j++) {
      if (arr[j] > arr[j + 1]) {
        swap(&arr[j], &arr[j + 1]);
      }
    }
  }
}

int main() {
  // Use memory starting at address 400 for the array
  volatile int *arr = (volatile int *)400;
  arr[0] = 5;
  arr[1] = 3;
  arr[2] = 8;
  arr[3] = 1;
  arr[4] = 4;

  bubble_sort((int *)arr, 5);

  // Return first element (should be 1)
  return arr[0];
}
