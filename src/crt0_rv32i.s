# UADL baremetal startup for RISC-V
# Provides _start entry point: initializes stack, calls main, halts

.section .text
.globl _start
_start:
    li sp, 8192       # stack at top of data memory
    call main          # call user's main()
    ecall              # halt simulator
