# RISC-V RV32I: Memory Test
# Tests: sw, lw with register+offset addressing

addi x1, zero, 42      # x1 = 42
addi x2, zero, 100     # x2 = base address (100)
sw   x1, 0(x2)         # DataMem[100] = 42
sw   x1, 4(x2)         # DataMem[104] = 42
addi x3, zero, 7
sw   x3, 8(x2)         # DataMem[108] = 7
lw   x4, 0(x2)         # x4 = DataMem[100] = 42
lw   x5, 8(x2)         # x5 = DataMem[108] = 7
add  x6, x4, x5        # x6 = 42 + 7 = 49
sw   x6, 12(x2)        # DataMem[112] = 49
ecall
