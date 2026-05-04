# UADL baremetal startup for RISC-V
# Provides _start entry point: initializes stack, calls main, halts.
# Also provides a software __mulsi3 because base RV32I has no MUL.
# Each call costs ~150 cycles -- this is intentional: a UADL-aware LLM
# should see the cost in telemetry and lower multiplies to shift-add.

.section .text
.globl _start
_start:
    li sp, 16384       # stack at top of data memory
    call main          # call user's main()
    ecall              # halt simulator

# Byte-wise memcpy: a0 = dst, a1 = src, a2 = n; returns dst in a0.
# clang -O0 emits memcpy for stack-allocated array initializers.
.globl memcpy
memcpy:
    li t0, 0
.Lmcpy_loop:
    bge t0, a2, .Lmcpy_done
    add t1, a1, t0
    lbu t2, 0(t1)
    add t1, a0, t0
    sb t2, 0(t1)
    addi t0, t0, 1
    j .Lmcpy_loop
.Lmcpy_done:
    ret

# Byte-wise memset: a0 = dst, a1 = value (low 8 bits), a2 = n; returns dst in a0.
.globl memset
memset:
    li t0, 0
.Lmset_loop:
    bge t0, a2, .Lmset_done
    add t1, a0, t0
    sb a1, 0(t1)
    addi t0, t0, 1
    j .Lmset_loop
.Lmset_done:
    ret

# 32-bit multiply: a0 = a0 * a1 (low 32 bits; signed == unsigned for low word)
.globl __mulsi3
__mulsi3:
    li a2, 0           # accumulator
.Lmul_loop:
    beqz a1, .Lmul_done
    andi a3, a1, 1
    beqz a3, .Lmul_skip
    add a2, a2, a0
.Lmul_skip:
    slli a0, a0, 1
    srli a1, a1, 1
    j .Lmul_loop
.Lmul_done:
    mv a0, a2
    ret
