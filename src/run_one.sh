#!/bin/bash
# Run a single UADL test case
#
# Usage:
#   ./src/run_one.sh [--isa rv32i|armv7] <test_name>
#
# Examples:
#   ./src/run_one.sh arithmetic             # default ISA (rv32i)
#   ./src/run_one.sh --isa rv32i c_sort     # explicit RISC-V
#   ./src/run_one.sh --isa armv7 c_sort     # ARM
#
# Toolchain: LLVM (clang, llvm-objcopy) + riscv64-elf-ld / arm-none-eabi-ld

set -ex

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"

if command -v clang >/dev/null 2>&1; then
    CLANG="clang"
elif [ -x "/opt/homebrew/opt/llvm/bin/clang" ]; then
    CLANG="/opt/homebrew/opt/llvm/bin/clang"
else
    echo "clang not found!" && exit 1
fi

if command -v ld.lld >/dev/null 2>&1; then
    LLD="ld.lld"
elif [ -x "/opt/homebrew/opt/llvm/bin/ld.lld" ]; then
    LLD="/opt/homebrew/opt/llvm/bin/ld.lld"
else
    echo "ld.lld not found!" && exit 1
fi

# Parse --isa flag
ISA="rv32i"
if [ "$1" = "--isa" ]; then
    ISA="$2"
    shift 2
fi

if [ -z "$1" ]; then
    echo "Usage: $0 [--isa rv32i|armv7] <test_name>"
    echo ""
    echo "Available tests for $ISA:"
    for f in "$SCRIPT_DIR/tests/$ISA"/*.expected; do
        basename "$f" .expected
    done
    exit 1
fi

TEST="$1"
TESTS_DIR="$SCRIPT_DIR/tests/$ISA"
ISA_YAML="$SCRIPT_DIR/isa/${ISA}.yaml"
MICROARCH="$SCRIPT_DIR/microarch/default.yaml"
TEMPLATE="$SCRIPT_DIR/sim_template.j2"
CPP="$SCRIPT_DIR/generated_sim_${ISA}.cpp"
SIM="$SCRIPT_DIR/sim_${ISA}"

OBJ="$TESTS_DIR/$TEST.o"
ELF="$TESTS_DIR/$TEST.elf"
BIN="$TESTS_DIR/$TEST.bin"

# 1. Build simulator (if needed)
if [ ! -f "$SIM" ] || [ "$ISA_YAML" -nt "$SIM" ] || [ "$TEMPLATE" -nt "$SIM" ] || [ "$MICROARCH" -nt "$SIM" ]; then
    echo "=== Building $ISA simulator ==="
    python3 "$SCRIPT_DIR/uadl_compiler.py" "$ISA_YAML" "$MICROARCH" "$TEMPLATE" "$CPP"
    g++ -O2 -std=c++17 "$CPP" -o "$SIM"
fi

# 2. Set ISA-specific toolchain flags
case "$ISA" in
    rv32i)
        CLANG_TARGET="--target=riscv32 -march=rv32i -mabi=ilp32"
        LD_CMD="$LLD -m elf32lriscv --image-base=0"
        CRT0="$SCRIPT_DIR/crt0_rv32i.s"
        ;;
    armv7)
        CLANG_TARGET="--target=armv7-none-eabi -mcpu=cortex-a9"
        LD_CMD="$LLD --image-base=0"
        CRT0="$SCRIPT_DIR/crt0_armv7.s"
        ;;
    *)
        echo "Unknown ISA: $ISA"
        exit 1
        ;;
esac

# 3. Compile / Assemble
if [ -f "$TESTS_DIR/$TEST.c" ]; then
    echo "=== Compiling: $TEST.c (clang $ISA) ==="
    $CLANG $CLANG_TARGET -c -O1 -fno-builtin -nostdlib -o "$TESTS_DIR/crt0.o" "$CRT0"
    $CLANG $CLANG_TARGET -c -O1 -fno-builtin -nostdlib -o "$OBJ" "$TESTS_DIR/$TEST.c"
    $LD_CMD -Ttext=0 -o "$ELF" "$TESTS_DIR/crt0.o" "$OBJ"
    rm -f "$TESTS_DIR/crt0.o"
elif [ -f "$TESTS_DIR/$TEST.s" ]; then
    echo "=== Assembling: $TEST.s (clang $ISA) ==="
    $CLANG $CLANG_TARGET -c -o "$OBJ" "$TESTS_DIR/$TEST.s"
    $LD_CMD -Ttext=0 -o "$ELF" "$OBJ"
else
    echo "Error: no test file '$TEST' in $TESTS_DIR/"
    exit 1
fi

python "$SCRIPT_DIR/elf2mem.py" "$ELF" "$BIN"
rm -f "$OBJ" "$ELF"

# 4. Run
echo "=== Running: $TEST ($ISA) ==="
echo ""
"$SIM" "$BIN"
