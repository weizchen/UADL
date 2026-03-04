// Simple arithmetic: add two numbers and store result
int add(int a, int b) { return a + b; }

int main() {
  int result = add(10, 20);
  // Store at memory address 100
  *(volatile int *)100 = result;
  return result;
}
