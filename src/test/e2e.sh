#!/bin/bash
# test_uadl_e2e.sh - UADL End-to-End Execution Script

# Exit immediately if a command exits with a non-zero status
set -ex

# --- 1. Define Paths and Tools ---
ROOT_DIR=$(pwd)
SRC_DIR="$ROOT_DIR"
TEST_DIR="$ROOT_DIR/test"

TEST_NAME="example_test"
TEST_C_FILE="$TEST_DIR/$TEST_NAME.c"
ISA="rv32i"

# You may need to tweak this to point to your specific LLVM installation
CLANG="clang"
LLD="ld.lld"

# --- 2. Generate the C++ Simulator Engine in the test folder ---
echo "=> Step 2: Generating $ISA Simulator C++ from UADL YAMLs"
python3 "$SRC_DIR/uadl_compiler.py" \
  "$SRC_DIR/isa/${ISA}.yaml" \
  "$SRC_DIR/microarch/default.yaml" \
  "$SRC_DIR/sim_template.j2" \
  "$TEST_DIR/generated_sim_${ISA}.cpp"

# --- 3. Compile the C++ Simulator in the test folder ---
echo "=> Step 3: Compiling the C++ Simulator (sim_${ISA})"
g++ -O2 -std=c++17 "$TEST_DIR/generated_sim_${ISA}.cpp" -o "$TEST_DIR/sim_${ISA}"

# --- 4. Create a Sample Target C Program in the test folder ---
echo "=> Step 4: Creating a sample C program ($TEST_C_FILE)"
cat << 'EOF' > "$TEST_C_FILE"
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

EOF

# --- 5. Cross-Compile the C Program to an ELF Binary in the test folder ---
echo "=> Step 5: Cross-compiling the C code to $ISA ELF"
CRT0_OBJ="$TEST_DIR/crt0.o"
TEST_OBJ="$TEST_DIR/$TEST_NAME.o"
TEST_ELF="$TEST_DIR/$TEST_NAME.elf"

# Compile the minimal boot code (crt0) and the test C file
$CLANG --target=riscv32 -march=rv32i -mabi=ilp32 -c -O1 -fno-builtin -nostdlib -o "$CRT0_OBJ" "$SRC_DIR/crt0_rv32i.s"
$CLANG --target=riscv32 -march=rv32i -mabi=ilp32 -c -O1 -fno-builtin -nostdlib -o "$TEST_OBJ" "$TEST_C_FILE"

# Link them together into an ELF file starting at address 0
$LLD -m elf32lriscv --image-base=0 -Ttext=0 -o "$TEST_ELF" "$CRT0_OBJ" "$TEST_OBJ"

# --- 6. Convert ELF to UADL .mem Format in the test folder ---
echo "=> Step 6: Converting ELF to UADL .mem format"
TEST_BIN="$TEST_DIR/$TEST_NAME.bin"
python3 "$SRC_DIR/elf2mem.py" "$TEST_ELF" "$TEST_BIN"

# Clean up intermediary object files (Optional)
rm -f "$CRT0_OBJ" "$TEST_OBJ" "$TEST_ELF"

# --- 7. Run the Simulation ---
echo "=> Step 7: Running the Simulator!"
"$TEST_DIR/sim_${ISA}" "$TEST_BIN"
