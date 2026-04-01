@ UADL baremetal startup for ARMv7
@ Provides _start entry point: initializes stack, calls main, halts
@ Uses mov/orr for immediates to avoid literal pool (PC-relative loads)

.section .text
.globl _start
_start:
    mov sp, #16384       @ stack at top of data memory (0x4000)
    bl main             @ call user's main()
    svc #0              @ halt simulator
