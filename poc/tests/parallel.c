// A math subroutine that works in parallel
void compute_a() {
  int a_base = 50;
  int a_bias = 5;
  int a_result = a_base + a_bias;
}

// Another distinct subroutine run in parallel
void compute_b() {
  int b_base = 100;
  int b_bias = 20;
  int b_result = b_base + b_bias;
}

int main() {
  // Spawn threads for independent subroutines onto available C++ emulator cores
  __fork(compute_a);
  __fork(compute_b);

  // Main thread computes its own math
  int main_base = 40;
  int main_bias = 2;
  int result = main_base + main_bias;

  // When main thread hits this return, it will HALT its hardware core.
  // The emulator loop will verify when ALL hardware threads hit a HALT
  // gracefully.
  return result;
}
