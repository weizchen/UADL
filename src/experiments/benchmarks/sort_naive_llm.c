int main() {
  volatile int *arr = (volatile int *)400;

  arr[0] = 42;
  arr[1] = 17;
  arr[2] = 5;
  arr[3] = 28;
  arr[4] = 12;
  arr[5] = 33;

  int a0 = arr[0];
  int a1 = arr[1];
  int a2 = arr[2];
  int a3 = arr[3];
  int a4 = arr[4];
  int a5 = arr[5];

  int tmp[6] = {a0, a1, a2, a3, a4, a5};

  for (int i = 1; i < 6; i++) {
    int key = tmp[i];
    int j = i - 1;
    while (j >= 0 && tmp[j] > key) {
      tmp[j + 1] = tmp[j];
      j--;
    }
    tmp[j + 1] = key;
  }

  arr[0] = tmp[0];
  arr[1] = tmp[1];
  arr[2] = tmp[2];
  arr[3] = tmp[3];
  arr[4] = tmp[4];
  arr[5] = tmp[5];

  return arr[0];
}