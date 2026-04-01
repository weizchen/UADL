int main() {
  volatile int *arr = (volatile int *)400;

  arr[0] = 42;
  arr[1] = 17;
  arr[2] = 5;
  arr[3] = 28;
  arr[4] = 12;
  arr[5] = 33;

  // Manual loop unrolling and register allocation
  int r0 = arr[0];
  int r1 = arr[1];
  int r2 = arr[2];
  int r3 = arr[3];
  int r4 = arr[4];
  int r5 = arr[5];

  int tmp;
  int key;

  // Insertion sort unrolled/inline logic for small fixed set
  // i = 1
  key = r1;
  if (r0 > key) {
    r1 = r0;
    r0 = key;
  }

  // i = 2
  key = r2;
  if (r1 > key) {
    r2 = r1;
    if (r0 > key) {
      r1 = r0;
      r0 = key;
    } else {
      r1 = key;
    }
  }

  // i = 3
  key = r3;
  if (r2 > key) {
    r3 = r2;
    if (r1 > key) {
      r2 = r1;
      if (r0 > key) {
        r1 = r0;
        r0 = key;
      } else {
        r1 = key;
      }
    } else {
      r2 = key;
    }
  }

  // i = 4
  key = r4;
  if (r3 > key) {
    r4 = r3;
    if (r2 > key) {
      r3 = r2;
      if (r1 > key) {
        r2 = r1;
        if (r0 > key) {
          r1 = r0;
          r0 = key;
        } else {
          r1 = key;
        }
      } else {
        r2 = key;
      }
    } else {
      r3 = key;
    }
  }

  // i = 5
  key = r5;
  if (r4 > key) {
    r5 = r4;
    if (r3 > key) {
      r4 = r3;
      if (r2 > key) {
        r3 = r2;
        if (r1 > key) {
          r2 = r1;
          if (r0 > key) {
            r1 = r0;
            r0 = key;
          } else {
            r1 = key;
          }
        } else {
          r2 = key;
        }
      } else {
        r3 = key;
      }
    } else {
      r4 = key;
    }
  }

  arr[0] = r0;
  arr[1] = r1;
  arr[2] = r2;
  arr[3] = r3;
  arr[4] = r4;
  arr[5] = r5;

  return arr[0];
}